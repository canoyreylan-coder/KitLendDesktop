"""Student authentication service (no GUI code).

Everything the screens need is: AuthService.register(...),
AuthService.login(...), and (Step 12) AuthService.get_account(...) and
AuthService.change_password(...). A future central backend can replace this class
without touching the GUI. School-email ownership is NOT verified here;
email verification will be added later.
"""
import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from app.database import DatabaseError, connect, default_db_path

SCHOOL_DOMAIN = "@csucc.edu.ph"
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
PBKDF2_ITERATIONS = 310_000
SALT_BYTES = 16
MAX_STUDENT_ID_LENGTH = 40  # a sanity limit only; no ID format is assumed

# letters, digits, and . _ % + - in the local part (so "+" is allowed)
_LOCAL_PART = re.compile(r"^[A-Za-z0-9._%+\-]+$")


ID_TAKEN_MESSAGE = "This Student ID Number is already registered to another account."


class AuthError(Exception):
    """A user-facing authentication problem; str(error) is safe to show."""


@dataclass(frozen=True)
class Student:
    id: int
    full_name: str
    email: str
    student_id_number: str | None = None  # None = not added yet (older accounts)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str:
    """Return the normalized email or raise AuthError."""
    normalized = normalize_email(email)
    local = normalized[: -len(SCHOOL_DOMAIN)] if normalized.endswith(SCHOOL_DOMAIN) else ""
    if not local or not _LOCAL_PART.match(local):
        raise AuthError(f"Please use your official {SCHOOL_DOMAIN} email.")
    return normalized


def normalize_student_id(value: str) -> str:
    """Trim and collapse spaces. Nothing else: the school's ID format is never assumed."""
    return " ".join((value or "").split())


def validate_student_id(value: str) -> str:
    """Return the cleaned Student ID Number or raise AuthError.

    Any text is accepted (digits, letters, dashes, ...) as long as it is not empty, not absurdly
    long and has no control characters. Upper/lower case never makes two IDs different.
    """
    cleaned = normalize_student_id(value)
    if not cleaned:
        raise AuthError("Please enter your Student ID Number.")
    if len(cleaned) > MAX_STUDENT_ID_LENGTH:
        raise AuthError(
            f"Your Student ID Number is too long (at most {MAX_STUDENT_ID_LENGTH} characters).")
    if not cleaned.isprintable():
        raise AuthError("Your Student ID Number contains characters that cannot be used.")
    return cleaned


def validate_password(password: str) -> None:
    if not (MIN_PASSWORD_LENGTH <= len(password or "") <= MAX_PASSWORD_LENGTH):
        raise AuthError(
            f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters."
        )


def hash_password(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return digest.hex()


class AuthService:
    def __init__(self, db_path=None):
        self._db_path = db_path if db_path is not None else default_db_path()

    @property
    def db_path(self):
        """Where the local database lives (read-only; other local services share it)."""
        return self._db_path

    def _connect(self):
        return connect(self._db_path)

    def register(self, full_name: str, email: str, password: str,
                 confirm_password: str, student_id_number: str = "") -> Student:
        """Create a student account. Raises AuthError with a friendly message.

        The Student ID Number is required and must not belong to another account.
        """
        full_name = " ".join((full_name or "").split())
        if not full_name or not (email or "").strip() or not password or not confirm_password:
            raise AuthError("Please fill in all fields.")
        normalized = validate_email(email)
        student_id_number = validate_student_id(student_id_number)
        validate_password(password)
        if password != confirm_password:
            raise AuthError("Passwords do not match.")

        salt = secrets.token_bytes(SALT_BYTES)
        password_hash = hash_password(password, salt)
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            conn = self._connect()
            try:
                if conn.execute("SELECT 1 FROM students WHERE email = ?",
                                (normalized,)).fetchone():
                    raise AuthError("An account with this email already exists.")
                if self._id_taken(conn, student_id_number):
                    raise AuthError(ID_TAKEN_MESSAGE)
                cur = conn.execute(
                    "INSERT INTO students (full_name, email, password_hash, salt, "
                    "iterations, created_at, student_id_number) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (full_name, normalized, password_hash, salt.hex(),
                     PBKDF2_ITERATIONS, created, student_id_number),
                )
                conn.commit()
                return Student(cur.lastrowid, full_name, normalized, student_id_number)
            finally:
                conn.close()
        except sqlite3.IntegrityError as exc:
            if "student_id_number" in str(exc):
                raise AuthError(ID_TAKEN_MESSAGE)
            raise AuthError("An account with this email already exists.")
        except (sqlite3.Error, DatabaseError):
            raise AuthError("Could not save your account (database problem). Please try again.")

    def login(self, email: str, password: str) -> Student:
        """Return the Student only if credentials are correct, else raise AuthError."""
        generic = AuthError("Incorrect email or password.")
        normalized = normalize_email(email)
        if not normalized or not password:
            raise AuthError("Please enter your email and password.")
        try:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM students WHERE email = ?", (normalized,)
                ).fetchone()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            raise AuthError("Could not read the account database. Please try again.")

        if row is None:
            # Do equal work so timing doesn't reveal whether the email exists.
            hash_password(password, b"\x00" * SALT_BYTES)
            raise generic
        try:
            candidate = hash_password(password, bytes.fromhex(row["salt"]), row["iterations"])
        except (ValueError, TypeError):
            raise generic
        if not hmac.compare_digest(candidate, row["password_hash"]):
            raise generic
        return Student(row["id"], row["full_name"], row["email"], row["student_id_number"])


    # ---------- Step 12: Settings ----------
    def get_account(self, student_id: int) -> Student:
        """The signed-in student's own name and registered email (read-only data)."""
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise AuthError("Please log in again.")
        try:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT id, full_name, email, student_id_number FROM students WHERE id = ?",
                    (student_id,)
                ).fetchone()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            raise AuthError("Could not read your account. Please try again.") from None
        if row is None:
            raise AuthError("Your account was not found. Please log in again.")
        return Student(row["id"], row["full_name"], row["email"], row["student_id_number"])

    # ---------- Step 29D: Student ID Number ----------
    @staticmethod
    def _id_taken(conn, student_id_number: str, except_student: int | None = None) -> bool:
        row = conn.execute(
            "SELECT id FROM students WHERE student_id_number = ? COLLATE NOCASE",
            (student_id_number,)).fetchone()
        return row is not None and row["id"] != except_student

    def set_student_id(self, student_id: int, student_id_number: str) -> str:
        """Add the missing Student ID Number of an existing account. Returns the saved ID.

        Only an account that has NO ID yet can use this: a registered ID is never changed here
        (so it cannot be replaced by accident), and an ID that belongs to someone else is refused.
        """
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise AuthError("Please log in again.")
        cleaned = validate_student_id(student_id_number)
        try:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT student_id_number FROM students WHERE id = ?",
                                   (student_id,)).fetchone()
                if row is None:
                    conn.rollback()
                    raise AuthError("Your account was not found. Please log in again.")
                if row["student_id_number"]:
                    conn.rollback()
                    raise AuthError(
                        "Your Student ID Number is already registered and cannot be changed here.")
                if self._id_taken(conn, cleaned):
                    conn.rollback()
                    raise AuthError(ID_TAKEN_MESSAGE)
                conn.execute(
                    "UPDATE students SET student_id_number = ? "
                    "WHERE id = ? AND student_id_number IS NULL", (cleaned, student_id))
                conn.commit()
                return cleaned
            finally:
                conn.close()
        except sqlite3.IntegrityError:
            raise AuthError(ID_TAKEN_MESSAGE) from None
        except (sqlite3.Error, DatabaseError):
            raise AuthError("Could not save your Student ID Number. Nothing was changed.") from None

    def change_password(self, student_id: int, current_password: str, new_password: str,
                        confirm_password: str) -> None:
        """Change THIS student's password. Raises AuthError with a friendly message.

        Reuses the registration/login hashing (PBKDF2 with a NEW random salt). The
        current password is checked inside the same transaction that saves the new
        one, only the salted hash is stored, and no password is ever logged or put
        in an error message.
        """
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise AuthError("Please log in again.")
        if not current_password or not new_password or not confirm_password:
            raise AuthError("Please fill in all three password fields.")
        validate_password(new_password)
        if new_password != confirm_password:
            raise AuthError("The new password and its confirmation do not match.")
        if new_password == current_password:
            raise AuthError("Your new password must be different from your current password.")

        wrong_current = AuthError("Your current password is incorrect.")
        try:
            conn = self._connect()
        except DatabaseError:
            raise AuthError("Could not open the account database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT salt, iterations, password_hash FROM students WHERE id = ?",
                (student_id,)).fetchone()
            if row is None:
                conn.rollback()
                raise AuthError("Your account was not found. Please log in again.")
            try:
                candidate = hash_password(
                    current_password, bytes.fromhex(row["salt"]), row["iterations"])
            except (ValueError, TypeError):
                conn.rollback()
                raise wrong_current from None
            if not hmac.compare_digest(candidate, row["password_hash"]):
                conn.rollback()
                raise wrong_current
            salt = secrets.token_bytes(SALT_BYTES)
            conn.execute(
                "UPDATE students SET password_hash = ?, salt = ?, iterations = ? WHERE id = ?",
                (hash_password(new_password, salt), salt.hex(), PBKDF2_ITERATIONS, student_id))
            conn.commit()
        except AuthError:
            raise
        except sqlite3.Error:
            conn.rollback()
            raise AuthError(
                "Could not save your new password (database problem). Nothing was changed."
            ) from None
        finally:
            conn.close()
