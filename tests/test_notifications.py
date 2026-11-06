"""Step 11 tests: Notifications (creation, read state, isolation, duplicates, migration,
screen, dashboard and regressions).

Run from the project folder:   python -m unittest discover -s tests -v

Groups 1-4 need no window. Groups 5-6 open widgets in Qt's invisible "offscreen" mode
and are skipped automatically if PySide6 is missing.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import database  # noqa: E402
from app.auth_service import AuthService  # noqa: E402
from app.my_list_screen import RequestDraft, get_max_borrow_days  # noqa: E402
from app.notification_service import (  # noqa: E402
    EVENT_REQUEST_CANCELLED,
    EVENT_REQUEST_SUBMITTED,
    SUPPORTED_EVENTS,
    NotificationError,
    NotificationService,
    format_notification_time,
    record_request_submitted,
)
from app.request_service import RequestError, RequestService  # noqa: E402
from seed_helpers import (  # noqa: E402
    AVAILABLE,
    insert_request,
    make_borrowing,
    now_fixed,
    seed_samples,
)

PW = "correct horse"


def make_draft(item, days=1, hours_ahead=48):
    pickup = (datetime.now().astimezone() + timedelta(hours=hours_ahead)).replace(
        minute=0, second=0, microsecond=0)
    return RequestDraft(item=item, pickup_at=pickup, days=days,
                        max_days=get_max_borrow_days(item))


class TempDbCase(unittest.TestCase):
    """Two students, one temporary database, and handy counters."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.requests = RequestService(self.db)
        self.notes = NotificationService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")

    def tearDown(self):
        self.tmp.cleanup()

    def query(self, sql, params=()):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def count(self, table="notifications"):
        return self.query(f"SELECT COUNT(*) FROM {table}")[0][0]

    def submit(self, student, item, key):
        return self.requests.submit_requests(student.id, [make_draft(item)], key)[0]


# ======================================================================
# 1. CREATION: only real, successful request actions create notifications
# ======================================================================
class NotificationCreationTests(TempDbCase):
    def test_new_student_has_no_notifications(self):
        self.assertEqual(self.notes.list_notifications(self.ana.id), [])
        self.assertEqual(self.notes.unread_count(self.ana.id), 0)

    def test_successful_submission_creates_one_unread_notification(self):
        request = self.submit(self.ana, AVAILABLE[0], "k1")
        notes = self.notes.list_notifications(self.ana.id)
        self.assertEqual(len(notes), 1)
        note = notes[0]
        self.assertEqual(note.event_type, EVENT_REQUEST_SUBMITTED)
        self.assertEqual(note.title, "Request submitted")
        self.assertIn(request.request_id, note.message)
        self.assertIn(AVAILABLE[0].title, note.message)
        self.assertEqual(note.request_id, request.request_id)
        self.assertEqual(note.student_id, self.ana.id)
        self.assertTrue(note.is_unread)
        self.assertIsNone(note.read_at)
        self.assertEqual(note.created_at, request.submitted_at)  # event date/time

    def test_a_batch_creates_one_notification_per_request(self):
        drafts = [make_draft(AVAILABLE[0]), make_draft(AVAILABLE[1])]
        saved = self.requests.submit_requests(self.ana.id, drafts, "batch")
        notes = self.notes.list_notifications(self.ana.id)
        self.assertEqual({n.request_id for n in notes}, {r.request_id for r in saved})
        self.assertEqual(len(notes), 2)

    def test_successful_cancellation_creates_a_cancelled_notification(self):
        request = self.submit(self.ana, AVAILABLE[0], "k1")
        when = now_fixed() + timedelta(minutes=5)
        self.requests.cancel_request(self.ana.id, request.request_id, when)
        notes = self.notes.list_notifications(self.ana.id)
        self.assertEqual(len(notes), 2)
        newest = notes[0]                                   # newest first
        self.assertEqual(newest.event_type, EVENT_REQUEST_CANCELLED)
        self.assertEqual(newest.title, "Request cancelled")
        self.assertIn(request.request_id, newest.message)
        self.assertIn(AVAILABLE[0].title, newest.message)
        self.assertTrue(newest.is_unread)
        self.assertGreaterEqual(newest.created_at, notes[1].created_at)
        self.assertEqual(notes[1].event_type, EVENT_REQUEST_SUBMITTED)

    def test_failed_submissions_create_nothing(self):
        item = AVAILABLE[0]
        self.submit(self.ana, item, "k1")
        before = self.count()
        with self.assertRaises(RequestError):               # active duplicate, new key
            self.requests.submit_requests(self.ana.id, [make_draft(item)], "k2")
        with self.assertRaises(RequestError):               # nothing to request
            self.requests.submit_requests(self.ana.id, [], "k3")
        with self.assertRaises(RequestError):               # unknown account
            self.requests.submit_requests(9999, [make_draft(AVAILABLE[1])], "k4")
        self.assertEqual(self.count(), before)

    def test_retrying_the_same_submission_creates_no_extra_notification(self):
        draft = make_draft(AVAILABLE[0])
        first = self.requests.submit_requests(self.ana.id, [draft], "same-key")
        again = self.requests.submit_requests(self.ana.id, [draft], "same-key")
        self.assertEqual([r.request_id for r in first], [r.request_id for r in again])
        self.assertEqual(self.count(), 1)

    def test_repeated_cancellation_creates_no_extra_notification(self):
        request = self.submit(self.ana, AVAILABLE[0], "k1")
        self.requests.cancel_request(self.ana.id, request.request_id)
        self.assertEqual(self.count(), 2)
        for _ in range(3):
            with self.assertRaises(RequestError):
                self.requests.cancel_request(self.ana.id, request.request_id)
        self.assertEqual(self.count(), 2)

    def test_failed_cancellations_create_nothing(self):
        mine = self.submit(self.ana, AVAILABLE[0], "k1")
        borrowed = make_borrowing("REQ-BORROW", now_fixed(), picked_days_ago=1, days=2)
        insert_request(self.db, self.ana.id, borrowed, "kb")
        before = self.count()
        with self.assertRaises(RequestError):               # not found
            self.requests.cancel_request(self.ana.id, "REQ-NOPE")
        with self.assertRaises(RequestError):               # someone else's request
            self.requests.cancel_request(self.ben.id, mine.request_id)
        with self.assertRaises(RequestError):               # already borrowed: not cancellable
            self.requests.cancel_request(self.ana.id, "REQ-BORROW")
        self.assertEqual(self.count(), before)
        self.assertEqual(self.requests.get_request(self.ana.id, mine.request_id).status.value,
                         "pending")

    def test_notification_is_saved_in_the_same_transaction_as_the_submission(self):
        with mock.patch("app.request_service.record_request_submitted",
                        side_effect=sqlite3.OperationalError("boom")):
            with self.assertRaises(RequestError):
                self.requests.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "k1")
        self.assertEqual(self.count("borrow_requests"), 0)  # request rolled back too
        self.assertEqual(self.count("borrow_request_history"), 0)
        self.assertEqual(self.count(), 0)

    def test_notification_is_saved_in_the_same_transaction_as_the_cancellation(self):
        request = self.submit(self.ana, AVAILABLE[0], "k1")
        with mock.patch("app.request_service.record_request_cancelled",
                        side_effect=sqlite3.OperationalError("boom")):
            with self.assertRaises(RequestError):
                self.requests.cancel_request(self.ana.id, request.request_id)
        again = self.requests.get_request(self.ana.id, request.request_id)
        self.assertEqual(again.status.value, "pending")     # cancellation rolled back too
        self.assertEqual(len(again.status_history), 1)
        self.assertEqual(self.count(), 1)                   # only the 'submitted' one

    def test_same_event_can_never_be_stored_twice(self):
        conn = database.connect(self.db)
        try:
            when = now_fixed()
            self.assertTrue(record_request_submitted(conn, self.ana.id, "REQ-X", "Item", when))
            self.assertFalse(record_request_submitted(conn, self.ana.id, "REQ-X", "Item", when))
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self.count(), 1)

    def test_no_notifications_for_requests_that_existed_before_step_11(self):
        seed_samples(self.db, self.ana.id)                  # written straight into SQLite
        self.assertEqual(len(self.requests.list_requests(self.ana.id)), 8)
        self.assertEqual(self.notes.list_notifications(self.ana.id), [])
        self.assertEqual(self.count(), 0)

    def test_only_two_event_kinds_exist_in_step_11(self):
        self.assertEqual(set(SUPPORTED_EVENTS), {"request_submitted", "request_cancelled"})
        self.submit(self.ana, AVAILABLE[0], "k1")
        self.assertEqual({r[0] for r in self.query("SELECT DISTINCT event_type FROM notifications")},
                         {"request_submitted"})

    def test_time_format_has_date_and_time(self):
        moment = datetime(2026, 10, 23, 15, 5).astimezone()
        self.assertEqual(format_notification_time(moment), "Oct 23, 2026 · 3:05 PM")
        self.assertEqual(format_notification_time(datetime(2026, 1, 2, 0, 30).astimezone()),
                         "Jan 2, 2026 · 12:30 AM")
        self.assertEqual(format_notification_time(None), "")


# ======================================================================
# 2. READ / UNREAD STATE (persisted in SQLite)
# ======================================================================
class NotificationReadStateTests(TempDbCase):
    def setUp(self):
        super().setUp()
        for index, item in enumerate(AVAILABLE[:3]):
            self.submit(self.ana, item, f"k{index}")

    def test_all_start_unread(self):
        self.assertEqual(self.notes.unread_count(self.ana.id), 3)

    def test_mark_one_as_read_changes_only_that_one(self):
        notes = self.notes.list_notifications(self.ana.id)
        self.assertTrue(self.notes.mark_read(self.ana.id, notes[0].id))
        after = {n.id: n for n in self.notes.list_notifications(self.ana.id)}
        self.assertTrue(after[notes[0].id].is_read)
        self.assertIsNotNone(after[notes[0].id].read_at)
        self.assertTrue(after[notes[1].id].is_unread)
        self.assertTrue(after[notes[2].id].is_unread)
        self.assertEqual(self.notes.unread_count(self.ana.id), 2)

    def test_read_state_survives_a_restart(self):
        first = self.notes.list_notifications(self.ana.id)[0]
        self.notes.mark_read(self.ana.id, first.id)
        restarted = NotificationService(self.db)            # a "new run" of the app
        again = {n.id: n for n in restarted.list_notifications(self.ana.id)}
        self.assertTrue(again[first.id].is_read)
        self.assertEqual(restarted.unread_count(self.ana.id), 2)

    def test_marking_an_already_read_notification_keeps_its_read_time(self):
        first = self.notes.list_notifications(self.ana.id)[0]
        self.notes.mark_read(self.ana.id, first.id)
        stamp = self.query("SELECT read_at FROM notifications WHERE id = ?", (first.id,))
        self.assertFalse(self.notes.mark_read(self.ana.id, first.id))
        self.assertEqual(
            self.query("SELECT read_at FROM notifications WHERE id = ?", (first.id,)), stamp)

    def test_mark_all_as_read(self):
        self.assertEqual(self.notes.mark_all_read(self.ana.id), 3)
        self.assertEqual(self.notes.unread_count(self.ana.id), 0)
        self.assertTrue(all(n.is_read for n in self.notes.list_notifications(self.ana.id)))
        self.assertEqual(self.notes.mark_all_read(self.ana.id), 0)  # nothing left to change
        self.assertEqual(NotificationService(self.db).unread_count(self.ana.id), 0)

    def test_marking_read_never_changes_the_message_or_event_time(self):
        before = self.query("SELECT id, title, message, created_at FROM notifications ORDER BY id")
        self.notes.mark_all_read(self.ana.id)
        after = self.query("SELECT id, title, message, created_at FROM notifications ORDER BY id")
        self.assertEqual(before, after)

    def test_a_new_event_after_reading_is_unread_again(self):
        self.notes.mark_all_read(self.ana.id)
        self.submit(self.ana, AVAILABLE[3], "later")
        self.assertEqual(self.notes.unread_count(self.ana.id), 1)

    def test_bad_ids_are_rejected(self):
        for bad in (None, "1", True, 99999):
            with self.assertRaises(NotificationError):
                self.notes.mark_read(self.ana.id, bad)
        for bad in (None, "1", True):
            with self.assertRaises(NotificationError):
                self.notes.list_notifications(bad)


# ======================================================================
# 3. ACCOUNT ISOLATION
# ======================================================================
class NotificationIsolationTests(TempDbCase):
    def setUp(self):
        super().setUp()
        self.ana_request = self.submit(self.ana, AVAILABLE[0], "ka")
        self.submit(self.ben, AVAILABLE[1], "kb")

    def test_each_student_sees_only_their_own_notifications(self):
        ana_ids = {n.request_id for n in self.notes.list_notifications(self.ana.id)}
        ben_ids = {n.request_id for n in self.notes.list_notifications(self.ben.id)}
        self.assertEqual(len(ana_ids), 1)
        self.assertEqual(len(ben_ids), 1)
        self.assertFalse(ana_ids & ben_ids)
        self.assertTrue(all(n.student_id == self.ana.id
                            for n in self.notes.list_notifications(self.ana.id)))

    def test_counts_are_per_student(self):
        self.notes.mark_all_read(self.ben.id)
        self.assertEqual(self.notes.unread_count(self.ben.id), 0)
        self.assertEqual(self.notes.unread_count(self.ana.id), 1)

    def test_a_student_cannot_mark_someone_elses_notification(self):
        ana_note = self.notes.list_notifications(self.ana.id)[0]
        with self.assertRaises(NotificationError):
            self.notes.mark_read(self.ben.id, ana_note.id)  # looks exactly like a missing one
        self.assertTrue(self.notes.list_notifications(self.ana.id)[0].is_unread)

    def test_mark_all_for_one_student_leaves_the_other_untouched(self):
        self.notes.mark_all_read(self.ana.id)
        self.assertEqual(self.notes.unread_count(self.ben.id), 1)

    def test_cancelling_notifies_only_the_owner(self):
        self.requests.cancel_request(self.ana.id, self.ana_request.request_id)
        self.assertEqual(len(self.notes.list_notifications(self.ana.id)), 2)
        self.assertEqual(len(self.notes.list_notifications(self.ben.id)), 1)

    def test_a_blocked_cancel_by_another_student_notifies_nobody(self):
        before = self.count()
        with self.assertRaises(RequestError):
            self.requests.cancel_request(self.ben.id, self.ana_request.request_id)
        self.assertEqual(self.count(), before)


# ======================================================================
# 4. RESTARTS, REFRESHES AND THE SAFE MIGRATION
# ======================================================================
class NotificationDuplicateTests(TempDbCase):
    def test_restarting_and_refreshing_never_creates_notifications(self):
        request = self.submit(self.ana, AVAILABLE[0], "k1")
        self.requests.cancel_request(self.ana.id, request.request_id)
        self.assertEqual(self.count(), 2)
        for _ in range(3):                                   # "restart" the app three times
            auth = AuthService(self.db)
            auth.login("ana@csucc.edu.ph", PW)
            requests, notes = RequestService(self.db), NotificationService(self.db)
            requests.load_requests(self.ana.id)              # a refresh of My Requests
            notes.list_notifications(self.ana.id)            # a refresh of Notifications
            notes.unread_count(self.ana.id)
            database.connect(self.db).close()                # migrations run again
        self.assertEqual(self.count(), 2)

    def test_each_event_has_its_own_key_and_keys_are_unique(self):
        request = self.submit(self.ana, AVAILABLE[0], "k1")
        self.requests.cancel_request(self.ana.id, request.request_id)
        keys = [r[0] for r in self.query("SELECT dedupe_key FROM notifications")]
        self.assertEqual(len(keys), len(set(keys)))
        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):  # the database itself refuses a clone
                conn.execute(
                    "INSERT INTO notifications (student_id, event_type, title, message, "
                    "request_id, dedupe_key, created_at) VALUES (?,?,?,?,?,?,?)",
                    (self.ana.id, "request_submitted", "t", "m", request.request_id,
                     keys[0], "2026-10-23T10:00:00+08:00"))
        finally:
            conn.close()


class NotificationMigrationTests(unittest.TestCase):
    """A Step 10 database (accounts, requests, history) must survive migration 3 intact."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "step10.db")
        conn = sqlite3.connect(self.db)                      # build exactly the Step 10 schema
        conn.executescript(database.SCHEMA)
        conn.execute(database._MIGRATION_TABLE)
        for version, name, statements in database.MIGRATIONS:
            if version > 2:
                continue
            for statement in statements:
                conn.execute(statement)
            conn.execute("INSERT INTO schema_migrations VALUES (?, ?, ?)",
                         (version, name, "2026-10-01T00:00:00+00:00"))
        conn.execute("INSERT INTO students (full_name, email, password_hash, salt, iterations, "
                     "created_at) VALUES ('Old Student', 'old@csucc.edu.ph', 'h', 's', 1, "
                     "'2026-10-01T00:00:00+00:00')")
        conn.commit()
        conn.close()
        seed_samples(self.db, 1)                             # 8 old requests + their history
        self.before = self.snapshot()

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self):
        conn = sqlite3.connect(self.db)
        try:
            return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()
                    for t in ("students", "borrow_requests", "borrow_request_history")}
        finally:
            conn.close()

    def tables(self):
        conn = sqlite3.connect(self.db)
        try:
            return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()

    def test_step_10_database_has_no_notifications_table_before_migrating(self):
        self.assertNotIn("notifications", self.tables())

    def test_migration_keeps_every_account_request_and_history_row_unchanged(self):
        database.connect(self.db).close()
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(len(self.before["borrow_requests"]), 8)

    def test_migration_creates_an_empty_notifications_table(self):
        database.connect(self.db).close()
        self.assertIn("notifications", self.tables())
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0], 0)
            columns = {r[1] for r in conn.execute("PRAGMA table_info(notifications)")}
        finally:
            conn.close()
        self.assertTrue({"student_id", "event_type", "message", "request_id", "dedupe_key",
                         "created_at", "read_at"} <= columns)

    def test_old_requests_get_no_notifications_and_the_service_sees_none(self):
        database.connect(self.db).close()
        self.assertEqual(NotificationService(self.db).list_notifications(1), [])

    def test_migration_is_recorded_once_and_is_repeatable(self):
        for _ in range(3):
            database.connect(self.db).close()
        conn = sqlite3.connect(self.db)
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY 1")]
        conn.close()
        self.assertEqual(versions, [m[0] for m in database.MIGRATIONS])  # every migration, once each
        self.assertEqual(self.snapshot(), self.before)

    def test_safety_copy_is_made_and_holds_the_pre_migration_state(self):
        database.connect(self.db).close()
        backup = Path(f"{self.db}.before-v3.bak")
        self.assertTrue(backup.exists())
        conn = sqlite3.connect(str(backup))
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        accounts = conn.execute("SELECT email FROM students").fetchall()
        conn.close()
        self.assertNotIn("notifications", names)
        self.assertEqual(accounts, [("old@csucc.edu.ph",)])

    def test_a_migrated_database_still_takes_requests_and_notifies(self):
        service, notes = RequestService(self.db), NotificationService(self.db)
        request = service.submit_requests(1, [make_draft(AVAILABLE[0])], "post-migration")[0]
        self.assertEqual([n.request_id for n in notes.list_notifications(1)],
                         [request.request_id])
        self.assertEqual(len(service.list_requests(1)), 9)

    def test_fresh_database_gets_the_table_without_a_backup(self):
        fresh = os.path.join(self.tmp.name, "fresh.db")
        AuthService(fresh).register("New One", "new@csucc.edu.ph", PW, PW, student_id_number="ID-NEW")
        conn = sqlite3.connect(fresh)
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        self.assertIn("notifications", names)
        self.assertFalse(Path(f"{fresh}.before-v3.bak").exists())


# ======================================================================
# 5 + 6. THE SCREEN, THE DASHBOARD AND NAVIGATION (need a real PySide6)
# ======================================================================
try:
    import PySide6
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False


def fake_notification(note_id, *, read=False, title="Request submitted",
                      message="Your request REQ-1 for “Item” was submitted and is now Pending.",
                      minutes_ago=0):
    from app.notification_service import Notification
    created = now_fixed() - timedelta(minutes=minutes_ago)
    return Notification(note_id, 1, EVENT_REQUEST_SUBMITTED, title, message, "REQ-1", created,
                        created if read else None)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class NotificationsScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.notifications_screen import NotificationsScreen
        self.screen = NotificationsScreen([], stored_locally=True)

    def test_empty_screen_shows_the_empty_state(self):
        self.assertFalse(self.screen.empty_state.isHidden())
        self.assertTrue(self.screen.list_section.isHidden())
        self.assertEqual(self.screen.cards(), [])
        self.assertFalse(self.screen.mark_all_button.isEnabled())
        self.assertEqual(self.screen.empty_title.text(), "No notifications yet")
        self.assertFalse(self.screen.empty_button.isHidden())
        self.assertEqual([b.text() for b in self.screen._tab_buttons.values()],
                         ["All  0", "Unread  0", "Read  0"])

    def test_empty_state_button_asks_for_the_catalog(self):
        seen = []
        self.screen.browse_catalog_requested.connect(lambda: seen.append(True))
        self.screen.empty_state.findChild(QPushButton, "catalogPrimaryButton").click()
        self.assertEqual(seen, [True])

    def test_cards_show_title_message_time_and_read_status(self):
        self.screen.set_notifications([fake_notification(2), fake_notification(1, read=True)])
        self.assertTrue(self.screen.empty_state.isHidden())
        unread_card, read_card = self.screen.cards()
        self.assertEqual(unread_card.status_pill.text(), "Unread")
        self.assertEqual(read_card.status_pill.text(), "Read")
        self.assertIn("REQ-1", unread_card.message_label.text())
        self.assertNotEqual(unread_card.time_label.text(), "")
        texts = " ".join(label.text() for label in unread_card.findChildren(QLabel))
        self.assertIn("Request submitted", texts)  # the title
        self.assertIsNotNone(unread_card.mark_read_button)   # only unread ones can be marked
        self.assertIsNone(read_card.mark_read_button)
        self.assertTrue(self.screen.mark_all_button.isEnabled())
        self.assertEqual(self.screen.unread_count, 1)

    def test_unread_rows_carry_the_accent_property_and_read_rows_do_not(self):
        self.screen.set_notifications([fake_notification(2), fake_notification(1, read=True)])
        unread_card, read_card = self.screen.cards()
        self.assertTrue(unread_card.property("unread"))
        self.assertFalse(read_card.property("unread"))

    def test_tabs_split_all_unread_and_read(self):
        notes = [fake_notification(3), fake_notification(2, read=True), fake_notification(1)]
        self.screen.set_notifications(notes)
        self.assertEqual([b.text() for b in self.screen._tab_buttons.values()],
                         ["All  3", "Unread  2", "Read  1"])
        self.assertEqual([c.notification.id for c in self.screen.cards()], [3, 2, 1])
        self.screen.set_tab("unread")
        self.assertEqual(self.screen.current_tab, "unread")
        self.assertEqual([c.notification.id for c in self.screen.cards()], [3, 1])
        self.screen.set_tab("read")
        self.assertEqual([c.notification.id for c in self.screen.cards()], [2])
        self.assertEqual(len(self.screen.notifications), 3)  # nothing is removed
        with self.assertRaises(ValueError):
            self.screen.set_tab("nope")

    def test_tab_empty_states_and_the_tab_survives_a_refresh(self):
        self.screen.set_notifications([fake_notification(1, read=True)])
        self.screen.set_tab("unread")
        self.assertFalse(self.screen.empty_state.isHidden())
        self.assertEqual(self.screen.empty_title.text(), "You are all caught up")
        self.assertTrue(self.screen.empty_button.isHidden())
        self.screen.set_notifications([fake_notification(2), fake_notification(1, read=True)])
        self.assertEqual(self.screen.current_tab, "unread")  # same tab after new data
        self.assertTrue(self.screen.empty_state.isHidden())
        self.screen.set_notifications([fake_notification(2)])
        self.screen.set_tab("read")
        self.assertEqual(self.screen.empty_title.text(), "No read notifications yet")

    def test_counts_line_and_guide(self):
        self.screen.set_notifications([fake_notification(2), fake_notification(1, read=True)])
        self.assertIn("1</b> unread", self.screen.counts_text)
        self.assertIn("2</b> total", self.screen.counts_text)
        self.assertTrue(self.screen.guide_body.isHidden())
        self.screen.guide_toggle.click()
        self.assertFalse(self.screen.guide_body.isHidden())

    def test_theme_is_limited_to_this_screen(self):
        import re
        from app.notifications_theme import NOTIFICATIONS_V2_QSS
        groups = re.findall(r"^([^\n{}/][^{}]*)\{", NOTIFICATIONS_V2_QSS, re.M)
        self.assertGreater(len(groups), 20)
        for group in groups:
            for selector in group.split(","):
                self.assertTrue(selector.strip().startswith("QWidget#notificationsScreen"),
                                selector.strip())

    def test_clicking_mark_as_read_asks_for_that_notification(self):
        seen = []
        self.screen.mark_read_requested.connect(seen.append)
        self.screen.set_notifications([fake_notification(7)])
        self.screen.cards()[0].mark_read_button.click()
        self.assertEqual(seen, [7])

    def test_clicking_mark_all_asks_for_all(self):
        seen = []
        self.screen.mark_all_read_requested.connect(lambda: seen.append(True))
        self.screen.set_notifications([fake_notification(1)])
        self.screen.mark_all_button.click()
        self.assertEqual(seen, [True])

    def test_all_read_disables_mark_all(self):
        self.screen.set_notifications([fake_notification(1, read=True)])
        self.assertFalse(self.screen.mark_all_button.isEnabled())

    def test_duplicate_ids_are_rejected_and_replacing_clears_old_cards(self):
        with self.assertRaises(ValueError):
            self.screen.set_notifications([fake_notification(1), fake_notification(1)])
        self.screen.set_notifications([fake_notification(1), fake_notification(2)])
        self.screen.set_notifications([fake_notification(3)])
        self.assertEqual(len(self.screen.notifications), 1)
        self.qt_app.processEvents()


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardNotificationsTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        self.build = lambda student, **kw: StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests, **kw)

    def home_unread(self, dash):
        return dash.home_page.notification_stat.number_label.text()

    def test_new_account_opens_the_empty_notifications_page(self):
        dash = self.build(self.ana)
        dash.go_to("notifications")
        self.assertIs(dash.content_stack.currentWidget(), dash.my_notifications_page)
        self.assertFalse(dash.my_notifications_page.empty_state.isHidden())
        self.assertEqual(self.home_unread(dash), "0")

    def test_submitting_a_request_refreshes_the_page_and_the_unread_count_immediately(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        page = dash.my_notifications_page
        self.assertEqual([n.title for n in page.notifications], ["Request submitted"])
        self.assertTrue(page.empty_state.isHidden())
        self.assertEqual(self.home_unread(dash), "1")

    def test_cancelling_refreshes_the_page_and_the_unread_count_immediately(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        request = dash.my_requests_page.requests[0]
        dash._cancel_request(request, now_fixed() + timedelta(seconds=5))
        self.assertEqual([n.title for n in dash.my_notifications_page.notifications],
                         ["Request cancelled", "Request submitted"])
        self.assertEqual(self.home_unread(dash), "2")

    def test_a_repeated_cancellation_through_the_dashboard_adds_nothing(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        request = dash.my_requests_page.requests[0]
        dash._cancel_request(request, now_fixed() + timedelta(seconds=5))
        with self.assertRaises(RequestError):
            dash._cancel_request(request, now_fixed() + timedelta(seconds=9))
        self.assertEqual(len(dash.my_notifications_page.notifications), 2)
        self.assertEqual(self.count(), 2)

    def test_marking_one_read_updates_page_and_dashboard_and_persists(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        dash._submit_drafts([make_draft(AVAILABLE[1])], "k2")
        first = dash.my_notifications_page.notifications[0]
        dash.my_notifications_page.mark_read_requested.emit(first.id)
        self.assertEqual(dash.my_notifications_page.unread_count, 1)
        self.assertEqual(self.home_unread(dash), "1")
        reopened = self.build(self.ana)                      # a restart
        self.assertEqual(reopened.my_notifications_page.unread_count, 1)
        self.assertEqual(self.home_unread(reopened), "1")

    def test_mark_all_read_updates_page_and_dashboard(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        dash._submit_drafts([make_draft(AVAILABLE[1])], "k2")
        dash.my_notifications_page.mark_all_read_requested.emit()
        self.assertEqual(dash.my_notifications_page.unread_count, 0)
        self.assertEqual(self.home_unread(dash), "0")
        self.assertFalse(dash.my_notifications_page.mark_all_button.isEnabled())
        self.assertEqual(len(dash.my_notifications_page.notifications), 2)  # kept, just read

    def test_dashboard_never_shows_another_students_notifications(self):
        self.build(self.ana)._submit_drafts([make_draft(AVAILABLE[0])], "ka")
        ben = self.build(self.ben)
        self.assertEqual(ben.my_notifications_page.notifications, [])
        self.assertEqual(self.home_unread(ben), "0")
        ana_note = self.notes.list_notifications(self.ana.id)[0]
        ben.my_notifications_page.mark_read_requested.emit(ana_note.id)   # forged id
        self.assertTrue(self.notes.list_notifications(self.ana.id)[0].is_unread)

    def test_restarting_the_dashboard_creates_no_duplicates(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        for _ in range(3):
            again = self.build(self.ana)
            again.go_to("notifications")
            again.go_to("dashboard")
            again.go_to("notifications")
        self.assertEqual(self.count(), 1)
        self.assertEqual(len(again.my_notifications_page.notifications), 1)

    def test_seeded_history_produces_no_notifications(self):
        seed_samples(self.db, self.ana.id)
        dash = self.build(self.ana)
        self.assertEqual(dash.my_notifications_page.notifications, [])
        self.assertEqual(self.home_unread(dash), "0")

    def test_logout_clears_the_notifications_page_and_dashboard_count(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        dash._emit_exit()
        self.assertEqual(dash.my_notifications_page.notifications, [])
        self.assertEqual(self.home_unread(dash), "0")

    def test_empty_state_button_goes_to_the_catalog(self):
        dash = self.build(self.ana)
        dash.go_to("notifications")
        dash.my_notifications_page.browse_catalog_requested.emit()
        self.assertIs(dash.content_stack.currentWidget(), dash.catalog_page)

    def test_dashboard_notification_card_previews_real_notifications(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        card = dash.home_page.notifications_card
        self.assertEqual(card._subtitle_label._full_text, "1 unread")
        self.assertEqual(card._rows.count(), 1)

    def test_main_window_shares_one_database_for_notifications(self):
        from app.main_window import MainWindow
        window = MainWindow(auth_service=self.auth)
        window.show_dashboard(self.ana)
        self.assertTrue(window.dashboard.stores_notifications)
        window.dashboard._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        self.assertEqual(len(self.notes.list_notifications(self.ana.id)), 1)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class NavigationRegressionTests(TempDbCase):
    """Everything from Steps 8C-10 still works next to a real Notifications page."""

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        seed_samples(self.db, self.ana.id)
        self.dash = StudentDashboard(build_empty_data("Ana Reyes"), signed_in_email=self.ana.email,
                                     student_id=self.ana.id, request_service=self.requests)

    def test_all_real_pages_open_in_the_same_stack(self):
        d = self.dash
        for key, page in (("dashboard", d.home_page), ("catalog", d.catalog_page),
                          ("my_list", d.my_list_page), ("my_requests", d.my_requests_page),
                          ("borrowings", d.my_borrowings_page),
                          ("reservations", d.my_reservations_page),
                          ("notifications", d.my_notifications_page)):
            d.go_to(key)
            self.assertIs(d.content_stack.currentWidget(), page, key)
            self.assertTrue(d._nav_buttons[key].isChecked(), key)

    def test_settings_is_a_real_page_since_step_12(self):
        self.dash.go_to("settings")
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.settings_page)

    def test_the_dashboard_notification_tile_opens_notifications(self):
        self.dash.home_page.navigate_requested.emit("notifications")
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.my_notifications_page)

    def test_my_requests_borrowings_and_reservations_are_unchanged(self):
        self.assertEqual(len(self.dash.my_requests_page.requests), 8)
        b = self.dash.my_borrowings_page
        self.assertEqual({r.status.value for r in b.current_requests + b.history_requests},
                         {"borrowed", "return_pending", "returned"})
        r = self.dash.my_reservations_page
        self.assertEqual(len(r.awaiting_requests + r.history_requests), 3)

    def test_request_status_rules_are_untouched(self):
        # Submitting and cancelling still produce exactly Pending -> Cancelled.
        request = self.requests.submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "k")[0]
        self.assertEqual(request.status.value, "pending")
        cancelled = self.requests.cancel_request(self.ana.id, request.request_id)
        self.assertEqual(cancelled.status.value, "cancelled")
        self.assertEqual([c.status.value for c in
                          self.requests.get_request(self.ana.id, request.request_id).status_history],
                         ["pending", "cancelled"])

    def test_my_list_still_has_its_calendar_code(self):
        import app.my_list_screen as my_list
        for name in ("AvailabilityCalendar", "PickupCalendarPopup", "PickupSchedule",
                     "validate_pickup", "RequestPreviewDialog"):
            self.assertTrue(hasattr(my_list, name), name)


if __name__ == "__main__":
    unittest.main()
