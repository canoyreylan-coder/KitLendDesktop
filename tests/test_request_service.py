"""Step 8C tests: request persistence, student isolation, cancellation, migrations.

Run from the project folder:   python -m unittest discover -s tests -v
No window is opened; only the plain-Python parts are used.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import database  # noqa: E402
from app.auth_service import AuthError, AuthService, hash_password  # noqa: E402
from app.catalog_screen import SAMPLE_ITEMS  # noqa: E402
from app.my_list_screen import RequestDraft, get_max_borrow_days  # noqa: E402
from app.my_requests_screen import RequestStatus, compute_due_at  # noqa: E402
from app.request_service import RequestError, RequestService  # noqa: E402

PW = "correct horse"
AVAILABLE = [item for item in SAMPLE_ITEMS if item.is_available]
UNAVAILABLE = [item for item in SAMPLE_ITEMS if not item.is_available]


def make_draft(item, days=1, hours_ahead=48):
    pickup = (datetime.now().astimezone() + timedelta(hours=hours_ahead)).replace(
        minute=0, second=0, microsecond=0)
    return RequestDraft(item=item, pickup_at=pickup, days=days, max_days=get_max_borrow_days(item))


class RequestServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.service = RequestService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")

    def tearDown(self):
        self.tmp.cleanup()

    def count_rows(self, table="borrow_requests"):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            conn.close()

    # ---------- saving ----------
    def test_submit_saves_pending_request_with_all_details(self):
        item = AVAILABLE[0]
        draft = make_draft(item, days=1)
        saved = self.service.submit_requests(self.ana.id, [draft], "key-1")
        self.assertEqual(len(saved), 1)
        loaded = self.service.list_requests(self.ana.id)
        self.assertEqual(len(loaded), 1)
        request = loaded[0]
        self.assertEqual(request.request_id, saved[0].request_id)
        self.assertTrue(request.request_id.startswith("REQ-"))
        self.assertEqual(request.status, RequestStatus.PENDING)
        self.assertEqual(request.item, item)
        self.assertEqual(request.requested_days, 1)
        self.assertEqual(request.max_days, draft.max_days)
        self.assertEqual(request.preferred_pickup_at, draft.pickup_at)
        self.assertEqual([c.status for c in request.status_history], [RequestStatus.PENDING])
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT student_id FROM borrow_requests").fetchone()[0],
                         self.ana.id)
        conn.close()

    def test_borrowing_rule_untouched_no_due_date_before_confirmed_pickup(self):
        self.service.submit_requests(self.ana.id, [make_draft(AVAILABLE[0], days=2)], "k")
        request = self.service.list_requests(self.ana.id)[0]
        self.assertIsNone(request.picked_up_at)
        self.assertIsNone(request.due_at)            # no countdown yet
        self.assertFalse(request.countdown_started)
        self.assertIsNone(request.approved_at)
        self.assertIsNone(request.scheduled_pickup_at)
        # The rule itself is unchanged: due = ACTUAL pickup + requested days (24 h each).
        pickup = datetime.now().astimezone()
        self.assertEqual(compute_due_at(pickup, 2) - pickup, timedelta(days=2))
        conn = sqlite3.connect(self.db)
        columns = [r[1] for r in conn.execute("PRAGMA table_info(borrow_requests)")]
        conn.close()
        self.assertNotIn("due_at", columns)          # a due date is never stored

    def test_each_item_saved_separately_with_unique_ids(self):
        drafts = [make_draft(item) for item in AVAILABLE[:3]]
        saved = self.service.submit_requests(self.ana.id, drafts, "batch")
        ids = [r.request_id for r in saved]
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(self.count_rows(), 3)
        self.assertEqual(self.count_rows("borrow_request_history"), 3)

    def test_ids_unique_across_many_requests(self):
        ids = set()
        for n, item in enumerate(AVAILABLE[:6]):
            for student in (self.ana, self.ben):
                saved = self.service.submit_requests(student.id, [make_draft(item)], f"k{n}")
                ids.add(saved[0].request_id)
        self.assertEqual(len(ids), 12)

    def test_requests_survive_restart(self):
        self.service.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "k")
        restarted = RequestService(self.db)                     # new objects, same file
        again = AuthService(self.db).login("ana@csucc.edu.ph", PW)
        loaded = restarted.list_requests(again.id)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].status, RequestStatus.PENDING)

    # ---------- isolation ----------
    def test_students_only_see_their_own_requests(self):
        mine = self.service.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "a")[0]
        theirs = self.service.submit_requests(self.ben.id, [make_draft(AVAILABLE[1])], "b")[0]
        self.assertEqual([r.request_id for r in self.service.list_requests(self.ana.id)],
                         [mine.request_id])
        self.assertEqual([r.request_id for r in self.service.list_requests(self.ben.id)],
                         [theirs.request_id])
        self.assertIsNone(self.service.get_request(self.ben.id, mine.request_id))

    def test_student_cannot_cancel_another_students_request(self):
        mine = self.service.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "a")[0]
        with self.assertRaises(RequestError):
            self.service.cancel_request(self.ben.id, mine.request_id)
        self.assertEqual(self.service.get_request(self.ana.id, mine.request_id).status,
                         RequestStatus.PENDING)
        with self.assertRaises(RequestError):                    # unknown id: same answer
            self.service.cancel_request(self.ben.id, "REQ-DOESNOTEXIST")

    def test_two_students_may_request_the_same_item(self):
        self.service.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "a")
        self.service.submit_requests(self.ben.id, [make_draft(AVAILABLE[0])], "b")
        self.assertEqual(self.count_rows(), 2)

    # ---------- cancellation ----------
    def test_cancel_pending_persists_status_and_history(self):
        saved = self.service.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "a")[0]
        cancelled = self.service.cancel_request(self.ana.id, saved.request_id)
        self.assertEqual(cancelled.status, RequestStatus.CANCELLED)

        reloaded = RequestService(self.db).get_request(self.ana.id, saved.request_id)
        self.assertEqual(reloaded.status, RequestStatus.CANCELLED)
        self.assertEqual([c.status for c in reloaded.status_history],
                         [RequestStatus.PENDING, RequestStatus.CANCELLED])
        self.assertIsNotNone(reloaded.status_changed_at)
        self.assertIn("Cancelled by you", reloaded.status_note)
        self.assertIsNone(reloaded.picked_up_at)
        self.assertIsNone(reloaded.due_at)
        self.assertFalse(reloaded.can_cancel)

    def test_cancelling_twice_is_rejected_and_changes_nothing(self):
        saved = self.service.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "a")[0]
        self.service.cancel_request(self.ana.id, saved.request_id)
        with self.assertRaises(RequestError):
            self.service.cancel_request(self.ana.id, saved.request_id)
        history = self.service.get_request(self.ana.id, saved.request_id).status_history
        self.assertEqual(len(history), 2)

    def test_cancelling_one_request_leaves_the_others_alone(self):
        saved = self.service.submit_requests(
            self.ana.id, [make_draft(AVAILABLE[0]), make_draft(AVAILABLE[1])], "a")
        self.service.cancel_request(self.ana.id, saved[0].request_id)
        statuses = {r.request_id: r.status for r in self.service.list_requests(self.ana.id)}
        self.assertEqual(statuses[saved[0].request_id], RequestStatus.CANCELLED)
        self.assertEqual(statuses[saved[1].request_id], RequestStatus.PENDING)

    def test_item_can_be_requested_again_after_cancelling(self):
        item = AVAILABLE[0]
        first = self.service.submit_requests(self.ana.id, [make_draft(item)], "a")[0]
        self.service.cancel_request(self.ana.id, first.request_id)
        again = self.service.submit_requests(self.ana.id, [make_draft(item)], "b")[0]
        self.assertNotEqual(first.request_id, again.request_id)

    def test_non_pending_request_cannot_be_cancelled(self):
        saved = self.service.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "a")[0]
        conn = sqlite3.connect(self.db)   # simulate a FUTURE handover (no UI can do this yet)
        conn.execute("UPDATE borrow_requests SET status = 'rejected' WHERE request_id = ?",
                     (saved.request_id,))
        conn.commit()
        conn.close()
        with self.assertRaises(RequestError):
            self.service.cancel_request(self.ana.id, saved.request_id)

    # ---------- duplicates and errors ----------
    def test_retrying_same_submission_never_creates_duplicates(self):
        drafts = [make_draft(AVAILABLE[0]), make_draft(AVAILABLE[1])]
        first = self.service.submit_requests(self.ana.id, drafts, "same-key")
        second = self.service.submit_requests(self.ana.id, drafts, "same-key")
        self.assertEqual([r.request_id for r in first], [r.request_id for r in second])
        self.assertEqual(self.count_rows(), 2)
        self.assertEqual(self.count_rows("borrow_request_history"), 2)

    def test_second_active_request_for_same_item_is_blocked(self):
        item = AVAILABLE[0]
        self.service.submit_requests(self.ana.id, [make_draft(item)], "a")
        with self.assertRaises(RequestError):
            self.service.submit_requests(self.ana.id, [make_draft(item)], "different-key")
        self.assertEqual(self.count_rows(), 1)

    def test_same_item_twice_in_one_batch_is_rejected(self):
        item = AVAILABLE[0]
        with self.assertRaises(RequestError):
            self.service.submit_requests(self.ana.id, [make_draft(item), make_draft(item)], "a")
        self.assertEqual(self.count_rows(), 0)

    def test_invalid_input_saves_nothing(self):
        good = make_draft(AVAILABLE[0])
        past = make_draft(AVAILABLE[1], hours_ahead=-5)
        too_long = make_draft(AVAILABLE[2], days=99)
        cases = [[good, past], [good, too_long], []]
        if UNAVAILABLE:
            cases.append([good, make_draft(UNAVAILABLE[0])])
        for drafts in cases:
            with self.assertRaises(RequestError):
                self.service.submit_requests(self.ana.id, drafts, "k")
        with self.assertRaises(RequestError):
            self.service.submit_requests(None, [good], "k")
        with self.assertRaises(RequestError):
            self.service.submit_requests(999999, [good], "k")      # no such account
        with self.assertRaises(RequestError):
            self.service.submit_requests(self.ana.id, [good], "")
        self.assertEqual(self.count_rows(), 0)

    def test_database_failure_midway_rolls_back_the_whole_batch(self):
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TRIGGER fail_second BEFORE INSERT ON borrow_requests "
            "WHEN NEW.batch_position = 1 BEGIN SELECT RAISE(ABORT, 'disk problem'); END")
        conn.commit()
        conn.close()
        drafts = [make_draft(AVAILABLE[0]), make_draft(AVAILABLE[1])]
        with self.assertRaises(RequestError) as caught:
            self.service.submit_requests(self.ana.id, drafts, "k")
        self.assertIn("Nothing was saved", str(caught.exception))
        self.assertEqual(self.count_rows(), 0)                    # not even the first item
        self.assertEqual(self.count_rows("borrow_request_history"), 0)
        self.assertEqual(self.service.list_requests(self.ana.id), [])

        conn = sqlite3.connect(self.db)                           # the problem goes away
        conn.execute("DROP TRIGGER fail_second")
        conn.commit()
        conn.close()
        saved = self.service.submit_requests(self.ana.id, drafts, "k")   # safe retry
        self.assertEqual(len(saved), 2)
        self.assertEqual(self.count_rows(), 2)

    def test_unreachable_database_gives_friendly_errors(self):
        broken = RequestService(os.path.join(self.tmp.name, "missing_dir", "x.db"))
        with self.assertRaises(RequestError):
            broken.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "k")
        with self.assertRaises(RequestError):
            broken.list_requests(self.ana.id)
        with self.assertRaises(RequestError):
            broken.cancel_request(self.ana.id, "REQ-1")

    def test_unreadable_record_does_not_hide_the_others(self):
        self.service.submit_requests(
            self.ana.id, [make_draft(AVAILABLE[0]), make_draft(AVAILABLE[1])], "k")
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE borrow_requests SET status = 'garbage' WHERE batch_position = 0")
        conn.commit()
        conn.close()
        result = self.service.load_requests(self.ana.id)
        self.assertEqual(len(result.requests), 1)
        self.assertEqual(result.skipped, 1)

    # ---------- authentication still works alongside ----------
    def test_login_still_works_after_requests_exist(self):
        self.service.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "k")
        self.assertEqual(self.auth.login("ANA@csucc.edu.ph", PW).id, self.ana.id)
        with self.assertRaises(AuthError):
            self.auth.login("ana@csucc.edu.ph", "wrong password")


class MigrationTests(unittest.TestCase):
    OLD_SCHEMA = """
    CREATE TABLE students (
        id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, salt TEXT NOT NULL,
        iterations INTEGER NOT NULL, created_at TEXT NOT NULL);
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "old.db")
        salt = bytes(range(16))
        self.old_row = ("Old Student", "old@csucc.edu.ph",
                        hash_password(PW, salt, 310_000), salt.hex(), 310_000,
                        "2026-10-01T00:00:00+00:00")
        conn = sqlite3.connect(self.db)               # a Step 8A/8B-era database
        conn.executescript(self.OLD_SCHEMA)
        conn.execute("INSERT INTO students (full_name, email, password_hash, salt, "
                     "iterations, created_at) VALUES (?, ?, ?, ?, ?, ?)", self.old_row)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def tables(self):
        conn = sqlite3.connect(self.db)
        try:
            return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()

    def test_existing_accounts_and_passwords_survive_migration(self):
        student = AuthService(self.db).login("old@csucc.edu.ph", PW)   # runs the migration
        self.assertEqual(student.full_name, "Old Student")
        conn = sqlite3.connect(self.db)
        row = conn.execute("SELECT full_name, email, password_hash, salt, iterations, "
                           "created_at FROM students").fetchone()
        conn.close()
        self.assertEqual(row, self.old_row)                          # byte-for-byte unchanged
        self.assertTrue({"borrow_requests", "borrow_request_history",
                         "schema_migrations"} <= self.tables())

    def test_requests_work_on_a_migrated_database(self):
        student = AuthService(self.db).login("old@csucc.edu.ph", PW)
        service = RequestService(self.db)
        service.submit_requests(student.id, [make_draft(AVAILABLE[0])], "k")
        self.assertEqual(len(service.list_requests(student.id)), 1)

    def test_migration_is_applied_once_and_is_repeatable(self):
        for _ in range(3):
            AuthService(self.db).login("old@csucc.edu.ph", PW)
        conn = sqlite3.connect(self.db)
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY 1")]
        conn.close()
        self.assertEqual(versions, [m[0] for m in database.MIGRATIONS])  # every migration, once each

    def test_one_time_safety_copy_keeps_the_old_accounts(self):
        AuthService(self.db).login("old@csucc.edu.ph", PW)
        backup = Path(f"{self.db}.before-v2.bak")
        self.assertTrue(backup.exists())
        conn = sqlite3.connect(str(backup))
        rows = conn.execute("SELECT email FROM students").fetchall()
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        self.assertEqual(rows, [("old@csucc.edu.ph",)])
        self.assertNotIn("borrow_requests", names)                   # copy is the pre-migration state

    def test_fresh_database_gets_everything(self):
        fresh = os.path.join(self.tmp.name, "fresh.db")
        AuthService(fresh).register("New One", "new@csucc.edu.ph", PW, PW, student_id_number="ID-NEW")
        conn = sqlite3.connect(fresh)
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        self.assertTrue({"students", "borrow_requests", "borrow_request_history"} <= names)
        self.assertFalse(Path(f"{fresh}.before-v2.bak").exists())    # nothing to protect yet


if __name__ == "__main__":
    unittest.main()
