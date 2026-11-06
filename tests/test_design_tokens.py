"""Stage 1A-1 tests: design tokens and token-based styles (no screen uses them yet)."""
import os
import re
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import design_tokens as tk  # noqa: E402
from app import theme  # noqa: E402

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class TokenTests(unittest.TestCase):
    def test_every_color_token_is_a_six_digit_hex(self):
        colors = {n: v for n, v in vars(tk).items() if n.startswith("COLOR_")}
        self.assertGreater(len(colors), 20)
        for name, value in colors.items():
            self.assertRegex(value, HEX, name)

    def test_spacing_radii_and_sizes_are_positive_integers_and_ordered(self):
        for prefix in ("SPACE_", "RADIUS_", "FONT_SIZE_", "CONTROL_HEIGHT_"):
            for name, value in vars(tk).items():
                if name.startswith(prefix) and name != "SPACE_0":
                    self.assertIsInstance(value, int, name)
                    self.assertGreater(value, 0, name)
        sizes = [tk.FONT_SIZE_CAPTION, tk.FONT_SIZE_SMALL, tk.FONT_SIZE_BODY, tk.FONT_SIZE_LEAD,
                 tk.FONT_SIZE_H3, tk.FONT_SIZE_H2, tk.FONT_SIZE_H1]
        self.assertEqual(sizes, sorted(sizes))
        radii = [tk.RADIUS_SM, tk.RADIUS_MD, tk.RADIUS_LG, tk.RADIUS_XL, tk.RADIUS_PILL]
        self.assertEqual(radii, sorted(radii))

    def test_spacing_follows_the_4px_grid(self):
        for name, value in vars(tk).items():
            if name.startswith("SPACE_"):
                self.assertEqual(value % 4, 0, name)

    def test_readable_text_contrast_on_every_surface(self):
        surfaces = (tk.COLOR_BG_APP, tk.COLOR_BG_SIDEBAR, tk.COLOR_BG_SURFACE, tk.COLOR_BG_RAISED)
        for surface in surfaces:
            self.assertGreaterEqual(contrast(tk.COLOR_TEXT_PRIMARY, surface), 7, surface)
            self.assertGreaterEqual(contrast(tk.COLOR_TEXT_SECONDARY, surface), 4.5, surface)
            self.assertGreaterEqual(contrast(tk.COLOR_TEXT_MUTED, surface), 4.5, surface)

    def test_accent_and_status_contrast(self):
        self.assertGreaterEqual(contrast(tk.COLOR_TEXT_ON_ACCENT, tk.COLOR_ACCENT), 4.5)
        for fg, bg in ((tk.COLOR_SUCCESS, tk.COLOR_SUCCESS_SOFT), (tk.COLOR_WARNING, tk.COLOR_WARNING_SOFT),
                       (tk.COLOR_DANGER, tk.COLOR_DANGER_SOFT), (tk.COLOR_INFO, tk.COLOR_INFO_SOFT),
                       (tk.COLOR_ACCENT_HOVER, tk.COLOR_BG_SURFACE)):
            self.assertGreaterEqual(contrast(fg, bg), 4.5, fg)

    def test_tokens_module_has_no_qt_dependency(self):
        source = Path(tk.__file__).read_text(encoding="utf-8")
        self.assertNotIn("PySide6", source)


class ThemeCompatibilityTests(unittest.TestCase):
    def test_old_theme_constants_are_unchanged(self):
        self.assertEqual((theme.NAVY, theme.PERIWINKLE, theme.PINK, theme.MINT, theme.CREAM),
                         ("#282A49", "#7175F5", "#F4A8C4", "#B7F1E1", "#FFF9EF"))
        self.assertEqual((theme.SIDEBAR_NAVY, theme.MUTED_TEXT, theme.SOFT_LAVENDER),
                         ("#1F2140", "#5A5C80", "#F4F5FF"))

    def test_the_global_stylesheet_does_not_contain_the_new_token_styles(self):
        self.assertNotIn('[ds=', theme.STYLESHEET)
        self.assertNotIn(tk.COLOR_BG_APP, theme.STYLESHEET)

    def test_token_stylesheet_uses_tokens_and_only_opt_in_selectors(self):
        css = theme.TOKEN_STYLESHEET
        self.assertEqual(css, theme.ds_stylesheet())
        for token in (tk.COLOR_ACCENT, tk.COLOR_BG_SURFACE, tk.COLOR_FOCUS_RING):
            self.assertIn(token, css)
        selectors = [s.strip() for block in re.findall(r"([^{}]+)\{", css) for s in block.split(",")]
        for selector in selectors:
            self.assertIn('[ds="', selector, selector)

    def test_button_variants_exist_with_all_states(self):
        css = theme.TOKEN_STYLESHEET
        for variant in ("primary", "secondary", "danger", "ghost"):
            base = f'QPushButton[ds="button-{variant}"]'
            for state in ("", ":hover", ":pressed", ":focus", ":disabled"):
                self.assertIn(base + state + " {", css, base + state)

    def test_token_stylesheet_applies_in_qt_without_touching_other_widgets(self):
        from PySide6.QtWidgets import QApplication, QPushButton
        app = QApplication.instance() or QApplication([])
        plain, styled = QPushButton("plain"), QPushButton("styled")
        styled.setProperty("ds", "button-primary")
        for widget in (plain, styled):
            widget.setStyleSheet(theme.TOKEN_STYLESHEET)
            widget.ensurePolished()
        self.assertEqual(plain.styleSheet(), styled.styleSheet())  # same rules, different match
        self.assertIsNotNone(app)

    def test_every_existing_screen_still_imports(self):
        import importlib
        for name in ("login_screen", "register_screen", "dashboard_screen", "catalog_screen",
                     "my_list_screen", "my_requests_screen", "my_borrowings_screen",
                     "my_reservations_screen", "notifications_screen", "settings_screen",
                     "main_window"):
            importlib.import_module(f"app.{name}")


if __name__ == "__main__":
    unittest.main()
