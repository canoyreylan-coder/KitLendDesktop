"""Step 14F tests: freeform sidebar layout (positions + sizes per icon, saved per account).

Groups 1-2 need no window and no PySide6 (plain Python + a temporary SQLite file).
Group 3 opens the real dashboard in Qt's invisible "offscreen" mode and is skipped
automatically if PySide6 is not installed.

Run from the project folder:   python -m unittest discover -s tests -v
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import database  # noqa: E402
from app import sidebar_layout as sl  # noqa: E402
from app import theme  # noqa: E402
from app.auth_service import AuthService  # noqa: E402
from app.sidebar_layout import SidebarLayout  # noqa: E402
from app.sidebar_layout_service import SidebarLayoutError, SidebarLayoutService  # noqa: E402

PW = "Passw0rd-long"
HEIGHTS = (500, 650, 900, 1200)


# ======================================================================
# 1. THE LAYOUT MODEL (plain data, no window)
# ======================================================================
class DefaultLayoutTests(unittest.TestCase):
    def test_the_defaults_match_the_step_14e_sizes(self):
        self.assertEqual(sl.SIDEBAR_WIDTH, theme.SIDEBAR_WIDTH)
        self.assertEqual(sl.DEFAULT_ICON_SIZE, theme.NAV_ICON_SIZE)
        self.assertEqual(sl.DEFAULT_AVATAR_SIZE, theme.AVATAR_SIZE)
        self.assertEqual(sl.box_for("dashboard", sl.DEFAULT_ICON_SIZE), theme.NAV_BUTTON_SIZE)
        self.assertEqual(sl.box_for(sl.KEY_AVATAR, sl.DEFAULT_AVATAR_SIZE), theme.AVATAR_SIZE)

    def test_there_are_exactly_ten_items_in_top_to_bottom_order(self):
        self.assertEqual(sl.ITEM_KEYS, (
            "avatar", "dashboard", "catalog", "my_list", "my_requests", "borrowings",
            "reservations", "notifications", "settings", "logout"))
        self.assertEqual(set(sl.ITEM_LABELS), set(sl.ITEM_KEYS))

    def test_default_items_are_inside_the_rail_and_do_not_overlap(self):
        for height in HEIGHTS:
            geometry = SidebarLayout().geometry(height)
            rects = [geometry[key] for key in sl.ITEM_KEYS]
            for x, y, box in rects:
                self.assertTrue(0 <= x and x + box <= sl.SIDEBAR_WIDTH, height)
                self.assertTrue(0 <= y and y + box <= height, height)
            for (x1, y1, b1), (x2, y2, _b2) in zip(rects, rects[1:]):
                self.assertLessEqual(y1 + b1, y2, height)  # strictly top to bottom, no overlap

    def test_default_icons_are_spread_evenly_and_log_out_hugs_the_bottom(self):
        geometry = SidebarLayout().geometry(820)
        rects = [geometry[key] for key in sl.ITEM_KEYS]
        gaps = [rects[i + 1][1] - (rects[i][1] + rects[i][2]) for i in range(len(rects) - 1)]
        self.assertLessEqual(max(gaps) - min(gaps), 2)
        self.assertEqual(820 - (rects[-1][1] + rects[-1][2]), sl.BOTTOM_MARGIN)

    def test_a_new_layout_is_the_default(self):
        self.assertTrue(SidebarLayout().is_default())
        self.assertEqual(SidebarLayout().customised_keys(), [])
        self.assertEqual(SidebarLayout().size_of("avatar"), 40)
        self.assertEqual(SidebarLayout().size_of("catalog"), 24)

    def test_unknown_items_are_rejected(self):
        with self.assertRaises(KeyError):
            SidebarLayout().set_size("admin_panel", 30, 650)
        with self.assertRaises(KeyError):
            SidebarLayout().set_position("admin_panel", 1, 1, 650)


class IndependentSizeTests(unittest.TestCase):
    def test_resizing_one_icon_changes_only_that_icon(self):
        layout = SidebarLayout()
        before = layout.geometry(650)
        self.assertTrue(layout.set_size("dashboard", 34, 650))
        after = layout.geometry(650)
        self.assertEqual(after["dashboard"][2], 34 + sl.ICON_PADDING)
        for key in sl.ITEM_KEYS:
            if key != "dashboard":
                self.assertEqual(after[key], before[key], key)
        self.assertEqual(layout.customised_keys(), ["dashboard"])

    def test_every_item_can_have_its_own_different_size(self):
        layout = SidebarLayout()
        wanted = {"avatar": 45, "dashboard": 34, "catalog": 28, "my_list": 32,
                  "notifications": 26, "logout": 20}
        for key, size in wanted.items():
            self.assertTrue(layout.set_size(key, size, 1000), key)
        for key, size in wanted.items():
            self.assertEqual(layout.size_of(key), size)
        self.assertEqual(layout.size_of("settings"), 24)  # untouched
        self.assertEqual(layout.geometry(1000)["avatar"][2], 45)

    def test_sizes_are_limited_to_a_sensible_range(self):
        layout = SidebarLayout()
        layout.set_size("catalog", 500, 1000)
        self.assertEqual(layout.size_of("catalog"), sl.MAX_ICON_SIZE)
        layout.set_size("catalog", -5, 1000)
        self.assertEqual(layout.size_of("catalog"), sl.MIN_ICON_SIZE)
        layout.set_size("avatar", 1, 1000)
        self.assertEqual(layout.size_of("avatar"), sl.MIN_AVATAR_SIZE)
        layout.set_size("avatar", 999, 1000)
        self.assertEqual(layout.size_of("avatar"), sl.MAX_AVATAR_SIZE)

    def test_resizing_keeps_the_icons_centre_where_it_was(self):
        layout = SidebarLayout()
        layout.set_position("catalog", 20, 300, 800)
        x, y, box = layout.geometry(800)["catalog"]
        centre = (x + box / 2.0, y + box / 2.0)
        layout.set_size("catalog", 36, 800)
        x2, y2, box2 = layout.geometry(800)["catalog"]
        self.assertAlmostEqual(x2 + box2 / 2.0, centre[0], delta=1)
        self.assertAlmostEqual(y2 + box2 / 2.0, centre[1], delta=1)

    def test_growing_into_a_neighbour_is_refused_and_changes_nothing(self):
        layout = SidebarLayout()
        x, y, box = layout.geometry(800)["catalog"]
        # lift My List so it just touches Catalog (a small overlap is allowed)
        self.assertTrue(layout.set_position("my_list", x, y + box - 10, 800))
        before = layout.to_dict()
        self.assertFalse(layout.set_size("catalog", 44, 800))  # the bigger icon would cover it
        self.assertEqual(layout.to_dict(), before)
        self.assertEqual(layout.size_of("catalog"), 24)


class PositionTests(unittest.TestCase):
    # The default rail is nearly full, so these tests nudge icons inside their own gaps.
    def test_an_item_can_be_put_somewhere_else_and_nothing_else_moves(self):
        layout = SidebarLayout()
        before = layout.geometry(900)
        x, y, _box = before["my_list"]
        self.assertTrue(layout.set_position("my_list", x - 8, y + 9, 900))
        after = layout.geometry(900)
        self.assertEqual(after["my_list"][:2], (x - 8, y + 9))
        for key in sl.ITEM_KEYS:
            if key != "my_list":
                self.assertEqual(after[key], before[key], key)

    def test_avatar_and_log_out_can_be_moved_too(self):
        layout = SidebarLayout()
        base = layout.geometry(900)
        self.assertTrue(layout.set_position("avatar", 28, base["avatar"][1] + 3, 900))
        self.assertTrue(layout.set_position("logout", 2, base["logout"][1] - 4, 900))
        geometry = layout.geometry(900)
        self.assertEqual(geometry["avatar"][:2], (28, base["avatar"][1] + 3))
        self.assertEqual(geometry["logout"][:2], (2, base["logout"][1] - 4))

    def test_positions_are_kept_inside_the_visible_rail(self):
        layout = SidebarLayout()
        layout.set_position("logout", 500, 9999, 650)
        x, y, box = layout.geometry(650)["logout"]
        self.assertEqual((x, y), (sl.SIDEBAR_WIDTH - box, 650 - box))
        layout.set_position("avatar", -40, -40, 650)
        self.assertEqual(layout.geometry(650)["avatar"][:2], (0, 0))

    def test_top_half_items_keep_their_distance_from_the_top_when_the_window_changes(self):
        layout = SidebarLayout()
        y = layout.geometry(700)["catalog"][1] + 4
        self.assertTrue(layout.set_position("catalog", 10, y, 700))
        for height in (500, 700, 1100):
            self.assertEqual(layout.geometry(height)["catalog"][1], y)

    def test_bottom_half_items_keep_their_distance_from_the_bottom(self):
        layout = SidebarLayout()
        x, y, box = layout.geometry(700)["settings"]
        self.assertTrue(layout.set_position("settings", 10, y + 3, 700))
        gap = 700 - (y + 3 + box)
        for height in (600, 700, 1000):
            _x, new_y, new_box = layout.geometry(height)["settings"]
            self.assertEqual(height - (new_y + new_box), gap)

    def test_resizing_the_window_never_changes_the_saved_numbers(self):
        layout = SidebarLayout()
        x, y, _box = layout.geometry(700)["settings"]
        layout.set_position("settings", 10, y + 3, 700)
        saved = layout.to_dict()
        layout.geometry(300)
        layout.geometry(2000)
        self.assertEqual(layout.to_dict(), saved)

    def test_too_much_overlap_is_refused_and_leaves_the_layout_unchanged(self):
        layout = SidebarLayout()
        before_dict = layout.to_dict()
        x, y, _box = layout.geometry(650)["dashboard"]
        self.assertFalse(layout.set_position("catalog", x, y, 650))  # right on top of Dashboard
        self.assertEqual(layout.to_dict(), before_dict)
        self.assertTrue(layout.is_default())

    def test_a_small_overlap_is_allowed(self):
        layout = SidebarLayout()
        x, y, box = layout.geometry(650)["dashboard"]
        self.assertTrue(layout.set_position("catalog", x, y + box - 6, 650))

    def test_refused_move_keeps_an_earlier_custom_position(self):
        layout = SidebarLayout()
        layout.set_position("catalog", 40, 300, 650)
        saved = layout.to_dict()
        x, y, _b = layout.geometry(650)["dashboard"]
        self.assertFalse(layout.set_position("catalog", x, y, 650))
        self.assertEqual(layout.to_dict(), saved)


class ResetTests(unittest.TestCase):
    def test_reset_selected_icon_resets_only_that_icon(self):
        layout = SidebarLayout()
        layout.set_position("catalog", 40, 300, 650)
        layout.set_size("catalog", 36, 650)
        layout.set_size("my_list", 30, 650)
        self.assertTrue(layout.reset_item("catalog"))
        self.assertEqual(layout.customised_keys(), ["my_list"])
        self.assertEqual(layout.geometry(650)["catalog"], SidebarLayout().geometry(650)["catalog"])
        self.assertFalse(layout.reset_item("catalog"))  # nothing left to reset

    def test_reset_all_returns_to_the_default(self):
        layout = SidebarLayout()
        layout.set_position("catalog", 40, 300, 650)
        layout.set_size("avatar", 50, 650)
        self.assertTrue(layout.reset_all())
        self.assertTrue(layout.is_default())
        self.assertEqual(layout.geometry(650), SidebarLayout().geometry(650))


class SerializationTests(unittest.TestCase):
    def test_round_trip_keeps_every_size_and_position(self):
        layout = SidebarLayout()
        layout.set_position("catalog", 40, 300, 650)
        layout.set_position("settings", 3, 570, 650)
        layout.set_size("avatar", 50, 650)
        copy = SidebarLayout.from_dict(json.loads(json.dumps(layout.to_dict())))
        self.assertEqual(copy, layout)
        self.assertEqual(copy.geometry(777), layout.geometry(777))

    def test_damaged_data_is_ignored_not_an_error(self):
        for bad in (None, 5, "x", [], {}, {"items": None}, {"items": []},
                    {"items": {"catalog": "oops"}},
                    {"items": {"catalog": {"size": "big", "x": "a", "y": None}}},
                    {"items": {"catalog": {"size": 999, "x": 5, "y": 5, "anchor": "left"}}},
                    {"items": {"catalog": {"x": 5, "y": -5, "anchor": "top"}}},
                    {"items": {"catalog": {"x": True, "y": 5, "anchor": "top"}}}):
            self.assertTrue(SidebarLayout.from_dict(bad).is_default(), bad)

    def test_unknown_items_in_saved_data_are_dropped(self):
        data = {"items": {"admin_panel": {"size": 30}, "catalog": {"size": 30}}}
        layout = SidebarLayout.from_dict(data)
        self.assertEqual(layout.customised_keys(), ["catalog"])

    def test_a_good_item_survives_next_to_a_bad_one(self):
        data = {"items": {"catalog": {"size": 30}, "my_list": {"size": "huge"}}}
        self.assertEqual(SidebarLayout.from_dict(data).customised_keys(), ["catalog"])


# ======================================================================
# 2. SAVING PER ACCOUNT (temporary SQLite file, no window)
# ======================================================================
class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")
        self.service = SidebarLayoutService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, sql, params=()):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def custom(self):
        layout = SidebarLayout()
        layout.set_position("catalog", 40, 300, 650)
        layout.set_size("avatar", 50, 650)
        return layout

    def test_a_student_with_nothing_saved_gets_the_default(self):
        self.assertTrue(self.service.get_layout(self.ana.id).is_default())

    def test_a_saved_layout_comes_back_exactly(self):
        layout = self.custom()
        self.service.save_layout(self.ana.id, layout)
        self.assertEqual(SidebarLayoutService(self.db).get_layout(self.ana.id), layout)

    def test_layouts_are_per_account(self):
        self.service.save_layout(self.ana.id, self.custom())
        self.assertTrue(self.service.get_layout(self.ben.id).is_default())
        other = SidebarLayout()
        other.set_size("settings", 30, 650)
        self.service.save_layout(self.ben.id, other)
        self.assertEqual(self.service.get_layout(self.ana.id), self.custom())
        self.assertEqual(self.service.get_layout(self.ben.id), other)

    def test_saving_again_replaces_the_old_layout(self):
        self.service.save_layout(self.ana.id, self.custom())
        newer = SidebarLayout()
        newer.set_size("catalog", 30, 650)
        self.service.save_layout(self.ana.id, newer)
        self.assertEqual(self.service.get_layout(self.ana.id), newer)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM sidebar_layouts")[0][0], 1)

    def test_saving_the_default_layout_removes_the_row(self):
        self.service.save_layout(self.ana.id, self.custom())
        self.service.save_layout(self.ana.id, SidebarLayout())
        self.assertEqual(self.rows("SELECT COUNT(*) FROM sidebar_layouts")[0][0], 0)
        self.assertTrue(self.service.get_layout(self.ana.id).is_default())

    def test_damaged_saved_text_falls_back_to_the_default(self):
        self.service.save_layout(self.ana.id, self.custom())
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE sidebar_layouts SET layout_json = 'not json {'")
        conn.commit()
        conn.close()
        self.assertTrue(self.service.get_layout(self.ana.id).is_default())

    def test_bad_arguments_are_refused_with_a_friendly_error(self):
        with self.assertRaises(SidebarLayoutError):
            self.service.get_layout(None)
        with self.assertRaises(SidebarLayoutError):
            self.service.save_layout(True, SidebarLayout())
        with self.assertRaises(SidebarLayoutError):
            self.service.save_layout(self.ana.id, {"items": {}})

    def test_the_migration_is_additive_and_leaves_accounts_alone(self):
        students = self.rows("SELECT * FROM students ORDER BY id")
        self.service.get_layout(self.ana.id)  # opens the database (migrations already applied)
        self.assertEqual(self.rows("SELECT * FROM students ORDER BY id"), students)
        versions = [r[0] for r in self.rows("SELECT version FROM schema_migrations ORDER BY 1")]
        self.assertEqual(versions[-1], max(m[0] for m in database.MIGRATIONS))  # newest migration applied (11 = cleared requests)
        tables = {r[0] for r in self.rows("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("sidebar_layouts", tables)

    def test_an_existing_database_without_the_table_is_upgraded_in_place(self):
        from app import database
        old = os.path.join(self.tmp.name, "old.db")
        conn = sqlite3.connect(old)
        conn.row_factory = sqlite3.Row
        conn.executescript(database.SCHEMA)
        conn.execute(database._MIGRATION_TABLE)
        for version, name, statements in database.MIGRATIONS:
            if version <= 5:
                for statement in statements:
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migrations VALUES (?, ?, 't')", (version, name))
        conn.commit()
        conn.close()
        auth = AuthService(old)
        student = auth.register("Old Account", "old@csucc.edu.ph", PW, PW, student_id_number="ID-OLD")
        self.assertTrue(SidebarLayoutService(old).get_layout(student.id).is_default())
        self.assertEqual(auth.login("old@csucc.edu.ph", PW).id, student.id)


# ======================================================================
# 3. THE REAL SIDEBAR EDITOR (needs PySide6)
# ======================================================================
try:
    import PySide6
    from PySide6.QtWidgets import QApplication
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class SidebarEditorWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.qt_app.setStyleSheet(theme.STYLESHEET)

    def setUp(self):
        from app.dashboard_screen import StudentDashboard
        from app.request_service import RequestService
        from app.sample_data import build_demo_data, build_empty_data
        self.StudentDashboard, self.build_empty_data = StudentDashboard, build_empty_data
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.requests = RequestService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")
        self.dash = self.make_dash(self.ana)
        self.demo = StudentDashboard(build_demo_data())
        self.dash.resize(1100, 700)
        self.dash.show()
        self.qt_app.processEvents()
        self.rail = self.dash.sidebar_rail

    def tearDown(self):
        self.dash.hide()
        self.tmp.cleanup()

    def make_dash(self, student):
        return self.StudentDashboard(
            self.build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests, auth_service=self.auth)

    # ---- helpers ----
    def send_mouse(self, widget, kind, gx, gy):
        from PySide6.QtCore import QEvent, QPointF, Qt
        from PySide6.QtGui import QMouseEvent
        buttons = Qt.NoButton if kind == QEvent.MouseButtonRelease else Qt.LeftButton
        event = QMouseEvent(kind, QPointF(5, 5), QPointF(gx, gy), Qt.LeftButton, buttons,
                            Qt.NoModifier)
        QApplication.sendEvent(widget, event)

    def drag(self, key, dx, dy):
        from PySide6.QtCore import QEvent
        button = self.dash._nav_buttons.get(key) or {
            "avatar": self.dash.avatar_button, "logout": self.dash.sidebar_exit_button}[key]
        self.send_mouse(button, QEvent.MouseButtonPress, 500, 500)
        self.send_mouse(button, QEvent.MouseMove, 500 + dx, 500 + dy)
        self.send_mouse(button, QEvent.MouseButtonRelease, 500 + dx, 500 + dy)

    def start_editing(self, dash=None):
        dash = dash or self.dash
        dash.go_to("settings")
        dash.settings_page.sidebar_edit_button.click()
        self.qt_app.processEvents()

    def all_buttons(self):
        buttons = dict(self.dash._nav_buttons)
        buttons["avatar"] = self.dash.avatar_button
        buttons["logout"] = self.dash.sidebar_exit_button
        return buttons

    # ---- the default look is unchanged ----
    def test_default_sizes_are_the_step_14e_sizes(self):
        buttons = self.all_buttons()
        for key in sl.NAV_KEYS + ("logout",):
            self.assertEqual((buttons[key].width(), buttons[key].height()),
                             (theme.NAV_BUTTON_SIZE,) * 2, key)
        self.assertEqual(buttons["avatar"].width(), theme.AVATAR_SIZE)

    # ---- Settings > Appearance ----
    def test_settings_has_an_appearance_card_that_starts_editing(self):
        page = self.dash.settings_page
        self.assertTrue(page.sidebar_editor.isHidden())
        self.assertFalse(self.rail.editing)
        self.start_editing()
        self.assertTrue(self.rail.editing)
        self.assertFalse(page.sidebar_editor.isHidden())
        self.assertTrue(page.sidebar_edit_button.isHidden())

    def test_the_demo_cannot_customize_the_sidebar(self):
        self.assertFalse(self.demo.stores_sidebar_layout)
        self.assertFalse(self.rail.editing)
        self.assertFalse(self.demo.sidebar_rail.editing)
        self.demo._start_sidebar_editing()  # even if called directly, nothing starts
        self.assertFalse(self.demo.sidebar_rail.editing)

    # ---- normal mode ----
    def test_dragging_does_nothing_outside_editing_mode(self):
        before = self.rail.sidebar_layout()
        self.drag("catalog", 10, 0)
        self.assertEqual(self.rail.sidebar_layout(), before)
        self.assertEqual(self.rail.selected_key, "")

    def test_icons_navigate_normally_outside_editing_mode(self):
        self.dash._nav_buttons["catalog"].click()
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.catalog_page)
        self.assertTrue(self.dash._nav_buttons["catalog"].isChecked())
        self.dash.avatar_button.click()
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.settings_page)

    def test_log_out_still_works_outside_editing_mode(self):
        seen = []
        self.dash.logout_requested.connect(lambda: seen.append("out"))
        with mock.patch.object(type(self.dash), "_confirm_logout", return_value=True):
            self.dash.sidebar_exit_button.click()
        self.assertEqual(seen, ["out"])

    # ---- editing mode ----
    def test_clicking_an_icon_selects_it_and_does_not_navigate(self):
        self.start_editing()
        self.dash._nav_buttons["catalog"].click()
        self.assertEqual(self.rail.selected_key, "catalog")
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.settings_page)
        self.dash.avatar_button.click()
        self.assertEqual(self.rail.selected_key, "avatar")
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.settings_page)

    def test_log_out_only_selects_while_editing(self):
        seen = []
        self.dash.logout_requested.connect(lambda: seen.append("out"))
        self.start_editing()
        self.dash.sidebar_exit_button.click()
        self.assertEqual(seen, [])
        self.assertEqual(self.rail.selected_key, "logout")

    def test_dragging_moves_only_that_icon_and_keeps_the_others(self):
        self.start_editing()
        before = self.rail.sidebar_layout().geometry(self.rail.height())
        self.drag("catalog", 12, 0)
        after = self.rail.sidebar_layout().geometry(self.rail.height())
        self.assertEqual(after["catalog"][0], before["catalog"][0] + 12)
        for key in sl.ITEM_KEYS:
            if key != "catalog":
                self.assertEqual(after[key], before[key], key)
        self.assertEqual(self.rail.sidebar_layout().customised_keys(), ["catalog"])
        self.assertEqual(self.dash._nav_buttons["catalog"].x(), after["catalog"][0])

    def test_dropping_on_top_of_another_icon_snaps_back(self):
        self.start_editing()
        refused = []
        self.rail.refused.connect(refused.append)
        start = self.dash._nav_buttons["catalog"].pos()
        mine = self.dash._nav_buttons["dashboard"].y() - start.y()
        self.drag("catalog", 0, mine)  # exactly onto Dashboard
        self.assertEqual(self.dash._nav_buttons["catalog"].pos(), start)
        self.assertTrue(self.rail.sidebar_layout().is_default())
        self.assertEqual(len(refused), 1)

    def test_icons_cannot_be_dragged_out_of_the_rail(self):
        self.start_editing()
        self.drag("settings", 900, 900)
        button = self.dash._nav_buttons["settings"]
        self.assertLessEqual(button.x() + button.width(), theme.SIDEBAR_WIDTH)
        self.assertLessEqual(button.y() + button.height(), self.rail.height())

    def test_the_slider_resizes_only_the_selected_icon(self):
        self.start_editing()
        self.dash._nav_buttons["dashboard"].click()
        editor = self.dash.settings_page.sidebar_editor
        editor.size_slider.setValue(34)
        self.assertEqual(self.dash._nav_buttons["dashboard"].width(), 34 + sl.ICON_PADDING)
        self.assertEqual(self.dash._nav_buttons["dashboard"].iconSize().width(), 34)
        for key in sl.NAV_KEYS[1:] + ("logout",):
            self.assertEqual(self.all_buttons()[key].width(), theme.NAV_BUTTON_SIZE, key)
        self.assertEqual(self.dash.avatar_button.width(), theme.AVATAR_SIZE)

    def test_plus_and_minus_buttons_change_the_size_by_one(self):
        self.start_editing()
        self.dash._nav_buttons["my_list"].click()
        editor = self.dash.settings_page.sidebar_editor
        editor.size_plus.click()
        editor.size_plus.click()
        editor.size_minus.click()
        self.assertEqual(self.rail.size_of("my_list"), 25)

    def test_the_avatar_and_log_out_can_be_resized(self):
        self.start_editing()
        self.dash.avatar_button.click()
        self.dash.settings_page.sidebar_editor.size_slider.setValue(45)
        self.assertEqual(self.dash.avatar_button.width(), 45)
        self.dash.sidebar_exit_button.click()
        self.dash.settings_page.sidebar_editor.size_slider.setValue(30)
        self.assertEqual(self.dash.sidebar_exit_button.width(), 30 + sl.ICON_PADDING)
        self.assertEqual(self.dash.avatar_button.width(), 45)

    def test_fine_position_boxes_move_the_selected_icon(self):
        self.start_editing()
        self.dash._nav_buttons["notifications"].click()
        editor = self.dash.settings_page.sidebar_editor
        editor.x_spin.setValue(6)
        self.assertEqual(self.dash._nav_buttons["notifications"].x(), 6)
        y = editor.y_spin.value()
        editor.y_spin.setValue(y - 5)
        self.assertEqual(self.dash._nav_buttons["notifications"].y(), y - 5)

    def test_the_position_boxes_follow_a_drag(self):
        self.start_editing()
        self.dash._nav_buttons["catalog"].click()
        self.drag("catalog", 9, 0)
        editor = self.dash.settings_page.sidebar_editor
        self.assertEqual(editor.x_spin.value(), self.dash._nav_buttons["catalog"].x())

    def test_the_active_page_is_still_highlighted_after_customizing(self):
        self.dash._nav_buttons["my_requests"].click()
        self.start_editing()
        self.rail.set_item_size("my_requests", 30)
        self.assertTrue(self.dash._nav_buttons["my_requests"].isChecked())

    def test_tooltips_survive_customizing(self):
        self.start_editing()
        self.rail.set_item_size("catalog", 30)
        self.assertEqual(self.dash._nav_buttons["catalog"].toolTip(), "Browse Catalog")

    # ---- the five buttons ----
    def test_reset_selected_icon_resets_only_that_icon(self):
        self.start_editing()
        self.rail.set_item_size("catalog", 36)
        self.rail.set_item_size("my_list", 30)
        self.dash._nav_buttons["catalog"].click()
        self.dash.settings_page.sidebar_editor.reset_item_button.click()
        self.assertEqual(self.rail.size_of("catalog"), 24)
        self.assertEqual(self.rail.size_of("my_list"), 30)

    def test_reset_all_returns_every_icon_to_default(self):
        self.start_editing()
        self.rail.set_item_size("catalog", 36)
        self.rail.set_item_size("avatar", 50)
        self.dash.settings_page.sidebar_editor.reset_all_button.click()
        self.assertTrue(self.rail.sidebar_layout().is_default())
        self.assertEqual(self.dash.avatar_button.width(), theme.AVATAR_SIZE)

    def test_save_keeps_the_layout_and_stays_in_editing_mode(self):
        self.start_editing()
        self.rail.set_item_size("catalog", 36)
        editor = self.dash.settings_page.sidebar_editor
        editor.save_button.click()
        self.assertTrue(self.rail.editing)
        self.assertEqual(SidebarLayoutService(self.db).get_layout(self.ana.id).size_of("catalog"), 36)

    def test_cancel_goes_back_to_the_last_saved_layout_and_leaves_editing(self):
        self.start_editing()
        self.rail.set_item_size("catalog", 36)
        self.dash.settings_page.sidebar_editor.save_button.click()
        self.rail.set_item_size("catalog", 20)
        self.rail.set_item_size("avatar", 52)
        self.dash.settings_page.sidebar_editor.cancel_button.click()
        self.assertFalse(self.rail.editing)
        self.assertEqual(self.rail.size_of("catalog"), 36)
        self.assertEqual(self.rail.size_of("avatar"), 40)
        self.assertEqual(self.dash._nav_buttons["catalog"].width(), 36 + sl.ICON_PADDING)
        self.assertEqual(SidebarLayoutService(self.db).get_layout(self.ana.id).size_of("catalog"), 36)

    def test_finish_saves_and_leaves_editing(self):
        self.start_editing()
        self.rail.set_item_size("catalog", 33)
        self.dash.settings_page.sidebar_editor.finish_button.click()
        self.assertFalse(self.rail.editing)
        self.assertTrue(self.dash.settings_page.sidebar_editor.isHidden())
        self.assertEqual(SidebarLayoutService(self.db).get_layout(self.ana.id).size_of("catalog"), 33)

    def test_after_finishing_dragging_is_disabled_again(self):
        self.start_editing()
        self.dash.settings_page.sidebar_editor.finish_button.click()
        before = self.rail.sidebar_layout()
        self.drag("catalog", 10, 0)
        self.assertEqual(self.rail.sidebar_layout(), before)
        self.dash._nav_buttons["catalog"].click()
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.catalog_page)

    # ---- saving per account ----
    def test_the_layout_is_remembered_after_reopening(self):
        self.start_editing()
        self.rail.set_item_size("dashboard", 34)
        self.rail.set_item_size("avatar", 45)
        self.rail.set_item_position("catalog", 30, 250)
        self.dash.settings_page.sidebar_editor.finish_button.click()
        again = self.make_dash(self.ana)
        again.resize(1100, 700)
        again.show()
        self.qt_app.processEvents()
        self.assertEqual(again.avatar_button.width(), 45)
        self.assertEqual(again._nav_buttons["dashboard"].width(), 34 + sl.ICON_PADDING)
        self.assertEqual((again._nav_buttons["catalog"].x(), again._nav_buttons["catalog"].y()),
                         (30, 250))
        self.assertEqual(again._nav_buttons["settings"].width(), theme.NAV_BUTTON_SIZE)
        again.hide()

    def test_another_account_keeps_the_default_look(self):
        self.start_editing()
        self.rail.set_item_size("dashboard", 40)
        self.dash.settings_page.sidebar_editor.finish_button.click()
        other = self.make_dash(self.ben)
        self.assertEqual(other._nav_buttons["dashboard"].width(), theme.NAV_BUTTON_SIZE)
        self.assertTrue(other.sidebar_rail.sidebar_layout().is_default())

    def test_saved_positions_survive_resizing_the_window(self):
        self.start_editing()
        self.rail.set_item_position("catalog", 30, 200)
        self.rail.set_item_position("settings", 4, 600)
        saved = self.rail.sidebar_layout().to_dict()
        for height in (520, 900, 700):
            self.dash.resize(1100, height)
            self.qt_app.processEvents()
            self.assertEqual(self.rail.sidebar_layout().to_dict(), saved)
            for key, button in self.all_buttons().items():
                self.assertGreaterEqual(button.y(), 0, key)
                self.assertLessEqual(button.y() + button.height(), self.rail.height(), key)
                self.assertLessEqual(button.x() + button.width(), theme.SIDEBAR_WIDTH, key)
            self.assertEqual(self.dash._nav_buttons["catalog"].y(), 200)

    def test_profile_photo_still_fits_a_resized_avatar(self):
        from PySide6.QtGui import QColor, QPixmap
        photo = QPixmap(80, 50)
        photo.fill(QColor("#cc5577"))
        self.dash.set_profile_photo(photo)
        self.start_editing()
        self.rail.set_item_size("avatar", 52)
        self.assertEqual(self.dash.avatar_button.text(), "")
        self.assertEqual(self.dash.avatar_button.iconSize().width(), 50)

    def test_other_pages_are_not_reachable_while_editing(self):
        self.start_editing()
        self.dash.home_page.navigate_requested.emit("notifications")
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.settings_page)


if __name__ == "__main__":
    unittest.main()
