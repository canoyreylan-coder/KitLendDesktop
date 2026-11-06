"""Small per-student preferences, saved in the local SQLite file (Step 17).

First use: which Browse Catalog layout (Grid or List) a student last chose. Same pattern as
SidebarLayoutService: one small service, one student at a time, the same database file as the
rest of the app. A student who never changed a preference has no row, so nothing about
existing accounts changes and the defaults apply. No Qt in this file.
"""
import sqlite3
from datetime import datetime, timezone

from app.database import DatabaseError, connect, default_db_path

from app.floating_layout import MAX_OUTER_MARGIN, MIN_OUTER_MARGIN

CATALOG_VIEW_KEY = "catalog_view"
OUTER_MARGIN_KEY = "outer_margin"
VIEW_GRID = "grid"
VIEW_LIST = "list"
VIEW_MODES = (VIEW_GRID, VIEW_LIST)
DEFAULT_CATALOG_VIEW = VIEW_GRID


class PreferenceError(Exception):
    """A preference problem; str(error) is safe to show to the student."""

    is_user_facing = True


class PreferenceService:
    def __init__(self, db_path=None):
        self._db_path = db_path if db_path is not None else default_db_path()

    @staticmethod
    def _check_student(student_id):
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise PreferenceError("Please log in again to change your preferences.")

    # ---------- generic ----------
    def get(self, student_id: int, key: str, default=None):
        """This student's saved value for `key`, or `default` (also if the file is unreadable)."""
        self._check_student(student_id)
        try:
            conn = connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT pref_value FROM student_preferences "
                    "WHERE student_id = ? AND pref_key = ?", (student_id, key)).fetchone()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            return default  # a preference must never stop the app from opening
        return default if row is None else row["pref_value"]

    def set(self, student_id: int, key: str, value: str) -> None:
        """Save one value for ONE student (inserts or replaces that one row)."""
        self._check_student(student_id)
        try:
            conn = connect(self._db_path)
        except DatabaseError:
            raise PreferenceError(
                "Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO student_preferences (student_id, pref_key, pref_value, updated_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (student_id, pref_key) DO UPDATE SET "
                "pref_value = excluded.pref_value, updated_at = excluded.updated_at",
                (student_id, key, str(value),
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise PreferenceError("Could not save your preference. Nothing was changed.") from None
        finally:
            conn.close()

    def delete(self, student_id: int, key: str) -> None:
        """Forget one saved value (the student goes back to the default for it)."""
        self._check_student(student_id)
        try:
            conn = connect(self._db_path)
        except DatabaseError:
            raise PreferenceError(
                "Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM student_preferences WHERE student_id = ? AND pref_key = ?",
                         (student_id, key))
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise PreferenceError("Could not save your preference. Nothing was changed.") from None
        finally:
            conn.close()

    # ---------- Floating container: Outer Margin ----------
    def get_outer_margin(self, student_id: int):
        """The saved Outer Margin (12-48), or None = automatic. Damaged values give None."""
        raw = self.get(student_id, OUTER_MARGIN_KEY, None)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if MIN_OUTER_MARGIN <= value <= MAX_OUTER_MARGIN else None

    def set_outer_margin(self, student_id: int, value: int) -> None:
        if (not isinstance(value, int) or isinstance(value, bool)
                or not MIN_OUTER_MARGIN <= value <= MAX_OUTER_MARGIN):
            raise PreferenceError(
                f"The outer margin must be between {MIN_OUTER_MARGIN} and {MAX_OUTER_MARGIN} px.")
        self.set(student_id, OUTER_MARGIN_KEY, value)

    def reset_outer_margin(self, student_id: int) -> None:
        """Back to the default (automatic) margin: the saved row is removed."""
        self.delete(student_id, OUTER_MARGIN_KEY)

    # ---------- Browse Catalog layout ----------
    def get_catalog_view(self, student_id: int) -> str:
        """'grid' or 'list'. New accounts, damaged values and read errors all give Grid."""
        value = self.get(student_id, CATALOG_VIEW_KEY, DEFAULT_CATALOG_VIEW)
        return value if value in VIEW_MODES else DEFAULT_CATALOG_VIEW

    def set_catalog_view(self, student_id: int, mode: str) -> None:
        if mode not in VIEW_MODES:
            raise PreferenceError("That catalog view is not available.")
        self.set(student_id, CATALOG_VIEW_KEY, mode)
