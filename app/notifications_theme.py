"""Soft-dark look for the Notifications screen only (Step 26). Styles, no behaviour.

Every rule starts with `QWidget#notificationsScreen`, so it cannot affect any other screen.
Colors come from app/design_tokens.py. Unread rows get a faint lavender tint, a thin lavender
edge and a lavender dot; read rows are quiet text on the page with a hairline between rows.
"""
from app import design_tokens as tk
from app.header_style import ACCENT_LAVENDER

HAIRLINE = "#292E4C"
S = "QWidget#notificationsScreen"

NOTIFICATIONS_V2_QSS = f"""
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
{S} QLabel#notifNotice {{
    background: transparent; color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
}}
{S} QLabel#notifCounts {{
    background: transparent; color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px; padding-top: 2px;
}}
{S} QPushButton#notifGuideToggle {{
    background: transparent; color: {ACCENT_LAVENDER}; border: none; padding: 4px 2px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#notifGuideToggle:hover, {S} QPushButton#notifGuideToggle:focus {{
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

/* ---------- tabs and the Mark all button ---------- */
{S} QPushButton#notifTab {{
    background-color: transparent; color: {tk.COLOR_TEXT_SECONDARY}; border: none;
    border-radius: 16px; padding: 8px 18px;
    font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#notifTab:hover {{ background-color: {tk.COLOR_BG_SURFACE}; color: {tk.COLOR_TEXT_PRIMARY}; }}
{S} QPushButton#notifTab:checked {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: {ACCENT_LAVENDER};
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QPushButton#notifTab:focus {{ border: 1px solid {tk.COLOR_FOCUS_RING}; }}
{S} QPushButton#notifMarkAll {{
    background-color: transparent; color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {HAIRLINE}; border-radius: {tk.RADIUS_MD}px; padding: 7px 16px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#notifMarkAll:hover {{
    background-color: {tk.COLOR_BG_SURFACE}; color: {tk.COLOR_TEXT_PRIMARY}; border-color: {tk.COLOR_BORDER};
}}
{S} QPushButton#notifMarkAll:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{S} QPushButton#notifMarkAll:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; border-color: {HAIRLINE}; }}

/* ---------- notification rows ---------- */
{S} QFrame#notifRow {{
    background-color: transparent; border: none; border-radius: 0px;
    border-left: 2px solid transparent; border-bottom: 1px solid {HAIRLINE};
}}
{S} QFrame#notifRow[unread="true"] {{
    background-color: rgba(185, 168, 245, 16); border-left: 2px solid {ACCENT_LAVENDER};
}}
{S} QFrame#notifRow QLabel {{ background: transparent; }}
{S} QLabel#notifDot {{ color: transparent; font-size: 11px; }}
{S} QLabel#notifDot[unread="true"] {{ color: {ACCENT_LAVENDER}; }}
{S} QLabel#notifTitle {{
    color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QLabel#notifTitle[unread="true"] {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#notifMessage {{
    color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{S} QLabel#notifMessage[unread="true"] {{ color: {tk.COLOR_TEXT_SECONDARY}; }}
{S} QLabel#notifTime {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px; }}
{S} QLabel#notifState {{ color: {tk.COLOR_TEXT_DISABLED}; font-size: {tk.FONT_SIZE_CAPTION}px; }}
{S} QLabel#notifState[unread="true"] {{
    color: {ACCENT_LAVENDER}; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QPushButton#notifMarkButton {{
    background: transparent; color: {ACCENT_LAVENDER}; border: none; border-radius: {tk.RADIUS_SM}px;
    padding: 4px 8px; font-size: {tk.FONT_SIZE_SMALL}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#notifMarkButton:hover {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: {tk.COLOR_TEXT_PRIMARY};
}}
{S} QPushButton#notifMarkButton:focus {{ border: 1px solid {tk.COLOR_FOCUS_RING}; }}

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
