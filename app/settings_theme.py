"""Soft-dark look for the Settings & Profile screen only (Step 28). Styles, no behaviour.

Every rule starts with `QWidget#settingsScreen`, so no other screen can be affected. It styles
the whole screen (including the sidebar editor panel inside Appearance) so nothing from the old
cream/outline look is left. Text-first headings, one hairline border per card, lavender accents.
"""
from app import design_tokens as tk
from app.header_style import ACCENT_LAVENDER
from app.home_theme import PILL_TONES

HAIRLINE = "#292E4C"
S = "QWidget#settingsScreen"


def _pill_rules() -> str:
    # StatusPill tones used by the Student Owner status and the Workspaces list.
    tone_for = {"mint": "mint", "purple": "lavender", "pink": "pink", "sun": "amber", "alert": "rose"}
    return "\n".join(
        f'{S} QLabel#statusPill[tone="{tone}"] {{ background-color: {PILL_TONES[pill][0]}; '
        f'color: {PILL_TONES[pill][1]}; border: none; }}'
        for tone, pill in tone_for.items())


SETTINGS_V2_QSS = f"""
{S} {{ background-color: {tk.COLOR_BG_APP}; }}
{S} QLabel {{ background: transparent; border: none; }}
{S} QScrollArea#catalogScroll, {S} QWidget#catalogContent {{ background: transparent; border: none; }}
{S} QScrollArea#catalogScroll QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
{S} QScrollArea#catalogScroll QScrollBar::handle:vertical {{
    background: {tk.COLOR_BORDER}; border-radius: 4px; min-height: 36px;
}}
{S} QScrollArea#catalogScroll QScrollBar::handle:vertical:hover {{ background: {tk.COLOR_BORDER_STRONG}; }}
{S} QScrollArea#catalogScroll QScrollBar::add-line:vertical,
{S} QScrollArea#catalogScroll QScrollBar::sub-line:vertical {{ height: 0px; }}
{S} QScrollArea#catalogScroll QScrollBar::add-page:vertical,
{S} QScrollArea#catalogScroll QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- section headings (text only) ---------- */
{S} QLabel#settingsSection {{
    color: {ACCENT_LAVENDER}; font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD}; padding: 14px 2px 0px 2px;
}}
{S} QFrame#settingsSectionLine {{ background-color: {HAIRLINE}; border: none; max-height: 1px; min-height: 1px; }}

/* ---------- cards ---------- */
{S} QFrame#settingsCard {{
    background-color: {tk.COLOR_BG_SURFACE}; border: 1px solid {HAIRLINE};
    border-radius: {tk.RADIUS_LG}px;
}}
{S} QLabel#settingsCardTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_LEAD}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#settingsCardText {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_SMALL + 1}px; }}
{S} QLabel#settingsFieldLabel {{
    color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM}; padding-top: 4px;
}}
{S} QLabel#settingsReadOnlyValue {{
    color: {tk.COLOR_TEXT_PRIMARY}; background-color: {tk.COLOR_BG_RAISED};
    border: none; border-radius: {tk.RADIUS_MD}px; padding: 9px 12px; font-size: {tk.FONT_SIZE_BODY}px;
}}
{S} QLabel#settingsMessage {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QLabel#settingsMessage[error="true"] {{ color: {tk.COLOR_DANGER}; }}
{S} QLabel#myListBanner {{
    background-color: {tk.COLOR_SUCCESS_SOFT}; color: {tk.COLOR_SUCCESS}; border: none;
    border-radius: {tk.RADIUS_MD}px; padding: 10px 14px; font-size: {tk.FONT_SIZE_BODY - 1}px;
}}

/* ---------- profile card ---------- */
{S} QLabel#profileName {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#profileEmail {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY - 1}px; }}
{S} QLabel#profileHint {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px; }}

/* ---------- rows inside cards ---------- */
{S} QFrame#settingsWorkspaceRow {{
    background-color: {tk.COLOR_BG_RAISED}; border: none; border-radius: {tk.RADIUS_MD}px;
}}
{S} QLabel#settingsWorkspaceName {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QLabel#statusPill {{
    border-radius: 10px; padding: 2px 10px; font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_pill_rules()}

/* ---------- inputs ---------- */
{S} QLineEdit, {S} QPlainTextEdit#settingsTextBox, {S} QSpinBox {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER}; border-radius: {tk.RADIUS_MD}px;
    padding: 6px 12px; font-size: {tk.FONT_SIZE_BODY}px;
    selection-background-color: {tk.COLOR_ACCENT}; selection-color: {tk.COLOR_TEXT_PRIMARY};
}}
{S} QLineEdit {{ min-height: {tk.CONTROL_HEIGHT_MD - 14}px; }}
{S} QLineEdit:hover, {S} QPlainTextEdit#settingsTextBox:hover, {S} QSpinBox:hover {{
    border-color: {tk.COLOR_BORDER_STRONG};
}}
{S} QLineEdit:focus, {S} QPlainTextEdit#settingsTextBox:focus, {S} QSpinBox:focus {{
    border-color: {tk.COLOR_FOCUS_RING};
}}
{S} QLineEdit:disabled, {S} QPlainTextEdit#settingsTextBox:disabled, {S} QSpinBox:disabled {{
    color: {tk.COLOR_TEXT_DISABLED}; background-color: {tk.COLOR_BG_SURFACE};
}}
{S} QSpinBox QLineEdit {{ border: none; background: transparent; padding: 0px; min-height: 0px; }}
{S} QSpinBox::up-button, {S} QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}

/* ---------- checkboxes ---------- */
{S} QCheckBox#settingsCheck {{ color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY - 1}px; spacing: 10px; }}
{S} QCheckBox#settingsCheck:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; }}
{S} QCheckBox#settingsCheck::indicator {{
    width: 16px; height: 16px; border-radius: {tk.RADIUS_SM}px;
    border: 1px solid {tk.COLOR_BORDER_STRONG}; background-color: {tk.COLOR_BG_RAISED};
}}
{S} QCheckBox#settingsCheck::indicator:hover {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{S} QCheckBox#settingsCheck::indicator:checked {{
    background-color: {tk.COLOR_ACCENT}; border-color: {tk.COLOR_ACCENT_HOVER};
}}

/* ---------- slider (sidebar editor) ---------- */
{S} QSlider::groove:horizontal {{ height: 4px; background: {tk.COLOR_BORDER}; border-radius: 2px; }}
{S} QSlider::sub-page:horizontal {{ background: {tk.COLOR_ACCENT}; border-radius: 2px; }}
{S} QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: {ACCENT_LAVENDER};
}}
{S} QSlider::handle:horizontal:disabled {{ background: {tk.COLOR_TEXT_DISABLED}; }}

/* ---------- buttons: primary (lavender) and quiet ---------- */
{S} QPushButton#catalogPrimaryButton {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: #D5D7FF;
    border: 1px solid {tk.COLOR_BORDER_STRONG}; border-radius: {tk.RADIUS_MD}px;
    padding: 9px 20px; font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{S} QPushButton#catalogPrimaryButton:hover {{ background-color: #353A78; border-color: {tk.COLOR_FOCUS_RING}; }}
{S} QPushButton#catalogPrimaryButton:pressed {{ background-color: {tk.COLOR_BG_OVERLAY}; }}
{S} QPushButton#catalogPrimaryButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{S} QPushButton#catalogPrimaryButton:disabled {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_DISABLED}; border: 1px solid {tk.COLOR_BORDER};
}}
{S} QPushButton#catalogClearButton {{
    background-color: transparent; color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER}; border-radius: {tk.RADIUS_MD}px;
    padding: 9px 16px; font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#catalogClearButton:hover {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY}; border-color: {tk.COLOR_BORDER_STRONG};
}}
{S} QPushButton#catalogClearButton:pressed {{ background-color: {tk.COLOR_BG_OVERLAY}; }}
{S} QPushButton#catalogClearButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{S} QPushButton#catalogClearButton:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; border-color: {HAIRLINE}; }}
{S} QPushButton#profileRemoveButton {{
    background-color: transparent; color: {tk.COLOR_DANGER}; border: 1px solid {HAIRLINE};
    border-radius: {tk.RADIUS_MD}px; padding: 9px 16px;
    font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{S} QPushButton#profileRemoveButton:hover {{ background-color: {tk.COLOR_DANGER_SOFT}; border-color: #5A2E3C; }}
{S} QPushButton#profileRemoveButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{S} QPushButton#profileRemoveButton:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; border-color: {HAIRLINE}; }}
"""
