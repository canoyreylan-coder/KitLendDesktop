"""Step 23 tests: My Requests soft-dark redesign (looks only; behaviour is covered elsewhere).

The first group needs no window. The second opens the real screen (needs PySide6).
"""
import os
import re
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.my_requests_theme import MY_REQUESTS_V2_QSS  # noqa: E402

try:
    import PySide6
    from PySide6.QtWidgets import QApplication, QLabel
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False

STATUSES = ("pending", "approved", "rejected", "borrowed", "return_pending", "returned",
            "cancelled", "expired")


class ThemeTests(unittest.TestCase):
    def test_every_rule_is_limited_to_the_my_requests_screen(self):
        selectors = re.findall(r"^([^\n{}/][^{}]*)\{", MY_REQUESTS_V2_QSS, re.M)
        self.assertGreater(len(selectors), 30)
        for group in selectors:
            for selector in group.split(","):
                self.assertTrue(selector.strip().startswith("QWidget#myRequestsScreen"),
                                selector.strip())

    def test_each_status_has_its_own_pill_look(self):
        looks = set()
        for status in STATUSES:
            match = re.search(r'\[status="%s"\]\s*\{\s*([^}]*)\}' % status, MY_REQUESTS_V2_QSS)
            self.assertIsNotNone(match, status)
            looks.add(match.group(1).strip())
        self.assertEqual(len(looks), len(STATUSES))  # no two statuses look alike

    def test_no_thick_outlines_and_no_cream_cards(self):
        self.assertIsNone(re.search(r"(?<!\d)[34]px solid", MY_REQUESTS_V2_QSS))
        self.assertNotIn("dashed", MY_REQUESTS_V2_QSS)
        for old in ("#FFF9EF", "#F1F0FA", "#E3E4FA"):
            self.assertNotIn(old.lower(), MY_REQUESTS_V2_QSS.lower())

    def test_the_screen_applies_the_new_theme_last(self):
        source = (ROOT / "app" / "my_requests_screen.py").read_text(encoding="utf-8")
        self.assertRegex(source, r"HEADER_QSS\s*\+ MY_REQUESTS_V2_QSS\)")

    def test_other_screens_do_not_use_it(self):
        for path in (ROOT / "app").glob("*.py"):
            if path.name in ("my_requests_screen.py", "my_requests_theme.py") or "(" in path.name:
                continue
            self.assertNotIn("MY_REQUESTS_V2_QSS", path.read_text(encoding="utf-8"), path.name)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class ScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_cards_pills_and_chips_still_exist_and_cancel_still_works(self):
        from app.my_requests_screen import FILTER_ALL, MyRequestsScreen, RequestStatus
        from app.my_requests_screen import build_sample_requests
        screen = MyRequestsScreen(build_sample_requests())
        screen.resize(900, 700)
        screen.show()
        self.qt_app.processEvents()
        pills = screen.findChildren(QLabel, "myReqStatus")
        self.assertEqual(len(pills), len(screen.visible_requests))
        self.assertEqual(len(screen._tab_buttons), 3)  # Active / History / Cancelled
        shown = {pill.property("status") for pill in pills}
        self.assertTrue(shown <= set(STATUSES))
        screen.set_filter(RequestStatus.PENDING)
        self.assertTrue(all(r.status is RequestStatus.PENDING for r in screen.visible_requests))
        screen.set_filter(FILTER_ALL)
        for width in (480, 700, 1100):  # responsive: no crash, grids re-flow
            screen.resize(width, 700)
            self.qt_app.processEvents()
        screen.hide()


if __name__ == "__main__":
    unittest.main()
