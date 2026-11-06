"""Stage 1A-2 tests: soft-dark Login/Registration styling is scoped to those two screens."""
import os
import re
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import design_tokens as tk  # noqa: E402
from app import theme  # noqa: E402


class AuthThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(theme.STYLESHEET)

    def test_every_auth_selector_is_scoped_to_the_login_screen(self):
        css = re.sub(r"/\*.*?\*/", "", theme.AUTH_STYLESHEET, flags=re.S)
        selectors = [s.strip() for block in re.findall(r"([^{}]+)\{", css)
                     for s in block.split(",")]
        self.assertGreater(len(selectors), 20)
        for selector in selectors:
            self.assertTrue(selector.startswith("QWidget#loginScreen"), selector)

    def test_auth_styles_are_not_in_the_global_stylesheet(self):
        self.assertNotIn(tk.COLOR_BG_SURFACE, theme.STYLESHEET)
        self.assertNotIn("QWidget#loginScreen QLineEdit", theme.STYLESHEET)

    def test_auth_styles_use_tokens_and_drop_the_bright_surfaces(self):
        css = theme.AUTH_STYLESHEET
        for token in (tk.COLOR_BG_APP, tk.COLOR_BG_SURFACE, tk.COLOR_ACCENT, tk.COLOR_FOCUS_RING):
            self.assertIn(token, css)
        for old in (theme.PINK, theme.CREAM, "3px solid"):
            self.assertNotIn(old, css)

    def test_both_screens_carry_the_auth_stylesheet_and_keep_their_signals(self):
        from app.login_screen import LoginScreen
        from app.register_screen import RegisterScreen
        login, register = LoginScreen(), RegisterScreen()
        self.assertEqual(login.styleSheet(), theme.AUTH_STYLESHEET)
        self.assertEqual(register.styleSheet(), theme.AUTH_STYLESHEET)
        seen = []
        login.login_requested.connect(lambda e, p: seen.append((e, p)))
        login.email_input.setText("a@csucc.edu.ph")
        login.password_input.setText("secret password")
        login.login_button.click()
        self.assertEqual(seen, [("a@csucc.edu.ph", "secret password")])
        reg_seen = []
        register.register_requested.connect(lambda *a: reg_seen.append(a))
        register.name_input.setText("Ana")
        register.student_id_input.setText("2024-0001")
        register.register_button.click()  # validation lives in AuthService, not the screen
        self.assertEqual(len(reg_seen), 1)
        self.assertEqual(reg_seen[0][0], "Ana")
        self.assertEqual(reg_seen[0][4], "2024-0001")

    def test_other_screens_do_not_receive_the_auth_stylesheet(self):
        from app.settings_screen import SettingsScreen
        from app.notifications_screen import NotificationsScreen
        for screen in (SettingsScreen(), NotificationsScreen([])):
            self.assertNotIn("loginScreen", screen.styleSheet())
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_demo_data
        dash = StudentDashboard(build_demo_data())
        self.assertNotIn("loginScreen", dash.styleSheet())


if __name__ == "__main__":
    unittest.main()
