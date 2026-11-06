"""Photos of an owner's listings (Step 31C): upload, remove and choose the primary photo.

Each listing can have 1-5 photos (MAX_PHOTOS). The picture files live in the application's
photos folder, one sub-folder per listing; the existing `listing_photos` table keeps only
where each file is, with the listing's ID as its `listing_key`. That is the same table and
the same key the Catalog gallery (PhotoService.photos_for) already reads, so these photos
show up in the existing gallery without any extra wiring once a listing is published.

Rules:
  * Only the approved owner of a listing can add, remove or re-order its photos (checked
    through OwnerListingService on EVERY call).
  * The picked file is never kept as it is: it is read, rotated as its camera says, shrunk
    to at most MAX_SIDE pixels (never stretched, never cropped) and saved as a new file in
    the photos folder, so the original can be moved or deleted afterwards.
  * The first photo of a listing is primary; removing the primary promotes the next one.
  * A listing may have 0 photos while it is a draft. Publishing requires at least
    MIN_PHOTOS_TO_PUBLISH usable photo.
"""
import os
import secrets
import sqlite3
from pathlib import Path

from app.database import DatabaseError, connect
from app.owner_listing_service import OwnerListingError
from app.photo_service import MAX_PHOTOS, PhotoError, PhotoService

ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
FORMATS_TEXT = "JPG, PNG or WEBP"
MIN_PHOTOS_TO_PUBLISH = 1
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_SIDE = 1600
MIN_SIDE = 64
MAX_INPUT_SIDE = 12000


def process_image(source: str, destination_base: str) -> str:
    """Read `source`, shrink it, write it beside `destination_base` and return the new path.

    `destination_base` is a path WITHOUT an extension; the extension chosen (.jpg, or .png
    when the picture has transparency) is returned in the result. Raises PhotoError.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImageReader

    reader = QImageReader(source)
    reader.setAutoTransform(True)   # honour the camera's rotation
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > MAX_INPUT_SIDE:
        raise PhotoError("That photo has too many pixels. Choose a smaller one.")
    image = reader.read()
    if image.isNull():
        raise PhotoError(f"That file is not a readable picture. Use {FORMATS_TEXT}.")
    if min(image.width(), image.height()) < MIN_SIDE:
        raise PhotoError("That photo is too small. Choose a larger one.")
    if max(image.width(), image.height()) > MAX_SIDE:
        image = image.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    has_alpha = image.hasAlphaChannel()
    path = destination_base + (".png" if has_alpha else ".jpg")
    if not image.save(path, "PNG" if has_alpha else "JPG", -1 if has_alpha else 90):
        raise OSError("could not write the image")
    return path


class OwnerListingPhotoService:
    def __init__(self, db_path, listing_service, photos_dir=None, image_processor=None):
        self._db_path = db_path
        self._listings = listing_service
        self._dir = Path(photos_dir) if photos_dir is not None else Path(db_path).parent / "photos"
        self._photos = PhotoService(db_path, self._dir)
        self._process = image_processor or process_image

    @property
    def photos_dir(self) -> Path:
        return self._dir

    # ---------- access ----------
    def _own(self, student_id, listing_id):
        try:
            return self._listings.get(student_id, listing_id)
        except OwnerListingError as exc:
            raise PhotoError(str(exc)) from None

    # ---------- reading ----------
    def photos(self, student_id, listing_id) -> list:
        """The listing's photos that can really be shown, primary first (at most 5)."""
        self._own(student_id, listing_id)
        return self._photos.photos_for(listing_id)

    def has_photo(self, student_id, listing_id) -> bool:
        return len(self.photos(student_id, listing_id)) >= MIN_PHOTOS_TO_PUBLISH

    def counts(self, student_id) -> dict:
        """{listing_id: number of usable photos} for all of THIS owner's listings."""
        try:
            listings = self._listings.list_drafts(student_id)
        except OwnerListingError as exc:
            raise PhotoError(str(exc)) from None
        paths = self._photos
        return {listing.listing_id: len(paths.photos_for(listing.listing_id))
                for listing in listings}

    def primary_paths(self, student_id) -> dict:
        """{listing_id: path of the primary photo} for THIS owner's listings (My Listings)."""
        try:
            listings = self._listings.list_drafts(student_id)
        except OwnerListingError as exc:
            raise PhotoError(str(exc)) from None
        found = self._photos.primary_photo_paths()
        return {l.listing_id: found[l.listing_id] for l in listings if l.listing_id in found}

    # ---------- writing ----------
    def add_photo(self, student_id, listing_id, source):
        """Add one picture to the listing. Returns the new ListingPhoto."""
        self._own(student_id, listing_id)
        source = str(source or "").strip()
        if not source:
            raise PhotoError("Choose a photo first.")
        if Path(source).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise PhotoError(f"That file type is not supported. Use {FORMATS_TEXT}.")
        try:
            size = os.path.getsize(source)
        except OSError:
            raise PhotoError("That file could not be opened.") from None
        if size == 0:
            raise PhotoError("That file is empty.")
        if size > MAX_FILE_BYTES:
            raise PhotoError(
                f"That photo is too large. Choose one under {MAX_FILE_BYTES // (1024 * 1024)} MB.")
        if len(self._photos.photos_for(listing_id, usable_only=False)) >= MAX_PHOTOS:
            raise PhotoError(f"A listing can have at most {MAX_PHOTOS} photos.")

        folder = self._dir / listing_id
        base = str(folder / ("p_" + secrets.token_hex(6)))
        try:
            folder.mkdir(parents=True, exist_ok=True)
            written = Path(self._process(source, base))
        except PhotoError:
            raise
        except OSError:
            raise PhotoError("Could not save the photo on this computer. Nothing was changed.") from None
        relative = f"{listing_id}/{written.name}"
        try:
            return self._photos.add_photo(listing_id, relative)
        except PhotoError:
            self._delete_file(written)
            raise
        except Exception:
            self._delete_file(written)
            raise PhotoError("Could not save the photo. Nothing was changed.") from None

    def set_primary(self, student_id, listing_id, photo_id):
        self._own(student_id, listing_id)
        self._photos.set_primary(listing_id, photo_id)

    def remove_photo(self, student_id, listing_id, photo_id):
        """Delete one photo (its row and its file). If it was primary, the next one is."""
        self._own(student_id, listing_id)
        try:
            conn = connect(self._db_path)
        except DatabaseError:
            raise PhotoError("Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT file_path, is_primary FROM listing_photos "
                "WHERE listing_key = ? AND photo_id = ?", (listing_id, photo_id)).fetchone()
            if row is None:
                conn.rollback()
                raise PhotoError("That photo is not on this listing.")
            conn.execute("DELETE FROM listing_photos WHERE photo_id = ?", (photo_id,))
            if row["is_primary"]:
                nxt = conn.execute(
                    "SELECT photo_id FROM listing_photos WHERE listing_key = ? "
                    "ORDER BY position, photo_id LIMIT 1", (listing_id,)).fetchone()
                if nxt is not None:
                    conn.execute("UPDATE listing_photos SET is_primary = 1 WHERE photo_id = ?",
                                 (nxt["photo_id"],))
            conn.commit()
        except PhotoError:
            raise
        except sqlite3.Error:
            conn.rollback()
            raise PhotoError("Could not remove the photo. Nothing was changed.") from None
        finally:
            conn.close()
        self._delete_file(Path(self._photos.resolve(row["file_path"])))

    def _delete_file(self, path: Path):
        """Delete a picture file, but only if it is inside the photos folder."""
        try:
            resolved = path.resolve()
            if self._dir.resolve() in resolved.parents and resolved.is_file():
                resolved.unlink()
        except OSError:
            pass   # a leftover file is harmless; the database is already right
