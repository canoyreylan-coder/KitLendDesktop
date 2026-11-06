"""Student Owner applications (Step 13). No GUI code in this file.

Applications are saved in the same local SQLite file as accounts and requests
(table `student_owner_applications`, created by migration 5 in app/database.py).

WHAT THIS MODULE DOES
  * Lets a signed-in student SUBMIT an application and READ their own applications.
  * Every read and write is tied to ONE student id; nobody can see another student's.
  * A new application always starts as Pending and gets its own unique application ID.
  * Rejected applicants may apply again. Old applications (and rejection reasons) are
    kept; nothing is ever updated or deleted here.
  * Duplicates are refused while one is Pending, and an Approved student cannot apply
    again. The database enforces this too (partial unique index).

WHAT THIS MODULE DELIBERATELY DOES NOT DO
  * There is NO method that approves, rejects or edits an application. Reviewing will
    be done by the future authorized review system, not by this student app.
  * Submitting grants nothing: borrowing is untouched and WorkspaceService still
    returns only the Student workspace, whatever the status is.
  * Local storage can be edited by whoever owns the computer, so an "Approved" row in
    this file is information only, never proof of permission. The real decision and
    enforcement will live on the central backend.
"""
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from app.database import DatabaseError, connect, default_db_path

STATUS_PENDING = "Pending"
STATUS_APPROVED = "Approved"
STATUS_REJECTED = "Rejected"
STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)

MIN_REASON_LENGTH = 20
MAX_REASON_LENGTH = 1000
MIN_ITEMS_LENGTH = 5
MAX_ITEMS_LENGTH = 1000

RULES_VERSION = "1"
# Shown next to the agreement box. DRAFT wording: please review before real use.
STUDENT_OWNER_RULES = (
    "I will only lend items that belong to me and that I am allowed to lend.",
    "I will describe each item honestly, including its condition.",
    "I will not lend dangerous, illegal or school-prohibited items.",
    "I will follow KitLend's borrowing rules and respond to requests on time.",
    "I understand that my application is reviewed, and that I may be rejected.",
)


class StudentOwnerError(Exception):
    """A user-facing problem; str(error) is safe to show to the student."""

    is_user_facing = True


@dataclass(frozen=True)
class OwnerApplication:
    application_id: str
    student_id: int
    reason: str
    items_to_lend: str
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None
    review_note: str

    @property
    def is_pending(self) -> bool:
        return self.status == STATUS_PENDING

    @property
    def is_approved(self) -> bool:
        return self.status == STATUS_APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.status == STATUS_REJECTED


def _clock() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def _from_text(text) -> datetime | None:
    return datetime.fromisoformat(text).astimezone() if text else None


def _row_to_application(row: sqlite3.Row) -> OwnerApplication:
    return OwnerApplication(
        application_id=row["application_id"],
        student_id=row["student_id"],
        reason=row["reason"],
        items_to_lend=row["items_to_lend"],
        status=row["status"],
        submitted_at=_from_text(row["submitted_at"]),
        reviewed_at=_from_text(row["reviewed_at"]),
        review_note=row["review_note"] or "",
    )


def _check_student_id(student_id):
    if not isinstance(student_id, int) or isinstance(student_id, bool):
        raise StudentOwnerError("Please log in again to use this page.")


def _clean(text) -> str:
    return "\n".join(line.rstrip() for line in str(text or "").strip().splitlines())


class StudentOwnerService:
    def __init__(self, db_path=None, clock=_clock):
        self._db_path = db_path if db_path is not None else default_db_path()
        self._clock = clock

    def _connect(self):
        return connect(self._db_path)

    # ---------- reading (always limited to the given student) ----------
    def list_applications(self, student_id: int) -> list:
        """All of this student's applications, newest first."""
        _check_student_id(student_id)
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT * FROM student_owner_applications WHERE student_id = ? "
                "ORDER BY submitted_at DESC, rowid DESC", (student_id,)).fetchall()
            return [_row_to_application(r) for r in rows]
        except sqlite3.Error as exc:
            raise StudentOwnerError("Could not load your applications.") from exc
        finally:
            conn.close()

    def current_application(self, student_id: int):
        """The newest application, or None if the student never applied."""
        applications = self.list_applications(student_id)
        return applications[0] if applications else None

    def apply_block_reason(self, student_id: int) -> str | None:
        """None when the student may apply now, otherwise a friendly reason why not."""
        return self._block_reason(self.list_applications(student_id))

    def can_apply(self, student_id: int) -> bool:
        return self.apply_block_reason(student_id) is None

    @staticmethod
    def _block_reason(applications) -> str | None:
        for application in applications:
            if application.is_pending:
                return ("You already have an application waiting for review. "
                        "You can apply again only if it is rejected.")
            if application.is_approved:
                return "Your application was approved, so you cannot apply again."
        return None

    # ---------- writing ----------
    def submit_application(self, student_id: int, reason: str, items_to_lend: str,
                           agreed_to_rules) -> OwnerApplication:
        """Save a NEW application for this student with status Pending.

        Raises StudentOwnerError (safe to show) when the form is incomplete, the rules
        are not agreed to, or the student already has a Pending/Approved application.
        Nothing is saved on any error.
        """
        _check_student_id(student_id)
        reason = _clean(reason)
        items = _clean(items_to_lend)
        if not reason:
            raise StudentOwnerError("Please tell us why you want to become a Student Owner.")
        if len(reason) < MIN_REASON_LENGTH:
            raise StudentOwnerError(
                f"Your reason is too short. Please write at least {MIN_REASON_LENGTH} characters.")
        if len(reason) > MAX_REASON_LENGTH:
            raise StudentOwnerError(
                f"Your reason is too long. Please keep it under {MAX_REASON_LENGTH} characters.")
        if not items:
            raise StudentOwnerError("Please list the items you intend to lend.")
        if len(items) < MIN_ITEMS_LENGTH:
            raise StudentOwnerError("Please describe the items you intend to lend a little more.")
        if len(items) > MAX_ITEMS_LENGTH:
            raise StudentOwnerError(
                f"Your item list is too long. Please keep it under {MAX_ITEMS_LENGTH} characters.")
        if agreed_to_rules is not True:
            raise StudentOwnerError("You must agree to the Student Owner lending rules to apply.")

        conn = self._open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone() is None:
                conn.rollback()
                raise StudentOwnerError("Please log in again to use this page.")
            rows = conn.execute(
                "SELECT * FROM student_owner_applications WHERE student_id = ?",
                (student_id,)).fetchall()
            blocked = self._block_reason([_row_to_application(r) for r in rows])
            if blocked:
                conn.rollback()
                raise StudentOwnerError(blocked)
            now = self._clock().isoformat(timespec="seconds")
            for _ in range(5):  # a clash on a random ID is astronomically unlikely
                application_id = "SO-" + secrets.token_hex(4).upper()
                try:
                    conn.execute(
                        "INSERT INTO student_owner_applications (application_id, student_id, "
                        "reason, items_to_lend, rules_agreed, rules_version, status, "
                        "submitted_at) VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
                        (application_id, student_id, reason, items, RULES_VERSION,
                         STATUS_PENDING, now))
                    break
                except sqlite3.IntegrityError as exc:
                    if "application_id" in str(exc):
                        continue
                    raise
            else:
                raise sqlite3.OperationalError("could not create a unique application ID")
            conn.commit()
            row = conn.execute("SELECT * FROM student_owner_applications "
                               "WHERE application_id = ?", (application_id,)).fetchone()
            return _row_to_application(row)
        except StudentOwnerError:
            raise
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise StudentOwnerError(
                "You already have an application that is Pending or Approved.") from exc
        except sqlite3.Error as exc:
            conn.rollback()
            raise StudentOwnerError(
                "Something went wrong, so your application was not saved.") from exc
        finally:
            conn.close()

    def _open(self):
        try:
            conn = self._connect()
        except DatabaseError as exc:
            raise StudentOwnerError("Could not open the local database.") from exc
        conn.isolation_level = None  # we control BEGIN/COMMIT ourselves
        return conn
