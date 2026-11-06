"""Soft-dark look for the My Requests screen only (Step 23). Styles, no behaviour.

Every rule starts with `QWidget#myRequestsScreen`, so it can only affect this one screen
(and wins over the older Pixel Pop rules that share some object names with other screens).
The Cancel Request dialog keeps its own stylesheet. Colors come from app/design_tokens.py,
plus a few hairline shades between the token surfaces.
"""
from app import design_tokens as tk
from app.catalog_theme import CHEVRON_PATH
from app.header_style import ACCENT_DUSTY_PINK, ACCENT_LAVENDER

HAIRLINE = "#292E4C"      # barely-there border, softer than COLOR_BORDER
INSET = "#171B31"         # recessed panel (details) on a card
CLOSED_CARD = "#191D34"   # finished requests sit a little quieter than active ones
S = "QWidget#myRequestsScreen"

MY_REQUESTS_V2_QSS = f"""
{S} {{ background-color: {tk.COLOR_BG_APP}; }}
{S} QScrollArea#catalogScroll, {S} QWidget#catalogContent {{ background: transparent; }}
{S} QScrollArea#catalogScroll QScrollBar:vertical {{
    background: transparent; width: 8px; margin: 2px;
}}
{S} QScrollArea#catalogScroll QScrollBar::handle:vertical {{
    background: {tk.COLOR_BORDER}; border-radius: 4px; min-height: 36px;
}}
{S} QScrollArea#catalogScroll QScrollBar::handle:vertical:hover {{ background: {tk.COLOR_BORDER_STRONG}; }}
{S} QScrollArea#catalogScroll QScrollBar::add-line:vertical,
{S} QScrollArea#catalogScroll QScrollBar::sub-line:vertical {{ height: 0px; }}
{S} QScrollArea#catalogScroll QScrollBar::add-page:vertical,
{S} QScrollArea#catalogScroll QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- notes and banners: tinted text blocks, no outlines ---------- */
{S} QFrame#myListInfo {{
    background-color: rgba(113, 117, 245, 22);
    border: none;
    border-radius: {tk.RADIUS_MD}px;
}}
{S} QLabel#myListInfoText {{
    background: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{S} QLabel#myListBanner {{
    background-color: {tk.COLOR_SUCCESS_SOFT};
    color: {tk.COLOR_SUCCESS};
    border: none;
    border-radius: {tk.RADIUS_MD}px;
    padding: 10px 14px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{S} QLabel#catalogResultLabel {{
    background: transparent;
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
}}

/* ---------- summary tiles ---------- */
{S} QFrame#myReqStat {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {HAIRLINE};
    border-radius: {tk.RADIUS_LG}px;
}}
{S} QLabel#myReqStatLabel {{
    background: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QLabel#myReqStatValue {{
    background: transparent;
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: 26px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#myReqStatHint {{
    background: transparent;
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_CAPTION}px;
}}

/* ---------- status filter chips ---------- */
{S} QPushButton#myReqChip {{
    background-color: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {HAIRLINE};
    border-radius: 15px;
    padding: 7px 12px;
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#myReqChip:hover {{
    background-color: {tk.COLOR_BG_SURFACE};
    border-color: {tk.COLOR_BORDER};
    color: {tk.COLOR_TEXT_PRIMARY};
}}
{S} QPushButton#myReqChip:checked {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: {ACCENT_LAVENDER};
    border-color: {tk.COLOR_ACCENT_SOFT};
}}
{S} QPushButton#myReqChip:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}

/* ---------- request cards ---------- */
{S} QFrame#myReqCard {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {HAIRLINE};
    border-radius: {tk.RADIUS_LG + 2}px;
}}
{S} QFrame#myReqCard[closed="true"] {{
    background-color: {CLOSED_CARD};
    border: 1px solid {HAIRLINE};
}}
{S} QFrame#myReqCard QLabel {{ background: transparent; }}
{S} QFrame#myReqCard QLabel#catalogItemTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_LEAD}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QFrame#myReqCard[closed="true"] QLabel#catalogItemTitle {{ color: {tk.COLOR_TEXT_SECONDARY}; }}
{S} QFrame#myReqCard QLabel#catalogItemCreator {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
}}
{S} QFrame#myReqCard QLabel#catalogItemNote {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_SMALL}px;
}}
{S} QFrame#myReqCard QLabel#myListIcon {{
    border-radius: {tk.RADIUS_MD + 2}px;
    font-size: 24px;
}}
{S} QLabel#myReqId {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QLabel#myReqDescription {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{S} QLabel#myReqNote {{
    color: {ACCENT_DUSTY_PINK};
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-style: italic;
}}
{S} QLabel#myReqActionNote {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
}}

/* owner tags: soft tints instead of outlined pills */
{S} QFrame#myReqCard QLabel#catalogPill {{
    border: none;
    border-radius: 10px;
    padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QFrame#myReqCard QLabel#catalogPill[tone="school"] {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: {ACCENT_LAVENDER};
}}
{S} QFrame#myReqCard QLabel#catalogPill[tone="student"] {{
    background-color: {tk.COLOR_HIGHLIGHT_SOFT}; color: {ACCENT_DUSTY_PINK};
}}

/* ---------- details: recessed panels, small caps labels ---------- */
{S} QFrame#myReqFact {{
    background-color: {INSET};
    border: none;
    border-radius: {tk.RADIUS_MD}px;
}}
{S} QLabel#myReqFactLabel {{
    background: transparent;
    color: {tk.COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#myReqFactValue {{
    background: transparent;
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QLabel#myReqFactValue[muted="true"] {{
    color: {tk.COLOR_TEXT_MUTED};
    font-weight: {tk.FONT_WEIGHT_REGULAR};
    font-style: italic;
}}

/* ---------- status pills: one soft tint per status (the words always say which) ---------- */
{S} QLabel#myReqStatus {{
    border: none;
    border-radius: 12px;
    padding: 4px 12px;
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#myReqStatus[status="pending"]        {{ background-color: {tk.COLOR_WARNING_SOFT}; color: {tk.COLOR_WARNING}; }}
{S} QLabel#myReqStatus[status="approved"]       {{ background-color: {tk.COLOR_SUCCESS_SOFT}; color: {tk.COLOR_SUCCESS}; }}
{S} QLabel#myReqStatus[status="borrowed"]       {{ background-color: {tk.COLOR_ACCENT_SOFT}; color: {ACCENT_LAVENDER}; }}
{S} QLabel#myReqStatus[status="return_pending"] {{ background-color: {tk.COLOR_HIGHLIGHT_SOFT}; color: {ACCENT_DUSTY_PINK}; }}
{S} QLabel#myReqStatus[status="returned"]       {{ background-color: {tk.COLOR_INFO_SOFT}; color: {tk.COLOR_INFO}; }}
{S} QLabel#myReqStatus[status="rejected"]       {{ background-color: {tk.COLOR_DANGER_SOFT}; color: {tk.COLOR_DANGER}; }}
{S} QLabel#myReqStatus[status="cancelled"]      {{ background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_MUTED}; }}
{S} QLabel#myReqStatus[status="expired"]        {{ background-color: #3A2A22; color: #E9A27A; }}

/* ---------- Cancel Request button: quiet until you need it ---------- */
{S} QFrame#myReqCard QPushButton#myListRemoveButton {{
    background-color: transparent;
    color: {tk.COLOR_DANGER};
    border: 1px solid #5A3040;
    border-radius: {tk.RADIUS_MD}px;
    padding: 7px 16px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QFrame#myReqCard QPushButton#myListRemoveButton:hover {{
    background-color: {tk.COLOR_DANGER_SOFT};
    border-color: {tk.COLOR_DANGER};
}}
{S} QFrame#myReqCard QPushButton#myListRemoveButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}

/* ---------- empty state ---------- */
{S} QFrame#catalogEmpty {{
    background-color: transparent;
    border: 1px solid {HAIRLINE};
    border-radius: {tk.RADIUS_XL}px;
}}
{S} QFrame#catalogEmpty QLabel {{ background: transparent; }}
{S} QLabel#catalogEmptyIcon {{ font-size: 34px; }}
{S} QLabel#catalogEmptyTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#catalogEmptyText {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{S} QFrame#catalogEmpty QPushButton#catalogPrimaryButton {{
    background-color: {tk.COLOR_ACCENT};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: none;
    border-radius: {tk.RADIUS_MD}px;
    padding: 10px 24px;
    font-size: {tk.FONT_SIZE_BODY}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QFrame#catalogEmpty QPushButton#catalogPrimaryButton:hover {{ background-color: {tk.COLOR_ACCENT_HOVER}; }}
{S} QFrame#catalogEmpty QPushButton#catalogPrimaryButton:pressed {{ background-color: {tk.COLOR_ACCENT_PRESSED}; }}
{S} QFrame#catalogEmpty QPushButton#catalogPrimaryButton:focus {{ border: 1px solid {tk.COLOR_FOCUS_RING}; }}

/* ---------- Step 23b: calmer layout (notice, counts, guide, tabs, toolbar) ---------- */
{S} QLabel#myReqNotice {{
    background: transparent;
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
}}
{S} QLabel#myReqCounts {{
    background: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    padding-top: 4px;
}}
{S} QPushButton#myReqGuideToggle {{
    background: transparent;
    color: {ACCENT_LAVENDER};
    border: none;
    padding: 4px 2px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#myReqGuideToggle:hover {{ color: {tk.COLOR_TEXT_PRIMARY}; }}
{S} QPushButton#myReqGuideToggle:focus {{ color: {tk.COLOR_TEXT_PRIMARY}; }}

{S} QPushButton#myReqTab {{
    background-color: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    border: none;
    border-radius: 16px;
    padding: 8px 20px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#myReqTab:hover {{
    background-color: {tk.COLOR_BG_SURFACE};
    color: {tk.COLOR_TEXT_PRIMARY};
}}
{S} QPushButton#myReqTab:checked {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: {ACCENT_LAVENDER};
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QPushButton#myReqTab:focus {{ border: 1px solid {tk.COLOR_FOCUS_RING}; }}

{S} QComboBox#myReqFilter {{
    background-color: {tk.COLOR_BG_SURFACE};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {HAIRLINE};
    border-radius: {tk.RADIUS_MD}px;
    padding: 6px 12px;
    min-height: 20px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
}}
{S} QComboBox#myReqFilter::drop-down {{ border: none; width: 24px; }}
{S} QComboBox#myReqFilter::down-arrow {{ image: url({CHEVRON_PATH}); width: 12px; height: 12px; }}
{S} QComboBox#myReqFilter:hover {{ border-color: {tk.COLOR_BORDER}; }}
{S} QComboBox#myReqFilter:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{S} QComboBox#myReqFilter QAbstractItemView {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    selection-background-color: {tk.COLOR_ACCENT_SOFT};
    selection-color: {ACCENT_LAVENDER};
    outline: none;
}}

{S} QPushButton#myReqClearButton {{
    background-color: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {HAIRLINE};
    border-radius: {tk.RADIUS_MD}px;
    padding: 7px 16px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#myReqClearButton:hover {{
    background-color: {tk.COLOR_BG_SURFACE};
    color: {tk.COLOR_TEXT_PRIMARY};
    border-color: {tk.COLOR_BORDER};
}}
{S} QPushButton#myReqClearButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}

/* ---------- compact request cards ---------- */
{S} QFrame#myReqRule {{ background-color: {HAIRLINE}; border: none; }}
{S} QLabel#myReqMiniLabel {{
    background: transparent;
    color: {tk.COLOR_TEXT_MUTED};
    font-size: 10px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#myReqMiniValue {{
    background: transparent;
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{S} QLabel#myReqMiniValue[muted="true"] {{
    color: {tk.COLOR_TEXT_MUTED};
    font-style: italic;
}}
"""

# The "Clear History / Clear Cancelled" confirmation (a separate window, so it has its own sheet).
CLEAR_DIALOG_QSS = f"""
QDialog#myReqClearDialog {{ background-color: {tk.COLOR_BG_SURFACE}; }}
QDialog#myReqClearDialog QLabel {{ background: transparent; }}
QLabel#clearTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#clearText {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
QPushButton#clearKeep {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: {ACCENT_LAVENDER};
    border: none;
    border-radius: {tk.RADIUS_MD}px;
    padding: 9px 20px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QPushButton#clearKeep:hover {{ background-color: #353A78; }}
QPushButton#clearConfirm {{
    background-color: transparent;
    color: {tk.COLOR_DANGER};
    border: 1px solid #5A3040;
    border-radius: {tk.RADIUS_MD}px;
    padding: 9px 20px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QPushButton#clearConfirm:hover {{ background-color: {tk.COLOR_DANGER_SOFT}; border-color: {tk.COLOR_DANGER}; }}
QPushButton#clearKeep:focus, QPushButton#clearConfirm:focus {{ border: 1px solid {tk.COLOR_FOCUS_RING}; }}
"""
