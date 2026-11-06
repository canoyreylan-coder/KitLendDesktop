"""Outer Margin tests: the adjustable size of the floating app container.

Group 1 (rules + saving) needs no window. Group 2 opens the real dashboard in Qt's invisible
"offscreen" mode and is skipped when PySide6 is missing.
Run:  python -m unittest discover -s tests -p "test_outer_margin.py" -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.auth_service import AuthService  # noqa: E402
from app.floating_layout import (  # noqa: E402
    MAX_OUTER_MARGIN, MIN_OUTER_MARGIN, SMALLEST_HEIGHT, SMALLEST_WIDTH, clamp_outer_margin,
    effective_margin, shell_margin)
from app.preference_service import OUTER_MARGIN_KEY, PreferenceError, PreferenceService  # noqa: E402

PW = "Passw0rd-long"


# ======================================================================
# 1. THE RULES (no window)
# ======================================================================
class MarginRuleTests(unittest.TestCase):
    def test_the_range_is_12_to_48(self):
        self.assertEqual((MIN_OUTER_MARGIN, MAX_OUTER_MARGIN), (12, 48))
        self.assertEqual(clamp_outer_margin(0), 12)
        self.assertEqual(clamp_outer_margin(999), 48)
        self.assertEqual(clamp_outer_margin(30), 30)

    def test_no_choice_keeps_the_old_automatic_gap_exactly(self):
        for size in ((800, 500), (1000, 650), (1366, 768), (1920, 1080)):
            self.assertEqual(effective_margin(None, *size), shell_margin(*size))

    def test_a_larger_margin_always_means_a_smaller_container(self):
        for width, height in ((1000, 650), (1366, 768), (1920, 1080)):
            container = [(width - 2 * effective_margin(m, width, height),
                          height - 2 * effective_margin(m, width, height))
                         for m in range(MIN_OUTER_MARGIN, MAX_OUTER_MARGIN + 1, 4)]
            self.assertEqual(container, sorted(container, reverse=True))
            self.assertLess(container[-1], container[0])

    def test_the_chosen_margin_is_used_when_there_is_room(self):
        self.assertEqual(effective_margin(12, 1366, 768), 12)
        self.assertEqual(effective_margin(48, 1366, 768), 48)
        self.assertEqual(effective_margin(48, 1000, 650), 48)  # visible at the default window too

    def test_the_container_never_gets_smaller_than_the_smallest_window_so_nothing_clips(self):
        for width in range(0, 2200, 50):
            for height in range(0, 1200, 25):
                for chosen in (None, 12, 30, 48):
                    gap = effective_margin(chosen, width, height)
                    self.assertGreaterEqual(gap, 0)
                    self.assertLessEqual(gap, MAX_OUTER_MARGIN)
                    if width >= SMALLEST_WIDTH and height >= SMALLEST_HEIGHT:
                        self.assertGreaterEqual(width - 2 * gap, SMALLEST_WIDTH)
                        self.assertGreaterEqual(height - 2 * gap, SMALLEST_HEIGHT)

    def test_the_smallest_window_has_no_gap_whatever_was_chosen(self):
        for chosen in (None, 12, 48):
            self.assertEqual(effective_margin(chosen, 800, 500), 0)


class MarginSavingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        auth = AuthService(self.db)
        self.ana = auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")
        self.prefs = PreferenceService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_accounts_have_no_saved_margin(self):
        self.assertIsNone(self.prefs.get_outer_margin(self.ana.id))

    def test_a_saved_margin_survives_a_restart_and_belongs_to_one_account(self):
        self.prefs.set_outer_margin(self.ana.id, 40)
        again = PreferenceService(self.db)  # "restart": a new service object, same file
        self.assertEqual(again.get_outer_margin(self.ana.id), 40)
        self.assertIsNone(again.get_outer_margin(self.ben.id))

    def test_saving_again_replaces_and_reset_removes_it(self):
        self.prefs.set_outer_margin(self.ana.id, 40)
        self.prefs.set_outer_margin(self.ana.id, 16)
        self.assertEqual(self.prefs.get_outer_margin(self.ana.id), 16)
        self.prefs.reset_outer_margin(self.ana.id)
        self.assertIsNone(self.prefs.get_outer_margin(self.ana.id))
        self.prefs.reset_outer_margin(self.ana.id)  # nothing to remove: still fine

    def test_reset_does_not_touch_other_preferences_or_accounts(self):
        self.prefs.set_catalog_view(self.ana.id, "list")
        self.prefs.set_outer_margin(self.ana.id, 20)
        self.prefs.set_outer_margin(self.ben.id, 44)
        self.prefs.reset_outer_margin(self.ana.id)
        self.assertEqual(self.prefs.get_catalog_view(self.ana.id), "list")
        self.assertEqual(self.prefs.get_outer_margin(self.ben.id), 44)

    def test_out_of_range_or_wrong_type_values_are_refused_and_change_nothing(self):
        self.prefs.set_outer_margin(self.ana.id, 24)
        for bad in (11, 49, 0, -5, True, "30", 30.5, None):
            with self.assertRaises(PreferenceError, msg=repr(bad)):
                self.prefs.set_outer_margin(self.ana.id, bad)
        self.assertEqual(self.prefs.get_outer_margin(self.ana.id), 24)

    def test_a_damaged_stored_value_means_automatic(self):
        for junk in ("junk", "5", "999", ""):
            self.prefs.set(self.ana.id, OUTER_MARGIN_KEY, junk)
            self.assertIsNone(self.prefs.get_outer_margin(self.ana.id), junk)

    def test_no_new_database_table_is_needed(self):
        import sqlite3
        conn = sqlite3.connect(self.db)
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        self.assertIn("student_preferences", tables)
        self.assertFalse([t for t in tables if "margin" in t])


# ======================================================================
# 2. THE REAL DASHBOARD (needs PySide6)
# ======================================================================
try:
    import PySide6
    from PySide6.QtWidgets import QApplication
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False

if HAVE_QT:
    from test_notifications import TempDbCase
else:  # pragma: no cover
    TempDbCase = unittest.TestCase


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class MarginDashboardTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        from app import theme
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.qt_app.setStyleSheet(theme.STYLESHEET)

    def setUp(self):
        super().setUp()
        self.dashes = []
        self.dash = self.make_dash(self.ana)

    def tearDown(self):
        for dash in self.dashes:
            dash.hide()
        super().tearDown()

    def make_dash(self, student):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        dash = StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests, auth_service=self.auth)
        dash.resize(1366, 768)
        dash.show()
        self.qt_app.processEvents()
        self.dashes.append(dash)
        return dash

    def gap(self, dash):
        return dash.shell.x()

    def test_dragging_the_slider_changes_the_container_at_once_and_it_stays_centered(self):
        page = self.dash.settings_page
        before = self.dash.shell.geometry()
        page.margin_slider.setValue(48)
        after = self.dash.shell.geometry()
        self.assertEqual(self.gap(self.dash), 48)
        self.assertLess(after.width(), before.width())
        self.assertLess(after.height(), before.height())
        w, h = self.dash.width(), self.dash.height()
        self.assertEqual((after.x(), after.y()), (48, 48))
        self.assertEqual((w - after.right() - 1, h - after.bottom() - 1), (48, 48))  # centered
        page.margin_slider.setValue(12)
        self.assertEqual(self.gap(self.dash), 12)

    def test_slider_range_and_default_state(self):
        page = self.dash.settings_page
        self.assertEqual((page.margin_slider.minimum(), page.margin_slider.maximum()), (12, 48))
        self.assertIn("Automatic", page.margin_value_label.text())
        self.assertFalse(page.margin_save_button.isEnabled())
        self.assertFalse(page.margin_cancel_button.isEnabled())
        self.assertFalse(page.margin_reset_button.isEnabled())

    def test_save_keeps_it_after_a_restart_for_this_account_only(self):
        self.dash.settings_page.margin_slider.setValue(40)
        self.assertTrue(self.dash.settings_page.margin_save_button.isEnabled())
        self.dash.settings_page.margin_save_button.click()
        self.assertEqual(self.dash.settings_page.margin_value_label.text(), "40 px")
        restarted = self.make_dash(self.ana)
        self.assertEqual(self.gap(restarted), 40)
        self.assertEqual(restarted.settings_page.margin_slider.value(), 40)
        self.assertNotEqual(self.gap(self.make_dash(self.ben)), 40)

    def test_cancel_goes_back_to_the_saved_margin(self):
        page = self.dash.settings_page
        page.margin_slider.setValue(20)
        page.margin_save_button.click()
        page.margin_slider.setValue(46)
        self.assertEqual(self.gap(self.dash), 46)
        page.margin_cancel_button.click()
        self.assertEqual(self.gap(self.dash), 20)
        self.assertEqual(page.margin_slider.value(), 20)
        self.assertFalse(page.margin_save_button.isEnabled())

    def test_cancel_on_an_unsaved_account_goes_back_to_automatic(self):
        auto = self.gap(self.dash)
        self.dash.settings_page.margin_slider.setValue(44)
        self.dash.settings_page.margin_cancel_button.click()
        self.assertEqual(self.gap(self.dash), auto)
        self.assertIn("Automatic", self.dash.settings_page.margin_value_label.text())

    def test_reset_to_default_previews_automatic_and_save_makes_it_permanent(self):
        page = self.dash.settings_page
        auto = self.gap(self.dash)
        page.margin_slider.setValue(14)
        page.margin_save_button.click()
        page.margin_reset_button.click()
        self.assertEqual(self.gap(self.dash), auto)
        self.assertIn("Automatic", page.margin_value_label.text())
        page.margin_save_button.click()
        self.assertIsNone(PreferenceServiceFor(self.db).get_outer_margin(self.ana.id))
        self.assertEqual(self.gap(self.make_dash(self.ana)), auto)

    def test_leaving_settings_drops_an_unsaved_preview(self):
        auto = self.gap(self.dash)
        self.dash.go_to("settings")
        self.dash.settings_page.margin_slider.setValue(48)
        self.assertEqual(self.gap(self.dash), 48)
        self.dash.go_to("catalog")
        self.assertEqual(self.gap(self.dash), auto)

    def test_small_windows_reduce_the_margin_so_nothing_is_clipped(self):
        self.dash.settings_page.margin_slider.setValue(48)
        for width, height in ((800, 500), (900, 560), (1000, 650)):
            self.dash.resize(width, height)
            self.qt_app.processEvents()
            shell = self.dash.shell.geometry()
            self.assertGreaterEqual(shell.width(), 800, (width, height))
            self.assertGreaterEqual(shell.height(), 500, (width, height))
            rail = self.dash.sidebar_rail
            self.assertEqual(rail.height(), shell.height())
            for button in list(self.dash._nav_buttons.values()) + [
                    self.dash.avatar_button, self.dash.sidebar_exit_button]:
                self.assertGreaterEqual(button.y(), 0)
                self.assertLessEqual(button.y() + button.height(), rail.height())
        self.assertEqual(self.gap(self.dash), 0)  # the smallest window: flush

    def test_margin_never_resizes_icons_or_changes_the_sidebar_layout(self):
        sizes = {k: b.size() for k, b in self.dash._nav_buttons.items()}
        avatar = self.dash.avatar_button.size()
        font = self.dash.settings_page.font().pointSizeF()
        self.dash.settings_page.margin_slider.setValue(48)
        self.qt_app.processEvents()
        self.assertEqual({k: b.size() for k, b in self.dash._nav_buttons.items()}, sizes)
        self.assertEqual(self.dash.avatar_button.size(), avatar)
        self.assertEqual(self.dash.settings_page.font().pointSizeF(), font)

    def test_container_keeps_its_rounded_corner_overlay_and_navigation_works(self):
        from PySide6.QtWidgets import QWidget
        self.dash.settings_page.margin_slider.setValue(36)
        self.assertIsNotNone(self.dash.shell.findChild(QWidget, "floatingShellOverlay"))
        for key in ("catalog", "my_requests", "settings", "dashboard"):
            self.dash.go_to(key)

    def test_demo_has_no_margin_controls_or_saving(self):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_demo_data
        demo = StudentDashboard(build_demo_data())
        demo.resize(1366, 768)
        demo.show()
        self.assertEqual(demo.shell.x(), shell_margin(1366, 768))
        demo.hide()


def PreferenceServiceFor(db):
    return PreferenceService(db)


if __name__ == "__main__":
    unittest.main()
