"""Step 29C tests: the small unread dot on the sidebar's notification bell.

The first group needs no window. The second opens the real dashboard (needs PySide6).
"""
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import PySide6
    from PySide6.QtWidgets import QApplication
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False


class SourceTests(unittest.TestCase):
    def test_the_dot_shows_no_numbers_and_ignores_the_mouse(self):
        source = (ROOT / "app" / "sidebar_indicator.py").read_text(encoding="utf-8")
        self.assertIn("WA_TransparentForMouseEvents", source)
        self.assertNotIn("drawText", source)
        self.assertNotIn("QLabel", source)

    def test_the_dot_is_a_child_of_the_bell_button_so_it_follows_the_icon(self):
        source = (ROOT / "app" / "sidebar_indicator.py").read_text(encoding="utf-8")
        self.assertIn("super().__init__(button)", source)
        dash = (ROOT / "app" / "dashboard_screen.py").read_text(encoding="utf-8")
        self.assertIn('if item.key == "notifications":', dash)
        self.assertIn("UnreadDot(button)", dash)


if HAVE_QT:
    from test_notifications import AVAILABLE, TempDbCase, make_draft, now_fixed
else:  # pragma: no cover
    TempDbCase = unittest.TestCase


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DotTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        self.build = lambda student: StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests)
        self.dash = self.build(self.ana)
        self.dash.resize(1100, 700)
        self.dash.show()
        self.qt_app.processEvents()

    def tearDown(self):
        self.dash.hide()

    def dot(self, dash=None):
        return (dash or self.dash)._notification_dot

    def bell(self):
        return self.dash._nav_buttons["notifications"]

    def test_no_dot_for_a_new_account(self):
        self.assertTrue(self.dot().isHidden())

    def test_a_new_notification_shows_the_dot_immediately(self):
        self.dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        self.assertFalse(self.dot().isHidden())

    def test_reading_everything_hides_the_dot_and_reading_one_of_two_keeps_it(self):
        self.dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        request = self.dash.my_requests_page.requests[0]
        self.dash._cancel_request(request, now_fixed() + timedelta(seconds=5))
        first, second = self.dash.my_notifications_page.notifications
        self.dash._on_notification_mark_read(first.id)
        self.assertFalse(self.dot().isHidden())          # one is still unread
        self.dash._on_notification_mark_read(second.id)
        self.assertTrue(self.dot().isHidden())

    def test_mark_all_read_hides_the_dot(self):
        self.dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        self.dash._on_notifications_mark_all_read()
        self.assertTrue(self.dot().isHidden())

    def test_the_dot_survives_a_restart_only_while_something_is_unread(self):
        self.dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        self.assertFalse(self.dot(self.build(self.ana)).isHidden())
        self.dash._on_notifications_mark_all_read()
        self.assertTrue(self.dot(self.build(self.ana)).isHidden())
        self.assertTrue(self.dot(self.build(self.ben)).isHidden())  # another account: nothing

    def test_the_dot_sits_at_the_top_right_of_the_bell_for_every_icon_size(self):
        self.dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        for size in (16, 24, 36, 44):
            self.dash.sidebar_rail.set_item_size("notifications", size)
            self.qt_app.processEvents()
            dot, bell = self.dot(), self.bell()
            self.assertGreater(dot.x() + dot.width() / 2.0, bell.width() / 2.0, size)
            self.assertLess(dot.y() + dot.height() / 2.0, bell.height() / 2.0, size)
            self.assertGreaterEqual(dot.x(), 0)
            self.assertLessEqual(dot.x() + dot.width(), bell.width())

    def test_the_dot_follows_the_icon_when_it_is_moved(self):
        self.dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        self.dash._start_sidebar_editing()
        self.dash.sidebar_rail.set_item_position("notifications", 30, self.bell().y() + 5)
        self.qt_app.processEvents()
        top_left = self.dot().mapTo(self.dash.sidebar_rail, self.dot().rect().topLeft())
        bell_top_left = self.bell().pos()
        self.assertEqual(self.dot().parent(), self.bell())
        self.assertGreater(top_left.x(), bell_top_left.x())
        self.assertLessEqual(top_left.y(), bell_top_left.y() + self.bell().height() // 2)

    def test_the_dot_does_not_block_clicking_the_bell(self):
        self.dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        self.bell().click()
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.my_notifications_page)
        self.assertEqual(self.bell().toolTip(), "Notifications")


if __name__ == "__main__":
    unittest.main()
