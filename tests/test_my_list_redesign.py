"""Step 22 tests: My List visual redesign (behaviour must be unchanged).

Run:   python -m unittest discover -s tests -p "test_my_list_redesign.py" -v
The stylesheet test needs no window; the rest use Qt's invisible "offscreen" mode.
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.my_list_theme import MY_LIST_V2_STYLESHEET  # noqa: E402

try:
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication, QDialog
    from app.catalog_screen import SAMPLE_ITEMS
    from app.my_list_screen import MyListScreen, SavedItemRow
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


class StyleTests(unittest.TestCase):
    def test_only_ml_selectors_so_nothing_leaks_into_other_widgets(self):
        selectors = re.findall(r"^([A-Za-z][^{\n]*?)\s*\{", MY_LIST_V2_STYLESHEET, re.M)
        self.assertTrue(selectors)
        for selector in selectors:
            for part in selector.split(","):
                self.assertTrue(re.search(r"#(ml|myList)", part), part)

    @unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
    def test_old_request_dialog_and_my_requests_styles_are_untouched(self):
        from app.my_list_screen import MY_LIST_STYLESHEET
        self.assertIn("QFrame#myListRow", MY_LIST_STYLESHEET)
        self.assertIn("QDialog#myListDialog", MY_LIST_STYLESHEET)


def pick(*titles):
    by = {i.title: i for i in SAMPLE_ITEMS}
    return [by[t] for t in titles]


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class MyListScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.available = pick("Grokking Algorithms", "Python Crash Course")
        self.unavailable = pick("Clean Code")
        self.screen = MyListScreen(self.available + self.unavailable)
        self.addCleanup(self.screen.deleteLater)

    def test_empty_state_and_browse_button(self):
        empty = MyListScreen([])
        self.addCleanup(empty.deleteLater)
        empty.show()
        self.assertFalse(empty.empty_state.isHidden())
        self.assertTrue(empty.action_bar.isHidden())
        seen = []
        empty.browse_catalog_requested.connect(lambda: seen.append(1))
        empty.empty_state.findChild(type(empty.request_button), "mlPrimaryButton").click()
        self.assertEqual(seen, [1])
        empty.hide()

    def test_cards_show_saved_items_and_status(self):
        self.assertEqual(self.screen.saved_items, self.available + self.unavailable)
        self.assertEqual(self.screen.summary_label.text(), "3 saved · 2 can be requested · 1 unavailable")
        row = self.screen._rows[self.unavailable[0]]
        self.assertFalse(row.check.isEnabled())

    def test_selection_request_button_and_select_all_still_work(self):
        self.assertFalse(self.screen.request_button.isEnabled())
        self.screen._rows[self.available[0]].check.click()
        self.assertEqual(self.screen.selected_items, [self.available[0]])
        self.assertEqual(self.screen.request_button.text(), "Request Selected (1)")
        self.assertTrue(self.screen._rows[self.available[0]].property("selected"))
        self.screen.select_all_button.click()
        self.assertEqual(self.screen.selected_items, self.available)
        self.screen.select_all_button.click()
        self.assertEqual(self.screen.selected_items, [])

    def test_remove_emits_and_updates(self):
        removed = []
        self.screen.item_removed.connect(removed.append)
        self.screen._rows[self.available[1]].remove_button.click()
        self.assertEqual(removed, [self.available[1]])
        self.assertNotIn(self.available[1], self.screen.saved_items)

    def test_request_dialog_flow_is_unchanged(self):
        from app import my_list_screen as m
        seen = {}

        class FakeDialog:
            drafts = []
            DialogCode = QDialog.DialogCode

            def __init__(self, items, parent=None, submit_handler=None):
                seen["items"] = list(items)

            def exec(self):
                return QDialog.DialogCode.Rejected

        original = m.RequestPreviewDialog
        m.RequestPreviewDialog = FakeDialog
        try:
            self.screen._rows[self.available[0]].check.click()
            self.screen.request_button.click()
        finally:
            m.RequestPreviewDialog = original
        self.assertEqual(seen["items"], [self.available[0]])

    def test_photos_or_placeholders_on_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.png")
            image = QImage(60, 40, QImage.Format_RGB32)
            image.fill(QColor("#3355aa"))
            image.save(path)
            item = self.available[0]
            self.screen.set_primary_photos({item.listing_key: path})
            self.assertTrue(self.screen._rows[item].thumb.has_photo)
            self.assertFalse(self.screen._rows[self.available[1]].thumb.has_photo)
            self.screen.set_saved_items(self.available)           # rebuilt rows keep photos
            self.assertTrue(self.screen._rows[item].thumb.has_photo)
            self.screen.set_primary_photos({item.listing_key: os.path.join(tmp, "gone.png")})
            self.assertFalse(self.screen._rows[item].thumb.has_photo)  # missing file -> placeholder

    def test_cards_fold_on_narrow_widths_and_keep_their_buttons(self):
        row = SavedItemRow(self.available[0])
        self.addCleanup(row.deleteLater)
        row.resize(900, 100)
        row.show()
        self.app.processEvents()
        self.assertFalse(row.is_compact)
        row.resize(400, 130)
        self.app.processEvents()
        self.assertTrue(row.is_compact)
        self.assertFalse(row.remove_button.isHidden())
        self.assertFalse(row.check.isHidden())
        row.resize(900, 100)
        self.app.processEvents()
        self.assertFalse(row.is_compact)
        row.hide()

    def test_small_window_hides_mascot_only(self):
        self.screen.resize(560, 600)
        self.screen.show()
        self.app.processEvents()
        if self.screen.mascot_label is not None:
            self.assertTrue(self.screen.mascot_label.isHidden())
        self.assertFalse(self.screen.request_button.isHidden())
        self.screen.resize(1200, 700)
        self.app.processEvents()
        if self.screen.mascot_label is not None:
            self.assertFalse(self.screen.mascot_label.isHidden())
        self.screen.hide()


if __name__ == "__main__":
    unittest.main()
