"""Soft-dark styles for the Browse Catalog screen ONLY (Step 16).

Built from app/design_tokens.py, in the same way as app/home_theme.py (the Dashboard).
Every selector uses a `cat*` object name that no other screen uses, so nothing else in
the application changes appearance.

IMPORTANT: the old Pixel Pop `CATALOG_STYLESHEET` in app/catalog_screen.py is intentionally
left alone. My List, My Requests, My Borrowings, Reservations, Notifications and Settings
still import and use it, and they move onto the tokens in later steps.
"""
from pathlib import Path

from app import design_tokens as tk
from app.home_theme import LAVENDER_TEXT, PILL_TONES

# Cover-image slot tints (background, text, border). Real item images will replace the
# slot contents later; the slot's size and rounded frame stay the same.
COVER_TINTS = {
    "lavender": ("#23284A", "#B9BCF5", "#343A66"),
    "pink": ("#33233F", tk.COLOR_HIGHLIGHT, "#4A3358"),
    "mint": ("#1E3238", "#9EE6CF", "#2C4A50"),
}


# Small arrow for the filter dropdowns (a file path, because QSS can only load images by path).
CHEVRON_PATH = (Path(__file__).resolve().parent.parent / "assets" / "icon_chevron_down.png").as_posix()


def _tag_rules() -> str:
    """Ownership + availability pills. Tone names: school, student, ok, low, none."""
    tone_to_pill = {
        "school": "lavender",
        "student": "pink",
        "ok": "mint",
        "low": "amber",
        "none": "rose",
    }
    rules = []
    for tone, pill in tone_to_pill.items():
        bg, fg = PILL_TONES[pill]
        rules.append(f'QLabel#catPill[tone="{tone}"] {{ background-color: {bg}; color: {fg}; }}')
    return "\n".join(rules)


CATALOG_V2_STYLESHEET = f"""
QWidget#catalogScreen {{
    background-color: {tk.COLOR_BG_APP};
}}
QLabel {{
    background: transparent;
    border: none;
}}

/* ---------- scroll areas ---------- */
QScrollArea#catScroll, QWidget#catContent {{
    background-color: {tk.COLOR_BG_APP};
    border: none;
}}
QScrollArea#catFilterScroll, QWidget#catFilterInner {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: none;
}}
QScrollArea#catScroll QScrollBar:vertical,
QScrollArea#catFilterScroll QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}
QScrollArea#catScroll QScrollBar::handle:vertical,
QScrollArea#catFilterScroll QScrollBar::handle:vertical {{
    background: {tk.COLOR_BORDER_STRONG};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollArea#catScroll QScrollBar::add-line:vertical,
QScrollArea#catScroll QScrollBar::sub-line:vertical,
QScrollArea#catFilterScroll QScrollBar::add-line:vertical,
QScrollArea#catFilterScroll QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollArea#catScroll QScrollBar::add-page:vertical,
QScrollArea#catScroll QScrollBar::sub-page:vertical,
QScrollArea#catFilterScroll QScrollBar::add-page:vertical,
QScrollArea#catFilterScroll QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- header ---------- */
QFrame#catHeader {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#catTag {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: {LAVENDER_TEXT};
    border-radius: 9px;
    padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#catTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: 24px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#catSubtitle {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}

/* ---------- search ---------- */
QLineEdit#catSearch {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
    padding: 0px 14px;
    min-height: 46px;
    font-size: {tk.FONT_SIZE_BODY + 1}px;
    selection-background-color: {tk.COLOR_ACCENT};
    selection-color: {tk.COLOR_TEXT_PRIMARY};
}}
QLineEdit#catSearch:hover {{ border-color: {tk.COLOR_BORDER_STRONG}; }}
QLineEdit#catSearch:focus {{
    border-color: {tk.COLOR_FOCUS_RING};
    background-color: {tk.COLOR_BG_SURFACE};
}}
QFrame#catStickyBar {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#catStickyLabel {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QLineEdit#catSearchCompact {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 12px;
    min-height: {tk.CONTROL_HEIGHT_MD}px;
    font-size: {tk.FONT_SIZE_BODY}px;
    selection-background-color: {tk.COLOR_ACCENT};
}}
QLineEdit#catSearchCompact:hover {{ border-color: {tk.COLOR_BORDER_STRONG}; }}
QLineEdit#catSearchCompact:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}

/* ---------- results bar ---------- */
QLabel#catResultLabel {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
    padding-left: 2px;
}}

/* ---------- horizontal filter bar + chips (Step 18) ---------- */
QFrame#catFilterBar {{ background: transparent; border: none; }}
QLabel#catFilterCaption {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
    padding-left: 2px;
}}
QComboBox#catFilterCombo {{
    background-color: {tk.COLOR_BG_SURFACE};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 6px 10px;
    min-height: 20px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
QComboBox#catFilterCombo::drop-down {{ border: none; width: 24px; }}
QComboBox#catFilterCombo::down-arrow {{ image: url({CHEVRON_PATH}); width: 12px; height: 12px; }}
QComboBox#catFilterCombo:hover {{ border-color: {tk.COLOR_BORDER_STRONG}; }}
QComboBox#catFilterCombo:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
QComboBox#catFilterCombo[active="true"] {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: #D5D7FF;
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QComboBox#catFilterCombo QAbstractItemView {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    selection-background-color: {tk.COLOR_ACCENT_SOFT};
    selection-color: #D5D7FF;
    outline: none;
}}
QFrame#catChip {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    border-radius: {tk.RADIUS_MD}px;
}}
QLabel#catChipText {{
    background: transparent;
    color: #D5D7FF;
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QToolButton#catChipRemove {{
    background: transparent;
    color: {LAVENDER_TEXT};
    border: none;
    border-radius: 9px;
    min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px;
    font-size: {tk.FONT_SIZE_BODY}px;
    font-weight: {tk.FONT_WEIGHT_BOLD};
}}
QToolButton#catChipRemove:hover {{
    background-color: {tk.COLOR_BG_OVERLAY};
    color: {tk.COLOR_TEXT_PRIMARY};
}}
QToolButton#catChipRemove:focus {{ border: 1px solid {tk.COLOR_FOCUS_RING}; }}

/* ---------- filter panel (Step 16 vertical panel; no longer used) ---------- */
QFrame#catFilters {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#catFilterTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_BODY + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#catSectionLabel {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
    padding-top: 6px;
}}
QPushButton#catFilterButton, QPushButton#catCollectionButton {{
    background-color: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid transparent;
    border-radius: {tk.RADIUS_MD}px;
    padding: 8px 12px;
    text-align: left;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QPushButton#catFilterButton:hover, QPushButton#catCollectionButton:hover {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
}}
QPushButton#catFilterButton:checked {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: #D5D7FF;
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QPushButton#catCollectionButton:checked {{
    background-color: {tk.COLOR_HIGHLIGHT_SOFT};
    color: {tk.COLOR_HIGHLIGHT};
    border-color: #4A3358;
}}
QPushButton#catFilterButton:focus, QPushButton#catCollectionButton:focus {{
    border-color: {tk.COLOR_FOCUS_RING};
}}
QPushButton#catLink {{
    background: transparent;
    border: none;
    color: {LAVENDER_TEXT};
    font-size: {tk.FONT_SIZE_SMALL}px;
    padding: 2px 4px;
}}
QPushButton#catLink:hover {{
    color: {tk.COLOR_TEXT_PRIMARY};
    text-decoration: underline;
}}
QPushButton#catLink:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; }}

/* ---------- item cards ---------- */
QFrame#catItemCard {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QFrame#catItemCard:hover {{
    background-color: #20253F;
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QLabel#catItemTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_BODY}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#catItemCreator {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
}}
QLabel#catItemNote {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_CAPTION}px;
}}
QLabel#catPill {{
    border-radius: 9px;
    padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_tag_rules()}

/* ---------- card buttons ---------- */
QPushButton#catRequestButton {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: #D5D7FF;
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 12px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QPushButton#catRequestButton:hover {{
    background-color: #353A78;
    border-color: {tk.COLOR_FOCUS_RING};
}}
QPushButton#catRequestButton:pressed {{ background-color: {tk.COLOR_BG_OVERLAY}; }}
QPushButton#catRequestButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
QPushButton#catRequestButton:disabled {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_DISABLED};
    border: 1px solid {tk.COLOR_BORDER};
}}
QPushButton#catBookmarkButton {{
    background-color: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px;
    font-size: 16px;
}}
QPushButton#catBookmarkButton:hover {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QPushButton#catBookmarkButton:checked {{
    background-color: {tk.COLOR_HIGHLIGHT_SOFT};
    color: {tk.COLOR_HIGHLIGHT};
    border-color: #4A3358;
}}
QPushButton#catBookmarkButton:checked:hover {{ background-color: #43304F; }}
QPushButton#catBookmarkButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}

/* ---------- Grid / List toggle (Step 17) ---------- */
QFrame#catViewToggle {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
}}
QPushButton#catViewButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: {tk.RADIUS_SM + 1}px;
    padding: 0px;
}}
QPushButton#catViewButton:hover {{ background-color: {tk.COLOR_BG_RAISED}; }}
QPushButton#catViewButton:checked {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QPushButton#catViewButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}

/* ---------- item rows (List view) ---------- */
QFrame#catItemRow {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QFrame#catItemRow:hover {{
    background-color: #20253F;
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QLabel#catRowCell {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_SMALL}px;
}}

/* ---------- empty state ---------- */
QFrame#catEmpty {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#catEmptyIcon {{ font-size: 36px; }}
QLabel#catEmptyTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#catEmptyText {{
    color: {tk.COLOR_TEXT_SECONDARY};
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
QPushButton#catPrimaryButton {{
    background-color: {tk.COLOR_ACCENT_SOFT};
    color: #D5D7FF;
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    border-radius: {tk.RADIUS_MD}px;
    padding: 9px 20px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QPushButton#catPrimaryButton:hover {{
    background-color: #353A78;
    border-color: {tk.COLOR_FOCUS_RING};
}}
QPushButton#catPrimaryButton:pressed {{ background-color: {tk.COLOR_BG_OVERLAY}; }}
"""


# ----------------------------------------------------------------------
# Step 19: Item Details page + Report Listing dialog (object names start with `det`)
# ----------------------------------------------------------------------
ITEM_DETAILS_STYLESHEET = CATALOG_V2_STYLESHEET + f"""
QWidget#itemDetailsScreen, QWidget#detContent, QDialog#detReportDialog {{
    background-color: {tk.COLOR_BG_APP};
}}
QScrollArea#detScroll {{ background-color: {tk.COLOR_BG_APP}; border: none; }}
QScrollArea#detScroll QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollArea#detScroll QScrollBar::handle:vertical {{
    background: {tk.COLOR_BORDER_STRONG}; border-radius: 3px; min-height: 30px;
}}
QScrollArea#detScroll QScrollBar::add-line:vertical, QScrollArea#detScroll QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollArea#detScroll QScrollBar::add-page:vertical, QScrollArea#detScroll QScrollBar::sub-page:vertical {{ background: transparent; }}

QPushButton#detBackButton {{
    background-color: {tk.COLOR_BG_SURFACE};
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 14px;
    min-height: {tk.CONTROL_HEIGHT_MD}px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QPushButton#detBackButton:hover {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QPushButton#detBackButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}

QFrame#detHero, QFrame#detSection {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QFrame#detSection, QFrame#detGallery {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: none;
    border-radius: {tk.RADIUS_MD}px;
}}
QFrame#detImageViewer {{
    background-color: {tk.COLOR_BG_APP};
    border: 1px solid {tk.COLOR_BORDER};
}}
QScrollArea#detViewerScroll, QScrollArea#detViewerScroll QWidget {{
    background-color: {tk.COLOR_BG_APP};
    border: none;
}}
QLabel#detViewerImage {{ background-color: {tk.COLOR_BG_APP}; }}
QPushButton#detViewerAction {{
    background-color: {tk.COLOR_BG_SURFACE};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 14px;
    min-height: 36px;
}}
QPushButton#detViewerAction:hover {{
    background-color: {tk.COLOR_BG_RAISED};
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QWidget#detAdaptiveGrid, QWidget#detInformation {{
    background: transparent;
    border: none;
}}
QFrame#detReportSection {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
QLabel#detKind {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#detTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_H2}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#detCreator {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY}px; }}
QLabel#detSectionTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_LEAD}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QLabel#detKey {{
    color: {tk.COLOR_TEXT_MUTED};
    font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QLabel#detValue {{ color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY - 1}px; }}
QLabel#detValueMuted {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_BODY - 1}px; }}
QLabel#detHint {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px; }}
QLabel#detMessage {{ color: {tk.COLOR_SUCCESS}; font-size: {tk.FONT_SIZE_SMALL + 1}px; }}
QLabel#detError {{ color: {tk.COLOR_DANGER}; font-size: {tk.FONT_SIZE_SMALL + 1}px; }}

QPushButton#detSaveButton {{
    background-color: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 14px;
    min-height: 34px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QPushButton#detSaveButton:hover {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QPushButton#detSaveButton:checked {{
    background-color: {tk.COLOR_HIGHLIGHT_SOFT};
    color: {tk.COLOR_HIGHLIGHT};
    border-color: #4A3358;
}}
QPushButton#detSaveButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}

QToolButton#detMenuButton {{
    background-color: {tk.COLOR_BG_SURFACE};
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    min-width: {tk.CONTROL_HEIGHT_MD}px; max-width: {tk.CONTROL_HEIGHT_MD}px;
    min-height: {tk.CONTROL_HEIGHT_MD}px; max-height: {tk.CONTROL_HEIGHT_MD}px;
    font-size: 18px;
    font-weight: {tk.FONT_WEIGHT_BOLD};
}}
QToolButton#detMenuButton::menu-indicator {{ image: none; width: 0px; }}
QToolButton#detMenuButton:hover {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border-color: {tk.COLOR_BORDER_STRONG};
}}
QToolButton#detMenuButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
QToolButton#detMenuButton:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; }}
QMenu#detMenu {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    border-radius: {tk.RADIUS_MD}px;
    padding: 4px;
}}
QMenu#detMenu::item {{
    padding: 7px 16px 7px 10px;
    border-radius: {tk.RADIUS_SM}px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
QMenu#detMenu::item:selected {{ background-color: {tk.COLOR_ACCENT_SOFT}; color: #D5D7FF; }}
QMenu#detMenu::item:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; }}

QPushButton#detReportButton {{
    background-color: {tk.COLOR_DANGER_SOFT};
    color: {tk.COLOR_DANGER};
    border: 1px solid #6A3342;
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 16px;
    min-height: 36px;
    font-size: {tk.FONT_SIZE_SMALL + 1}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QPushButton#detReportButton:hover {{ background-color: #55293A; border-color: {tk.COLOR_DANGER}; }}
QPushButton#detReportButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
QPushButton#detReportButton:disabled {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_DISABLED};
    border-color: {tk.COLOR_BORDER};
}}

/* ---------- report dialog ---------- */
QLabel#detDialogTitle {{
    color: {tk.COLOR_TEXT_PRIMARY};
    font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
QDialog#detReportDialog QLabel {{ background: transparent; }}
QComboBox#detReasonCombo {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 6px 10px;
    min-height: 22px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
QComboBox#detReasonCombo::drop-down {{ border: none; width: 24px; }}
QComboBox#detReasonCombo::down-arrow {{ image: url({CHEVRON_PATH}); width: 12px; height: 12px; }}
QComboBox#detReasonCombo:hover {{ border-color: {tk.COLOR_BORDER_STRONG}; }}
QComboBox#detReasonCombo:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
QComboBox#detReasonCombo QAbstractItemView {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    selection-background-color: {tk.COLOR_ACCENT_SOFT};
    selection-color: #D5D7FF;
    outline: none;
}}
QPlainTextEdit#detDescription {{
    background-color: {tk.COLOR_BG_RAISED};
    color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 8px 10px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    selection-background-color: {tk.COLOR_ACCENT};
}}
QPlainTextEdit#detDescription:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
QPushButton#detCancelButton {{
    background-color: transparent;
    color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
    padding: 0px 18px;
    min-height: 36px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
QPushButton#detCancelButton:hover {{ background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY}; }}
QPushButton#detCancelButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
"""
