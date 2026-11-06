# Pixel Pop colors
NAVY = "#282A49"        # deep background
PERIWINKLE = "#7175F5"  # main accent
PINK = "#F4A8C4"        # soft highlight
MINT = "#B7F1E1"        # fresh accent
CREAM = "#FFF9EF"       # light surfaces

# Qt Style Sheet (like CSS for desktop apps)
STYLESHEET = f"""
QMainWindow, QWidget#central {{
    background-color: {NAVY};
}}

QFrame#card {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 28px;
}}

QLabel {{
    background: transparent;
    border: none;
}}

QLabel#title {{
    color: {NAVY};
    font-size: 44px;
    font-weight: bold;
}}

QLabel#tagline {{
    color: {NAVY};
    font-size: 16px;
}}

QLabel#pill {{
    background-color: {MINT};
    color: {NAVY};
    border: 2px solid {PINK};
    border-radius: 16px;
    padding: 6px 18px;
    font-size: 13px;
    font-weight: bold;
}}

/* ---------- Login Screen ---------- */
QWidget#loginScreen {{
    background-color: {NAVY};
}}

QFrame#brandPanel {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {NAVY}, stop:1 #3A3D7A);
}}

QLabel#brandLogo {{
    color: {CREAM};
    font-size: 54px;
    font-weight: bold;
}}

QLabel#brandSlogan {{
    color: {MINT};
    font-size: 18px;
    font-weight: bold;
}}

QLabel#chip {{
    background-color: rgba(183, 241, 225, 30);
    color: {MINT};
    border: 2px solid {MINT};
    border-radius: 14px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: bold;
}}

QFrame#formPanel, QScrollArea#formScroll, QWidget#formInner {{
    background-color: {PINK};
    border: none;
}}

QFrame#loginCard {{
    background-color: {CREAM};
    border: 3px solid {NAVY};
    border-radius: 26px;
}}

QLabel#heading {{
    color: {NAVY};
    font-size: 28px;
    font-weight: bold;
}}

QLabel#subheading {{
    color: #5A5C80;
    font-size: 13px;
}}

QLabel#fieldLabel {{
    color: {NAVY};
    font-size: 13px;
    font-weight: bold;
}}

QLineEdit {{
    background-color: white;
    color: {NAVY};
    border: 2px solid {NAVY};
    border-radius: 14px;
    padding: 10px 14px;
    font-size: 14px;
    selection-background-color: {PERIWINKLE};
}}

QLineEdit:hover {{
    border-color: {PERIWINKLE};
}}

QLineEdit:focus {{
    border: 3px solid {PERIWINKLE};
    background-color: #F4F5FF;
}}

QPushButton#toggleButton {{
    background-color: {MINT};
    color: {NAVY};
    border: 2px solid {NAVY};
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: bold;
}}

QPushButton#toggleButton:hover {{
    background-color: {PINK};
}}

QPushButton#linkButton {{
    background: transparent;
    color: {PERIWINKLE};
    border: none;
    font-size: 13px;
    font-weight: bold;
    padding: 2px 4px;
}}

QPushButton#linkButton:hover {{
    color: {NAVY};
    text-decoration: underline;
}}

QPushButton#primaryButton {{
    background-color: {PERIWINKLE};
    color: white;
    border: 3px solid {NAVY};
    border-radius: 16px;
    padding: 12px;
    font-size: 16px;
    font-weight: bold;
}}

QPushButton#primaryButton:hover {{
    background-color: #5C60E0;
}}

QPushButton#primaryButton:pressed {{
    background-color: {NAVY};
}}

QLabel#statusLabel {{
    color: #2E7D68;
    font-size: 12px;
    font-weight: bold;
}}

QLabel#statusLabel[error="true"] {{
    color: #C2386B;
}}
"""


# ======================================================================
# Student Dashboard (Step 4) + Login "Preview Dashboard (Demo)" button
# Added as a separate block so the Login/Registration styles stay untouched.
# ======================================================================
SIDEBAR_NAVY = "#1F2140"   # slightly darker navy for the sidebar
MUTED_TEXT = "#5A5C80"     # same soft text color used by the login screen
SOFT_LAVENDER = "#F4F5FF"  # light row background inside cream cards

DASHBOARD_STYLESHEET = f"""
/* ---------- Login: demo preview button ---------- */
QPushButton#demoButton {{
    background-color: {MINT};
    color: {NAVY};
    border: 3px dashed {NAVY};
    border-radius: 16px;
    padding: 10px;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#demoButton:hover {{
    background-color: {PINK};
}}

/* ---------- Dashboard shell ---------- */
QWidget#dashboardScreen {{
    background-color: {NAVY};
}}

QFrame#demoBanner {{
    background-color: {PINK};
    border: none;
    border-bottom: 3px solid {NAVY};
}}

QLabel#demoTag {{
    background-color: {NAVY};
    color: {PINK};
    border-radius: 10px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: bold;
}}

QLabel#demoBannerText {{
    color: {NAVY};
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#exitDemoButton {{
    background-color: {NAVY};
    color: {CREAM};
    border: 2px solid {NAVY};
    border-radius: 12px;
    padding: 6px 16px;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#exitDemoButton:hover {{
    background-color: {PERIWINKLE};
}}

/* ---------- Sidebar ---------- */
QFrame#sidebar {{
    background-color: {SIDEBAR_NAVY};
    border: none;
    border-right: 3px solid {PERIWINKLE};
}}

QLabel#sidebarLogo {{
    color: {CREAM};
    font-size: 30px;
    font-weight: bold;
}}

QLabel#sidebarRole {{
    color: {MINT};
    font-size: 12px;
    font-weight: bold;
}}

QPushButton#navButton {{
    background: transparent;
    color: {CREAM};
    border: 2px solid transparent;
    border-radius: 14px;
    padding: 11px 14px;
    text-align: left;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#navButton:hover {{
    background-color: rgba(113, 117, 245, 70);
}}

QPushButton#navButton:checked {{
    background-color: {PERIWINKLE};
    color: white;
    border-color: {PINK};
}}

QFrame#profileCard {{
    background-color: rgba(255, 249, 239, 14);
    border: 2px solid rgba(183, 241, 225, 70);
    border-radius: 18px;
}}

QLabel#avatar {{
    background-color: {PINK};
    color: {NAVY};
    border-radius: 20px;
    font-size: 14px;
    font-weight: bold;
}}

QLabel#profileName {{
    color: {CREAM};
    font-size: 13px;
    font-weight: bold;
}}

QLabel#profileRole {{
    color: {MINT};
    font-size: 11px;
}}

QPushButton#sidebarExitButton {{
    background: transparent;
    color: {PINK};
    border: 2px solid {PINK};
    border-radius: 14px;
    padding: 9px;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#sidebarExitButton:hover {{
    background-color: {PINK};
    color: {NAVY};
}}

/* ---------- Scrolling content area ---------- */
QScrollArea#dashScroll, QWidget#dashContent {{
    background-color: {NAVY};
    border: none;
}}

QScrollArea#dashScroll QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 4px;
}}

QScrollArea#dashScroll QScrollBar::handle:vertical {{
    background: {PERIWINKLE};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollArea#dashScroll QScrollBar::add-line:vertical,
QScrollArea#dashScroll QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollArea#dashScroll QScrollBar::add-page:vertical,
QScrollArea#dashScroll QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* ---------- Welcome section ---------- */
QFrame#welcomeCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #3A3D7A, stop:1 {PERIWINKLE});
    border: 3px solid {PINK};
    border-radius: 28px;
}}

QLabel#welcomeTitle {{
    color: {CREAM};
    font-size: 30px;
    font-weight: bold;
}}

QLabel#welcomeText {{
    color: {CREAM};
    font-size: 14px;
}}

/* ---------- Cards and rows ---------- */
QFrame#dashCard {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 24px;
}}

QLabel#cardTitle {{
    color: {NAVY};
    font-size: 17px;
    font-weight: bold;
}}

QLabel#cardSubtitle {{
    color: {MUTED_TEXT};
    font-size: 12px;
}}

QLabel#mutedNote {{
    color: {MUTED_TEXT};
    font-size: 13px;
}}

QFrame#rowItem {{
    background-color: {SOFT_LAVENDER};
    border: 2px solid #DDDFFA;
    border-radius: 16px;
}}

QFrame#rowItem[unread="true"] {{
    background-color: #EAEBFF;
    border-color: {PERIWINKLE};
}}

QLabel#rowTitle {{
    color: {NAVY};
    font-size: 13px;
    font-weight: bold;
}}

QLabel#rowMeta {{
    color: {MUTED_TEXT};
    font-size: 12px;
}}

QProgressBar {{
    background-color: #DDDFFA;
    border: none;
    border-radius: 4px;
}}

QProgressBar::chunk {{
    background-color: {PERIWINKLE};
    border-radius: 4px;
}}

/* ---------- Summary tiles ---------- */
QFrame#statCard {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 22px;
}}

QFrame#statCard:hover {{
    background-color: white;
    border-color: {PINK};
}}

QLabel#statNumber {{
    color: {NAVY};
    font-size: 34px;
    font-weight: bold;
}}

QLabel#statLabel {{
    color: {NAVY};
    font-size: 13px;
    font-weight: bold;
}}

QLabel#statHint {{
    color: {MUTED_TEXT};
    font-size: 12px;
}}

/* ---------- Icon badges and status pills ---------- */
QLabel#iconBadge {{
    border: 2px solid {NAVY};
    border-radius: 14px;
    font-size: 18px;
}}

QLabel#iconBadge[big="true"] {{
    border-radius: 26px;
    font-size: 34px;
}}

QLabel#iconBadge[accent="mint"] {{ background-color: {MINT}; }}
QLabel#iconBadge[accent="pink"] {{ background-color: {PINK}; }}
QLabel#iconBadge[accent="purple"] {{ background-color: {PERIWINKLE}; }}
QLabel#iconBadge[accent="cream"] {{ background-color: #E3E4FA; }}

QLabel#statusPill {{
    border: 2px solid {NAVY};
    border-radius: 11px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: bold;
}}

QLabel#statusPill[tone="mint"] {{ background-color: {MINT}; color: {NAVY}; }}
QLabel#statusPill[tone="pink"] {{ background-color: {PINK}; color: {NAVY}; }}
QLabel#statusPill[tone="purple"] {{ background-color: {PERIWINKLE}; color: white; }}
QLabel#statusPill[tone="alert"] {{
    background-color: #FFD9E6;
    color: #C2386B;
    border-color: #C2386B;
}}

/* ---------- Buttons inside the dashboard ---------- */
QPushButton#mintButton {{
    background-color: {MINT};
    color: {NAVY};
    border: 3px solid {NAVY};
    border-radius: 16px;
    padding: 10px 22px;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#mintButton:hover {{
    background-color: {PINK};
}}

QPushButton#mintButton:pressed {{
    background-color: {CREAM};
}}

QPushButton#categoryButton {{
    background-color: {SOFT_LAVENDER};
    color: {NAVY};
    border: 2px solid {PERIWINKLE};
    border-radius: 16px;
    padding: 12px;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#categoryButton:hover {{
    background-color: {MINT};
    border-color: {NAVY};
}}

/* ---------- "Coming soon" pages ---------- */
QLabel#placeholderTitle {{
    color: {NAVY};
    font-size: 24px;
    font-weight: bold;
}}

QLabel#placeholderMessage {{
    color: {MUTED_TEXT};
    font-size: 14px;
}}
"""

# main.py still imports STYLESHEET, so we simply extend it.
STYLESHEET = STYLESHEET + DASHBOARD_STYLESHEET


# ======================================================================
# Stage 1A-1: token-based styles (Design Foundation)
# ======================================================================
# NOT added to STYLESHEET, so no existing screen changes. Every selector below only
# matches a widget that opts in with a dynamic property, e.g.
#       button.setProperty("ds", "button-primary")
# Later stages apply TOKEN_STYLESHEET (or `ds_stylesheet()`) and move one screen at a
# time onto these names. The old constants above (NAVY, PINK, ...) stay as they are.
from app import design_tokens as tk  # noqa: E402


def ds_button_qss(variant: str, fill: str, fill_hover: str, fill_pressed: str, text: str,
                  border: str = "transparent") -> str:
    """QSS for one button variant (shared by primary/secondary/danger/ghost)."""
    selector = f'QPushButton[ds="button-{variant}"]'
    return f"""
{selector} {{
    background-color: {fill};
    color: {text};
    border: 1px solid {border};
    border-radius: {tk.RADIUS_MD}px;
    min-height: {tk.CONTROL_HEIGHT_MD - 2}px;
    padding: 0 {tk.SPACE_5}px;
    font-family: {tk.FONT_FAMILY};
    font-size: {tk.FONT_SIZE_BODY}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{selector}:hover {{ background-color: {fill_hover}; }}
{selector}:pressed {{ background-color: {fill_pressed}; }}
{selector}:focus {{ border: 2px solid {tk.COLOR_FOCUS_RING}; }}
{selector}:disabled {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_DISABLED};
    border: 1px solid {tk.COLOR_BORDER};
}}
"""


def ds_stylesheet() -> str:
    """Reusable token-based styles. Opt in per widget with the `ds` property."""
    return "".join([
        ds_button_qss("primary", tk.COLOR_ACCENT, tk.COLOR_ACCENT_HOVER,
                      tk.COLOR_ACCENT_PRESSED, tk.COLOR_TEXT_ON_ACCENT),
        ds_button_qss("secondary", tk.COLOR_BG_RAISED, tk.COLOR_BG_OVERLAY,
                      tk.COLOR_BG_SURFACE, tk.COLOR_TEXT_PRIMARY, tk.COLOR_BORDER_STRONG),
        ds_button_qss("danger", tk.COLOR_DANGER_SOFT, tk.COLOR_DANGER_SOFT,
                      tk.COLOR_BG_SURFACE, tk.COLOR_DANGER, tk.COLOR_DANGER),
        ds_button_qss("ghost", "transparent", tk.COLOR_BG_RAISED, tk.COLOR_BG_OVERLAY,
                      tk.COLOR_TEXT_SECONDARY),
        f"""
QWidget[ds="page"] {{
    background-color: {tk.COLOR_BG_APP};
    color: {tk.COLOR_TEXT_PRIMARY};
    font-family: {tk.FONT_FAMILY};
    font-size: {tk.FONT_SIZE_BODY}px;
}}
QFrame[ds="sidebar"] {{ background-color: {tk.COLOR_BG_SIDEBAR}; }}
QFrame[ds="card"] {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel[ds="h1"] {{ color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_H1}px; font-weight: {tk.FONT_WEIGHT_BOLD}; }}
QLabel[ds="h2"] {{ color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_H2}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD}; }}
QLabel[ds="h3"] {{ color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_H3}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD}; }}
QLabel[ds="body"] {{ color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY}px; }}
QLabel[ds="secondary"] {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY}px; }}
QLabel[ds="muted"] {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px; }}
QLabel[ds="caption"] {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_CAPTION}px; }}
QLineEdit[ds="input"], QPlainTextEdit[ds="input"] {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    min-height: {tk.CONTROL_HEIGHT_MD - 2}px;
    padding: 0 {tk.SPACE_3}px;
    font-size: {tk.FONT_SIZE_BODY}px;
    selection-background-color: {tk.COLOR_ACCENT};
}}
QLineEdit[ds="input"]:hover, QPlainTextEdit[ds="input"]:hover {{ border: 1px solid {tk.COLOR_BORDER_STRONG}; }}
QLineEdit[ds="input"]:focus, QPlainTextEdit[ds="input"]:focus {{ border: 2px solid {tk.COLOR_FOCUS_RING}; }}
QLabel[ds="pill-success"] {{ background-color: {tk.COLOR_SUCCESS_SOFT}; color: {tk.COLOR_SUCCESS}; border-radius: {tk.RADIUS_MD}px; padding: {tk.SPACE_1}px {tk.SPACE_3}px; font-size: {tk.FONT_SIZE_SMALL}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD}; }}
QLabel[ds="pill-warning"] {{ background-color: {tk.COLOR_WARNING_SOFT}; color: {tk.COLOR_WARNING}; border-radius: {tk.RADIUS_MD}px; padding: {tk.SPACE_1}px {tk.SPACE_3}px; font-size: {tk.FONT_SIZE_SMALL}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD}; }}
QLabel[ds="pill-danger"] {{ background-color: {tk.COLOR_DANGER_SOFT}; color: {tk.COLOR_DANGER}; border-radius: {tk.RADIUS_MD}px; padding: {tk.SPACE_1}px {tk.SPACE_3}px; font-size: {tk.FONT_SIZE_SMALL}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD}; }}
QLabel[ds="pill-info"] {{ background-color: {tk.COLOR_INFO_SOFT}; color: {tk.COLOR_INFO}; border-radius: {tk.RADIUS_MD}px; padding: {tk.SPACE_1}px {tk.SPACE_3}px; font-size: {tk.FONT_SIZE_SMALL}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD}; }}
""",
    ])


TOKEN_STYLESHEET = ds_stylesheet()


# ======================================================================
# Stage 1A-2: soft-dark Login + Registration styles
# ======================================================================
# NOT added to STYLESHEET. LoginScreen and RegisterScreen apply this on themselves with
# setStyleSheet(), and every selector starts with `QWidget#loginScreen` (the object name
# both screens use), so it can only reach widgets inside those two screens. Other screens
# keep the global styles above. Object names are unchanged, so layouts and code are too.
_A = "QWidget#loginScreen"

AUTH_STYLESHEET = f"""
{_A} {{
    background-color: {tk.COLOR_BG_APP};
    font-family: {tk.FONT_FAMILY};
}}

/* ---------- left brand panel: deep navy with a quiet lavender glow ---------- */
{_A} QFrame#brandPanel {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {tk.COLOR_BG_SIDEBAR}, stop:1 #232754);
    border: none;
}}
{_A} QLabel#brandLogo {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: 48px;
    font-weight: {tk.FONT_WEIGHT_BOLD};
}}
{_A} QLabel#brandSlogan {{
    color: {tk.COLOR_ACCENT_HOVER};
    font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_A} QLabel#chip {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
    padding: {tk.SPACE_1}px {tk.SPACE_3}px;
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}

/* ---------- right form side: charcoal navy, one calm card ---------- */
{_A} QFrame#formPanel, {_A} QScrollArea#formScroll, {_A} QWidget#formInner {{
    background-color: {tk.COLOR_BG_APP};
    border: none;
}}
{_A} QFrame#loginCard {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_XL}px;
}}
{_A} QLabel {{
    background: transparent;
    border: none;
}}
{_A} QLabel#heading {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_H1}px;
    font-weight: {tk.FONT_WEIGHT_BOLD};
}}
{_A} QLabel#subheading {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
}}
{_A} QLabel#fieldLabel {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}

/* ---------- inputs ---------- */
{_A} QLineEdit {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 10px 14px;
    font-size: {tk.FONT_SIZE_BODY}px;
    selection-background-color: {tk.COLOR_ACCENT};
    selection-color: {tk.COLOR_TEXT_PRIMARY};
    placeholder-text-color: {tk.COLOR_TEXT_MUTED};
}}
{_A} QLineEdit:hover {{
    border: 1px solid {tk.COLOR_BORDER_STRONG};
}}
{_A} QLineEdit:focus {{
    border: 2px solid {tk.COLOR_FOCUS_RING};
    padding: 9px 13px;
    background-color: {tk.COLOR_BG_RAISED};
}}

/* ---------- buttons ---------- */
{_A} QPushButton#toggleButton {{
    background-color: {tk.COLOR_BG_OVERLAY};
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_SM + 2}px;
    padding: 2px 8px;
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_A} QPushButton#toggleButton:hover {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
}}
{_A} QPushButton#linkButton {{
    background: transparent;
    color: {tk.COLOR_ACCENT_HOVER};
    border: none;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
    padding: 2px 4px;
}}
{_A} QPushButton#linkButton:hover {{
    color: {tk.COLOR_TEXT_PRIMARY};
    text-decoration: underline;
}}
{_A} QPushButton#primaryButton {{
    background-color: {tk.COLOR_ACCENT};
    color: {tk.COLOR_TEXT_ON_ACCENT};
    border: 1px solid {tk.COLOR_ACCENT};
    border-radius: {tk.RADIUS_MD}px;
    padding: 12px;
    font-size: {tk.FONT_SIZE_LEAD}px;
    font-weight: {tk.FONT_WEIGHT_BOLD};
}}
{_A} QPushButton#primaryButton:hover {{
    background-color: {tk.COLOR_ACCENT_HOVER};
    border: 1px solid {tk.COLOR_ACCENT_HOVER};
}}
{_A} QPushButton#primaryButton:pressed {{
    background-color: {tk.COLOR_ACCENT_PRESSED};
    border: 1px solid {tk.COLOR_ACCENT_PRESSED};
}}
{_A} QPushButton#primaryButton:focus {{
    border: 2px solid {tk.COLOR_FOCUS_RING};
}}
{_A} QPushButton#primaryButton:disabled {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_DISABLED};
    border: 1px solid {tk.COLOR_BORDER};
}}

/* ---------- messages ---------- */
{_A} QLabel#statusLabel {{
    color: {tk.COLOR_SUCCESS};
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_A} QLabel#statusLabel[error="true"] {{
    color: {tk.COLOR_DANGER};
}}
"""


# ======================================================================
# Stage 1B/1C: compact icon-only sidebar
# ======================================================================
# NOT added to STYLESHEET. StudentDashboard applies SIDEBAR_STYLESHEET on the sidebar frame
# itself with setStyleSheet(); a widget's own style sheet wins over the application-wide one,
# and every selector starts with `QFrame#sidebar`, so nothing outside the sidebar changes.
# The old sidebar rules in DASHBOARD_STYLESHEET stay in place for the preview_*.py scripts.
SIDEBAR_WIDTH = 72        # px: a compact rail, icons only
NAV_BUTTON_SIZE = 46      # px: square, comfortably clickable
NAV_ICON_SIZE = 24        # px
AVATAR_SIZE = 40          # px

_S = "QFrame#sidebar"

SIDEBAR_STYLESHEET = f"""
{_S} {{
    background-color: {tk.COLOR_BG_SIDEBAR};
    border: none;
    border-right: 1px solid {tk.COLOR_BORDER};
}}

/* the scrolling list of navigation icons (scrolls only on very short windows) */
{_S} QScrollArea#sidebarScroll, {_S} QWidget#sidebarNav,
{_S} QScrollArea#sidebarScroll QWidget#qt_scrollarea_viewport {{
    background: transparent;
    border: none;
}}

/* navigation icons: quiet, soft lavender when it is the open page */
{_S} QPushButton#navButton, {_S} QPushButton#sidebarExitButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {tk.RADIUS_LG}px;
    padding: 0;
}}
{_S} QPushButton#navButton:hover, {_S} QPushButton#sidebarExitButton:hover {{
    background-color: {tk.COLOR_BG_RAISED};
}}
{_S} QPushButton#navButton:pressed, {_S} QPushButton#sidebarExitButton:pressed {{
    background-color: {tk.COLOR_BG_OVERLAY};
}}
{_S} QPushButton#navButton:checked, {_S} QPushButton#navButton:checked:hover {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    border: 1px solid transparent;
}}
{_S} QPushButton#navButton:focus, {_S} QPushButton#sidebarExitButton:focus {{
    border: 1px solid {tk.COLOR_FOCUS_RING};
}}

/* the student's circular avatar (initials for now); clicking opens Settings */
{_S} QPushButton#avatar {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    border-radius: {AVATAR_SIZE // 2}px;
    padding: 0;
    font-family: {tk.FONT_FAMILY};
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_S} QPushButton#avatar:hover {{
    border: 1px solid {tk.COLOR_ACCENT_HOVER};
}}
{_S} QPushButton#avatar:pressed {{
    background-color: {tk.COLOR_BG_OVERLAY};
}}
{_S} QPushButton#avatar:focus {{
    border: 2px solid {tk.COLOR_FOCUS_RING};
}}

/* hover labels for the icons */
{_S} QToolTip {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    padding: {tk.SPACE_1}px {tk.SPACE_2}px;
    font-size: {tk.FONT_SIZE_SMALL}px;
}}
"""
