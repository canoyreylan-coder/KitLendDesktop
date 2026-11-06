"""Step 18 tests: horizontal Catalog filters, chips, Clear all filters, one shared pipeline."""
import dataclasses
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import catalog_screen as cs  # noqa: E402
from app.catalog_screen import (  # noqa: E402
    CATEGORIES,
    SAMPLE_ITEMS,
    CatalogItem,
    CatalogScreen,
    filter_items,
)
from app.preference_service import VIEW_GRID, VIEW_LIST  # noqa: E402

_app = QApplication.instance() or QApplication([])
TOTAL = len(SAMPLE_ITEMS)


def expected(**kw):
    """Independent re-implementation straight from the sample data (not from filter_items)."""
    out = []
    for i in SAMPLE_ITEMS:
        if kw.get("category") and i.category != kw["category"]:
            continue
        if kw.get("ownership") and i.ownership != kw["ownership"]:
            continue
        if kw.get("status") == "available" and not i.copies_available > 0:
            continue
        if kw.get("status") == "unavailable" and i.copies_available != 0:
            continue
        if kw.get("search") and not all(w in i.search_text for w in kw["search"].split()):
            continue
        out.append(i)
    return out


class PipelineTests(unittest.TestCase):
    def test_each_filter_alone(self):
        self.assertEqual(set(filter_items(SAMPLE_ITEMS, category="Electronics")),
                         set(expected(category="Electronics")))
        self.assertEqual(set(filter_items(SAMPLE_ITEMS, ownership="school")),
                         set(expected(ownership="school")))
        self.assertEqual(set(filter_items(SAMPLE_ITEMS, ownership="student")),
                         set(expected(ownership="student")))
        self.assertEqual(set(filter_items(SAMPLE_ITEMS, availability="available")),
                         set(expected(status="available")))
        self.assertEqual(set(filter_items(SAMPLE_ITEMS, availability="unavailable")),
                         set(expected(status="unavailable")))

    def test_all_three_combine_with_and_logic_and_with_search(self):
        got = filter_items(SAMPLE_ITEMS, category="Electronics", ownership="school",
                           availability="available")
        self.assertEqual(set(got), set(expected(category="Electronics", ownership="school",
                                                status="available")))
        self.assertTrue(got)
        got = filter_items(SAMPLE_ITEMS, search="kit", category="Electronics",
                           ownership="school", availability="available")
        self.assertEqual(set(got), set(expected(search="kit", category="Electronics",
                                                ownership="school", status="available")))
        self.assertTrue(0 < len(got) < len(filter_items(
            SAMPLE_ITEMS, category="Electronics", ownership="school", availability="available")))

    def test_available_and_unavailable_partition_the_catalog(self):
        a = set(filter_items(SAMPLE_ITEMS, availability="available"))
        u = set(filter_items(SAMPLE_ITEMS, availability="unavailable"))
        self.assertFalse(a & u)
        self.assertEqual(len(a) + len(u), TOTAL)
        self.assertTrue(u)  # the sample data really contains unavailable items

    def test_old_available_only_argument_still_works(self):
        self.assertEqual(filter_items(SAMPLE_ITEMS, available_only=True),
                         filter_items(SAMPLE_ITEMS, availability="available"))

    def test_missing_or_unknown_values_are_handled_consistently(self):
        base = SAMPLE_ITEMS[0]
        odd = [
            dataclasses.replace(base, title="No copies info", copies_available=None),
            dataclasses.replace(base, title="Negative", copies_available=-2),
            dataclasses.replace(base, title="Bad owner", ownership=""),
            dataclasses.replace(base, title="No owner", ownership=None),
            dataclasses.replace(base, title="No category", category=None),
            dataclasses.replace(base, title="No collections", collections=None),
            dataclasses.replace(base, title="No note", owner_note=None),
        ]
        self.assertEqual(len(filter_items(odd)), 7)  # nothing raises, all match "any"
        titles = lambda r: {i.title for i in r}  # noqa: E731
        self.assertNotIn("No copies info", titles(filter_items(odd, availability="available")))
        self.assertNotIn("No copies info", titles(filter_items(odd, availability="unavailable")))
        self.assertNotIn("Negative", titles(filter_items(odd, availability="available")))
        self.assertEqual(odd[0].availability_status, "unknown")
        self.assertFalse(odd[0].is_available)
        self.assertEqual(odd[0].availability_text, "Availability unknown")
        for school in titles(filter_items(odd, ownership="school")):
            self.assertNotIn(school, ("Bad owner", "No owner"))
        self.assertNotIn("No category", titles(filter_items(odd, category="Mathematics")))
        self.assertNotIn("No collections", titles(filter_items(odd, collection="Maker Corner")))
        self.assertEqual(filter_items(odd, search="no copies"), [odd[0]])


class FilterBarTests(unittest.TestCase):
    def setUp(self):
        self.screen = CatalogScreen()
        self.bar = self.screen.filter_panel

    def test_default_options_and_real_categories_only(self):
        self.assertEqual(self.bar.combo("category").itemText(0), "All Categories")
        self.assertEqual([self.bar.combo("category").itemText(i)
                          for i in range(1, self.bar.combo("category").count())],
                         [c.name for c in CATEGORIES])
        self.assertEqual([self.bar.combo("ownership").itemText(i) for i in range(3)],
                         ["All Owners", "School-Owned", "Student-Owned"])
        self.assertEqual([self.bar.combo("availability").itemText(i) for i in range(3)],
                         ["Any Status", "Available", "Unavailable"])
        self.assertEqual(len(self.screen.visible_items), TOTAL)
        self.assertTrue(self.bar.chip_area.isHidden())

    def test_categories_come_from_the_given_items_too(self):
        extra = dataclasses.replace(SAMPLE_ITEMS[0], category="Art")
        screen = CatalogScreen(items=SAMPLE_ITEMS[:3] + [extra])
        names = [screen.filter_panel.combo("category").itemText(i)
                 for i in range(screen.filter_panel.combo("category").count())]
        self.assertIn("Art", names)
        screen.filter_panel.combo("category").setCurrentText("Art")
        self.assertEqual([i.category for i in screen.visible_items], ["Art"])

    def test_dynamic_catalog_refresh_preserves_search_view_and_bookmarks(self):
        screen = CatalogScreen()
        published = dataclasses.replace(
            SAMPLE_ITEMS[0], title="Published Soldering Kit", creator="Ana Reyes",
            ownership="student", owner_note="Shared by Ana Reyes",
            record_id="LD-STABLE1", condition="Good")
        screen.set_items(SAMPLE_ITEMS + [published])
        screen.search_input.setText("published")
        screen.set_bookmarked_items([published])
        screen.set_view_mode(VIEW_LIST, emit=False)
        refreshed = dataclasses.replace(published, title="Published Soldering Kit Updated")

        screen.set_items(SAMPLE_ITEMS + [refreshed])

        self.assertEqual(screen.search_input.text(), "published")
        self.assertEqual(screen.view_mode, VIEW_LIST)
        self.assertEqual(screen.visible_items, [refreshed])
        self.assertEqual(screen.visible_rows[0].item.listing_key, "LD-STABLE1")
        self.assertEqual(screen.bookmarked_items[0].listing_key, "LD-STABLE1")
        self.assertEqual(screen.filter_panel.combo("category").findData("Mathematics"), 1)

    def test_each_dropdown_filters_the_visible_items(self):
        self.bar.combo("ownership").setCurrentText("Student-Owned")
        self.assertEqual(set(self.screen.visible_items), set(expected(ownership="student")))
        self.bar.combo("ownership").setCurrentIndex(0)
        self.bar.combo("availability").setCurrentText("Unavailable")
        self.assertEqual(set(self.screen.visible_items), set(expected(status="unavailable")))
        self.bar.combo("availability").setCurrentIndex(0)
        self.bar.combo("category").setCurrentText("Programming")
        self.assertEqual(set(self.screen.visible_items), set(expected(category="Programming")))

    def test_combined_filters_and_search_work_together(self):
        self.bar.combo("category").setCurrentText("Electronics")
        self.bar.combo("ownership").setCurrentText("School-Owned")
        self.bar.combo("availability").setCurrentText("Available")
        self.screen.search_input.setText("kit")
        self.assertEqual(set(self.screen.visible_items), set(expected(
            category="Electronics", ownership="school", status="available", search="kit")))
        self.assertEqual(self.screen.result_label.text(),
                         f"Showing {len(self.screen.visible_items)} of {TOTAL} items")

    def test_chips_show_only_selected_filters_in_order(self):
        self.bar.combo("category").setCurrentText("Electronics")
        self.bar.combo("availability").setCurrentText("Available")
        self.assertFalse(self.bar.chip_area.isHidden())
        self.assertEqual([c.label.text() for c in self.bar.chips()], ["Electronics", "Available"])
        self.bar.combo("ownership").setCurrentText("School-Owned")
        self.assertEqual([c.label.text() for c in self.bar.chips()],
                         ["Electronics", "School-Owned", "Available"])

    def test_removing_one_chip_keeps_the_others_and_the_search(self):
        self.bar.combo("category").setCurrentText("Electronics")
        self.bar.combo("ownership").setCurrentText("School-Owned")
        self.bar.combo("availability").setCurrentText("Available")
        self.screen.search_input.setText("e")
        next(c for c in self.bar.chips() if c.label.text() == "School-Owned").remove_button.click()
        self.assertEqual(self.bar.combo("ownership").currentIndex(), 0)
        self.assertEqual(self.bar.category, "Electronics")
        self.assertEqual(self.bar.availability, "available")
        self.assertEqual(self.screen.search_input.text(), "e")
        self.assertEqual([c.label.text() for c in self.bar.chips()], ["Electronics", "Available"])
        self.assertEqual(set(self.screen.visible_items), set(expected(
            category="Electronics", status="available", search="e")))

    def test_chips_disappear_when_the_last_filter_is_removed(self):
        self.bar.combo("category").setCurrentText("Science")
        self.bar.chips()[0].remove_button.click()
        self.assertTrue(self.bar.chip_area.isHidden())
        self.assertEqual(len(self.screen.visible_items), TOTAL)

    def test_changing_a_dropdown_by_hand_updates_the_chip_not_the_others(self):
        self.bar.combo("category").setCurrentText("Science")
        self.bar.combo("category").setCurrentText("Mathematics")
        self.assertEqual([c.label.text() for c in self.bar.chips()], ["Mathematics"])

    def test_clear_all_resets_filters_but_keeps_search_and_view(self):
        self.screen.set_view_mode(VIEW_LIST)
        self.bar.combo("category").setCurrentText("Electronics")
        self.bar.combo("ownership").setCurrentText("School-Owned")
        self.bar.combo("collection").setCurrentText("Maker Corner")
        self.screen.search_input.setText("kit")
        self.bar.clear_button.click()
        for key in ("category", "ownership", "availability", "collection"):
            self.assertEqual(self.bar.combo(key).currentIndex(), 0, key)
        self.assertTrue(self.bar.chip_area.isHidden())
        self.assertEqual(self.screen.search_input.text(), "kit")
        self.assertEqual(self.screen.sticky_search_input.text(), "kit")
        self.assertEqual(self.screen.view_mode, VIEW_LIST)
        self.assertEqual(set(self.screen.visible_items), set(expected(search="kit")))

    def test_collection_filter_still_works(self):
        self.bar.combo("collection").setCurrentText("DSA Final Project")
        self.assertTrue(self.screen.visible_items)
        self.assertTrue(all("DSA Final Project" in i.collections
                            for i in self.screen.visible_items))

    def test_empty_results_show_a_readable_message_and_can_recover(self):
        self.bar.combo("category").setCurrentText("Study Gear")
        self.bar.combo("availability").setCurrentText("Unavailable")
        self.assertEqual(self.screen.visible_items, [])
        self.assertFalse(self.screen.empty_state.isHidden())
        self.assertEqual(self.screen.empty_title.text(), "No items found")
        self.assertEqual(self.screen.result_label.text(), "No items match your search")
        self.bar.clear_button.click()
        self.assertTrue(self.screen.empty_state.isHidden())
        self.assertEqual(len(self.screen.visible_items), TOTAL)


class ViewSwitchingTests(unittest.TestCase):
    def setUp(self):
        self.screen = CatalogScreen()
        self.bar = self.screen.filter_panel

    def test_both_views_use_the_same_matches_and_keep_every_choice(self):
        self.bar.combo("category").setCurrentText("Electronics")
        self.bar.combo("ownership").setCurrentText("School-Owned")
        self.bar.combo("availability").setCurrentText("Available")
        self.screen.search_input.setText("e")
        want = set(expected(category="Electronics", ownership="school",
                            status="available", search="e"))
        self.assertTrue(want)
        for mode in (VIEW_LIST, VIEW_GRID, VIEW_LIST, VIEW_GRID):
            self.screen.set_view_mode(mode)
            self.assertEqual(self.bar.category, "Electronics")
            self.assertEqual(self.bar.ownership, "school")
            self.assertEqual(self.bar.availability, "available")
            self.assertEqual(self.screen.search_input.text(), "e")
            self.assertEqual(set(self.screen.visible_items), want)
            self.assertEqual({r.item for r in self.screen.visible_rows}, want)
            self.assertEqual(len(self.bar.chips()), 3)

    def test_filtering_in_list_view_updates_the_list_rows(self):
        self.screen.set_view_mode(VIEW_LIST)
        self.bar.combo("ownership").setCurrentText("Student-Owned")
        self.assertEqual({r.item for r in self.screen.visible_rows},
                         set(expected(ownership="student")))

    def test_filters_do_not_reset_each_other_or_the_search(self):
        self.screen.search_input.setText("python")
        self.bar.combo("category").setCurrentText("Programming")
        self.bar.combo("availability").setCurrentText("Available")
        self.bar.combo("ownership").setCurrentText("Student-Owned")
        self.assertEqual((self.bar.category, self.bar.availability, self.bar.ownership),
                         ("Programming", "available", "student"))
        self.assertEqual(self.screen.search_input.text(), "python")

    def test_the_saved_view_preference_signal_is_unaffected_by_filtering(self):
        seen = []
        self.screen.view_mode_changed.connect(seen.append)
        self.bar.combo("category").setCurrentText("Science")
        self.bar.clear_button.click()
        self.assertEqual(seen, [])
        self.screen.list_view_button.click()
        self.assertEqual(seen, [VIEW_LIST])


class ItemActionAndLayoutTests(unittest.TestCase):
    def test_item_actions_work_on_filtered_results(self):
        screen = CatalogScreen()
        screen.filter_panel.combo("availability").setCurrentText("Available")
        sent, stars = [], []
        screen.direct_request_requested.connect(sent.append)
        screen.bookmark_toggled.connect(lambda i, on: stars.append((i, on)))
        card = screen._visible_cards[0]
        card.request_button.click()
        card.bookmark_button.click()
        self.assertEqual(sent, [card.item])
        self.assertEqual(stars, [(card.item, True)])
        screen.filter_panel.combo("availability").setCurrentText("Unavailable")
        blocked = screen._visible_cards[0]
        blocked.request_button.click()
        self.assertEqual(sent, [card.item])  # unavailable items still cannot be requested

    def test_catalog_with_unknown_values_builds_and_filters_without_errors(self):
        base = SAMPLE_ITEMS[0]
        items = [dataclasses.replace(base, title="A", copies_available=None),
                 dataclasses.replace(base, title="B", ownership="", category="Unlisted"),
                 dataclasses.replace(base, title="C", collections=None, owner_note="")]
        screen = CatalogScreen(items=items)
        self.assertEqual(len(screen.visible_items), 3)
        screen.filter_panel.combo("availability").setCurrentText("Available")
        self.assertEqual({i.title for i in screen.visible_items}, {"B", "C"})
        screen.set_view_mode(VIEW_LIST)
        screen.filter_panel.combo("availability").setCurrentText("Unavailable")
        self.assertEqual(screen.visible_items, [])
        screen.filter_panel.combo("availability").setCurrentIndex(0)
        screen.filter_panel.combo("category").setCurrentText("Unlisted")
        self.assertEqual([i.title for i in screen.visible_items], ["B"])

    def test_filters_wrap_and_nothing_is_clipped_at_small_and_laptop_widths(self):
        screen = CatalogScreen()
        screen.filter_panel.combo("category").setCurrentText("Electronics")
        screen.filter_panel.combo("ownership").setCurrentText("School-Owned")
        screen.filter_panel.combo("availability").setCurrentText("Available")
        for width in (700, 1000, 1366):
            screen.resize(width, 720)
            screen.show()
            _app.processEvents()
            bar = screen.filter_panel
            self.assertGreaterEqual(bar.dropdown_row._columns, 1)
            for combo in bar._combos.values():
                self.assertGreaterEqual(combo.width(), 100, width)
            for chip in bar.chips():
                self.assertTrue(bar.chip_flow_host.rect().contains(chip.geometry()), width)
        screen.hide()

    def test_the_old_vertical_panel_is_gone(self):
        self.assertFalse(hasattr(cs, "FilterPanel"))


if __name__ == "__main__":
    unittest.main()
