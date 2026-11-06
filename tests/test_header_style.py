"""Header & label redesign tests: shared heading look, accent words, Kit only on the Dashboard.

The first group needs no window. The second opens the real screens (needs PySide6).
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import header_style  # noqa: E402

try:
    import PySide6
    from PySide6.QtWidgets import QApplication, QLabel
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False


class AccentTests(unittest.TestCase):
    def test_the_accent_words_are_coloured_and_the_rest_is_untouched(self):
        html = header_style.accent_html("My List", "List")
        self.assertEqual(html, f'My <span style="color:{header_style.ACCENT_LAVENDER};">List</span>')

    def test_no_accent_gives_plain_escaped_text(self):
        self.assertEqual(header_style.accent_html("Settings", ""), "Settings")
        self.assertEqual(header_style.accent_html("A & B", "zzz"), "A &amp; B")

    def test_text_is_escaped(self):
        self.assertIn("&lt;b&gt;", header_style.accent_html("<b>x", "x"))

    def test_headings_have_no_box_border_or_background(self):
        qss = header_style.HEADER_QSS
        for name in ("catHeader", "mlHeader", "catalogHeader", "homeWelcome"):
            self.assertIn(f"QFrame#{name}", qss)
        block = qss[qss.index("QFrame#catHeader"):qss.index("}", qss.index("QFrame#catHeader"))]
        self.assertIn("background: transparent", block)
        self.assertIn("border: none", block)

    def test_every_page_title_style_uses_the_same_size(self):
        self.assertEqual(header_style.HEADER_QSS.count("font-size: 28px"), 1)  # one shared rule

    def test_no_screen_other_than_the_dashboard_loads_the_mascot_in_its_header(self):
        for name in ("catalog_screen", "my_list_screen", "my_requests_screen", "my_borrowings_screen",
                     "my_reservations_screen", "notifications_screen", "settings_screen"):
            source = (ROOT / "app" / f"{name}.py").read_text(encoding="utf-8")
            self.assertNotIn("QPixmap(str(HAPPY_MASCOT_PATH))", source, name)
            self.assertNotIn("QPixmap(str(CURIOUS_MASCOT_PATH))", source, name)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class ScreenHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def labels(self, screen, name):
        return screen.findChildren(QLabel, name)

    def test_page_titles_use_an_accent_word(self):
        from app.catalog_screen import CatalogScreen
        from app.my_borrowings_screen import MyBorrowingsScreen
        from app.my_list_screen import MyListScreen
        from app.my_requests_screen import MyRequestsScreen
        for screen, name, word in ((CatalogScreen(), "catTitle", "Catalog"),
                                   (MyListScreen([]), "mlTitle", "List"),
                                   (MyRequestsScreen([]), "catalogTitle", "Requests"),
                                   (MyBorrowingsScreen([]), "catalogTitle", "Borrowings")):
            title = self.labels(screen, name)[0]
            self.assertIn(header_style.ACCENT_LAVENDER, title.text())
            self.assertIn(word, title.text())

    def test_only_the_dashboard_shows_the_mascot(self):
        from app.catalog_screen import CatalogScreen
        from app.my_borrowings_screen import MyBorrowingsScreen
        from app.my_list_screen import MyListScreen
        from app.my_requests_screen import MyRequestsScreen
        from app.my_reservations_screen import MyReservationsScreen
        from app.notifications_screen import NotificationsScreen
        from app.settings_screen import SettingsScreen
        screens = (CatalogScreen(), MyListScreen([]), MyRequestsScreen([]), MyBorrowingsScreen([]),
                   MyReservationsScreen([]), NotificationsScreen([]), SettingsScreen())
        for screen in screens:
            for label in screen.findChildren(QLabel):
                pixmap = label.pixmap()
                if pixmap is not None and not pixmap.isNull():
                    # only item photos/icons may carry a picture; never the 100-140px Kit art
                    self.assertLess(max(pixmap.width(), pixmap.height()), 100,
                                    type(screen).__name__)


if __name__ == "__main__":
    unittest.main()
