"""Soft-dark styles for the Dashboard home page ONLY (Stage 2A).

Built from app/design_tokens.py. The sheet is set on the home page widget itself and every
selector uses a `home*` object name that no other screen uses, so nothing else in the
application changes appearance. Other screens move onto the tokens in later stages.
"""
from app import design_tokens as tk

# Soft text tones for pills/dots on dark surfaces (the tokens' accents are fill colors).
LAVENDER_TEXT = "#B9BCF5"
PILL_TONES = {                      # tone -> (background, text)
    "lavender": (tk.COLOR_ACCENT_SOFT, LAVENDER_TEXT),
    "pink": (tk.COLOR_HIGHLIGHT_SOFT, tk.COLOR_HIGHLIGHT),
    "mint": (tk.COLOR_SUCCESS_SOFT, tk.COLOR_SUCCESS),
    "amber": (tk.COLOR_WARNING_SOFT, tk.COLOR_WARNING),
    "rose": (tk.COLOR_DANGER_SOFT, tk.COLOR_DANGER),
    "muted": (tk.COLOR_BG_RAISED, tk.COLOR_TEXT_SECONDARY),
}
DOT_COLORS = {
    "lavender": "#8B8FFF", "pink": tk.COLOR_HIGHLIGHT, "mint": tk.COLOR_SUCCESS,
    "amber": tk.COLOR_WARNING, "rose": tk.COLOR_DANGER, "muted": tk.COLOR_TEXT_DISABLED,
}


def _tone_rules() -> str:
    rules = []
    for tone, (bg, fg) in PILL_TONES.items():
        rules.append(f'QLabel#homePill[tone="{tone}"] {{ background-color: {bg}; color: {fg}; }}')
    for tone, color in DOT_COLORS.items():
        rules.append(f'QLabel#homeDot[tone="{tone}"] {{ background-color: {color}; }}')
    return "\n".join(rules)


HOME_STYLESHEET = f"""
QScrollArea#homeScroll, QWidget#homeContent {{
    background-color: {tk.COLOR_BG_APP};
    border: none;
}}

QScrollArea#homeScroll QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}
QScrollArea#homeScroll QScrollBar::handle:vertical {{
    background: {tk.COLOR_BORDER_STRONG};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollArea#homeScroll QScrollBar::add-line:vertical,
QScrollArea#homeScroll QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollArea#homeScroll QScrollBar::add-page:vertical,
QScrollArea#homeScroll QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- welcome bar ---------- */
QFrame#homeWelcome {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#homeEyebrow {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
    background: transparent;
}}
QLabel#homeTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_H2}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
    background: transparent;
}}
QLabel#homeSummary {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    background: transparent;
}}

/* ---------- stat tiles ---------- */
QFrame#homeStat {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QFrame#homeStat:hover {{
    background-color: {tk.COLOR_BG_RAISED};
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QLabel#homeStatLabel {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
    background: transparent;
}}
QLabel#homeStatNumber {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: 28px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
    background: transparent;
}}
QLabel#homeStatHint {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
    background: transparent;
}}

/* ---------- cards ---------- */
QFrame#homeCard {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#homeCardTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_BODY + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
    background: transparent;
}}
QLabel#homeCardSubtitle {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
    background: transparent;
}}
QLabel#homeNote {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    background: transparent;
    padding: 6px 2px;
}}

/* ---------- rows ---------- */
QFrame#homeRow {{
    background-color: {tk.COLOR_BG_RAISED};
    border: 1px solid transparent;
    border-radius: {tk.RADIUS_MD}px;
}}
QFrame#homeRow[unread="true"] {{
    background-color: #2A2F52;
    border: 1px solid {tk.COLOR_BORDER};
}}
QLabel#homeRowTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
    background: transparent;
}}
QLabel#homeRowMeta {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
    background: transparent;
}}
QProgressBar#homeProgress {{
    background-color: {tk.COLOR_BG_OVERLAY};
    border: none;
    border-radius: 2px;
}}
QProgressBar#homeProgress::chunk {{
    background-color: #8B8FFF;
    border-radius: 2px;
}}
QLabel#homePill {{
    border-radius: 9px;
    padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#homeDot {{
    border-radius: 4px;
}}

/* ---------- buttons ---------- */
QPushButton#homeLink {{
    background: transparent;
    border: none;
    color: {LAVENDER_TEXT};
    font-size: {tk.FONT_SIZE_SMALL}px;
    padding: 2px 4px;
}}
QPushButton#homeLink:hover {{ color: {tk.COLOR_TEXT_PRIMARY}; text-decoration: underline; }}

QPushButton#homePrimary {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: #D5D7FF;
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    border-radius: {tk.RADIUS_MD}px;
    padding: 9px 18px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QPushButton#homePrimary:hover {{
    background-color: #353A78;
    border-color: {tk.COLOR_FOCUS_RING};
}}
QPushButton#homePrimary:pressed {{ background-color: {tk.COLOR_BG_OVERLAY}; }}

QPushButton#homeAction {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 11px 14px;
    text-align: left;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QPushButton#homeAction:hover {{
    background-color: {tk.COLOR_BG_OVERLAY};
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QPushButton#homeAction:pressed {{ background-color: {tk.COLOR_ACCENT_SOFT}; }}

{_tone_rules()}
"""
