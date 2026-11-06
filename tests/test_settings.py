"""Step 12 tests: Settings (account info, password change, notification preferences,
workspaces, migration 4 and regressions).

Run from the project folder:   python -m unittest discover -s tests -v

Everything uses TEMPORARY databases. Groups 1-5 need no window; groups 6-7 open widgets
in Qt's invisible "offscreen" mode.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import database  # noqa: E402
from app.auth_service import AuthError, AuthService  # noqa: E402
from app.notification_service import (  # noqa: E402
    EVENT_REQUEST_CANCELLED,
    EVENT_REQUEST_SUBMITTED,
    NotificationError,
    NotificationService,
)
from app.request_service import RequestService  # noqa: E402
from app.workspace_service import (  # noqa: E402
    WORKSPACE_CATALOG,
    WORKSPACE_STUDENT,
    WorkspaceService,
)
from test_notifications import PW, TempDbCase, make_draft  # noqa: E402
from seed_helpers import AVAILABLE, seed_samples  # noqa: E402

NEW_PW = "brand new pass"


# ======================================================================
# 1. ACCOUNT INFORMATION (service side)
# ======================================================================
class AccountInformationTests(TempDbCase):
    def test_get_account_returns_the_students_own_name_and_email(self):
        account = self.auth.get_account(self.ana.id)
        self.assertEqual((account.full_name, account.email), ("Ana Reyes", "ana@csucc.edu.ph"))
        self.assertEqual(self.auth.get_account(self.ben.id).email, "ben@csucc.edu.ph")

    def test_account_contains_no_password_data(self):
        account = self.auth.get_account(self.ana.id)
        self.assertFalse(hasattr(account, "password_hash"))
        self.assertFalse(hasattr(account, "salt"))

    def test_unknown_or_invalid_student_is_rejected(self):
        for bad in (9999, None, "1", True):
            with self.assertRaises(AuthError):
                self.auth.get_account(bad)


# ======================================================================
# 2. PASSWORD VERIFICATION AND UPDATE
# ======================================================================
class ChangePasswordTests(TempDbCase):
    PW_ROW = "SELECT password_hash, salt, iterations FROM students WHERE id = ?"

    def change(self, current=None, new=NEW_PW, confirm=None, student=None):
        student = student or self.ana
        return self.auth.change_password(
            student.id, PW if current is None else current, new,
            new if confirm is None else confirm)

    def test_correct_current_password_updates_it(self):
        self.change()
        self.auth.login("ana@csucc.edu.ph", NEW_PW)  # new password works

    def test_old_password_no_longer_works(self):
        self.change()
        with self.assertRaises(AuthError):
            self.auth.login("ana@csucc.edu.ph", PW)

    def test_wrong_current_password_is_rejected_and_changes_nothing(self):
        before = self.query(self.PW_ROW, (self.ana.id,))
        with self.assertRaisesRegex(AuthError, "current password is incorrect"):
            self.change(current="not my password")
        self.assertEqual(self.query(self.PW_ROW, (self.ana.id,)), before)
        self.auth.login("ana@csucc.edu.ph", PW)  # old one still fine

    def test_mismatched_confirmation_is_rejected(self):
        before = self.query(self.PW_ROW, (self.ana.id,))
        with self.assertRaisesRegex(AuthError, "do not match"):
            self.change(confirm="something else")
        self.assertEqual(self.query(self.PW_ROW, (self.ana.id,)), before)

    def test_invalid_new_passwords_are_rejected(self):
        before = self.query(self.PW_ROW, (self.ana.id,))
        for bad in ("short", "x" * 129):
            with self.assertRaises(AuthError):
                self.change(new=bad)
        self.assertEqual(self.query(self.PW_ROW, (self.ana.id,)), before)

    def test_empty_fields_are_rejected(self):
        for current, new, confirm in (("", NEW_PW, NEW_PW), (PW, "", ""), (PW, NEW_PW, "")):
            with self.assertRaises(AuthError):
                self.auth.change_password(self.ana.id, current, new, confirm)

    def test_new_password_must_differ_from_the_current_one(self):
        with self.assertRaisesRegex(AuthError, "different"):
            self.change(new=PW)

    def test_plaintext_is_never_stored_and_hash_uses_a_new_salt(self):
        old_hash, old_salt, _ = self.query(self.PW_ROW, (self.ana.id,))[0]
        self.change()
        new_hash, new_salt, iterations = self.query(self.PW_ROW, (self.ana.id,))[0]
        self.assertNotEqual(new_hash, old_hash)
        self.assertNotEqual(new_salt, old_salt)
        self.assertEqual(iterations, 310_000)
        conn = sqlite3.connect(self.db)
        dump = "\n".join(conn.iterdump())
        conn.close()
        self.assertNotIn(NEW_PW, dump)
        self.assertNotIn(PW, dump)

    def test_error_messages_never_contain_a_password(self):
        for current, new, confirm in (("wrong pass 1", NEW_PW, NEW_PW), (PW, NEW_PW, "typo typo")):
            with self.assertRaises(AuthError) as ctx:
                self.auth.change_password(self.ana.id, current, new, confirm)
            for secret in (current, new, confirm, PW):
                self.assertNotIn(secret, str(ctx.exception))

    def test_nothing_is_written_to_the_log_streams(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), self.assertLogs(level="DEBUG") as logs:
            import logging
            logging.getLogger("kitlend-test").debug("sentinel")  # keeps assertLogs satisfied
            self.change()
        text = out.getvalue() + err.getvalue() + "".join(logs.output)
        self.assertNotIn(NEW_PW, text)
        self.assertNotIn(PW, text)

    def test_only_the_signed_in_student_is_changed(self):
        self.change()
        self.auth.login("ben@csucc.edu.ph", PW)  # Ben untouched
        with self.assertRaises(AuthError):
            self.auth.login("ben@csucc.edu.ph", NEW_PW)

    def test_another_students_current_password_cannot_be_used(self):
        # Ben's password is also PW here, so give him a different one first.
        self.auth.change_password(self.ben.id, PW, "ben secret 99", "ben secret 99")
        with self.assertRaises(AuthError):
            self.auth.change_password(self.ana.id, "ben secret 99", NEW_PW, NEW_PW)
        self.auth.login("ana@csucc.edu.ph", PW)

    def test_invalid_student_id_is_rejected(self):
        for bad in (9999, None, True):
            with self.assertRaises(AuthError):
                self.auth.change_password(bad, PW, NEW_PW, NEW_PW)

    def test_password_survives_a_restart(self):
        self.change()
        restarted = AuthService(self.db)  # brand-new service objects = app restart
        restarted.login("ana@csucc.edu.ph", NEW_PW)
        with self.assertRaises(AuthError):
            restarted.login("ana@csucc.edu.ph", PW)

    def test_password_can_be_changed_twice(self):
        self.change()
        self.auth.change_password(self.ana.id, NEW_PW, "third password", "third password")
        self.auth.login("ana@csucc.edu.ph", "third password")

    def test_name_email_and_other_data_are_untouched(self):
        self.submit(self.ana, AVAILABLE[0], "k1")
        before = (self.query("SELECT id, full_name, email, created_at FROM students ORDER BY id"),
                  self.count(), self.count("borrow_requests"))
        self.change()
        after = (self.query("SELECT id, full_name, email, created_at FROM students ORDER BY id"),
                 self.count(), self.count("borrow_requests"))
        self.assertEqual(before, after)

    def test_a_database_failure_changes_nothing_and_is_user_friendly(self):
        before = self.query(self.PW_ROW, (self.ana.id,))
        with mock.patch.object(AuthService, "_connect", side_effect=database.DatabaseError("x")):
            with self.assertRaises(AuthError):
                self.change()
        self.assertEqual(self.query(self.PW_ROW, (self.ana.id,)), before)


# ======================================================================
# 3. NOTIFICATION PREFERENCES: persistence
# ======================================================================
class PreferencePersistenceTests(TempDbCase):
    def test_everything_defaults_to_on_without_any_saved_row(self):
        self.assertEqual(self.notes.get_preferences(self.ana.id),
                         {EVENT_REQUEST_SUBMITTED: True, EVENT_REQUEST_CANCELLED: True})
        self.assertEqual(self.count("notification_preferences"), 0)

    def test_a_choice_is_saved_and_survives_a_restart(self):
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_CANCELLED, False)
        restarted = NotificationService(self.db)
        self.assertEqual(restarted.get_preferences(self.ana.id),
                         {EVENT_REQUEST_SUBMITTED: True, EVENT_REQUEST_CANCELLED: False})

    def test_a_choice_can_be_turned_back_on_without_duplicate_rows(self):
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, False)
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, True)
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, True)
        self.assertTrue(self.notes.get_preferences(self.ana.id)[EVENT_REQUEST_SUBMITTED])
        self.assertEqual(self.count("notification_preferences"), 1)

    def test_invalid_input_is_rejected(self):
        for args in ((self.ana.id, "request_approved", True), (self.ana.id, "", True),
                     (self.ana.id, EVENT_REQUEST_SUBMITTED, "yes"),
                     (self.ana.id, EVENT_REQUEST_SUBMITTED, 1),
                     (None, EVENT_REQUEST_SUBMITTED, True), (True, EVENT_REQUEST_SUBMITTED, True)):
            with self.assertRaises(NotificationError):
                self.notes.set_preference(*args)
        self.assertEqual(self.count("notification_preferences"), 0)

    def test_unknown_student_cannot_get_a_preference_row(self):
        with self.assertRaises(NotificationError):
            self.notes.set_preference(9999, EVENT_REQUEST_SUBMITTED, False)
        self.assertEqual(self.count("notification_preferences"), 0)


# ======================================================================
# 4. NOTIFICATION PREFERENCES: enforcement, isolation, duplicates, counts
# ======================================================================
class PreferenceEnforcementTests(TempDbCase):
    def test_submitted_off_creates_no_notification_but_the_request_is_saved(self):
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, False)
        request = self.submit(self.ana, AVAILABLE[0], "k1")
        self.assertEqual(self.notes.list_notifications(self.ana.id), [])
        self.assertEqual(self.notes.unread_count(self.ana.id), 0)
        self.assertEqual(len(self.requests.list_requests(self.ana.id)), 1)
        self.assertEqual(request.status.value, "pending")

    def test_cancelled_off_creates_no_notification_but_the_cancellation_happens(self):
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_CANCELLED, False)
        request = self.submit(self.ana, AVAILABLE[0], "k1")  # submitted is still ON
        self.requests.cancel_request(self.ana.id, request.request_id)
        titles = [n.title for n in self.notes.list_notifications(self.ana.id)]
        self.assertEqual(titles, ["Request submitted"])
        self.assertEqual(self.requests.list_requests(self.ana.id)[0].status.value, "cancelled")

    def test_each_type_is_independent(self):
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, False)
        request = self.submit(self.ana, AVAILABLE[0], "k1")
        self.requests.cancel_request(self.ana.id, request.request_id)  # cancelled still ON
        self.assertEqual([n.event_type for n in self.notes.list_notifications(self.ana.id)],
                         [EVENT_REQUEST_CANCELLED])

    def test_turning_a_type_off_keeps_existing_notifications_and_read_state(self):
        first = self.submit(self.ana, AVAILABLE[0], "k1")
        read_one = self.notes.list_notifications(self.ana.id)[0]
        self.notes.mark_read(self.ana.id, read_one.id)
        self.submit(self.ana, AVAILABLE[1], "k2")
        before = self.query("SELECT * FROM notifications ORDER BY id")
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, False)
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_CANCELLED, False)
        self.assertEqual(self.query("SELECT * FROM notifications ORDER BY id"), before)
        self.assertEqual(self.notes.unread_count(self.ana.id), 1)
        self.assertEqual(first.request_id, self.notes.list_notifications(self.ana.id)[-1].request_id)

    def test_turning_a_type_back_on_applies_to_future_events_only(self):
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, False)
        self.submit(self.ana, AVAILABLE[0], "k1")  # skipped while off
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, True)
        self.assertEqual(self.notes.list_notifications(self.ana.id), [])  # nothing back-filled
        self.submit(self.ana, AVAILABLE[1], "k2")
        self.assertEqual(len(self.notes.list_notifications(self.ana.id)), 1)

    def test_preferences_are_per_student(self):
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, False)
        self.submit(self.ana, AVAILABLE[0], "k1")
        self.submit(self.ben, AVAILABLE[1], "k2")
        self.assertEqual(self.notes.list_notifications(self.ana.id), [])
        self.assertEqual(len(self.notes.list_notifications(self.ben.id)), 1)
        self.assertTrue(self.notes.get_preferences(self.ben.id)[EVENT_REQUEST_SUBMITTED])
        self.assertFalse(self.notes.get_preferences(self.ana.id)[EVENT_REQUEST_SUBMITTED])

    def test_an_off_choice_survives_logout_and_restart_and_still_applies(self):
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_SUBMITTED, False)
        self.auth.login("ana@csucc.edu.ph", PW)  # "log in again"
        RequestService(self.db).submit_requests(self.ana.id, [make_draft(AVAILABLE[0])], "k9")
        self.assertEqual(NotificationService(self.db).list_notifications(self.ana.id), [])

    def test_no_duplicates_with_preferences_on_and_a_retried_submission(self):
        draft = [make_draft(AVAILABLE[0])]
        self.requests.submit_requests(self.ana.id, draft, "same")
        self.requests.submit_requests(self.ana.id, draft, "same")  # retry of the same batch
        self.assertEqual(len(self.notes.list_notifications(self.ana.id)), 1)

    def test_unread_count_always_matches_the_real_unread_rows(self):
        a = self.submit(self.ana, AVAILABLE[0], "k1")
        self.notes.set_preference(self.ana.id, EVENT_REQUEST_CANCELLED, False)
        self.requests.cancel_request(self.ana.id, a.request_id)
        self.submit(self.ana, AVAILABLE[1], "k2")
        real = self.query("SELECT COUNT(*) FROM notifications WHERE student_id = ? "
                          "AND read_at IS NULL", (self.ana.id,))[0][0]
        self.assertEqual(self.notes.unread_count(self.ana.id), real)
        self.assertEqual(real, 2)

    def test_a_failed_submission_still_leaves_no_notification_and_no_request(self):
        self.submit(self.ana, AVAILABLE[0], "k1")
        with self.assertRaises(Exception):  # same item again while active -> rejected
            self.submit(self.ana, AVAILABLE[0], "k2")
        self.assertEqual(len(self.notes.list_notifications(self.ana.id)), 1)



# ======================================================================
# 5. SAFE MIGRATION (version 4) AND WORKSPACES
# ======================================================================
class PreferenceMigrationTests(unittest.TestCase):
    """A Step 11 database (accounts, requests, notifications) must survive migration 4."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "step11.db")
        conn = sqlite3.connect(self.db)
        conn.executescript(database.SCHEMA)
        conn.execute(database._MIGRATION_TABLE)
        for version, name, statements in database.MIGRATIONS:
            if version > 3:
                continue
            for statement in statements:
                conn.execute(statement)
            conn.execute("INSERT INTO schema_migrations VALUES (?, ?, ?)",
                         (version, name, "2026-10-01T00:00:00+00:00"))
        conn.execute("INSERT INTO students (full_name, email, password_hash, salt, iterations, "
                     "created_at) VALUES ('Old Student', 'old@csucc.edu.ph', 'h', 's', 1, "
                     "'2026-10-01T00:00:00+00:00')")
        conn.execute("INSERT INTO notifications (student_id, event_type, title, message, "
                     "request_id, dedupe_key, created_at, read_at) VALUES "
                     "(1, 'request_submitted', 'Request submitted', 'm', 'R1', 'k', "
                     "'2026-10-02T00:00:00+00:00', NULL)")
        conn.commit()
        conn.close()
        seed_samples(self.db, 1)
        self.before = self.snapshot()

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self):
        conn = sqlite3.connect(self.db)
        try:
            return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()
                    for t in ("students", "borrow_requests", "borrow_request_history",
                              "notifications")}
        finally:
            conn.close()

    def test_existing_data_is_unchanged_and_the_table_is_created(self):
        database.connect(self.db).close()
        self.assertEqual(self.snapshot(), self.before)
        conn = sqlite3.connect(self.db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        self.assertIn("notification_preferences", tables)

    def test_migration_is_recorded_once_and_is_repeatable(self):
        for _ in range(3):
            database.connect(self.db).close()
        conn = sqlite3.connect(self.db)
        versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY 1")]
        conn.close()
        self.assertEqual(versions, [m[0] for m in database.MIGRATIONS])  # every migration, once each
        self.assertEqual(self.snapshot(), self.before)

    def test_old_accounts_start_with_everything_on_and_nothing_is_pre_written(self):
        service = NotificationService(self.db)
        self.assertEqual(service.get_preferences(1),
                         {EVENT_REQUEST_SUBMITTED: True, EVENT_REQUEST_CANCELLED: True})
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM notification_preferences").fetchone()[0], 0)
        conn.close()

    def test_old_unread_notification_still_counts_after_migration(self):
        self.assertEqual(NotificationService(self.db).unread_count(1), 1)

    def test_one_time_safety_copy_is_taken_before_the_new_migration(self):
        database.connect(self.db).close()
        self.assertTrue(os.path.exists(f"{self.db}.before-v4.bak"))

    def test_the_students_table_columns_are_not_changed(self):
        database.connect(self.db).close()
        conn = sqlite3.connect(self.db)
        columns = [r[1] for r in conn.execute("PRAGMA table_info(students)")]
        conn.close()
        self.assertEqual(columns, ["id", "full_name", "email", "password_hash", "salt",
                                   "iterations", "created_at"])

    def test_a_failing_migration_changes_nothing(self):
        broken = database.MIGRATIONS + [(5, "broken", ["CREATE TABLE ok_t (a)", "NOT SQL"])]
        with mock.patch.object(database, "MIGRATIONS", broken):
            with self.assertRaises(database.DatabaseError):
                database.connect(self.db)
        conn = sqlite3.connect(self.db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        self.assertNotIn("ok_t", tables)
        self.assertEqual(self.snapshot(), self.before)


class WorkspaceServiceTests(unittest.TestCase):
    def test_a_registered_student_only_has_the_student_workspace(self):
        spaces = WorkspaceService().assigned_workspaces(1)
        self.assertEqual([w.key for w in spaces], [WORKSPACE_STUDENT])
        self.assertTrue(spaces[0].is_default)

    def test_invalid_account_ids_get_no_workspace(self):
        for bad in (None, "1", True):
            self.assertEqual(WorkspaceService().assigned_workspaces(bad), [])

    def test_the_catalog_names_all_six_workspaces_but_only_student_is_default(self):
        self.assertEqual(len(WORKSPACE_CATALOG), 6)
        self.assertEqual([k for k, w in WORKSPACE_CATALOG.items() if w.is_default],
                         [WORKSPACE_STUDENT])


# ======================================================================
# 6. THE SETTINGS SCREEN ITSELF
# ======================================================================
class SettingsScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.settings_screen import SettingsScreen
        self.screen = SettingsScreen(stored_locally=True)

    def test_account_details_are_read_only_labels(self):
        from PySide6.QtWidgets import QLineEdit, QSpinBox
        self.screen.set_account("Ana Reyes", "ana@csucc.edu.ph")
        self.assertEqual(self.screen.name_value.text(), "Ana Reyes")
        self.assertEqual(self.screen.email_value.text(), "ana@csucc.edu.ph")
        # (the sidebar editor's number boxes contain their own internal line edits)
        editable = {w for w in self.screen.findChildren(QLineEdit)
                    if not isinstance(w.parent(), QSpinBox)}
        self.assertEqual(editable, {self.screen.current_input, self.screen.new_input,
                                    self.screen.confirm_input,
                                    self.screen.student_id_input})  # no email/name edit box

    def test_password_boxes_hide_what_is_typed(self):
        from PySide6.QtWidgets import QLineEdit
        for box in (self.screen.current_input, self.screen.new_input, self.screen.confirm_input):
            self.assertEqual(box.echoMode(), QLineEdit.Password)

    def test_clicking_change_password_emits_the_three_values(self):
        seen = []
        self.screen.change_password_requested.connect(lambda *a: seen.append(a))
        self.screen.current_input.setText("a")
        self.screen.new_input.setText("b")
        self.screen.confirm_input.setText("c")
        self.screen.password_button.click()
        self.assertEqual(seen, [("a", "b", "c")])

    def test_result_messages_clear_the_password_boxes(self):
        for box in (self.screen.current_input, self.screen.new_input, self.screen.confirm_input):
            box.setText("secret")
        self.screen.show_password_result("Nope", error=True)
        self.assertEqual([self.screen.current_input.text(), self.screen.new_input.text(),
                          self.screen.confirm_input.text()], ["", "", ""])
        self.assertEqual(self.screen.password_message.text(), "Nope")
        self.assertFalse(self.screen.password_message.isHidden())

    def test_toggling_a_preference_emits_but_loading_saved_values_does_not(self):
        seen = []
        self.screen.preference_changed.connect(lambda e, v: seen.append((e, v)))
        self.screen.set_preferences({EVENT_REQUEST_SUBMITTED: False, EVENT_REQUEST_CANCELLED: True})
        self.assertEqual(seen, [])
        self.assertEqual(self.screen.preferences(),
                         {EVENT_REQUEST_SUBMITTED: False, EVENT_REQUEST_CANCELLED: True})
        self.screen.preference_boxes[EVENT_REQUEST_CANCELLED].click()
        self.assertEqual(seen, [(EVENT_REQUEST_CANCELLED, False)])

    def test_only_the_two_supported_preferences_are_offered(self):
        self.assertEqual(set(self.screen.preference_boxes),
                         {EVENT_REQUEST_SUBMITTED, EVENT_REQUEST_CANCELLED})

    def test_workspaces_shows_exactly_what_it_is_given_and_nothing_more(self):
        self.screen.set_workspaces(WorkspaceService().assigned_workspaces(1))
        self.assertEqual(self.screen.workspace_names, ["Student"])
        from PySide6.QtWidgets import QPushButton
        texts = [b.text() for b in self.screen.findChildren(QPushButton)]
        for forbidden in ("Switch", "Admin", "Lender", "Moderator", "Super"):
            self.assertFalse(any(forbidden in t for t in texts), forbidden)

    def test_clear_forgets_the_account_and_any_typed_passwords(self):
        self.screen.set_account("Ana Reyes", "ana@csucc.edu.ph")
        self.screen.new_input.setText("secret")
        self.screen.clear()
        self.assertEqual(self.screen.name_value.text(), "")
        self.assertEqual(self.screen.email_value.text(), "")
        self.assertEqual(self.screen.new_input.text(), "")


# ======================================================================
# 7. INTEGRATION: sidebar, StudentDashboard, MainWindow, isolation, regressions
# ======================================================================
class SettingsDashboardTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        self.build = lambda student, **kw: StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests,
            auth_service=self.auth, **kw)

    def test_sidebar_settings_opens_the_real_page_inside_the_same_stack(self):
        dash = self.build(self.ana)
        dash.go_to("settings")
        self.assertIs(dash.content_stack.currentWidget(), dash.settings_page)
        self.assertTrue(dash._nav_buttons["settings"].isChecked())
        self.assertEqual(dash.content_stack.indexOf(dash.settings_page) >= 0, True)

    def test_page_shows_the_signed_in_students_own_account(self):
        dash = self.build(self.ben)
        dash.go_to("settings")
        self.assertEqual(dash.settings_page.name_value.text(), "Ben Cruz")
        self.assertEqual(dash.settings_page.email_value.text(), "ben@csucc.edu.ph")

    def test_dashboard_without_an_explicit_auth_service_still_works(self):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        dash = StudentDashboard(build_empty_data("Ana Reyes"), signed_in_email=self.ana.email,
                                student_id=self.ana.id, request_service=self.requests)
        dash.go_to("settings")
        self.assertEqual(dash.settings_page.email_value.text(), "ana@csucc.edu.ph")

    def test_changing_the_password_through_the_page_works_and_shows_success(self):
        dash = self.build(self.ana)
        page = dash.settings_page
        page.current_input.setText(PW)
        page.new_input.setText(NEW_PW)
        page.confirm_input.setText(NEW_PW)
        page.password_button.click()
        self.assertIn("Password changed", page.password_message.text())
        self.assertEqual(page.new_input.text(), "")
        AuthService(self.db).login("ana@csucc.edu.ph", NEW_PW)
        with self.assertRaises(AuthError):
            AuthService(self.db).login("ana@csucc.edu.ph", PW)

    def test_wrong_current_password_shows_an_error_and_changes_nothing(self):
        dash = self.build(self.ana)
        page = dash.settings_page
        page.current_input.setText("wrong wrong")
        page.new_input.setText(NEW_PW)
        page.confirm_input.setText(NEW_PW)
        page.password_button.click()
        self.assertIn("incorrect", page.password_message.text())
        self.assertEqual(page.current_input.text(), "")
        AuthService(self.db).login("ana@csucc.edu.ph", PW)

    def test_unexpected_storage_errors_show_a_safe_message(self):
        dash = self.build(self.ana)
        page = dash.settings_page
        with mock.patch.object(AuthService, "change_password", side_effect=RuntimeError("boom")):
            page.current_input.setText(PW)
            page.new_input.setText(NEW_PW)
            page.confirm_input.setText(NEW_PW)
            page.password_button.click()
        self.assertNotIn("boom", page.password_message.text())
        self.assertIn("not changed", page.password_message.text())

    def test_preference_toggle_is_saved_and_applied_to_the_next_request(self):
        dash = self.build(self.ana)
        dash.settings_page.preference_boxes[EVENT_REQUEST_SUBMITTED].click()  # turn OFF
        self.assertFalse(self.notes.get_preferences(self.ana.id)[EVENT_REQUEST_SUBMITTED])
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        self.assertEqual(dash.my_notifications_page.notifications, [])
        self.assertEqual(dash.home_page.notification_stat.number_label.text(), "0")
        self.assertEqual(len(dash.my_requests_page.requests), 1)

    def test_turning_off_does_not_delete_or_hide_existing_notifications(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        dash.settings_page.preference_boxes[EVENT_REQUEST_SUBMITTED].click()
        dash.go_to("notifications")
        self.assertEqual(len(dash.my_notifications_page.notifications), 1)
        self.assertEqual(dash.home_page.notification_stat.number_label.text(), "1")

    def test_saved_preferences_appear_in_a_new_dashboard_after_restart(self):
        first = self.build(self.ana)
        first.settings_page.preference_boxes[EVENT_REQUEST_CANCELLED].click()
        second = self.build(self.ana)  # logout + login = a fresh dashboard
        second.go_to("settings")
        self.assertEqual(second.settings_page.preferences(),
                         {EVENT_REQUEST_SUBMITTED: True, EVENT_REQUEST_CANCELLED: False})

    def test_a_failed_save_is_reported_and_the_box_shows_the_database_value(self):
        dash = self.build(self.ana)
        with mock.patch.object(NotificationService, "set_preference",
                               side_effect=NotificationError("Could not save.")):
            dash.settings_page.preference_boxes[EVENT_REQUEST_SUBMITTED].click()
        self.assertTrue(dash.settings_page.preferences()[EVENT_REQUEST_SUBMITTED])
        self.assertTrue(self.notes.get_preferences(self.ana.id)[EVENT_REQUEST_SUBMITTED])

    def test_two_dashboards_keep_separate_accounts_and_preferences(self):
        ana, ben = self.build(self.ana), self.build(self.ben)
        ana.settings_page.preference_boxes[EVENT_REQUEST_SUBMITTED].click()
        ben.go_to("settings")
        self.assertTrue(ben.settings_page.preferences()[EVENT_REQUEST_SUBMITTED])
        self.assertEqual(ben.settings_page.email_value.text(), "ben@csucc.edu.ph")
        ben._submit_drafts([make_draft(AVAILABLE[0])], "kb")
        ana._submit_drafts([make_draft(AVAILABLE[1])], "ka")
        self.assertEqual(len(ben.my_notifications_page.notifications), 1)
        self.assertEqual(len(ana.my_notifications_page.notifications), 0)

    def test_logout_clears_the_settings_page(self):
        dash = self.build(self.ana)
        dash.go_to("settings")
        dash.settings_page.new_input.setText("typed")
        seen = []
        dash.logout_requested.connect(lambda: seen.append(True))
        with mock.patch.object(type(dash), "_confirm_logout", return_value=True):
            dash.sidebar_exit_button.click()  # the single Log Out control (Stage 1C)
        self.assertEqual(seen, [True])
        self.assertEqual(dash.settings_page.email_value.text(), "")
        self.assertEqual(dash.settings_page.new_input.text(), "")

    def test_page_lists_only_the_student_workspace_and_no_extra_sidebar_pages(self):
        from app.dashboard_screen import NAV_ITEMS
        dash = self.build(self.ana)
        dash.go_to("settings")
        self.assertEqual(dash.settings_page.workspace_names, ["Student"])
        self.assertEqual([i.key for i in NAV_ITEMS],
                         ["dashboard", "catalog", "my_list", "my_requests", "borrowings",
                          "reservations", "notifications", "settings"])

    def test_the_demo_dashboard_still_has_only_a_placeholder_for_settings(self):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_demo_data
        demo = StudentDashboard(build_demo_data())
        demo.go_to("settings")
        self.assertIs(demo.content_stack.currentWidget(), demo.placeholder_page)

    def test_mainwindow_full_flow_login_change_password_logout_login_again(self):
        from app.main_window import MainWindow
        window = MainWindow(auth_service=self.auth, request_service=self.requests,
                            notification_service=self.notes)
        window.handle_login("ana@csucc.edu.ph", PW)
        dash = window.dashboard
        self.assertIsNotNone(dash)
        dash.go_to("settings")
        page = dash.settings_page
        page.current_input.setText(PW)
        page.new_input.setText(NEW_PW)
        page.confirm_input.setText(NEW_PW)
        page.password_button.click()
        window.handle_logout()
        self.assertIsNone(window.dashboard)
        window.handle_login("ana@csucc.edu.ph", PW)  # old password: refused
        self.assertIsNone(window.dashboard)
        window.handle_login("ana@csucc.edu.ph", NEW_PW)
        self.assertEqual(window.dashboard.settings_page.preferences()[EVENT_REQUEST_SUBMITTED], True)
        self.assertEqual(window.current_student.email, "ana@csucc.edu.ph")


class SettingsRegressionTests(TempDbCase):
    """Everything from Steps 8C-11 still works with Settings added."""

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        seed_samples(self.db, self.ana.id)
        self.dash = StudentDashboard(build_empty_data("Ana Reyes"), signed_in_email=self.ana.email,
                                     student_id=self.ana.id, request_service=self.requests,
                                     auth_service=self.auth)

    def test_every_sidebar_page_opens_in_the_same_stack(self):
        d = self.dash
        pages = (("dashboard", d.home_page), ("catalog", d.catalog_page),
                 ("my_list", d.my_list_page), ("my_requests", d.my_requests_page),
                 ("borrowings", d.my_borrowings_page), ("reservations", d.my_reservations_page),
                 ("notifications", d.my_notifications_page), ("settings", d.settings_page))
        for key, page in pages:
            d.go_to(key)
            self.assertIs(d.content_stack.currentWidget(), page, key)
            self.assertTrue(d._nav_buttons[key].isChecked(), key)

    def test_requests_borrowings_and_reservations_are_unchanged(self):
        self.assertEqual(len(self.dash.my_requests_page.requests), 8)
        b = self.dash.my_borrowings_page
        self.assertEqual({r.status.value for r in b.current_requests + b.history_requests},
                         {"borrowed", "return_pending", "returned"})

    def test_submit_and_cancel_still_create_their_notifications_by_default(self):
        d = self.dash
        saved = d._submit_drafts([make_draft(AVAILABLE[0])], "reg1")
        self.assertEqual([n.title for n in d.my_notifications_page.notifications],
                         ["Request submitted"])
        d._cancel_request(saved[0], None)
        self.assertEqual(sorted(n.title for n in d.my_notifications_page.notifications),
                         ["Request cancelled", "Request submitted"])
        self.assertEqual(d.home_page.notification_stat.number_label.text(), "2")

    def test_mark_read_still_works_and_counts_stay_in_sync(self):
        d = self.dash
        d._submit_drafts([make_draft(AVAILABLE[0])], "reg2")
        note = d.my_notifications_page.notifications[0]
        d._on_notification_mark_read(note.id)
        self.assertEqual(d.home_page.notification_stat.number_label.text(), "0")
        self.assertEqual(self.notes.unread_count(self.ana.id), 0)

    def test_registration_and_login_are_unchanged(self):
        with self.assertRaises(AuthError):
            self.auth.register("X", "x@gmail.com", PW, PW, student_id_number="ID-X")
        with self.assertRaises(AuthError):
            self.auth.register("Ana Again", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.assertEqual(self.auth.login("ana@csucc.edu.ph", PW).id, self.ana.id)
        with self.assertRaises(AuthError):
            self.auth.login("ana@csucc.edu.ph", "wrong")


if __name__ == "__main__":
    unittest.main()
