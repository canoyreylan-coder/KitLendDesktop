"""Soft-dark styles for the My List SCREEN only (Step 22).

Built from app/design_tokens.py, like the Dashboard, Catalog and Item Details. Every selector
uses an `ml*` object name that no other widget uses and there are NO generic selectors
(such as a bare `QLabel`), so nothing leaks into the request dialog (which keeps its own
styles in MY_LIST_STYLESHEET) or into My Requests, which still imports that old sheet.
"""
from app import design_tokens as tk
from app.home_theme import LAVENDER_TEXT, PILL_TONES


def _pill_rules() -> str:
    tone_to_pill = {"school": "lavender", "student": "pink", "ok": "mint", "low": "amber",
                    "none": "rose"}
    return "\n".join(
        f'QLabel#mlPill[tone="{tone}"] {{ background-color: {PILL_TONES[pill][0]}; '
        f'color: {PILL_TONES[pill][1]}; }}' for tone, pill in tone_to_pill.items())


MY_LIST_V2_STYLESHEET = f"""
QWidget#myListScreen {{ background-color: {tk.COLOR_BG_APP}; }}
QScrollArea#mlScroll, QWidget#mlContent, QWidget#mlRows {{
    background-color: {tk.COLOR_BG_APP};
    border: none;
}}
QScrollArea#mlScroll QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollArea#mlScroll QScrollBar::handle:vertical {{
    background: {tk.COLOR_BORDER_STRONG}; border-radius: 3px; min-height: 30px;
}}
QScrollArea#mlScroll QScrollBar::add-line:vertical,
QScrollArea#mlScroll QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollArea#mlScroll QScrollBar::add-page:vertical,
QScrollArea#mlScroll QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- header ---------- */
QFrame#mlHeader {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#mlTag {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: {LAVENDER_TEXT};
    border-radius: 9px;
    padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#mlTitle {{
    background: transparent;
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: 24px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#mlSubtitle {{
    background: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
QLabel#mlMascot {{ background: transparent; }}

/* ---------- banner ---------- */
QLabel#myListBanner {{
    background-color: {tk.COLOR_SUCCESS_SOFT};
    color: {tk.COLOR_SUCCESS};
    border: 1px solid #25584A;
    border-radius: {tk.RADIUS_MD}px;
    padding: 10px 14px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}

/* ---------- toolbar ---------- */
QFrame#mlToolbar {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#mlSummary {{
    background: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QPushButton#mlSelectAll {{
    background-color: transparent;
    color: {LAVENDER_TEXT};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 14px;
    min-height: 32px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QPushButton#mlSelectAll:hover {{
    background-color: {tk.COLOR_BG_RAISED};
    border-color: {tk.COLOR_BORDER_STRONG};
    color: {tk.COLOR_TEXT_PRIMARY};
}}
QPushButton#mlSelectAll:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
QPushButton#mlSelectAll:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; }}

/* ---------- saved item cards ---------- */
QFrame#mlCard {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QFrame#mlCard:hover {{ background-color: #20253F; border-color: {tk.COLOR_BORDER_STRONG}; }}
QFrame#mlCard[selected="true"] {{
    background-color: #20254A;
    border-color: {tk.COLOR_FOCUS_RING};
}}
QFrame#mlCard[unavailable="true"] {{ background-color: #191D32; }}
QLabel#mlItemTitle {{
    background: transparent;
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_BODY}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QFrame#mlCard[unavailable="true"] QLabel#mlItemTitle {{ color: {tk.COLOR_TEXT_SECONDARY}; }}
QLabel#mlItemMeta {{
    background: transparent;
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
}}
QLabel#mlItemNote {{
    background: transparent;
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_CAPTION}px;
}}
QLabel#mlPill {{
    border-radius: 9px;
    padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_pill_rules()}
QPushButton#mlCheck {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_ON_ACCENT};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    border-radius: 8px;
    font-size: 15px;
    font-weight: {tk.FONT_WEIGHT_BOLD};
}}
QPushButton#mlCheck:hover {{ border-color: {tk.COLOR_FOCUS_RING}; }}
QPushButton#mlCheck:checked {{
    background-color: {tk.COLOR_ACCENT_HOVER};
    border-color: {tk.COLOR_ACCENT_HOVER};
}}
QPushButton#mlCheck:focus {{ border: 2px solid {tk.COLOR_FOCUS_RING}; }}
QPushButton#mlCheck:disabled {{
    background-color: transparent;
    border: 1px dashed {tk.COLOR_BORDER};
}}
QPushButton#myListRemoveButton {{
    background-color: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 14px;
    min-height: 30px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QPushButton#myListRemoveButton:hover {{
    background-color: {tk.COLOR_DANGER_SOFT};
    color: {tk.COLOR_DANGER};
    border-color: #6A3342;
}}
QPushButton#myListRemoveButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}

/* ---------- bottom action bar ---------- */
QFrame#mlActionBar {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#mlSelectedLabel {{
    background: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QPushButton#mlRequestButton {{
    background-color: {tk.COLOR_ACCENT};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_ACCENT_HOVER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 22px;
    min-height: 38px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QPushButton#mlRequestButton:hover {{ background-color: {tk.COLOR_ACCENT_HOVER}; }}
QPushButton#mlRequestButton:pressed {{ background-color: {tk.COLOR_ACCENT_PRESSED}; }}
QPushButton#mlRequestButton:focus {{ border: 2px solid {tk.COLOR_TEXT_PRIMARY}; }}
QPushButton#mlRequestButton:disabled {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_DISABLED};
    border: 1px solid {tk.COLOR_BORDER};
}}

/* ---------- empty state ---------- */
QFrame#mlEmpty {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#mlEmptyIcon {{ background: transparent; font-size: 36px; }}
QLabel#mlEmptyTitle {{
    background: transparent;
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#mlEmptyText {{
    background: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
QPushButton#mlPrimaryButton {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: #D5D7FF;
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    border-radius: {tk.RADIUS_MD}px;
    padding: 9px 22px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QPushButton#mlPrimaryButton:hover {{
    background-color: #353A78;
    border-color: {tk.COLOR_FOCUS_RING};
}}
QPushButton#mlPrimaryButton:pressed {{ background-color: {tk.COLOR_BG_OVERLAY}; }}
QPushButton#mlPrimaryButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
"""
