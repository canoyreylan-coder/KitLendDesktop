"""Saves each student's My List (bookmarked items) in the local SQLite file.

Same pattern as PreferenceService: one small service, one student at a time, the same database
file as the rest of the app. Items are stored by their `listing_key`. Primary key
(student_id, listing_key) makes duplicates impossible. No Qt in this file.
"""
import sqlite3
from datetime import datetime, timezone

from app.database import DatabaseError, connect, default_db_path


class SavedItemsError(Exception):
    """A My List saving problem; str(error) is safe to show to the student."""

    is_user_facing = True


class SavedItemsService:
    def __init__(self, db_path=None):
        self._db_path = db_path if db_path is not None else default_db_path()

    @staticmethod
    def _check(student_id, listing_key):
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise SavedItemsError("Please log in again to change your My List.")
        if not isinstance(listing_key, str) or not listing_key:
            raise SavedItemsError("That item cannot be saved.")

    def list_keys(self, student_id: int) -> list:
        """This student's saved listing keys, oldest first. Unreadable file -> empty list."""
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            return []
        try:
            conn = connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT listing_key FROM saved_items WHERE student_id = ? "
                    "ORDER BY saved_at, rowid", (student_id,)).fetchall()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            return []  # a damaged list must never stop the app from opening
        return [row["listing_key"] for row in rows]

    def add(self, student_id: int, listing_key: str) -> bool:
        """Save one item for ONE student. True if newly saved, False if it was already saved."""
        self._check(student_id, listing_key)
        conn = self._open("Could not open the local database. Your My List was not changed.")
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "INSERT OR IGNORE INTO saved_items (student_id, listing_key, saved_at) "
                "VALUES (?, ?, ?)",
                (student_id, listing_key, datetime.now(timezone.utc).isoformat(timespec="seconds")))
            conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error:
            conn.rollback()
            raise SavedItemsError("Could not save this item to your My List.") from None
        finally:
            conn.close()

    def remove(self, student_id: int, listing_key: str) -> bool:
        """Remove one item for ONE student. True if it was saved."""
        self._check(student_id, listing_key)
        conn = self._open("Could not open the local database. Your My List was not changed.")
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "DELETE FROM saved_items WHERE student_id = ? AND listing_key = ?",
                (student_id, listing_key))
            conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error:
            conn.rollback()
            raise SavedItemsError("Could not remove this item from your My List.") from None
        finally:
            conn.close()

    def _open(self, message: str):
        try:
            return connect(self._db_path)
        except DatabaseError:
            raise SavedItemsError(message) from None
