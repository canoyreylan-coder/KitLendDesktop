"""Saves each student's sidebar layout in the local SQLite file (Step 14F).

Same pattern as NotificationService: one small service, one student at a time, user-facing
error messages, and the same database file as the rest of the app. A student who never
customised the sidebar has no row, so existing accounts are untouched.
"""
import json
import sqlite3
from datetime import datetime, timezone

from app.database import DatabaseError, connect, default_db_path
from app.sidebar_layout import SidebarLayout


class SidebarLayoutError(Exception):
    """A sidebar layout problem; str(error) is safe to show to the student."""

    is_user_facing = True


class SidebarLayoutService:
    def __init__(self, db_path=None):
        self._db_path = db_path if db_path is not None else default_db_path()

    @staticmethod
    def _check_student(student_id):
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise SidebarLayoutError("Please log in again to change your sidebar.")

    def get_layout(self, student_id: int) -> SidebarLayout:
        """This student's saved layout, or the default look if none (or a damaged one)."""
        self._check_student(student_id)
        try:
            conn = connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT layout_json FROM sidebar_layouts WHERE student_id = ?",
                    (student_id,)).fetchone()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            raise SidebarLayoutError(
                "Could not load your sidebar layout. The default layout is shown.") from None
        if row is None:
            return SidebarLayout()
        try:
            return SidebarLayout.from_dict(json.loads(row["layout_json"]))
        except (ValueError, TypeError):
            return SidebarLayout()  # damaged text: fall back to the default look

    def save_layout(self, student_id: int, layout: SidebarLayout) -> None:
        """Save ONE student's layout. A default layout simply removes the row."""
        self._check_student(student_id)
        if not isinstance(layout, SidebarLayout):
            raise SidebarLayoutError("That sidebar layout cannot be saved.")
        try:
            conn = connect(self._db_path)
        except DatabaseError:
            raise SidebarLayoutError(
                "Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            if layout.is_default():
                conn.execute("DELETE FROM sidebar_layouts WHERE student_id = ?", (student_id,))
            else:
                conn.execute(
                    "INSERT INTO sidebar_layouts (student_id, layout_json, updated_at) "
                    "VALUES (?, ?, ?) ON CONFLICT (student_id) DO UPDATE SET "
                    "layout_json = excluded.layout_json, updated_at = excluded.updated_at",
                    (student_id, json.dumps(layout.to_dict(), sort_keys=True),
                     datetime.now(timezone.utc).isoformat(timespec="seconds")))
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise SidebarLayoutError(
                "Could not save your sidebar layout. Nothing was changed.") from None
        finally:
            conn.close()
