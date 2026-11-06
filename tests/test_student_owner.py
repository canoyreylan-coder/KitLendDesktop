"""Step 13 tests: Student Owner applications (migration 5, service, Settings, dashboard).

Run from the project folder:   python -m unittest discover -s tests -p "test_student_owner.py" -v
Everything uses TEMPORARY databases; widget tests use Qt's invisible "offscreen" mode.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from app import database  # noqa: E402
from app.student_owner_service import (  # noqa: E402
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    StudentOwnerError,
    StudentOwnerService,
)
from app.workspace_service import WorkspaceService  # noqa: E402
from test_notifications import TempDbCase  # noqa: E402
from seed_helpers import AVAILABLE  # noqa: E402

REASON = "I have spare lab equipment and would like to help classmates."
ITEMS = "A scientific calculator and a soldering kit."


class OwnerCase(TempDbCase):
    def setUp(self):
        super().setUp()
        self.owner = StudentOwnerService(self.db)

    def apply(self, student=None, reason=REASON, items=ITEMS, agreed=True):
        return self.owner.submit_application((student or self.ana).id, reason, items, agreed)

    def review(self, application_id, status, note=""):
        """Simulates the FUTURE review system (the student app has no such method)."""
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE student_owner_applications SET status=?, review_note=?, "
                     "reviewed_at='2026-10-24T00:00:00+00:00' WHERE application_id=?",
                     (status, note, application_id))
        conn.commit()
        conn.close()


class SubmissionTests(OwnerCase):
    def test_submission_is_saved_as_pending_for_the_signed_in_student(self):
        app = self.apply()
        self.assertEqual(app.status, STATUS_PENDING)
        rows = self.query("SELECT student_id, status, reason, items_to_lend, rules_agreed "
                          "FROM student_owner_applications")
        self.assertEqual(rows, [(self.ana.id, "Pending", REASON, ITEMS, 1)])

    def test_it_survives_a_restart(self):
        app = self.apply()
        again = StudentOwnerService(self.db).current_application(self.ana.id)
        self.assertEqual(again.application_id, app.application_id)

    def test_no_application_means_none(self):
        self.assertIsNone(self.owner.current_application(self.ana.id))
        self.assertTrue(self.owner.can_apply(self.ana.id))

    def test_incomplete_forms_are_rejected_and_nothing_is_saved(self):
        for kwargs in ({"reason": ""}, {"reason": "   "}, {"reason": "too short"},
                       {"items": ""}, {"items": "x"}, {"agreed": False},
                       {"agreed": None}, {"agreed": 1}, {"agreed": "yes"},
                       {"reason": "r" * 1001}, {"items": "i" * 1001}):
            with self.assertRaises(StudentOwnerError, msg=str(kwargs)):
                self.apply(**kwargs)
        self.assertEqual(self.count("student_owner_applications"), 0)

    def test_invalid_students_are_rejected(self):
        for bad in (9999, None, "1", True):
            with self.assertRaises(StudentOwnerError):
                self.owner.submit_application(bad, REASON, ITEMS, True)
        self.assertEqual(self.count("student_owner_applications"), 0)

    def test_text_is_stored_as_plain_data(self):
        evil = "x'); DROP TABLE students;-- and more words"
        self.apply(reason=evil)
        self.assertEqual(self.count("students"), 2)
        self.assertEqual(self.owner.current_application(self.ana.id).reason, evil)


class DuplicateAndReapplyTests(OwnerCase):
    def test_second_submission_while_pending_is_refused(self):
        self.apply()
        with self.assertRaises(StudentOwnerError):
            self.apply()
        self.assertEqual(self.count("student_owner_applications"), 1)
        self.assertFalse(self.owner.can_apply(self.ana.id))

    def test_approved_students_cannot_apply_again(self):
        app = self.apply()
        self.review(app.application_id, STATUS_APPROVED)
        with self.assertRaises(StudentOwnerError):
            self.apply()
        self.assertFalse(self.owner.can_apply(self.ana.id))

    def test_rejected_students_can_apply_again_and_history_is_kept(self):
        first = self.apply()
        self.review(first.application_id, STATUS_REJECTED, "Please list real items.")
        self.assertTrue(self.owner.can_apply(self.ana.id))
        second = self.apply(reason="I now have a list of items I can lend safely.")
        self.assertNotEqual(first.application_id, second.application_id)
        self.assertEqual(second.status, STATUS_PENDING)
        history = self.owner.list_applications(self.ana.id)
        self.assertEqual([a.application_id for a in history],
                         [second.application_id, first.application_id])
        self.assertEqual(history[1].status, STATUS_REJECTED)
        self.assertEqual(history[1].review_note, "Please list real items.")
        self.assertFalse(self.owner.can_apply(self.ana.id))  # pending again

    def test_many_rejections_are_all_kept_with_unique_ids(self):
        ids = []
        for _ in range(3):
            app = self.apply()
            ids.append(app.application_id)
            self.review(app.application_id, STATUS_REJECTED, "no")
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(self.count("student_owner_applications"), 3)

    def test_the_database_itself_refuses_a_second_open_application(self):
        self.apply()
        conn = sqlite3.connect(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO student_owner_applications VALUES "
                         "('X1', ?, 'r', 'i', 1, '1', 'Pending', 't', NULL, '')",
                         (self.ana.id,))
        conn.close()

    def test_the_database_refuses_unknown_statuses_and_unagreed_rules(self):
        conn = sqlite3.connect(self.db)
        for status, agreed in (("Maybe", 1), ("Pending", 0)):
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO student_owner_applications VALUES "
                             "('X2', ?, 'r', 'i', ?, '1', ?, 't', NULL, '')",
                             (self.ana.id, agreed, status))
        conn.close()

    def test_students_are_independent(self):
        self.apply(self.ana)
        self.apply(self.ben)
        self.assertEqual(self.count("student_owner_applications"), 2)
        self.assertEqual(len(self.owner.list_applications(self.ana.id)), 1)
        self.assertEqual(self.owner.current_application(self.ben.id).student_id, self.ben.id)


class NoSelfServiceTests(OwnerCase):
    def test_the_service_has_no_way_to_change_a_status(self):
        public = [n for n in dir(StudentOwnerService) if not n.startswith("_")]
        for name in public:
            for word in ("approve", "reject", "review", "set_status", "update", "delete",
                         "cancel", "withdraw"):
                self.assertNotIn(word, name)

    def test_submitting_never_creates_a_workspace_or_changes_borrowing(self):
        self.apply()
        labels = [w.label for w in WorkspaceService().assigned_workspaces(self.ana.id)]
        self.assertEqual(labels, ["Student"])

    def test_normal_borrowing_works_in_every_status(self):
        from test_notifications import make_draft
        for i, status in enumerate((None, STATUS_PENDING, STATUS_REJECTED, STATUS_APPROVED)):
            student = self.auth.register(f"S{i} Test", f"s{i}@csucc.edu.ph",
                                         "password123", "password123",
                                         student_id_number=f"ID-S{i}")
            if status:
                app = self.owner.submit_application(student.id, REASON, ITEMS, True)
                if status != STATUS_PENDING:
                    self.review(app.application_id, status, "n")
            saved = self.requests.submit_requests(student.id, [make_draft(AVAILABLE[0])], f"k{i}")
            self.assertEqual(saved[0].status.value, "pending")

    def test_the_students_table_is_untouched(self):
        columns = [r[1] for r in self.query("PRAGMA table_info(students)")]
        self.assertEqual(columns, ["id", "full_name", "email", "password_hash", "salt",
                                   "iterations", "created_at"])


class MigrationTests(unittest.TestCase):
    def test_a_step_12_database_is_upgraded_without_touching_existing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "step12.db")
            conn = sqlite3.connect(db)
            conn.executescript(database.SCHEMA)
            conn.execute(database._MIGRATION_TABLE)
            for version, name, statements in database.MIGRATIONS:
                if version > 4:
                    continue
                for statement in statements:
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migrations VALUES (?, ?, 't')", (version, name))
            conn.execute("INSERT INTO students (full_name, email, password_hash, salt, "
                         "iterations, created_at) VALUES ('Old', 'old@csucc.edu.ph', 'h', 's', 1, 't')")
            conn.commit()
            before = conn.execute("SELECT * FROM students").fetchall()
            conn.close()
            for _ in range(2):  # twice: it must be repeatable
                database.connect(db).close()
            conn = sqlite3.connect(db)
            self.assertEqual(conn.execute("SELECT * FROM students").fetchall(), before)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schema_migrations "
                                          "WHERE version = 5").fetchone()[0], 1)
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM student_owner_applications").fetchone()[0], 0)
            conn.close()
            self.assertTrue(os.path.exists(db + ".before-v5.bak"))


class OwnerSettingsScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.settings_screen import SettingsScreen
        self.screen = SettingsScreen(stored_locally=True)

    def fake(self, status, note="", app_id="SO-1"):
        from datetime import datetime
        from app.student_owner_service import OwnerApplication
        return OwnerApplication(app_id, 1, REASON, ITEMS, status,
                                datetime.now().astimezone(), None, note)

    def test_form_has_the_three_required_inputs_and_emits_them(self):
        seen = []
        self.screen.owner_application_submitted.connect(lambda *a: seen.append(a))
        self.screen.owner_reason_input.setPlainText(REASON)
        self.screen.owner_items_input.setPlainText(ITEMS)
        self.screen.owner_agree_box.setChecked(True)
        self.screen.owner_submit_button.click()
        self.assertEqual(seen, [(REASON, ITEMS, True)])

    def test_agreement_starts_unticked(self):
        self.assertFalse(self.screen.owner_agree_box.isChecked())

    def test_status_text_and_form_visibility_follow_the_state(self):
        s = self.screen
        s.set_student_owner_state([], None)
        self.assertFalse(s.owner_form.isHidden())
        self.assertIn("not applied", s.owner_status_label.text())
        s.set_student_owner_state([self.fake(STATUS_PENDING)], "wait")
        self.assertTrue(s.owner_form.isHidden())
        self.assertEqual(s.owner_status_pill.text(), "Pending")
        s.set_student_owner_state([self.fake(STATUS_APPROVED)], "approved")
        self.assertEqual(s.owner_status_pill.text(), "Approved")
        self.assertTrue(s.owner_form.isHidden())
        s.set_student_owner_state([self.fake(STATUS_REJECTED, "Not enough detail")], None)
        self.assertEqual(s.owner_status_pill.text(), "Rejected")
        self.assertFalse(s.owner_form.isHidden())

    def test_there_is_no_approve_reject_or_status_button(self):
        self.screen.set_student_owner_state([self.fake(STATUS_PENDING)], "wait")
        texts = [b.text() for b in self.screen.findChildren(QPushButton)]
        self.assertEqual(sorted(texts), ["Change Password", "Submit Application"])

    def test_clear_forgets_the_applications_and_the_typed_text(self):
        self.screen.owner_reason_input.setPlainText("secret plan")
        self.screen.set_student_owner_state([self.fake(STATUS_PENDING)], "wait")
        self.screen.clear()
        self.assertEqual(self.screen.owner_reason_input.toPlainText(), "")
        self.assertEqual(self.screen.owner_application_ids, [])


class OwnerDashboardTests(OwnerCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def build(self, student):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        return StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests, auth_service=self.auth)

    def fill_and_submit(self, dash, reason=REASON, items=ITEMS, agree=True):
        page = dash.settings_page
        page.owner_reason_input.setPlainText(reason)
        page.owner_items_input.setPlainText(items)
        page.owner_agree_box.setChecked(agree)
        page.owner_submit_button.click()
        return page

    def test_full_flow_submit_shows_pending_and_blocks_a_duplicate(self):
        dash = self.build(self.ana)
        dash.go_to("settings")
        page = self.fill_and_submit(dash)
        self.assertEqual(self.count("student_owner_applications"), 1)
        self.assertEqual(page.owner_status_pill.text(), "Pending")
        self.assertTrue(page.owner_form.isHidden())
        self.assertIn("Pending", page.owner_message.text())
        self.assertEqual(page.workspace_names, ["Student"])

    def test_missing_agreement_shows_an_error_and_saves_nothing(self):
        dash = self.build(self.ana)
        dash.go_to("settings")
        page = self.fill_and_submit(dash, agree=False)
        self.assertEqual(self.count("student_owner_applications"), 0)
        self.assertIn("agree", page.owner_message.text())
        self.assertEqual(page.owner_reason_input.toPlainText(), REASON)  # not lost

    def test_status_is_shown_after_restart_and_only_for_the_right_student(self):
        self.apply(self.ana)
        dash = self.build(self.ana)
        dash.go_to("settings")
        self.assertEqual(dash.settings_page.owner_status_pill.text(), "Pending")
        other = self.build(self.ben)
        other.go_to("settings")
        self.assertEqual(other.settings_page.owner_application_ids, [])
        self.assertFalse(other.settings_page.owner_form.isHidden())

    def test_rejected_student_sees_the_reason_and_can_reapply(self):
        first = self.apply(self.ana)
        self.review(first.application_id, STATUS_REJECTED, "Please list real items.")
        dash = self.build(self.ana)
        dash.go_to("settings")
        page = dash.settings_page
        self.assertEqual(page.owner_status_pill.text(), "Rejected")
        self.assertFalse(page.owner_form.isHidden())
        from PySide6.QtWidgets import QLabel
        self.assertTrue(any("Please list real items." in l.text()
                            for l in page.findChildren(QLabel)))
        self.fill_and_submit(dash)
        self.assertEqual(self.count("student_owner_applications"), 2)
        self.assertEqual(len(page.owner_application_ids), 2)
        self.assertEqual(page.owner_status_pill.text(), "Pending")

    def test_logout_clears_the_owner_section(self):
        dash = self.build(self.ana)
        dash.go_to("settings")
        self.fill_and_submit(dash)
        dash.logout_requested.connect(lambda: None)
        dash._emit_exit()
        self.assertEqual(dash.settings_page.owner_application_ids, [])
        self.assertEqual(dash.settings_page.owner_reason_input.toPlainText(), "")

    def test_a_storage_failure_is_reported_safely(self):
        from unittest import mock
        dash = self.build(self.ana)
        dash.go_to("settings")
        with mock.patch.object(StudentOwnerService, "submit_application",
                               side_effect=RuntimeError("secret internals")):
            page = self.fill_and_submit(dash)
        self.assertNotIn("secret", page.owner_message.text())
        self.assertIn("not saved", page.owner_message.text())

    def test_demo_dashboard_has_no_owner_storage(self):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_demo_data
        dash = StudentDashboard(build_demo_data())
        self.assertFalse(dash.stores_owner_applications)


if __name__ == "__main__":
    unittest.main()
