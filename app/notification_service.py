"""Local notification storage (Step 11). No GUI code in this file.

Notifications are saved in the same local SQLite file as accounts and requests
(table `notifications`, created by migration 3 in app/database.py).

Rules this module enforces:
  * Every read and write is tied to ONE student id. A student can never read or
    change another student's notification: someone else's notification looks
    exactly like a missing one.
  * A notification is created ONLY by a real request event that succeeded
    (request submitted, request cancelled). `record_*` below are called by
    RequestService on the SAME open connection, inside the SAME transaction as
    the request change, so both are saved together or neither is.
  * Each real event has one stable `dedupe_key`, and (student_id, dedupe_key) is
    UNIQUE. Refreshing a page, restarting the app or retrying can never store the
    same event twice.
  * Nothing is generated from older requests, sample data or page refreshes.
  * Reading is separate from creating: the service only marks things read.

Step 12 preferences: each student can switch "request submitted" and "request cancelled"
notifications on or off (table `notification_preferences`, migration 4). The check lives
in `_insert`, the single place a notification is created, on the SAME connection and
transaction as the request change. A switched-off kind is simply not created; existing
notifications are never deleted or hidden, and the request itself is unaffected. No
saved choice means ON.

Future-friendly: `event_type` is the hook for notification preferences, and a later
email-reminder feature can add its own delivery table that points at `notifications.id`.
Nothing here sends email or runs in the background.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from app.database import DatabaseError, connect, default_db_path

EVENT_REQUEST_SUBMITTED = "request_submitted"
EVENT_REQUEST_CANCELLED = "request_cancelled"
SUPPORTED_EVENTS = (EVENT_REQUEST_SUBMITTED, EVENT_REQUEST_CANCELLED)


EVENT_LABELS = {
    EVENT_REQUEST_SUBMITTED: "Request submitted",
    EVENT_REQUEST_CANCELLED: "Request cancelled",
}


class NotificationError(Exception):
    """A notification problem; str(error) is safe to show to the student."""

    is_user_facing = True


@dataclass(frozen=True)
class Notification:
    id: int
    student_id: int
    event_type: str
    title: str
    message: str
    request_id: str | None
    created_at: datetime
    read_at: datetime | None

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    @property
    def is_unread(self) -> bool:
        return self.read_at is None


# ---------- small helpers ----------
def _to_text(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _from_text(text) -> datetime | None:
    if not text:
        return None
    return datetime.fromisoformat(text).astimezone()  # timezone-aware, local zone


def _default_clock() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def format_notification_time(moment: datetime | None) -> str:
    """e.g. 'Oct 23, 2026 · 3:45 PM' (no platform-specific strftime codes)."""
    if moment is None:
        return ""
    hour = moment.hour % 12 or 12
    suffix = "AM" if moment.hour < 12 else "PM"
    return f"{moment:%b} {moment.day}, {moment.year} · {hour}:{moment:%M} {suffix}"


def _row_to_notification(row: sqlite3.Row) -> Notification:
    return Notification(
        id=row["id"],
        student_id=row["student_id"],
        event_type=row["event_type"],
        title=row["title"],
        message=row["message"],
        request_id=row["request_id"],
        created_at=_from_text(row["created_at"]),
        read_at=_from_text(row["read_at"]),
    )


# ----------------------------------------------------------------------
# Creating (called by RequestService INSIDE its own transaction)
# ----------------------------------------------------------------------
def _is_enabled(conn: sqlite3.Connection, student_id: int, event_type: str) -> bool:
    """This student's choice for one kind of notification (no saved choice = ON)."""
    row = conn.execute(
        "SELECT enabled FROM notification_preferences WHERE student_id = ? AND event_type = ?",
        (student_id, event_type)).fetchone()
    return True if row is None else bool(row[0])


def _insert(conn: sqlite3.Connection, student_id: int, event_type: str, title: str,
            message: str, request_id: str, dedupe_key: str, at: datetime) -> bool:
    """Store one notification on the caller's connection. Never commits.

    INSERT OR IGNORE + the UNIQUE (student_id, dedupe_key) rule means the same real
    event can never be stored twice. Returns True if a new row was stored, and False
    when it was a duplicate OR this student switched that kind of notification off
    (Step 12). Only THIS student's own preference is consulted.
    """
    if not _is_enabled(conn, student_id, event_type):
        return False
    cursor = conn.execute(
        "INSERT OR IGNORE INTO notifications "
        "(student_id, event_type, title, message, request_id, dedupe_key, created_at, read_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        (student_id, event_type, title, message, request_id, dedupe_key, _to_text(at)),
    )
    return cursor.rowcount == 1


def record_request_submitted(conn: sqlite3.Connection, student_id: int, request_id: str,
                             item_title: str, at: datetime) -> bool:
    return _insert(
        conn, student_id, EVENT_REQUEST_SUBMITTED, "Request submitted",
        f"Your request {request_id} for “{item_title}” was submitted and is now Pending.",
        request_id, f"{EVENT_REQUEST_SUBMITTED}:{request_id}", at,
    )


def record_request_cancelled(conn: sqlite3.Connection, student_id: int, request_id: str,
                             item_title: str, at: datetime) -> bool:
    return _insert(
        conn, student_id, EVENT_REQUEST_CANCELLED, "Request cancelled",
        f"Your request {request_id} for “{item_title}” was cancelled.",
        request_id, f"{EVENT_REQUEST_CANCELLED}:{request_id}", at,
    )


# ----------------------------------------------------------------------
# Reading and marking as read (always for ONE student)
# ----------------------------------------------------------------------
class NotificationService:
    def __init__(self, db_path=None, clock=_default_clock):
        self._db_path = db_path if db_path is not None else default_db_path()
        self._clock = clock  # tests can pass a fixed clock

    def _connect(self):
        return connect(self._db_path)

    @staticmethod
    def _check_student(student_id):
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise NotificationError("Please log in again to see your notifications.")

    def list_notifications(self, student_id: int) -> list:
        """This student's notifications, newest first (and nobody else's)."""
        self._check_student(student_id)
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM notifications WHERE student_id = ? "
                    "ORDER BY created_at DESC, id DESC", (student_id,)).fetchall()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            raise NotificationError(
                "Could not load your notifications. Please try again.") from None
        loaded = []
        for row in rows:
            try:
                loaded.append(_row_to_notification(row))
            except (ValueError, KeyError, TypeError):
                continue  # one damaged record must not hide all the others
        return loaded

    # ---------- Step 12: notification preferences ----------
    def get_preferences(self, student_id: int) -> dict:
        """{event_type: True/False} for every supported kind (unchosen kinds are True)."""
        self._check_student(student_id)
        try:
            conn = self._connect()
            try:
                return {event: _is_enabled(conn, student_id, event)
                        for event in SUPPORTED_EVENTS}
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            raise NotificationError(
                "Could not load your notification settings. Please try again.") from None

    def set_preference(self, student_id: int, event_type: str, enabled: bool) -> None:
        """Save ONE choice for THIS student. Existing notifications are never touched."""
        self._check_student(student_id)
        if event_type not in SUPPORTED_EVENTS:
            raise NotificationError("That notification type is not available.")
        if not isinstance(enabled, bool):
            raise NotificationError("Please choose on or off.")
        now = self._clock()
        try:
            conn = self._connect()
        except DatabaseError:
            raise NotificationError(
                "Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO notification_preferences (student_id, event_type, enabled, "
                "updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (student_id, event_type) DO UPDATE SET "
                "enabled = excluded.enabled, updated_at = excluded.updated_at",
                (student_id, event_type, int(enabled), _to_text(now)))
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise NotificationError(
                "Could not save your notification settings. Nothing was changed.") from None
        finally:
            conn.close()

    def unread_count(self, student_id: int) -> int:
        self._check_student(student_id)
        try:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT COUNT(*) FROM notifications "
                    "WHERE student_id = ? AND read_at IS NULL", (student_id,)).fetchone()[0]
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            raise NotificationError(
                "Could not load your notifications. Please try again.") from None

    def mark_read(self, student_id: int, notification_id: int) -> bool:
        """Mark ONE of this student's notifications as read.

        Returns True if it changed. Already read -> False (nothing changes, the
        original read time is kept). Another student's id -> NotificationError, the
        same as a missing one.
        """
        self._check_student(student_id)
        if not isinstance(notification_id, int) or isinstance(notification_id, bool):
            raise NotificationError("That notification was not found in your account.")
        now = self._clock()
        try:
            conn = self._connect()
        except DatabaseError:
            raise NotificationError(
                "Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT read_at FROM notifications WHERE id = ? AND student_id = ?",
                (notification_id, student_id)).fetchone()
            if row is None:
                conn.rollback()
                raise NotificationError("That notification was not found in your account.")
            changed = conn.execute(
                "UPDATE notifications SET read_at = ? "
                "WHERE id = ? AND student_id = ? AND read_at IS NULL",
                (_to_text(now), notification_id, student_id)).rowcount
            conn.commit()
            return changed == 1
        except NotificationError:
            raise
        except sqlite3.Error:
            conn.rollback()
            raise NotificationError(
                "Could not update the notification. Nothing was changed.") from None
        finally:
            conn.close()

    def mark_all_read(self, student_id: int) -> int:
        """Mark every unread notification of THIS student as read. Returns how many."""
        self._check_student(student_id)
        now = self._clock()
        try:
            conn = self._connect()
        except DatabaseError:
            raise NotificationError(
                "Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                "UPDATE notifications SET read_at = ? "
                "WHERE student_id = ? AND read_at IS NULL",
                (_to_text(now), student_id)).rowcount
            conn.commit()
            return changed
        except sqlite3.Error:
            conn.rollback()
            raise NotificationError(
                "Could not update your notifications. Nothing was changed.") from None
        finally:
            conn.close()
