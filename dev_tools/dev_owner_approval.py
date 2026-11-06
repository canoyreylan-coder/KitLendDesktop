"""DEVELOPMENT ONLY: mark ONE test account as an approved Student Owner (Step 31A testing).

Why this exists: the real review/approval system (Admin Workspace / backend) is not built yet,
and the student app deliberately cannot approve anything. To test the Owner workspace you need
one account whose application is Approved. This script stands in for the future reviewer.

Safety:
  * It is a separate command-line tool. Nothing in `app/` imports or calls it, and the
    KitLend window has no button, menu or hidden shortcut for it (a test checks this).
  * It changes only the ONE account you name with --email. Students, passwords, requests,
    My List and every other table are never touched.
  * Writing needs the explicit flag --confirm-dev, and a one-time backup of the database is
    saved next to it first (*.before-dev-owner.bak).
  * Everything it writes is marked "DEV TEST APPROVAL" in review_note, and --revoke only
    undoes rows carrying that mark, so a genuine review can never be undone by accident.

Usage (from the project folder, with the KitLend window CLOSED):
    python dev_tools/dev_owner_approval.py --email ana@csucc.edu.ph --status
    python dev_tools/dev_owner_approval.py --email ana@csucc.edu.ph --approve --confirm-dev
    python dev_tools/dev_owner_approval.py --email ana@csucc.edu.ph --revoke  --confirm-dev
Optional: --db PATH to use another database file (default: the app's normal local database).
"""
import argparse
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import DatabaseError, connect, default_db_path  # noqa: E402
from app.student_owner_service import RULES_VERSION  # noqa: E402

MARK = "DEV TEST APPROVAL"
NOTE_NEW = f"{MARK} (new) - not a real review"
NOTE_WAS_PENDING = f"{MARK} (was Pending) - not a real review"
NOTE_REVOKED = f"{MARK} REVOKED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _backup(conn, db_path):
    if str(db_path) == ":memory:":
        return
    backup_path = Path(f"{db_path}.before-dev-owner.bak")
    if backup_path.exists():
        return
    target = sqlite3.connect(str(backup_path))
    try:
        conn.backup(target)
    finally:
        target.close()


def _student(conn, email):
    return conn.execute("SELECT id, full_name, email FROM students WHERE lower(email) = ?",
                        ((email or "").strip().lower(),)).fetchone()


def _applications(conn, student_id):
    return conn.execute(
        "SELECT * FROM student_owner_applications WHERE student_id = ? "
        "ORDER BY submitted_at DESC, rowid DESC", (student_id,)).fetchall()


def describe(conn, student) -> str:
    apps = _applications(conn, student["id"])
    lines = [f"Account: {student['full_name']} <{student['email']}> (id {student['id']})"]
    if not apps:
        lines.append("Student Owner applications: none")
    for app in apps:
        dev = " [DEV TEST]" if (app["review_note"] or "").startswith(MARK) else ""
        lines.append(f"  {app['application_id']}  {app['status']}{dev}")
    approved = any(a["status"] == "Approved" for a in apps)
    lines.append("Owner workspace: " + ("AVAILABLE" if approved else "not available"))
    return "\n".join(lines)


def approve(conn, student) -> str:
    apps = _applications(conn, student["id"])
    if any(a["status"] == "Approved" for a in apps):
        return "Already approved. Nothing changed."
    now = _now()
    pending = next((a for a in apps if a["status"] == "Pending"), None)
    conn.execute("BEGIN IMMEDIATE")
    try:
        if pending is not None:   # keep their real application: just mark it approved
            conn.execute(
                "UPDATE student_owner_applications SET status = 'Approved', reviewed_at = ?, "
                "review_note = ? WHERE application_id = ?",
                (now, NOTE_WAS_PENDING, pending["application_id"]))
            result = f"Application {pending['application_id']} (was Pending) is now Approved."
        else:
            application_id = "SO-" + secrets.token_hex(4).upper()
            conn.execute(
                "INSERT INTO student_owner_applications (application_id, student_id, reason, "
                "items_to_lend, rules_agreed, rules_version, status, submitted_at, reviewed_at, "
                "review_note) VALUES (?, ?, ?, ?, 1, ?, 'Approved', ?, ?, ?)",
                (application_id, student["id"], "Development test account.",
                 "Development test items.", RULES_VERSION, now, now, NOTE_NEW))
            result = f"Created application {application_id} with status Approved."
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return result


def revoke(conn, student) -> str:
    rows = [a for a in _applications(conn, student["id"])
            if a["status"] == "Approved" and (a["review_note"] or "").startswith(MARK)]
    if not rows:
        approved = any(a["status"] == "Approved" for a in _applications(conn, student["id"]))
        return ("This account's approval is not a dev test approval, so it was left alone."
                if approved else "No dev test approval to revoke. Nothing changed.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for row in rows:
            if "(was Pending)" in row["review_note"]:   # put the real application back as it was
                conn.execute(
                    "UPDATE student_owner_applications SET status = 'Pending', "
                    "reviewed_at = NULL, review_note = '' WHERE application_id = ?",
                    (row["application_id"],))
            else:
                conn.execute(
                    "UPDATE student_owner_applications SET status = 'Rejected', "
                    "reviewed_at = ?, review_note = ? WHERE application_id = ?",
                    (_now(), NOTE_REVOKED, row["application_id"]))
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return "Dev test approval revoked. The account is a normal student again."


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="DEVELOPMENT ONLY: approve/revoke ONE test account as a Student Owner.")
    parser.add_argument("--email", required=True, help="the test student's email")
    parser.add_argument("--db", help="database file (default: the app's local database)")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--status", action="store_true", help="show the account's state")
    action.add_argument("--approve", action="store_true", help="mark the account as approved")
    action.add_argument("--revoke", action="store_true", help="undo a dev test approval")
    parser.add_argument("--confirm-dev", action="store_true",
                        help="required for --approve / --revoke (development databases only)")
    args = parser.parse_args(argv)

    db_path = args.db if args.db else default_db_path()
    if (args.approve or args.revoke) and not args.confirm_dev:
        print("Refusing to change anything: add --confirm-dev to confirm this is a "
              "development/test database.")
        return 2
    if args.db and not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        return 1
    print(f"Database: {db_path}")
    try:
        conn = connect(db_path)
    except DatabaseError as exc:
        print(exc)
        return 1
    try:
        student = _student(conn, args.email)
        if student is None:
            print(f"No account with the email {args.email!r}. Nothing changed.")
            return 1
        if args.status:
            print(describe(conn, student))
            return 0
        _backup(conn, db_path)
        print(approve(conn, student) if args.approve else revoke(conn, student))
        print(describe(conn, student))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(run())
