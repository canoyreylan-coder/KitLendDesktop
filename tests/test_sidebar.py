"""Stage 1B + 1C tests: compact icon-only sidebar, top avatar, no top banner.

Groups 1-2 need no window and no PySide6. Group 3 opens widgets in Qt's invisible
"offscreen" mode and is skipped automatically if PySide6 is not installed.

Run from the project folder:   python -m unittest discover -s tests -v
"""
import os
import re
import sys
import unittest
from unittest import mock
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import design_tokens as tk  # noqa: E402
from app import theme  # noqa: E402
from app.icon_shapes import ICON_BOX, ICON_SHAPES, all_points, shapes_for  # noqa: E402

EXPECTED_NAV_KEYS = ["dashboard", "catalog", "my_list", "my_requests", "borrowings",
                     "reservations", "notifications", "settings"]
EXPECTED_LABELS = {
    "dashboard": "Dashboard", "catalog": "Browse Catalog", "my_list": "My List",
    "my_requests": "My Requests", "borrowings": "My Borrowings",
    "reservations": "Reservations", "notifications": "Notifications", "settings": "Settings",
}


def _luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# ======================================================================
# 1. ICON SHAPES (plain data)
# ======================================================================
class IconShapeTests(unittest.TestCase):
    def test_every_navigation_page_and_logout_has_an_icon(self):
        for key in EXPECTED_NAV_KEYS + ["logout"]:
            self.assertTrue(shapes_for(key), key)

    def test_no_stray_icons_and_every_icon_is_different(self):
        self.assertEqual(set(ICON_SHAPES), set(EXPECTED_NAV_KEYS) | {"logout"})
        rendered = [repr(shapes_for(key)) for key in ICON_SHAPES]
        self.assertEqual(len(rendered), len(set(rendered)))

    def test_unknown_icon_is_rejected(self):
        with self.assertRaises(KeyError):
            shapes_for("admin_panel")

    def test_all_shapes_stay_inside_the_24_box_with_room_for_the_stroke(self):
        for key in ICON_SHAPES:
            for x, y in all_points(key):
                self.assertTrue(1 <= x <= ICON_BOX - 1, f"{key} x={x}")
                self.assertTrue(1 <= y <= ICON_BOX - 1, f"{key} y={y}")

    def test_only_known_shape_kinds_are_used(self):
        for key in ICON_SHAPES:
            for shape in shapes_for(key):
                self.assertIn(shape[0], {"rrect", "circle", "line", "poly", "path"}, key)


# ======================================================================
# 2. SIDEBAR STYLES AND SIZES (plain strings, no window needed)
# ======================================================================
class SidebarStyleTests(unittest.TestCase):
    def test_sidebar_is_compact(self):
        self.assertTrue(68 <= theme.SIDEBAR_WIDTH <= 72)
        self.assertLessEqual(theme.NAV_BUTTON_SIZE, theme.SIDEBAR_WIDTH - 16)
        self.assertLess(theme.NAV_ICON_SIZE, theme.NAV_BUTTON_SIZE)
        self.assertLessEqual(theme.AVATAR_SIZE, theme.NAV_BUTTON_SIZE)

    def test_braces_are_balanced(self):
        css = theme.SIDEBAR_STYLESHEET
        self.assertEqual(css.count("{"), css.count("}"))

    def test_every_selector_is_scoped_to_the_sidebar(self):
        css = re.sub(r"/\*.*?\*/", "", theme.SIDEBAR_STYLESHEET, flags=re.S)
        selectors = []
        for block in re.finditer(r"([^{}]+)\{[^{}]*\}", css):
            selectors += [s.strip() for s in block.group(1).split(",") if s.strip()]
        self.assertGreater(len(selectors), 10)
        for selector in selectors:
            self.assertTrue(selector.startswith("QFrame#sidebar"), selector)

    def test_only_design_token_colors_are_used(self):
        allowed = {v.upper() for k, v in vars(tk).items()
                   if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v)}
        used = set(re.findall(r"#[0-9A-Fa-f]{6}", theme.SIDEBAR_STYLESHEET))
        self.assertTrue(used)
        self.assertLessEqual({u.upper() for u in used}, allowed)

    def test_old_pixel_pop_only_colors_are_gone_from_the_new_sidebar(self):
        css = theme.SIDEBAR_STYLESHEET.upper()
        for old in (theme.NAVY, theme.MINT, theme.CREAM, theme.SIDEBAR_NAVY):
            self.assertNotIn(old.upper(), css)

    def test_active_page_uses_the_soft_lavender_tint(self):
        css = theme.SIDEBAR_STYLESHEET
        checked = css[css.index("QPushButton#navButton:checked"):]
        checked = checked[:checked.index("}")]
        self.assertIn(tk.COLOR_ACCENT_SOFT, checked)

    def test_icons_and_labels_are_readable_on_the_sidebar(self):
        self.assertGreaterEqual(contrast(tk.COLOR_TEXT_SECONDARY, tk.COLOR_BG_SIDEBAR), 4.5)
        self.assertGreaterEqual(contrast(tk.COLOR_TEXT_PRIMARY, tk.COLOR_BG_RAISED), 4.5)  # tooltip
        self.assertGreaterEqual(contrast(tk.COLOR_ACCENT_HOVER, tk.COLOR_ACCENT_SOFT), 3.0)  # active icon
        self.assertGreaterEqual(contrast(tk.COLOR_TEXT_PRIMARY, tk.COLOR_ACCENT_SOFT), 4.5)  # initials

    def test_global_stylesheet_and_old_constants_are_untouched(self):
        # Stage 1B must not restyle any other screen: nothing was added to the global sheet.
        self.assertNotIn("sidebarMark", theme.STYLESHEET)
        self.assertNotIn(theme.SIDEBAR_STYLESHEET, theme.STYLESHEET)
        self.assertEqual((theme.NAVY, theme.PERIWINKLE, theme.PINK, theme.MINT, theme.CREAM),
                         ("#282A49", "#7175F5", "#F4A8C4", "#B7F1E1", "#FFF9EF"))
        self.assertEqual((theme.SIDEBAR_NAVY, theme.MUTED_TEXT, theme.SOFT_LAVENDER),
                         ("#1F2140", "#5A5C80", "#F4F5FF"))

    def test_login_and_registration_styles_are_untouched(self):
        self.assertTrue(theme.AUTH_STYLESHEET.strip())
        self.assertNotIn("QFrame#sidebar", theme.AUTH_STYLESHEET)

    def test_dashboard_source_lists_the_same_pages_in_the_same_order(self):
        source = (ROOT / "app" / "dashboard_screen.py").read_text(encoding="utf-8")
        keys = re.findall(r'NavItem\("(\w+)"', source)
        self.assertEqual(keys, EXPECTED_NAV_KEYS)
        for key, label in EXPECTED_LABELS.items():
            self.assertIn(f'"{label}"', source)

    def test_dashboard_source_no_longer_builds_a_wide_text_sidebar(self):
        source = (ROOT / "app" / "dashboard_screen.py").read_text(encoding="utf-8")
        self.assertNotIn("setFixedWidth(230)", source)
        self.assertNotIn('f"{item.icon}   {item.label}"', source)

    def test_stage_1c_banner_and_duplicate_logout_are_gone(self):
        source = (ROOT / "app" / "dashboard_screen.py").read_text(encoding="utf-8")
        for gone in ("_build_demo_banner", '"SIGNED IN"', '"DEMO MODE"', "self.exit_button",
                     "exitDemoButton", "demoBanner", "Signed in as {self._signed_in_email}"):
            self.assertNotIn(gone, source, gone)

    def test_stage_1c_k_tile_and_bottom_avatar_are_gone(self):
        source = (ROOT / "app" / "dashboard_screen.py").read_text(encoding="utf-8")
        self.assertNotIn("sidebarMark", source)
        self.assertNotIn('QLabel("K")', source)
        self.assertEqual(source.count("self._build_avatar(sidebar)"), 1)  # built once
        self.assertEqual(source.count('setObjectName("avatar")'), 1)
        self.assertEqual(source.count('setObjectName("sidebarExitButton")'), 1)
        self.assertNotIn("sidebarMark", theme.SIDEBAR_STYLESHEET)

    def test_step_14f_sidebar_is_freeform_not_an_automatic_layout(self):
        source = (ROOT / "app" / "dashboard_screen.py").read_text(encoding="utf-8")
        self.assertIn("SidebarRail()", source)
        self.assertNotIn("_add_nav_gap", source)        # the equal stretchy gaps are gone
        self.assertNotIn("QScrollArea", source)         # no scrolling nav list any more
        rail = (ROOT / "app" / "sidebar_rail.py").read_text(encoding="utf-8")
        self.assertIn("button.move(x, y)", rail)        # items are placed by pixel position
        self.assertNotIn("QVBoxLayout", rail)

    def test_avatar_is_a_round_button_style_inside_the_sidebar_sheet(self):
        css = theme.SIDEBAR_STYLESHEET
        self.assertIn("QFrame#sidebar QPushButton#avatar", css)
        self.assertNotIn("QLabel#avatar", css)
        block = css[css.index("QFrame#sidebar QPushButton#avatar {"):]
        block = block[:block.index("}")]
        self.assertIn(f"border-radius: {theme.AVATAR_SIZE // 2}px", block)


# ======================================================================
# 3. THE REAL SIDEBAR (needs PySide6)
# ======================================================================
try:
    import PySide6
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False

if HAVE_QT:
    from test_notifications import TempDbCase
else:  # pragma: no cover
    TempDbCase = unittest.TestCase


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class SidebarWidgetTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.qt_app.setStyleSheet(theme.STYLESHEET)

    def setUp(self):
        super().setUp()
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_demo_data, build_empty_data
        self.dash = StudentDashboard(
            build_empty_data(self.ana.full_name), signed_in_email=self.ana.email,
            student_id=self.ana.id, request_service=self.requests, auth_service=self.auth)
        self.demo = StudentDashboard(build_demo_data())

    def sidebar(self, dash=None):
        from PySide6.QtWidgets import QFrame
        return (dash or self.dash).findChild(QFrame, "sidebar")

    def test_sidebar_is_compact_and_fixed_width(self):
        side = self.sidebar()
        self.assertEqual(side.width() if side.isVisible() else side.maximumWidth(),
                         theme.SIDEBAR_WIDTH)
        self.assertEqual(side.minimumWidth(), theme.SIDEBAR_WIDTH)
        self.assertEqual(side.maximumWidth(), theme.SIDEBAR_WIDTH)

    def test_there_is_one_icon_button_per_page_in_order(self):
        self.assertEqual(list(self.dash._nav_buttons), EXPECTED_NAV_KEYS)
        for button in self.dash._nav_buttons.values():
            self.assertIsInstance(button, QPushButton)
            self.assertEqual(button.objectName(), "navButton")

    def test_buttons_are_icon_only_with_tooltips_for_the_labels(self):
        for key, button in self.dash._nav_buttons.items():
            self.assertEqual(button.text(), "", key)
            self.assertFalse(button.icon().isNull(), key)
            self.assertEqual(button.toolTip(), EXPECTED_LABELS[key])
            self.assertEqual(button.accessibleName(), EXPECTED_LABELS[key])
            self.assertEqual(button.width(), theme.NAV_BUTTON_SIZE)

    def test_sidebar_stays_icon_only_after_clicking(self):
        for key in EXPECTED_NAV_KEYS:
            self.dash._nav_buttons[key].click()
            self.assertEqual(self.dash._nav_buttons[key].text(), "")
            self.assertEqual(self.sidebar().maximumWidth(), theme.SIDEBAR_WIDTH)
            self.assertEqual(self.sidebar().minimumWidth(), theme.SIDEBAR_WIDTH)

    def test_every_icon_looks_different_and_the_checked_look_is_different(self):
        images = {}
        for key, button in self.dash._nav_buttons.items():
            from PySide6.QtGui import QIcon
            normal = button.icon().pixmap(24, 24, QIcon.Normal, QIcon.Off).toImage()
            checked = button.icon().pixmap(24, 24, QIcon.Normal, QIcon.On).toImage()
            self.assertNotEqual(normal, checked, key)
            images[key] = tuple(normal.pixel(x, y) for y in range(normal.height())
                                for x in range(normal.width()))
        self.assertEqual(len(set(images.values())), len(images))

    def test_clicking_each_icon_opens_its_page_and_highlights_only_that_one(self):
        pages = {"dashboard": self.dash.home_page, "catalog": self.dash.catalog_page,
                 "my_list": self.dash.my_list_page, "my_requests": self.dash.my_requests_page,
                 "borrowings": self.dash.my_borrowings_page,
                 "reservations": self.dash.my_reservations_page,
                 "notifications": self.dash.my_notifications_page,
                 "settings": self.dash.settings_page}
        for key, page in pages.items():
            self.dash._nav_buttons[key].click()
            self.assertIs(self.dash.content_stack.currentWidget(), page, key)
            checked = [k for k, b in self.dash._nav_buttons.items() if b.isChecked()]
            self.assertEqual(checked, [key])

    def test_go_to_still_works_from_other_screens(self):
        self.dash.home_page.navigate_requested.emit("notifications")
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.my_notifications_page)
        self.assertTrue(self.dash._nav_buttons["notifications"].isChecked())

    def test_avatar_is_the_first_widget_in_the_rail_and_shows_the_initials(self):
        avatar = self.dash.avatar_button
        self.assertIsInstance(avatar, QPushButton)
        self.assertEqual(avatar.objectName(), "avatar")
        self.assertEqual(avatar.text(), "AR")
        self.assertEqual((avatar.width(), avatar.height()), (theme.AVATAR_SIZE, theme.AVATAR_SIZE))
        buttons = self.sidebar().findChildren(QPushButton)
        self.assertIs(buttons[0], avatar)  # first item of the rail, no "K" tile above it
        self.assertEqual(avatar.y(), 16)   # and at the top (Step 14E look)
        self.assertIsNone(self.sidebar().findChild(QLabel, "sidebarMark"))

    def test_avatar_tooltip_has_name_and_email(self):
        tip = self.dash.avatar_button.toolTip()
        self.assertIn("Ana Reyes", tip)
        self.assertIn(self.ana.email, tip)
        self.assertIn("Settings", tip)

    def test_clicking_the_avatar_opens_settings(self):
        self.dash._nav_buttons["catalog"].click()
        self.dash.avatar_button.click()
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.settings_page)
        self.assertTrue(self.dash._nav_buttons["settings"].isChecked())

    def test_there_is_exactly_one_avatar_and_one_logout_control(self):
        self.assertEqual(len(self.dash.findChildren(QPushButton, "avatar")), 1)
        self.assertEqual(len(self.dash.findChildren(QPushButton, "sidebarExitButton")), 1)
        self.assertEqual(len(self.dash.findChildren(QLabel, "avatar")), 0)
        logout_like = [b for b in self.dash.findChildren(QPushButton)
                       if b.text() in ("Log Out", "Exit Demo")
                       or b.toolTip() in ("Log Out", "Back to Login")]
        self.assertEqual(len(logout_like), 1)

    def test_logout_is_the_last_widget_at_the_bottom_of_the_rail(self):
        buttons = self.sidebar().findChildren(QPushButton)
        self.assertIs(buttons[-1], self.dash.sidebar_exit_button)
        for button in self.dash._nav_buttons.values():
            self.assertGreater(self.dash.sidebar_exit_button.y(), button.y())

    def test_profile_photo_hook_shows_a_circular_photo_and_can_be_cleared(self):
        from PySide6.QtGui import QColor, QPixmap
        photo = QPixmap(80, 50)
        photo.fill(QColor("#cc5577"))
        self.dash.set_profile_photo(photo)
        self.assertEqual(self.dash.avatar_button.text(), "")
        self.assertFalse(self.dash.avatar_button.icon().isNull())
        corner = self.dash.avatar_button.icon().pixmap(38, 38).toImage().pixelColor(0, 0)
        self.assertEqual(corner.alpha(), 0)  # cropped to a circle: the corner is transparent
        self.dash.set_profile_photo(None)
        self.assertEqual(self.dash.avatar_button.text(), "AR")
        self.assertTrue(self.dash.avatar_button.icon().isNull())

    def test_unreadable_profile_photo_falls_back_to_the_initials(self):
        self.dash.set_profile_photo(os.path.join(self.tmp.name, "missing.png"))
        self.assertEqual(self.dash.avatar_button.text(), "AR")
        self.assertTrue(self.dash.avatar_button.icon().isNull())

    def test_demo_sidebar_is_the_same_rail_and_still_navigates(self):
        self.assertEqual(self.sidebar(self.demo).maximumWidth(), theme.SIDEBAR_WIDTH)
        self.assertIn("Demo student", self.demo.avatar_button.toolTip())
        self.demo._nav_buttons["settings"].click()
        self.assertIs(self.demo.content_stack.currentWidget(), self.demo.placeholder_page)
        self.assertEqual(self.demo._nav_buttons["settings"].toolTip(), "Settings")

    def test_sidebar_logout_icon_still_logs_out(self):
        seen = []
        self.dash.logout_requested.connect(lambda: seen.append("logout"))
        self.assertEqual(self.dash.sidebar_exit_button.toolTip(), "Log Out")
        with mock.patch.object(type(self.dash), "_confirm_logout", return_value=True):
            self.dash.sidebar_exit_button.click()
        self.assertEqual(seen, ["logout"])

    def test_demo_sidebar_exit_returns_to_login(self):
        seen = []
        self.demo.exit_demo_requested.connect(lambda: seen.append("exit"))
        self.assertEqual(self.demo.sidebar_exit_button.toolTip(), "Back to Login")
        self.demo.sidebar_exit_button.click()
        self.assertEqual(seen, ["exit"])

    def test_the_rail_never_forces_a_tall_window(self):
        from app.sidebar_rail import SidebarRail
        self.assertIsInstance(self.sidebar(), SidebarRail)
        self.assertIsNone(self.dash.findChild(QScrollArea, "sidebarScroll"))
        self.assertLess(self.sidebar().minimumSizeHint().height(), 500)

    def test_the_top_banner_and_its_duplicate_logout_button_are_gone(self):
        from PySide6.QtWidgets import QFrame, QLabel as Label
        for dash in (self.dash, self.demo):
            self.assertFalse(hasattr(dash, "exit_button"))
            self.assertIsNone(dash.findChild(QFrame, "demoBanner"))
            self.assertIsNone(dash.findChild(QPushButton, "exitDemoButton"))
            texts = [w.text() for w in dash.findChildren(Label)]
            self.assertNotIn("SIGNED IN", texts)
            self.assertNotIn("DEMO MODE", texts)
            self.assertFalse([t for t in texts if t.startswith("Signed in as")])

    def test_content_area_now_starts_at_the_very_top(self):
        layout = self.dash.layout()
        self.assertEqual(layout.count(), 1)  # just the sidebar + pages row, nothing above it

    def _rail_geometry(self, height):
        from PySide6.QtCore import QPoint
        dash = self.dash
        dash.resize(1100, height)
        dash.show()
        self.qt_app.processEvents()
        side = self.sidebar()

        def box(widget):
            top = widget.mapTo(side, QPoint(0, 0)).y()
            return top, top + widget.height()

        icons = [box(b) for b in dash._nav_buttons.values()]
        return box(dash.avatar_button), icons, box(dash.sidebar_exit_button), side.height()

    def test_icons_are_spread_evenly_between_the_avatar_and_log_out(self):
        avatar, icons, logout, _height = self._rail_geometry(820)
        gaps = ([icons[0][0] - avatar[1]]
                + [icons[i + 1][0] - icons[i][1] for i in range(len(icons) - 1)]
                + [logout[0] - icons[-1][1]])
        self.assertGreater(min(gaps), 0)
        self.assertLessEqual(max(gaps) - min(gaps), 2)  # equal gaps, give or take rounding
        self.assertGreater(min(gaps), 10)               # really spread out, not crowded at the top
        self.dash.hide()

    def test_rail_keeps_avatar_on_top_and_log_out_at_the_bottom_at_any_height(self):
        for height in (520, 700, 1000):
            avatar, icons, logout, rail_height = self._rail_geometry(height)
            self.assertLess(avatar[0], icons[0][0])
            self.assertLessEqual(icons[-1][1], logout[0])
            self.assertLessEqual(logout[1], rail_height)      # not clipped at the bottom
            self.assertGreaterEqual(avatar[0], 0)             # not clipped at the top
            self.assertGreater(rail_height - logout[1], 0)    # still anchored near the bottom edge
            self.assertLess(rail_height - logout[1], 30)
            self.dash.hide()

    def test_nothing_overlaps_at_the_smallest_window_height(self):
        avatar, icons, logout, _h = self._rail_geometry(500)  # MainWindow's minimum height
        self.assertEqual(avatar[1] - avatar[0], theme.AVATAR_SIZE)
        for top, bottom in icons:
            self.assertEqual(bottom - top, theme.NAV_BUTTON_SIZE)
        self.assertEqual(sorted(icons), icons)
        for (_t1, b1), (t2, _b2) in zip(icons, icons[1:]):
            self.assertLessEqual(b1, t2)
        self.assertLessEqual(icons[-1][1], logout[0])
        self.assertEqual(logout[1] - logout[0], theme.NAV_BUTTON_SIZE)
        self.dash.hide()

    def test_icons_stay_the_same_size_and_centered_when_resized(self):
        from PySide6.QtCore import QPoint
        for height in (520, 900):
            self._rail_geometry(height)
            side = self.sidebar()
            centers = {b.mapTo(side, QPoint(b.width() // 2, 0)).x()
                       for b in self.dash._nav_buttons.values()}
            centers.add(self.dash.avatar_button.mapTo(
                side, QPoint(self.dash.avatar_button.width() // 2, 0)).x())
            centers.add(self.dash.sidebar_exit_button.mapTo(
                side, QPoint(self.dash.sidebar_exit_button.width() // 2, 0)).x())
            self.assertLessEqual(max(centers) - min(centers), 1)  # one shared vertical axis
            for b in self.dash._nav_buttons.values():
                self.assertEqual((b.width(), b.height()), (theme.NAV_BUTTON_SIZE,) * 2)
            self.dash.hide()

    def test_page_titles_in_the_content_area_are_unchanged(self):
        self.dash._nav_buttons["settings"].click()
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.settings_page)
        self.demo._nav_buttons["my_list"].click()
        self.assertEqual(self.demo.placeholder_page.title_label.text(), "My List")


if __name__ == "__main__":
    unittest.main()
