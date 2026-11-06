"""Soft-dark look for the Reservations screen only (Step 27). Styles, no behaviour.

Every rule starts with `QWidget#reservationsScreen`, so it cannot affect any other screen.
A reservation whose pickup deadline has passed gets the same single soft rose tone that
overdue borrowings use (the time-to-collect text and a faint card tint).
"""
from app import design_tokens as tk
from app.header_style import ACCENT_LAVENDER

HAIRLINE = "#292E4C"
CLOSED_CARD = "#191D34"
S = "QWidget#reservationsScreen"

MY_RESERVATIONS_V2_QSS = f"""
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
{S} QLabel#resvNotice {{
    background: transparent; color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
}}
{S} QLabel#resvCounts {{
    background: transparent; color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px; padding-top: 2px;
}}
{S} QPushButton#resvGuideToggle {{
    background: transparent; color: {ACCENT_LAVENDER}; border: none; padding: 4px 2px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#resvGuideToggle:hover, {S} QPushButton#resvGuideToggle:focus {{
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
{S} QPushButton#resvTab {{
    background-color: transparent; color: {tk.COLOR_TEXT_SECONDARY}; border: none;
    border-radius: 16px; padding: 8px 18px;
    font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#resvTab:hover {{ background-color: {tk.COLOR_BG_SURFACE}; color: {tk.COLOR_TEXT_PRIMARY}; }}
{S} QPushButton#resvTab:checked {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: {ACCENT_LAVENDER};
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QPushButton#resvTab:focus {{ border: 1px solid {tk.COLOR_FOCUS_RING}; }}
{S} QLabel#resvTabHint {{
    background: transparent; color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
}}

/* ---------- compact reservation cards ---------- */
{S} QFrame#resvCard {{
    background-color: {tk.COLOR_BG_SURFACE}; border: 1px solid {HAIRLINE};
    border-radius: {tk.RADIUS_LG}px;
}}
{S} QFrame#resvCard[closed="true"] {{ background-color: {CLOSED_CARD}; }}
{S} QFrame#resvCard[late="true"] {{
    background-color: #241E34; border: 1px solid #4A3042;
}}
{S} QFrame#resvCard QLabel {{ background: transparent; }}
{S} QFrame#resvCard QLabel#resvTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_LEAD}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QFrame#resvCard[closed="true"] QLabel#resvTitle {{ color: {tk.COLOR_TEXT_SECONDARY}; }}
{S} QFrame#resvCard QLabel#resvSub {{
    color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
}}
{S} QFrame#resvCard QLabel#myListIcon {{
    border-radius: {tk.RADIUS_MD}px; font-size: 20px;
}}
{S} QLabel#resvFactLabel {{
    background: transparent; color: {tk.COLOR_TEXT_MUTED}; font-size: 10px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#resvFactValue {{
    background: transparent; color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{S} QLabel#resvFactValue[muted="true"] {{ color: {tk.COLOR_TEXT_MUTED}; font-style: italic; }}
{S} QLabel#resvFactValue[late="true"] {{ color: {tk.COLOR_DANGER}; font-weight: {tk.FONT_WEIGHT_MEDIUM}; }}

/* status pills: quiet tints; the words always say which */
{S} QLabel#resvStatus {{
    border: none; border-radius: 11px; padding: 3px 11px;
    font-size: {tk.FONT_SIZE_SMALL}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#resvStatus[status="approved"]  {{ background-color: {tk.COLOR_ACCENT_SOFT}; color: {ACCENT_LAVENDER}; }}
{S} QLabel#resvStatus[status="expired"]   {{ background-color: {tk.COLOR_WARNING_SOFT}; color: {tk.COLOR_WARNING}; }}
{S} QLabel#resvStatus[status="cancelled"] {{ background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_MUTED}; }}
{S} QLabel#resvNote {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px; font-style: italic; }}

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
