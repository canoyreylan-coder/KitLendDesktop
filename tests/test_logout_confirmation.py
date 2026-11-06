"""Step 29A tests: Log Out asks for confirmation (Cancel keeps the student signed in)."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from test_notifications import TempDbCase  # noqa: E402

_app = QApplication.instance() or QApplication([])


class LogoutConfirmationTests(TempDbCase):
    def setUp(self):
        super().setUp()
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_demo_data, build_empty_data
        self.dash = StudentDashboard(
            build_empty_data(self.ana.full_name), signed_in_email=self.ana.email,
            student_id=self.ana.id, request_service=self.requests, auth_service=self.auth)
        self.demo = StudentDashboard(build_demo_data())
        self.seen = []
        self.dash.logout_requested.connect(lambda: self.seen.append("out"))

    def click_logout(self, choice):
        """Click the real Log Out icon and 'press' Cancel or Log Out in the real dialog."""
        def fake_exec(box):
            buttons = {b.text(): b for b in box.buttons()}
            box._test_choice = buttons[choice]
            box.setProperty("shown", True)
            self.last_box = box
            # emulate the user pressing that button
            box.clickedButton = lambda: buttons[choice]
            return 0
        with mock.patch.object(QMessageBox, "exec", fake_exec):
            self.dash.sidebar_exit_button.click()

    def test_log_out_shows_a_dialog_with_cancel_and_log_out_buttons(self):
        self.click_logout("Cancel")
        texts = [b.text() for b in self.last_box.buttons()]
        self.assertEqual(sorted(texts), ["Cancel", "Log Out"])
        self.assertEqual(self.last_box.defaultButton().text(), "Cancel")
        self.assertEqual(self.last_box.escapeButton().text(), "Cancel")

    def test_cancel_keeps_the_student_signed_in_and_changes_nothing(self):
        item = self.dash.catalog_page._cards[0].item
        self.dash.catalog_page._cards[0].bookmark_button.click()
        self.dash.settings_page.set_account("Ana Reyes", "ana@csucc.edu.ph")
        self.dash.go_to("catalog")
        self.click_logout("Cancel")
        self.assertEqual(self.seen, [])
        self.assertIn(item, self.dash._bookmarks)
        self.assertEqual(self.dash.settings_page.email_value.text(), "ana@csucc.edu.ph")
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.catalog_page)

    def test_log_out_button_logs_out_and_clears_session_data(self):
        self.dash.catalog_page._cards[0].bookmark_button.click()
        self.click_logout("Log Out")
        self.assertEqual(self.seen, ["out"])
        self.assertEqual(self.dash._bookmarks, [])
        self.assertEqual(self.dash.settings_page.email_value.text(), "")

    def test_cancel_can_be_followed_by_a_real_logout(self):
        self.click_logout("Cancel")
        self.click_logout("Log Out")
        self.assertEqual(self.seen, ["out"])

    def test_the_dialog_is_asked_exactly_once_per_click(self):
        with mock.patch.object(type(self.dash), "_confirm_logout", return_value=False) as ask:
            self.dash.sidebar_exit_button.click()
        ask.assert_called_once()
        self.assertEqual(self.seen, [])

    def test_demo_back_to_login_has_no_confirmation(self):
        seen = []
        self.demo.exit_demo_requested.connect(lambda: seen.append("exit"))
        with mock.patch.object(type(self.demo), "_confirm_logout") as ask:
            self.demo.sidebar_exit_button.click()
        ask.assert_not_called()
        self.assertEqual(seen, ["exit"])

    def test_while_editing_the_sidebar_log_out_only_selects_and_asks_nothing(self):
        self.dash.go_to("settings")
        self.dash.settings_page.sidebar_edit_button.click()
        _app.processEvents()
        self.assertTrue(self.dash.sidebar_rail.editing)
        with mock.patch.object(type(self.dash), "_confirm_logout") as ask:
            self.dash.sidebar_exit_button.click()
        ask.assert_not_called()
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()
