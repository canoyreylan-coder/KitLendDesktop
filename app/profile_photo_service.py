"""Saves each student's profile photo as a file in the application-data folder (Step 28).

* Stored in a `profile_photos` folder next to the local database (the real app-data folder
  for a normal run), never in a temporary folder and never inside the project.
* The student's own file is only READ. What is stored is a fresh square PNG made from it
  (centre-cropped, never stretched, at most 512 x 512), so metadata is dropped and a huge
  original is not kept. The student's file name is never used.
* One photo per account. The file name comes from a hash of the account (id + email), so
  another account can never pick it up, even if a database is deleted and ids are reused.
* A new photo gets a NEW file name, then the older file is deleted. The sidebar never sees a
  half-written file and Qt's picture cache can never show the old picture.
* Reading never raises: a missing or damaged file simply means "no photo" (initials).

The image decoding is the only Qt part and is imported lazily, so the file handling can be
tested without PySide6 by passing `processor=` (a function (source, destination) -> None).
"""
import hashlib
import os
import time
from pathlib import Path

from app.database import get_app_data_dir

ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
ALLOWED_FORMATS = (b"jpeg", b"png", b"webp")  # what the file REALLY is, not just its name
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
STORED_SIZE = 512
UNSUPPORTED_TEXT = "Please choose a JPG, PNG or WEBP picture."


class ProfilePhotoError(Exception):
    """A photo problem; str(error) is safe to show to the student."""

    is_user_facing = True


def default_profile_photos_dir() -> Path:
    return get_app_data_dir() / "profile_photos"


def _decode_to_square_png(source: str, destination: str) -> None:
    """Read `source`, centre-crop it to a square, scale it down and save a PNG."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QImageReader

    reader = QImageReader(source)
    reader.setAutoTransform(True)  # respect the camera's rotation
    if bytes(reader.format()).lower() not in ALLOWED_FORMATS:
        raise ProfilePhotoError(UNSUPPORTED_TEXT)
    size = reader.size()
    if size.isValid() and size.width() * size.height() > MAX_PIXELS:
        raise ProfilePhotoError("That picture is too large. Please choose a smaller one.")
    image = reader.read()
    if image.isNull() or image.width() < 1 or image.height() < 1:
        raise ProfilePhotoError("That picture could not be read. Please choose another one.")
    image = image.convertToFormat(QImage.Format_ARGB32)
    side = min(image.width(), image.height())
    square = image.copy((image.width() - side) // 2, (image.height() - side) // 2, side, side)
    target = min(side, STORED_SIZE)  # never blow a small picture up
    if side != target:
        square = square.scaled(target, target, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    if not square.save(destination, "PNG"):
        raise ProfilePhotoError("Could not save the picture. Nothing was changed.")


class ProfilePhotoService:
    def __init__(self, photos_dir=None, processor=None):
        self._dir = Path(photos_dir) if photos_dir is not None else None
        self._processor = processor or _decode_to_square_png

    # ---------- helpers ----------
    def directory(self) -> Path:
        return self._dir if self._dir is not None else default_profile_photos_dir()

    @staticmethod
    def _check_student(student_id, email):
        if not isinstance(student_id, int) or isinstance(student_id, bool) or not email:
            raise ProfilePhotoError("Please log in again to change your photo.")

    @staticmethod
    def _prefix(student_id: int, email: str) -> str:
        digest = hashlib.sha256(f"{student_id}:{email.strip().lower()}".encode("utf-8"))
        return f"avatar-{digest.hexdigest()[:16]}-"

    def _files(self, student_id, email) -> list:
        """This account's stored photo files, oldest first (normally zero or one)."""
        prefix = self._prefix(student_id, email)
        try:
            found = [p for p in self.directory().iterdir()
                     if p.name.startswith(prefix) and p.suffix == ".png" and p.is_file()]
        except OSError:
            return []
        return sorted(found, key=lambda p: p.name)

    # ---------- reading (never raises) ----------
    def photo_path(self, student_id, email):
        """Absolute path of this account's photo, or None (show the initials)."""
        try:
            self._check_student(student_id, email)
            files = self._files(student_id, email)
        except ProfilePhotoError:
            return None
        for path in reversed(files):
            try:
                if path.stat().st_size > 0:
                    return str(path)
            except OSError:
                continue
        return None

    # ---------- writing ----------
    def save_photo(self, student_id, email, source_path) -> str:
        """Validate, crop and store the picture for ONE account; returns the stored path."""
        self._check_student(student_id, email)
        source = str(source_path or "").strip()
        if not source or Path(source).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ProfilePhotoError(UNSUPPORTED_TEXT)
        try:
            if not os.path.isfile(source):
                raise ProfilePhotoError("That file could not be found.")
            if os.path.getsize(source) > MAX_FILE_BYTES:
                raise ProfilePhotoError("That picture is larger than 10 MB. Please choose a smaller one.")
        except OSError:
            raise ProfilePhotoError("That file could not be opened.") from None

        prefix = self._prefix(student_id, email)
        final = self.directory() / f"{prefix}{time.time_ns():x}.png"
        temporary = final.with_suffix(".tmp")
        try:
            self.directory().mkdir(parents=True, exist_ok=True)
            old_files = self._files(student_id, email)
            self._processor(source, str(temporary))
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise ProfilePhotoError("Could not save the picture. Nothing was changed.")
            os.replace(temporary, final)  # all-or-nothing
        except ProfilePhotoError:
            self._discard(temporary)
            raise
        except OSError:
            self._discard(temporary)
            raise ProfilePhotoError(
                "Could not save the picture. Nothing was changed.") from None
        for old in old_files:  # only after the new one is safely in place
            self._discard(old)
        return str(final)

    def remove_photo(self, student_id, email) -> bool:
        """Delete this account's photo. True if there was one."""
        self._check_student(student_id, email)
        files = self._files(student_id, email)
        for path in files:
            self._discard(path)
        return bool(files)

    @staticmethod
    def _discard(path):
        try:
            Path(path).unlink()
        except OSError:
            pass
