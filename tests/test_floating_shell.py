"""Step 30A tests: the floating app container (sizing rules, container, sidebar inside it).

Group 1 needs no window. Group 2 opens the real dashboard in Qt's invisible "offscreen" mode
(skipped when PySide6 is missing).
Run:  python -m unittest discover -s tests -p "test_floating_shell.py" -v
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import design_tokens as tk  # noqa: E402
from app.floating_layout import MAX_MARGIN, SHELL_RADIUS, shell_margin  # noqa: E402


def _luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


# ======================================================================
# 1. THE RULES (no window)
# ======================================================================
class SizingRuleTests(unittest.TestCase):
    def test_the_smallest_window_has_no_gap_because_the_sidebar_needs_the_height(self):
        self.assertEqual(shell_margin(800, 500), 0)
        self.assertEqual(shell_margin(1400, 500), 0)

    def test_the_gap_grows_with_the_window_and_stops_at_the_maximum(self):
        sizes = [(800, 500), (900, 560), (1000, 650), (1100, 700), (1366, 768), (1920, 1080)]
        gaps = [shell_margin(w, h) for w, h in sizes]
        self.assertEqual(gaps, sorted(gaps))
        self.assertEqual(shell_margin(1366, 768), MAX_MARGIN)  # typical laptop
        self.assertEqual(shell_margin(3840, 2160), MAX_MARGIN)  # maximized on a big screen
        self.assertGreater(shell_margin(1000, 650), 15)         # comfortable at the default size

    def test_the_maximum_gap_is_around_30px_and_the_sidebar_always_keeps_its_height(self):
        self.assertTrue(28 <= MAX_MARGIN <= 32)
        for width in range(800, 2000, 50):
            for height in range(500, 1100, 20):
                gap = shell_margin(width, height)
                self.assertLessEqual(gap, MAX_MARGIN)
                self.assertGreaterEqual(height - 2 * gap, 500)  # the rail never gets shorter than at 500 px

    def test_the_gap_is_never_negative_even_for_tiny_sizes(self):
        for size in ((0, 0), (100, 100), (-5, 300)):
            self.assertEqual(shell_margin(*size), 0)

    def test_the_container_uses_the_xl_corner_radius_token(self):
        self.assertEqual(SHELL_RADIUS, tk.RADIUS_XL)


class WindowColorTests(unittest.TestCase):
    def test_outside_the_container_is_darker_than_everything_inside(self):
        outside = _luminance(tk.COLOR_BG_WINDOW)
        for inside in (tk.COLOR_BG_APP, tk.COLOR_BG_SIDEBAR, tk.COLOR_BG_SURFACE):
            self.assertLess(outside, _luminance(inside), inside)


# ======================================================================
# 2. THE REAL DASHBOARD (needs PySide6)
# ======================================================================
try:
    import PySide6
    from PySide6.QtWidgets import QApplication, QFrame, QPushButton
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False

if HAVE_QT:
    from test_notifications import TempDbCase
else:  # pragma: no cover
    TempDbCase = unittest.TestCase


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class FloatingDashboardTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        from app import theme
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.qt_app.setStyleSheet(theme.STYLESHEET)

    def setUp(self):
        super().setUp()
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        self.dash = StudentDashboard(
            build_empty_data(self.ana.full_name), signed_in_email=self.ana.email,
            student_id=self.ana.id, request_service=self.requests, auth_service=self.auth)

    def tearDown(self):
        self.dash.hide()
        super().tearDown()

    def show_at(self, width, height):
        self.dash.resize(width, height)
        self.dash.show()
        self.qt_app.processEvents()
        return self.dash.shell.geometry()

    def test_the_whole_app_is_inside_one_container_with_equal_gaps(self):
        for width, height in ((1000, 650), (1366, 768), (1920, 1080)):
            shell = self.show_at(width, height)
            gap = shell_margin(width, height)
            self.assertGreater(gap, 0)
            self.assertEqual((shell.x(), shell.y()), (gap, gap))
            self.assertEqual((width - shell.right() - 1, height - shell.bottom() - 1), (gap, gap))

    def test_sidebar_and_every_page_live_inside_the_container(self):
        shell = self.dash.shell
        self.assertTrue(shell.isAncestorOf(self.dash.sidebar_rail))
        self.assertTrue(shell.isAncestorOf(self.dash.content_stack))
        for key, page in self.dash._pages.items():
            self.assertTrue(shell.isAncestorOf(page), key)
        self.assertEqual(self.dash.layout().count(), 1)  # nothing sits outside the container

    def test_the_gap_follows_the_window_when_it_is_resized_or_maximized(self):
        self.show_at(1000, 650)
        small = self.dash.shell.x()
        self.show_at(1920, 1080)
        big = self.dash.shell.x()
        self.assertGreater(big, small)
        self.assertEqual(big, MAX_MARGIN)
        self.show_at(800, 500)  # the smallest window: flush, so the sidebar still fits
        self.assertEqual(self.dash.shell.x(), 0)

    def test_outside_the_container_is_the_darker_window_color_and_corners_are_rounded(self):
        from PySide6.QtGui import QColor
        self.show_at(1366, 768)
        image = self.dash.grab().toImage()
        window = QColor(tk.COLOR_BG_WINDOW)
        gap = shell_margin(1366, 768)
        self.assertEqual(image.pixelColor(3, 3).name(), window.name())            # the margin
        corner = image.pixelColor(gap + 1, gap + 1)                                 # clipped corner
        self.assertEqual(corner.name(), window.name())
        inside = image.pixelColor(gap + 60, gap + 60)
        self.assertNotEqual(inside.name(), window.name())

    def test_the_corner_overlay_never_blocks_the_mouse(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget
        overlay = self.dash.shell.findChild(QWidget, "floatingShellOverlay")
        self.assertTrue(overlay.testAttribute(Qt.WA_TransparentForMouseEvents))

    def test_sidebar_still_fits_and_stays_inside_the_container_at_every_size(self):
        rail = self.dash.sidebar_rail
        for width, height in ((800, 500), (1000, 650), (1366, 768), (1920, 1080)):
            self.show_at(width, height)
            self.assertEqual(rail.height(), self.dash.shell.height())
            buttons = list(self.dash._nav_buttons.values()) + [
                self.dash.avatar_button, self.dash.sidebar_exit_button]
            for button in buttons:
                self.assertGreaterEqual(button.y(), 0)
                self.assertLessEqual(button.y() + button.height(), rail.height())

    def test_navigation_still_works_inside_the_container(self):
        self.show_at(1100, 700)
        for key in ("catalog", "my_list", "my_requests", "borrowings", "reservations",
                    "notifications", "settings", "dashboard"):
            self.dash.go_to(key)
            expected = self.dash.home_page if key == "dashboard" else self.dash._pages[key]
            self.assertIs(self.dash.content_stack.currentWidget(), expected)

    def test_login_screen_is_not_wrapped_and_the_mascot_stays_on_the_dashboard(self):
        from app.login_screen import LoginScreen
        login = LoginScreen()
        self.assertIsNone(login.findChild(QFrame, "floatingShell"))
        from PySide6.QtWidgets import QLabel
        for key, page in self.dash._pages.items():
            self.assertEqual(page.findChildren(QLabel, "homeMascot"), [], key)  # Dashboard only


if __name__ == "__main__":
    unittest.main()
