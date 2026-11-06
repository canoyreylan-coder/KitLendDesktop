"""Step 17 tests: Browse Catalog Grid/List toggle and its saved preference.

Run from the project folder:   python -m unittest discover -s tests -p "test_catalog_view.py" -v

Groups 1-2 need no window (a temporary database only). Groups 3-5 open the Catalog in Qt's
invisible "offscreen" mode. Nothing here ever touches your real database.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import database  # noqa: E402
from app.auth_service import AuthService  # noqa: E402
from app.preference_service import (  # noqa: E402
    CATALOG_VIEW_KEY,
    VIEW_GRID,
    VIEW_LIST,
    PreferenceError,
    PreferenceService,
)

try:
    from PySide6.QtWidgets import QApplication, QLabel
    from app import catalog_screen  # noqa: F401
    from app.catalog_screen import (
        SAMPLE_ITEMS,
        CatalogItem,
        CatalogScreen,
        ItemList,
        filter_items,
    )
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

PW = "correct horse"


# ======================================================================
# 1. THE SAVED PREFERENCE (temporary database, no window)
# ======================================================================
class PreferenceServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")
        self.prefs = PreferenceService(self.db)

    def rows(self, sql, params=()):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_new_account_gets_grid_and_nothing_is_written(self):
        self.assertEqual(self.prefs.get_catalog_view(self.ana.id), VIEW_GRID)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM student_preferences")[0][0], 0)

    def test_choice_is_remembered_after_a_restart(self):
        self.prefs.set_catalog_view(self.ana.id, VIEW_LIST)
        self.assertEqual(PreferenceService(self.db).get_catalog_view(self.ana.id), VIEW_LIST)
        self.prefs.set_catalog_view(self.ana.id, VIEW_GRID)
        self.assertEqual(PreferenceService(self.db).get_catalog_view(self.ana.id), VIEW_GRID)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM student_preferences")[0][0], 1)

    def test_each_account_has_its_own_choice(self):
        self.prefs.set_catalog_view(self.ana.id, VIEW_LIST)
        self.assertEqual(self.prefs.get_catalog_view(self.ben.id), VIEW_GRID)
        self.prefs.set_catalog_view(self.ben.id, VIEW_GRID)
        self.assertEqual(self.prefs.get_catalog_view(self.ana.id), VIEW_LIST)

    def test_unknown_views_are_refused_and_damaged_values_fall_back_to_grid(self):
        with self.assertRaises(PreferenceError):
            self.prefs.set_catalog_view(self.ana.id, "tiles")
        self.assertEqual(self.prefs.get_catalog_view(self.ana.id), VIEW_GRID)
        self.prefs.set(self.ana.id, CATALOG_VIEW_KEY, "garbage")
        self.assertEqual(self.prefs.get_catalog_view(self.ana.id), VIEW_GRID)

    def test_an_unreadable_database_never_breaks_opening_the_catalog(self):
        broken = PreferenceService(os.path.join(self.tmp.name, "no", "such", "dir", "x.db"))
        self.assertEqual(broken.get_catalog_view(1), VIEW_GRID)
        with self.assertRaises(PreferenceError):
            broken.set_catalog_view(1, VIEW_LIST)

    def test_a_bad_student_id_is_refused(self):
        with self.assertRaises(PreferenceError):
            self.prefs.set_catalog_view(None, VIEW_LIST)

    def test_saving_changes_no_account_or_borrowing_data(self):
        before = (self.rows("SELECT * FROM students ORDER BY id"),
                  self.rows("SELECT COUNT(*) FROM borrow_requests"),
                  self.rows("SELECT COUNT(*) FROM notifications"))
        self.prefs.set_catalog_view(self.ana.id, VIEW_LIST)
        after = (self.rows("SELECT * FROM students ORDER BY id"),
                 self.rows("SELECT COUNT(*) FROM borrow_requests"),
                 self.rows("SELECT COUNT(*) FROM notifications"))
        self.assertEqual(before, after)


# ======================================================================
# 2. BACKWARD COMPATIBILITY: a Step 16 database opens, and nothing is lost
# ======================================================================
class OldDatabaseTests(unittest.TestCase):
    def test_a_step_16_database_gets_the_new_table_and_keeps_every_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.path.join(tmp, "step16.db")
            conn = sqlite3.connect(old)
            conn.executescript(database.SCHEMA)
            conn.execute(database._MIGRATION_TABLE)
            for version, name, statements in database.MIGRATIONS:
                if version <= 6:  # exactly what Step 16 had
                    for statement in statements:
                        conn.execute(statement)
                    conn.execute("INSERT INTO schema_migrations VALUES (?, ?, 't')",
                                 (version, name))
            conn.commit()
            conn.close()

            student = AuthService(old).register("Old Account", "old@csucc.edu.ph", PW, PW, student_id_number="ID-OLD")
            conn = sqlite3.connect(old)
            students_before = conn.execute("SELECT * FROM students").fetchall()
            conn.close()

            for _ in range(2):  # repeatable
                self.assertEqual(
                    PreferenceService(old).get_catalog_view(student.id), VIEW_GRID)
            conn = sqlite3.connect(old)
            self.assertEqual(conn.execute("SELECT * FROM students").fetchall(), students_before)
            versions = [r[0] for r in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY 1")]
            self.assertEqual(versions[-1], max(m[0] for m in database.MIGRATIONS))
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM student_preferences").fetchone()[0], 0)
            conn.close()
            self.assertEqual(AuthService(old).login("old@csucc.edu.ph", PW).id, student.id)


# ======================================================================
# 3. THE TOGGLE AND BOTH VIEWS (Catalog screen, offscreen)
# ======================================================================
if HAVE_QT:
    _app = QApplication.instance() or QApplication([])

    @dataclass(frozen=True)
    class ConditionItem(CatalogItem):
        """An item that HAS a recorded condition (no real item does yet)."""
        condition: str = ""


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class ToggleTests(unittest.TestCase):
    def setUp(self):
        self.screen = CatalogScreen()
        self.addCleanup(self.screen.deleteLater)

    def widgets(self, mode):
        return self.screen._cards if mode == VIEW_GRID else self.screen._rows

    def test_grid_is_the_default(self):
        self.assertEqual(self.screen.view_mode, VIEW_GRID)
        self.assertTrue(self.screen.grid_view_button.isChecked())
        self.assertFalse(self.screen.list_view_button.isChecked())
        self.assertFalse(self.screen.grid.isHidden())
        self.assertTrue(self.screen.list_view.isHidden())

    def test_buttons_switch_the_layout_and_highlight_the_active_view(self):
        self.screen.list_view_button.click()
        self.assertEqual(self.screen.view_mode, VIEW_LIST)
        self.assertTrue(self.screen.list_view_button.isChecked())
        self.assertFalse(self.screen.grid_view_button.isChecked())
        self.assertTrue(self.screen.grid.isHidden())
        self.assertFalse(self.screen.list_view.isHidden())
        self.screen.grid_view_button.click()
        self.assertEqual(self.screen.view_mode, VIEW_GRID)
        self.assertTrue(self.screen.grid_view_button.isChecked())
        self.assertTrue(self.screen.list_view.isHidden())
        self.assertFalse(self.screen.grid.isHidden())

    def test_buttons_have_names_tooltips_and_icons(self):
        for button, name in ((self.screen.grid_view_button, "Grid view"),
                             (self.screen.list_view_button, "List view")):
            self.assertEqual(button.toolTip(), name)
            self.assertEqual(button.accessibleName(), name)
            self.assertFalse(button.icon().isNull())
            self.assertTrue(button.isCheckable())

    def test_clicking_the_active_view_again_changes_nothing(self):
        changes = []
        self.screen.view_mode_changed.connect(changes.append)
        self.screen.grid_view_button.click()
        self.assertEqual(changes, [])
        self.assertTrue(self.screen.grid_view_button.isChecked())
        self.screen.list_view_button.click()
        self.screen.list_view_button.click()
        self.assertEqual(changes, [VIEW_LIST])

    def test_restoring_a_saved_choice_is_silent_and_unknown_values_mean_grid(self):
        changes = []
        self.screen.view_mode_changed.connect(changes.append)
        self.screen.set_view_mode(VIEW_LIST, emit=False)
        self.assertEqual((self.screen.view_mode, changes), (VIEW_LIST, []))
        self.screen.set_view_mode("tiles")
        self.assertEqual(self.screen.view_mode, VIEW_GRID)

    def test_both_views_show_the_same_records_in_the_same_order(self):
        self.assertEqual(len(self.screen._cards), len(SAMPLE_ITEMS))
        self.assertEqual(len(self.screen._rows), len(SAMPLE_ITEMS))
        self.assertEqual([c.item for c in self.screen._cards],
                         [r.item for r in self.screen._rows])
        self.screen.set_view_mode(VIEW_LIST)
        self.assertEqual(self.screen.visible_items, [r.item for r in self.screen.visible_rows])
        self.assertEqual(len(self.screen.visible_rows), len(SAMPLE_ITEMS))

    def test_switching_never_duplicates_or_alters_items(self):
        before_items = [c.item for c in self.screen._cards]
        for _ in range(4):
            self.screen.list_view_button.click()
            self.screen.grid_view_button.click()
        self.assertEqual([c.item for c in self.screen._cards], before_items)
        self.assertEqual([r.item for r in self.screen._rows], before_items)
        self.assertEqual(len(self.screen._cards), len(SAMPLE_ITEMS))
        self.assertEqual(len(self.screen._rows), len(SAMPLE_ITEMS))
        self.assertEqual(self.screen.grid._grid.count(), len(SAMPLE_ITEMS))

    def test_search_and_filters_survive_switching_and_match_in_both_views(self):
        panel = self.screen.filter_panel
        panel.combo("category").setCurrentText("Electronics")
        panel.combo("availability").setCurrentText("Available")
        self.screen.search_input.setText("e")
        expected = filter_items(SAMPLE_ITEMS, search="e", category="Electronics",
                                available_only=True)
        self.assertTrue(expected)  # the check below needs something to compare
        for mode in (VIEW_LIST, VIEW_GRID, VIEW_LIST):
            self.screen.set_view_mode(mode)
            self.assertEqual(self.screen.search_input.text(), "e")
            self.assertEqual(self.screen.sticky_search_input.text(), "e")
            self.assertEqual(panel.category, "Electronics")
            self.assertTrue(panel.available_only)
            self.assertEqual(set(self.screen.visible_items), set(expected))
            self.assertEqual({r.item for r in self.screen.visible_rows}, set(expected))
        self.assertEqual(self.screen.result_label.text(),
                         f"Showing {len(expected)} of {len(SAMPLE_ITEMS)} items")

    def test_filtering_while_in_list_view_updates_the_list(self):
        self.screen.set_view_mode(VIEW_LIST)
        self.screen.search_input.setText("python")
        rows = {r.item for r in self.screen.visible_rows}
        self.assertEqual(rows, set(filter_items(SAMPLE_ITEMS, search="python")))
        self.assertTrue(0 < len(rows) < len(SAMPLE_ITEMS))
        shown = [r for r in self.screen._rows if not r.isHidden()]
        self.assertEqual({r.item for r in shown}, rows)
        self.screen.set_view_mode(VIEW_GRID)  # the cards must have followed the same search
        self.assertEqual({c.item for c in self.screen._cards if not c.isHidden()}, rows)

    def test_no_results_state_works_in_list_view(self):
        self.screen.set_view_mode(VIEW_LIST)
        self.screen.search_input.setText("zzzz-no-such-item")
        self.assertEqual(self.screen.visible_items, [])
        self.assertEqual(self.screen.visible_rows, [])
        self.assertFalse(self.screen.empty_state.isHidden())
        self.assertTrue(self.screen.list_view.isHidden())
        self.assertEqual(self.screen.empty_title.text(), "No items found")
        self.screen.empty_button.click()  # Clear filters
        self.assertTrue(self.screen.empty_state.isHidden())
        self.assertFalse(self.screen.list_view.isHidden())
        self.assertEqual(len(self.screen.visible_rows), len(SAMPLE_ITEMS))

    def test_empty_catalog_state_works_in_both_views(self):
        screen = CatalogScreen(items=[])
        self.addCleanup(screen.deleteLater)
        for mode in (VIEW_GRID, VIEW_LIST):
            screen.set_view_mode(mode)
            self.assertEqual(screen.empty_title.text(), "The catalog is empty")
            self.assertFalse(screen.empty_state.isHidden())
            self.assertTrue(screen.empty_button.isHidden())
            self.assertTrue(screen.grid.isHidden())
            self.assertTrue(screen.list_view.isHidden())


# ======================================================================
# 4. ONE SET OF BEHAVIOURS (every item action is identical in both views)
# ======================================================================
def label_texts(widget):
    """The FULL text of every label (ElidedLabel shortens what it shows to fit its width)."""
    return {getattr(label, "_full_text", label.text()) for label in widget.findChildren(QLabel)}


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class SharedBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.screen = CatalogScreen()
        self.addCleanup(self.screen.deleteLater)
        self.requested, self.toggled, self.selected = [], [], []
        self.screen.direct_request_requested.connect(self.requested.append)
        self.screen.bookmark_toggled.connect(lambda i, on: self.toggled.append((i, on)))
        self.screen.item_selected.connect(self.selected.append)

    def widgets(self, mode):
        return self.screen._cards if mode == VIEW_GRID else self.screen._rows

    def test_request_now_behaves_the_same_in_both_views(self):
        for mode in (VIEW_GRID, VIEW_LIST):
            with self.subTest(mode=mode):
                self.requested.clear()
                self.screen.set_view_mode(mode)
                available = next(w for w in self.widgets(mode) if w.item.is_available)
                unavailable = next(w for w in self.widgets(mode) if not w.item.is_available)
                self.assertFalse(unavailable.request_button.isEnabled())
                unavailable.request_button.click()
                self.assertEqual(self.requested, [])
                available.request_button.click()
                self.assertEqual(self.requested, [available.item])  # exactly once

    def test_bookmark_behaves_the_same_in_both_views(self):
        for mode in (VIEW_GRID, VIEW_LIST):
            with self.subTest(mode=mode):
                self.screen.set_bookmarked_items([])
                self.toggled.clear()
                self.screen.set_view_mode(mode)
                widget = self.widgets(mode)[0]
                widget.bookmark_button.click()
                self.assertEqual(self.toggled, [(widget.item, True)])
                self.assertEqual(self.screen.bookmarked_items, [widget.item])
                widget.bookmark_button.click()
                self.assertEqual(self.toggled[-1], (widget.item, False))
                self.assertEqual(self.screen.bookmarked_items, [])

    def test_a_star_set_in_one_view_shows_in_the_other(self):
        card, row = self.screen._cards[2], self.screen._rows[2]
        self.screen.set_view_mode(VIEW_LIST)
        row.bookmark_button.click()
        self.assertTrue(card.bookmark_button.isChecked())
        self.assertEqual(card.bookmark_button.text(), "★")
        self.assertEqual(self.toggled, [(row.item, True)])  # one signal, no echo from the card
        self.screen.set_view_mode(VIEW_GRID)
        card.bookmark_button.click()
        self.assertFalse(row.bookmark_button.isChecked())
        self.assertEqual(self.toggled, [(row.item, True), (row.item, False)])

    def test_outside_sync_updates_both_views_without_a_signal(self):
        items = [self.screen._cards[0].item, self.screen._cards[3].item]
        self.screen.set_bookmarked_items(items)
        self.assertEqual(self.toggled, [])
        for widget in self.screen._cards + self.screen._rows:
            self.assertEqual(widget.bookmark_button.isChecked(), widget.item in items)
        self.screen.set_view_mode(VIEW_LIST)
        self.assertEqual(self.screen.bookmarked_items, items)

    def test_clicking_an_item_selects_it_in_both_views(self):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        self.screen.resize(1294, 700)
        self.screen.show()
        for mode in (VIEW_GRID, VIEW_LIST):
            with self.subTest(mode=mode):
                self.selected.clear()
                self.screen.set_view_mode(mode)
                _app.processEvents()
                widget = self.widgets(mode)[0]
                QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
                self.assertEqual(self.selected, [widget.item])
                self.requested.clear()
                # ...but a click on Request Now is a request, not a "select"
                self.selected.clear()
                button = next(w for w in self.widgets(mode) if w.item.is_available).request_button
                button.click()
                self.assertEqual(self.selected, [])
        self.screen.hide()

    def test_cards_and_rows_share_one_implementation_of_the_actions(self):
        from app.catalog_screen import CatalogItemWidget, ItemCard, ItemRow
        self.assertTrue(issubclass(ItemCard, CatalogItemWidget))
        self.assertTrue(issubclass(ItemRow, CatalogItemWidget))
        for name in ("_on_request_clicked", "_on_bookmark_toggled", "set_bookmarked",
                     "mousePressEvent"):
            self.assertIs(getattr(ItemCard, name), getattr(ItemRow, name), name)

    def test_rows_show_the_information_the_cards_show_and_never_invent_any(self):
        from app.catalog_screen import ItemRow
        item = SAMPLE_ITEMS[0]
        row = ItemRow(item)
        self.addCleanup(row.deleteLater)
        texts = label_texts(row)
        self.assertIn(item.title, texts)
        self.assertIn(item.creator_line, texts)
        self.assertIn(f"{item.kind} · {item.category}", texts)
        self.assertIn(item.ownership_label, texts)
        self.assertIn(item.owner_note, texts)
        self.assertIn(item.availability_text, texts)
        self.assertEqual(row.request_button.isEnabled(), item.is_available)
        self.assertFalse(any(t.startswith("Condition") for t in texts))  # none recorded

    def test_condition_appears_only_when_one_is_recorded(self):
        from app.catalog_screen import ItemRow
        base = SAMPLE_ITEMS[0]
        fields = {name: getattr(base, name) for name in (
            "title", "creator", "category", "kind", "ownership", "owner_note",
            "copies_total", "copies_available", "collections")}
        with_condition = ItemRow(ConditionItem(**fields, condition="Good"))
        self.addCleanup(with_condition.deleteLater)
        self.assertIn("Condition: Good", label_texts(with_condition))
        blank = ItemRow(ConditionItem(**fields, condition="  "))
        self.addCleanup(blank.deleteLater)
        self.assertFalse(any(t.startswith("Condition") for t in label_texts(blank)))


# ======================================================================
# 5. RESPONSIVE LAYOUT (1366x768 laptop, small window, maximized)
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class ResponsiveTests(unittest.TestCase):
    # (width, height) of the Catalog page itself: the window minus the 72px sidebar
    SIZES = ((1294, 700), (1100, 620), (728, 420), (1848, 1000))

    def setUp(self):
        self.screen = CatalogScreen()
        self.addCleanup(self.screen.deleteLater)

    def test_row_density_follows_the_width(self):
        self.assertEqual(ItemList.density_for_width(1000), "wide")
        self.assertEqual(ItemList.density_for_width(700), "compact")
        self.assertEqual(ItemList.density_for_width(400), "tiny")

    def test_neither_view_scrolls_sideways_or_squeezes_its_items(self):
        for mode in (VIEW_GRID, VIEW_LIST):
            self.screen.set_view_mode(mode)
            for width, height in self.SIZES:
                with self.subTest(mode=mode, size=(width, height)):
                    self.screen.resize(width, height)
                    self.screen.show()
                    _app.processEvents()
                    _app.processEvents()  # a density change re-lays the rows out once more
                    scroll = self.screen.catalog_scroll
                    self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                    viewport_width = scroll.viewport().width()
                    if mode == VIEW_LIST:
                        lst = self.screen.list_view
                        self.assertEqual(lst.density, ItemList.density_for_width(lst.width()))
                        self.assertLessEqual(lst.width(), viewport_width)
                        for row in self.screen.visible_rows:
                            self.assertEqual(row.density, lst.density)
                            self.assertGreaterEqual(row.width(), row.minimumSizeHint().width())
                            self.assertLessEqual(row.geometry().right(), lst.width())
                    else:
                        self.assertGreaterEqual(self.screen.grid._columns, 1)
        self.screen.hide()

    def test_folded_row_details_replace_the_columns_on_narrow_lists(self):
        self.screen.set_view_mode(VIEW_LIST)
        self.screen.resize(1294, 700)
        self.screen.show()
        _app.processEvents()
        row = self.screen.visible_rows[0]
        self.assertEqual(row.density, "wide")
        self.assertFalse(row.category_cell.isHidden())
        self.assertTrue(row.meta_line.isHidden())
        self.screen.resize(728, 420)
        _app.processEvents()
        _app.processEvents()
        self.assertTrue(row.category_cell.isHidden())
        self.assertTrue(row.owner_cell.isHidden())
        self.assertFalse(row.meta_line.isHidden())
        self.assertFalse(row.request_button.isHidden())      # actions never disappear
        self.assertFalse(row.bookmark_button.isHidden())
        self.screen.hide()

    def test_switching_view_keeps_the_page_size_and_state(self):
        self.screen.resize(1294, 700)
        self.screen.show()
        self.screen.search_input.setText("python")
        _app.processEvents()
        size = self.screen.size()
        for _ in range(3):
            self.screen.list_view_button.click()
            self.screen.grid_view_button.click()
        self.assertEqual(self.screen.size(), size)
        self.assertEqual(self.screen.search_input.text(), "python")
        self.screen.hide()


# ======================================================================
# 6. INSIDE THE REAL DASHBOARD (temporary database, per account)
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardPreferenceTests(unittest.TestCase):
    def setUp(self):
        from test_notifications import TempDbCase

        class Case(TempDbCase):
            def runTest(self):  # pragma: no cover
                pass

        self.case = Case()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)

    def build(self, student, **kw):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        dash = StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.case.requests, **kw)
        self.addCleanup(dash.deleteLater)
        return dash

    def test_new_account_opens_the_catalog_in_grid_view(self):
        dash = self.build(self.case.ana)
        self.assertEqual(dash.catalog_page.view_mode, VIEW_GRID)
        self.assertTrue(dash.stores_preferences)

    def test_choice_is_saved_and_restored_when_the_student_logs_in_again(self):
        first = self.build(self.case.ana)
        first.go_to("catalog")
        first.catalog_page.list_view_button.click()
        self.assertEqual(PreferenceService(self.case.db).get_catalog_view(self.case.ana.id),
                         VIEW_LIST)
        again = self.build(self.case.ana)  # a fresh login / a restart of KitLend
        self.assertEqual(again.catalog_page.view_mode, VIEW_LIST)
        self.assertFalse(again.catalog_page.list_view_button.isHidden())
        again.catalog_page.grid_view_button.click()
        third = self.build(self.case.ana)
        self.assertEqual(third.catalog_page.view_mode, VIEW_GRID)

    def test_another_account_still_gets_grid(self):
        self.build(self.case.ana).catalog_page.list_view_button.click()
        self.assertEqual(self.build(self.case.ben).catalog_page.view_mode, VIEW_GRID)

    def test_restoring_the_saved_choice_writes_nothing(self):
        PreferenceService(self.case.db).set_catalog_view(self.case.ana.id, VIEW_LIST)
        before = self.case.query("SELECT updated_at FROM student_preferences")
        self.build(self.case.ana)
        self.assertEqual(self.case.query("SELECT updated_at FROM student_preferences"), before)

    def test_a_failed_save_does_not_interrupt_browsing(self):
        class Failing(PreferenceService):
            def set_catalog_view(self, student_id, mode):
                raise PreferenceError("disk full")

        dash = self.build(self.case.ana, preference_service=Failing(self.case.db))
        dash.catalog_page.list_view_button.click()  # must not raise
        self.assertEqual(dash.catalog_page.view_mode, VIEW_LIST)

    def test_switching_the_view_leaves_the_sidebar_and_other_data_alone(self):
        dash = self.build(self.case.ana)
        keys = set(dash._nav_buttons)
        layouts = self.case.query("SELECT COUNT(*) FROM sidebar_layouts")
        students = self.case.query("SELECT * FROM students ORDER BY id")
        dash.catalog_page.list_view_button.click()
        dash.catalog_page.grid_view_button.click()
        self.assertEqual(set(dash._nav_buttons), keys)
        self.assertEqual(self.case.query("SELECT COUNT(*) FROM sidebar_layouts"), layouts)
        self.assertEqual(self.case.query("SELECT * FROM students ORDER BY id"), students)

    def test_item_actions_still_reach_my_list_from_the_list_view(self):
        dash = self.build(self.case.ana)
        dash.go_to("catalog")
        dash.catalog_page.set_view_mode(VIEW_LIST)
        row = dash.catalog_page._rows[0]
        row.bookmark_button.click()
        self.assertEqual(dash._bookmarks, [row.item])
        self.assertEqual(dash.my_list_page._saved_items, [row.item])  # reached My List
        self.assertTrue(dash.catalog_page._cards[0].bookmark_button.isChecked())  # grid agrees
        available = next(r for r in dash.catalog_page._rows if r.item.is_available)
        self.assertTrue(available.request_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
