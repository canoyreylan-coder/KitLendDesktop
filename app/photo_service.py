"""Persistent local photo REFERENCES for listings (Step 21). No Qt in this file.

A listing can have up to 5 photos, one of them primary. The database stores only where each
picture file is (never the picture itself). This step has NO uploading: nothing creates
photo rows yet. `add_photo()` is the entry point the future Student Owner upload feature
will call after it has saved a file, so the storage rules already exist:
  * at most MAX_PHOTOS per listing, at most one primary (the first photo becomes primary),
  * the same file cannot be added twice to a listing,
  * a file that is missing or unreadable is simply skipped when photos are read - the
    listing keeps working and falls back to the next photo or the placeholder.
"""
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.database import DatabaseError, connect, default_db_path, get_app_data_dir

MAX_PHOTOS = 5
ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


class PhotoError(Exception):
    """A photo problem; str(error) is safe to show to the student."""

    is_user_facing = True


@dataclass(frozen=True)
class ListingPhoto:
    photo_id: int
    listing_key: str
    path: str          # absolute path of the file (already resolved)
    is_primary: bool
    position: int


def default_photos_dir() -> Path:
    """Folder for future uploaded pictures (next to the database; not created here)."""
    return get_app_data_dir() / "photos"


class PhotoService:
    def __init__(self, db_path=None, photos_dir=None):
        self._db_path = db_path if db_path is not None else default_db_path()
        self._photos_dir = Path(photos_dir) if photos_dir is not None else None

    # ---------- helpers ----------
    def _base_dir(self) -> Path:
        return self._photos_dir if self._photos_dir is not None else default_photos_dir()

    @property
    def photos_dir(self) -> Path:
        """The folder the picture files live in (the Step 31C owner upload writes there)."""
        return self._base_dir()

    def resolve(self, stored_path: str) -> str:
        """Stored path -> absolute path (relative paths live in the photos folder)."""
        path = Path(stored_path)
        return str(path if path.is_absolute() else self._base_dir() / path)

    @staticmethod
    def is_usable(path: str) -> bool:
        """True if the file exists and looks like a picture we support."""
        try:
            return os.path.isfile(path) and Path(path).suffix.lower() in ALLOWED_EXTENSIONS
        except (OSError, ValueError):
            return False

    def _rows_to_photos(self, rows, usable_only: bool) -> list:
        photos = []
        for row in rows:
            path = self.resolve(row["file_path"])
            if usable_only and not self.is_usable(path):
                continue  # missing/unreadable file: skip it, never crash
            photos.append(ListingPhoto(row["photo_id"], row["listing_key"], path,
                                       bool(row["is_primary"]), row["position"]))
        return photos

    # ---------- reading (never raises) ----------
    def photos_for(self, listing_key: str, usable_only: bool = True) -> list:
        """The listing's photos, primary first then by position (max 5)."""
        try:
            conn = connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT * FROM listing_photos WHERE listing_key = ? "
                    "ORDER BY is_primary DESC, position, photo_id", (listing_key,)).fetchall()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            return []
        return self._rows_to_photos(rows, usable_only)[:MAX_PHOTOS]

    def primary_photo_paths(self) -> dict:
        """{listing_key: path of the first usable photo, primary first} for the Catalog."""
        try:
            conn = connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT * FROM listing_photos ORDER BY listing_key, is_primary DESC, "
                    "position, photo_id").fetchall()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            return {}
        result = {}
        for photo in self._rows_to_photos(rows, usable_only=True):
            result.setdefault(photo.listing_key, photo.path)
        return result

    # ---------- writing (for the future upload feature; the app does not call these yet) ----------
    def add_photo(self, listing_key: str, file_path, make_primary: bool = False) -> ListingPhoto:
        path = str(file_path or "").strip()
        if not listing_key or not path:
            raise PhotoError("A photo needs a listing and a file.")
        if Path(path).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise PhotoError("That file type is not supported. Use PNG, JPG, WEBP, BMP or GIF.")
        try:
            conn = connect(self._db_path)
        except DatabaseError:
            raise PhotoError("Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT position, file_path FROM listing_photos WHERE listing_key = ?",
                (listing_key,)).fetchall()
            if len(rows) >= MAX_PHOTOS:
                raise PhotoError(f"A listing can have at most {MAX_PHOTOS} photos.")
            if any(r["file_path"] == path for r in rows):
                raise PhotoError("That photo is already on this listing.")
            position = next(i for i in range(MAX_PHOTOS) if i not in {r["position"] for r in rows})
            primary = make_primary or not rows  # the first photo is always primary
            if primary:
                conn.execute("UPDATE listing_photos SET is_primary = 0 WHERE listing_key = ?",
                             (listing_key,))
            cursor = conn.execute(
                "INSERT INTO listing_photos (listing_key, file_path, position, is_primary, "
                "added_at) VALUES (?, ?, ?, ?, ?)",
                (listing_key, path, position, int(primary),
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            conn.commit()
        except PhotoError:
            conn.rollback()
            raise
        except sqlite3.Error:
            conn.rollback()
            raise PhotoError("Could not save the photo. Nothing was changed.") from None
        finally:
            conn.close()
        return ListingPhoto(cursor.lastrowid, listing_key, self.resolve(path), primary, position)

    def set_primary(self, listing_key: str, photo_id: int) -> None:
        try:
            conn = connect(self._db_path)
        except DatabaseError:
            raise PhotoError("Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            found = conn.execute(
                "SELECT 1 FROM listing_photos WHERE listing_key = ? AND photo_id = ?",
                (listing_key, photo_id)).fetchone()
            if found is None:
                raise PhotoError("That photo is not on this listing.")
            conn.execute("UPDATE listing_photos SET is_primary = 0 WHERE listing_key = ?",
                         (listing_key,))
            conn.execute("UPDATE listing_photos SET is_primary = 1 WHERE photo_id = ?",
                         (photo_id,))
            conn.commit()
        except PhotoError:
            conn.rollback()
            raise
        except sqlite3.Error:
            conn.rollback()
            raise PhotoError("Could not change the primary photo.") from None
        finally:
            conn.close()
