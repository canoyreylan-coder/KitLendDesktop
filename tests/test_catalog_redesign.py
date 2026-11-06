"""Step 16 tests: the redesigned Browse Catalog (soft-dark look) keeps its behaviour.

Run from the project folder:   python -m unittest discover -s tests -p "test_catalog_redesign.py" -v
Widgets open in Qt's invisible "offscreen" mode, so no window appears.
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import catalog_screen  # noqa: E402
from app.catalog_screen import SAMPLE_ITEMS, CatalogScreen  # noqa: E402
from app.catalog_theme import CATALOG_V2_STYLESHEET  # noqa: E402

_app = QApplication.instance() or QApplication([])


class LookTests(unittest.TestCase):
    def test_catalog_uses_the_soft_dark_sheet_with_no_pixel_pop_colors(self):
        screen = CatalogScreen()
        self.assertEqual(screen.styleSheet(), CATALOG_V2_STYLESHEET)
        for pixel_pop in (catalog_screen.NAVY, catalog_screen.CREAM):
            self.assertNotIn(pixel_pop.lower(), CATALOG_V2_STYLESHEET.lower())

    def test_old_sheet_is_untouched_for_the_other_screens(self):
        old = catalog_screen.CATALOG_STYLESHEET
        for name in ("catalogItemCard", "catalogHeader", "catalogPill", "catalogPrimaryButton"):
            self.assertIn(name, old)
        self.assertNotIn("catItemCard", old)

    def test_new_sheet_only_uses_its_own_object_names(self):
        self.assertNotIn("#catalog", CATALOG_V2_STYLESHEET.replace("#catalogScreen", ""))

    def test_cards_show_no_condition_label_because_no_condition_data_exists(self):
        self.assertFalse(hasattr(SAMPLE_ITEMS[0], "condition"))


class BehaviourTests(unittest.TestCase):
    def setUp(self):
        self.screen = CatalogScreen()

    def test_all_sample_items_start_visible(self):
        self.assertEqual(len(self.screen.visible_items), len(SAMPLE_ITEMS))
        self.assertFalse(self.screen.grid.isHidden())
        self.assertTrue(self.screen.empty_state.isHidden())

    def test_search_narrows_the_results_and_both_search_fields_stay_in_sync(self):
        self.screen.search_input.setText("python")
        self.assertTrue(0 < len(self.screen.visible_items) < len(SAMPLE_ITEMS))
        self.assertEqual(self.screen.sticky_search_input.text(), "python")

    def test_no_results_shows_a_readable_empty_state_and_clear_restores_everything(self):
        self.screen.search_input.setText("zzzz-no-such-item")
        self.assertEqual(self.screen.visible_items, [])
        self.assertFalse(self.screen.empty_state.isHidden())
        self.assertTrue(self.screen.grid.isHidden())
        self.assertEqual(self.screen.empty_title.text(), "No items found")
        self.assertFalse(self.screen.empty_button.isHidden())
        self.screen.empty_button.click()
        self.assertEqual(len(self.screen.visible_items), len(SAMPLE_ITEMS))
        self.assertTrue(self.screen.empty_state.isHidden())

    def test_filters_still_work(self):
        panel = self.screen.filter_panel
        panel.combo("category").setCurrentText("Electronics")
        self.assertTrue(self.screen.visible_items)
        self.assertTrue(all(i.category == "Electronics" for i in self.screen.visible_items))
        panel.combo("availability").setCurrentText("Available")
        self.assertTrue(all(i.is_available for i in self.screen.visible_items))
        panel.combo("ownership").setCurrentText("Student-Owned")
        self.assertTrue(all(i.ownership == "student" for i in self.screen.visible_items))
        panel.clear_button.click()
        self.assertEqual(len(self.screen.visible_items), len(SAMPLE_ITEMS))

    def test_request_now_only_works_for_available_items(self):
        sent = []
        self.screen.direct_request_requested.connect(sent.append)
        available = next(c for c in self.screen._cards if c.item.is_available)
        unavailable = next(c for c in self.screen._cards if not c.item.is_available)
        self.assertFalse(unavailable.request_button.isEnabled())
        unavailable.request_button.click()
        self.assertEqual(sent, [])
        available.request_button.click()
        self.assertEqual(sent, [available.item])

    def test_bookmark_signal_and_outside_sync(self):
        toggled = []
        self.screen.bookmark_toggled.connect(lambda item, on: toggled.append((item, on)))
        card = self.screen._cards[0]
        card.bookmark_button.click()
        self.assertEqual(toggled, [(card.item, True)])
        self.assertEqual(self.screen.bookmarked_items, [card.item])
        self.screen.set_bookmarked_items([])          # sync from outside: no signal
        self.assertEqual(toggled, [(card.item, True)])
        self.assertFalse(card.bookmark_button.isChecked())

    def test_empty_catalog_has_its_own_message_and_no_clear_button(self):
        screen = CatalogScreen(items=[])
        self.assertEqual(screen.empty_title.text(), "The catalog is empty")
        self.assertTrue(screen.empty_button.isHidden())
        self.assertFalse(screen.empty_state.isHidden())

    def test_grid_reflows_at_laptop_and_maximized_widths_without_error(self):
        for width, height in ((900, 640), (1280, 720), (1920, 1040)):
            self.screen.resize(width, height)
            self.screen.show()
            _app.processEvents()
            self.assertGreaterEqual(self.screen.grid._columns, 1)
        self.screen.hide()


if __name__ == "__main__":
    unittest.main()
