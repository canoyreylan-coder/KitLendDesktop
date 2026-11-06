"""Listing reports, saved in the local SQLite file (Step 19). No Qt in this file.

A student can report a Catalog listing once. A report only records the problem: it never
hides, removes or changes the listing (a future review system decides what to do). Same
pattern as the other services: one small class, the same database file, user-safe errors.
"""
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.database import DatabaseError, connect, default_db_path

REASON_OTHER = "Other"
REPORT_REASONS = (
    "Inaccurate information",
    "Wrong availability or status",
    "Inappropriate content",
    "Suspected scam or misuse",
    "Item damaged or unsafe",
    "Duplicate listing",
    REASON_OTHER,
)
MAX_DESCRIPTION_LENGTH = 500


class ReportError(Exception):
    """A report problem; str(error) is safe to show to the student."""

    is_user_facing = True


@dataclass(frozen=True)
class ListingReport:
    report_id: str
    student_id: int
    listing_key: str
    listing_title: str
    reason: str
    description: str
    status: str
    created_at: str


def validate_report(reason, description) -> tuple:
    """Return the cleaned (reason, description) or raise ReportError."""
    reason = (reason or "").strip() if isinstance(reason, str) else ""
    description = (description or "").strip() if isinstance(description, str) else ""
    if reason not in REPORT_REASONS:
        raise ReportError("Please choose a reason for your report.")
    if reason == REASON_OTHER and not description:
        raise ReportError("Please describe the problem when the reason is Other.")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ReportError(
            f"Please keep the description under {MAX_DESCRIPTION_LENGTH} characters.")
    return reason, description


class ReportService:
    def __init__(self, db_path=None):
        self._db_path = db_path if db_path is not None else default_db_path()

    @staticmethod
    def _check_student(student_id):
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise ReportError("Please log in again to report a listing.")

    def has_reported(self, student_id: int, listing_key: str) -> bool:
        """True if THIS account already reported this listing (False if unreadable)."""
        self._check_student(student_id)
        try:
            conn = connect(self._db_path)
            try:
                return conn.execute(
                    "SELECT 1 FROM listing_reports WHERE student_id = ? AND listing_key = ?",
                    (student_id, listing_key)).fetchone() is not None
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            return False

    def submit_report(self, student_id: int, item, reason, description="") -> ListingReport:
        """Save one report linked to the account and the listing. Raises ReportError."""
        self._check_student(student_id)
        reason, description = validate_report(reason, description)
        try:
            conn = connect(self._db_path)
        except DatabaseError:
            raise ReportError(
                "Could not open the local database. Your report was not sent.") from None
        report = ListingReport(
            uuid.uuid4().hex, student_id, item.listing_key, item.title, reason, description,
            "Open", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO listing_reports (report_id, student_id, listing_key, "
                "listing_title, listing_owner, reason, description, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (report.report_id, student_id, item.listing_key, item.title,
                 item.owner_note, reason, description, report.status, report.created_at))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise ReportError("You have already reported this listing.") from None
        except sqlite3.Error:
            conn.rollback()
            raise ReportError("Could not save your report. Nothing was sent.") from None
        finally:
            conn.close()
        return report

    def list_reports(self, student_id: int) -> list:
        """This student's own reports, newest first."""
        self._check_student(student_id)
        try:
            conn = connect(self._db_path)
            try:
                rows = conn.execute(
                    "SELECT * FROM listing_reports WHERE student_id = ? "
                    "ORDER BY created_at DESC, report_id", (student_id,)).fetchall()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            raise ReportError("Could not load your reports.") from None
        return [ListingReport(r["report_id"], r["student_id"], r["listing_key"],
                              r["listing_title"], r["reason"], r["description"],
                              r["status"], r["created_at"]) for r in rows]
