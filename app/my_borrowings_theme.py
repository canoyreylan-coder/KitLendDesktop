"""Soft-dark look for the My Borrowings screen only (Step 25). Styles, no behaviour.

Every rule starts with `QWidget#myBorrowingsScreen`, so it cannot affect any other screen
(and it wins over older shared rules). Colors come from app/design_tokens.py plus a hairline
shade. Overdue uses ONE warm color (the token danger tone), used sparingly: a small pill,
the due-date text and a faint card tint.
"""
from app import design_tokens as tk
from app.header_style import ACCENT_LAVENDER

HAIRLINE = "#292E4C"
CLOSED_CARD = "#191D34"
S = "QWidget#myBorrowingsScreen"

MY_BORROWINGS_V2_QSS = f"""
{S} {{ background-color: {tk.COLOR_BG_APP}; }}
{S} QScrollArea#catalogScroll, {S} QWidget#catalogContent {{ background: transparent; }}
{S} QScrollArea#catalogScroll QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
{S} QScrollArea#catalogScroll QScrollBar::handle:vertical {{
    background: {tk.COLOR_BORDER}; border-radius: 4px; min-height: 36px;
}}
{S} QScrollArea#catalogScroll QScrollBar::handle:vertical:hover {{ background: {tk.COLOR_BORDER_STRONG}; }}
{S} QScrollArea#catalogScroll QScrollBar::add-line:vertical,
{S} QScrollArea#catalogScroll QScrollBar::sub-line:vertical {{ height: 0px; }}
{S} QScrollArea#catalogScroll QScrollBar::add-page:vertical,
{S} QScrollArea#catalogScroll QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- header text ---------- */
{S} QLabel#borrowNotice {{
    background: transparent; color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
}}
{S} QLabel#borrowCounts {{
    background: transparent; color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px; padding-top: 2px;
}}
{S} QPushButton#borrowGuideToggle {{
    background: transparent; color: {ACCENT_LAVENDER}; border: none; padding: 4px 2px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#borrowGuideToggle:hover, {S} QPushButton#borrowGuideToggle:focus {{
    color: {tk.COLOR_TEXT_PRIMARY};
}}
{S} QFrame#myListInfo {{
    background-color: rgba(113, 117, 245, 22); border: none; border-radius: {tk.RADIUS_MD}px;
}}
{S} QLabel#myListInfoText {{
    background: transparent; color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{S} QLabel#myListBanner {{
    background-color: {tk.COLOR_SUCCESS_SOFT}; color: {tk.COLOR_SUCCESS}; border: none;
    border-radius: {tk.RADIUS_MD}px; padding: 10px 14px; font-size: {tk.FONT_SIZE_BODY - 1}px;
}}

/* ---------- tabs ---------- */
{S} QPushButton#borrowTab {{
    background-color: transparent; color: {tk.COLOR_TEXT_SECONDARY}; border: none;
    border-radius: 16px; padding: 8px 18px;
    font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#borrowTab:hover {{ background-color: {tk.COLOR_BG_SURFACE}; color: {tk.COLOR_TEXT_PRIMARY}; }}
{S} QPushButton#borrowTab:checked {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: {ACCENT_LAVENDER};
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QPushButton#borrowTab:focus {{ border: 1px solid {tk.COLOR_FOCUS_RING}; }}
{S} QLabel#borrowTabHint {{
    background: transparent; color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
}}

/* ---------- compact borrowing cards ---------- */
{S} QFrame#borrowCard {{
    background-color: {tk.COLOR_BG_SURFACE}; border: 1px solid {HAIRLINE};
    border-radius: {tk.RADIUS_LG}px;
}}
{S} QFrame#borrowCard[closed="true"] {{ background-color: {CLOSED_CARD}; }}
{S} QFrame#borrowCard[overdue="true"] {{
    background-color: #241E34; border: 1px solid #4A3042;
}}
{S} QFrame#borrowCard QLabel {{ background: transparent; }}
{S} QFrame#borrowCard QLabel#borrowTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_LEAD}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QFrame#borrowCard[closed="true"] QLabel#borrowTitle {{ color: {tk.COLOR_TEXT_SECONDARY}; }}
{S} QFrame#borrowCard QLabel#borrowSub {{
    color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
}}
{S} QFrame#borrowCard QLabel#myListIcon {{
    border-radius: {tk.RADIUS_MD}px; font-size: 20px;
}}
{S} QLabel#borrowFactLabel {{
    background: transparent; color: {tk.COLOR_TEXT_MUTED}; font-size: 10px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#borrowFactValue {{
    background: transparent; color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{S} QLabel#borrowFactValue[muted="true"] {{ color: {tk.COLOR_TEXT_MUTED}; font-style: italic; }}
{S} QLabel#borrowFactValue[overdue="true"] {{ color: {tk.COLOR_DANGER}; font-weight: {tk.FONT_WEIGHT_MEDIUM}; }}

/* status pills: quiet tints; the words always say which */
{S} QLabel#borrowStatus {{
    border: none; border-radius: 11px; padding: 3px 11px;
    font-size: {tk.FONT_SIZE_SMALL}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#borrowStatus[status="borrowed"]       {{ background-color: {tk.COLOR_ACCENT_SOFT}; color: {ACCENT_LAVENDER}; }}
{S} QLabel#borrowStatus[status="return_pending"] {{ background-color: {tk.COLOR_HIGHLIGHT_SOFT}; color: {tk.COLOR_HIGHLIGHT}; }}
{S} QLabel#borrowStatus[status="returned"]       {{ background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_SECONDARY}; }}
{S} QLabel#borrowStatus[status="overdue"]        {{ background-color: {tk.COLOR_DANGER_SOFT}; color: {tk.COLOR_DANGER}; }}

/* ---------- empty state ---------- */
{S} QFrame#catalogEmpty {{
    background-color: transparent; border: 1px solid {HAIRLINE}; border-radius: {tk.RADIUS_XL}px;
}}
{S} QFrame#catalogEmpty QLabel {{ background: transparent; }}
{S} QLabel#catalogEmptyIcon {{ font-size: 30px; color: {ACCENT_LAVENDER}; }}
{S} QLabel#catalogEmptyTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#catalogEmptyText {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY - 1}px; }}
{S} QFrame#catalogEmpty QPushButton#catalogPrimaryButton {{
    background-color: {tk.COLOR_ACCENT}; color: {tk.COLOR_TEXT_PRIMARY}; border: none;
    border-radius: {tk.RADIUS_MD}px; padding: 10px 24px;
    font-size: {tk.FONT_SIZE_BODY}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QFrame#catalogEmpty QPushButton#catalogPrimaryButton:hover {{ background-color: {tk.COLOR_ACCENT_HOVER}; }}
{S} QFrame#catalogEmpty QPushButton#catalogPrimaryButton:pressed {{ background-color: {tk.COLOR_ACCENT_PRESSED}; }}
{S} QFrame#catalogEmpty QPushButton#catalogPrimaryButton:focus {{ border: 1px solid {tk.COLOR_FOCUS_RING}; }}
"""
