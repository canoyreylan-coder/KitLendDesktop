"""KitLend design tokens (Stage 1A-1: Design Foundation).

Plain constants only: NO Qt imports and NO behaviour, so anything (screens, tests, a
future backend-driven theme) can import them safely.

The look is a "professional soft-dark" palette: calm dark-navy surfaces, soft light text
and the existing KitLend periwinkle / pink / mint accents. Nothing uses these tokens yet:
existing screens still use the old Pixel Pop constants in app/theme.py. Later redesign
stages will move one screen at a time onto these tokens.

Naming: COLOR_* (colors), FONT_* (typography), SPACE_* (spacing, px), RADIUS_* (corner
radii, px). Use the tokens instead of typing hex codes or pixel numbers in screens.
"""

# ----------------------------------------------------------------------
# Colors
# ----------------------------------------------------------------------
# Surfaces, darkest to lightest (a card sits on the page, a raised element on a card)
COLOR_BG_WINDOW = "#0B0D1A"     # outside the floating app container (Step 30A)
COLOR_BG_APP = "#14172A"        # page background (inside the container)
COLOR_BG_SIDEBAR = "#101326"    # navigation rail, slightly deeper than the page
COLOR_BG_SURFACE = "#1C2036"    # cards and panels
COLOR_BG_RAISED = "#252A45"     # inputs, hovered rows, popups
COLOR_BG_OVERLAY = "#2E3453"    # pressed / selected rows

COLOR_BORDER = "#343A5C"        # default hairline border
COLOR_BORDER_STRONG = "#4A5180" # hover / emphasised border
COLOR_FOCUS_RING = "#8B8FFF"    # keyboard focus outline

# Text (contrast ratios on COLOR_BG_SURFACE are checked in tests/test_design_tokens.py)
COLOR_TEXT_PRIMARY = "#EEF0FB"
COLOR_TEXT_SECONDARY = "#B4B9D6"
COLOR_TEXT_MUTED = "#8C92B5"
COLOR_TEXT_DISABLED = "#5E6486"
COLOR_TEXT_ON_ACCENT = "#10132A"  # dark text for use on light accent fills

# Brand accents (same hues as the Pixel Pop palette, tuned for dark surfaces)
COLOR_ACCENT = "#7175F5"          # primary actions
COLOR_ACCENT_HOVER = "#8B8FFF"
COLOR_ACCENT_PRESSED = "#5B5FE0"
COLOR_ACCENT_SOFT = "#2A2E5E"     # tinted background behind accent text/icons
COLOR_HIGHLIGHT = "#F4A8C4"       # soft pink highlight
COLOR_HIGHLIGHT_SOFT = "#3A2740"
COLOR_FRESH = "#B7F1E1"           # mint
COLOR_FRESH_SOFT = "#1F3A3C"

# Status colors (always pair with an icon or a word, never color alone)
COLOR_SUCCESS = "#6FE0B0"
COLOR_SUCCESS_SOFT = "#17382F"
COLOR_WARNING = "#F5C26B"
COLOR_WARNING_SOFT = "#3D3220"
COLOR_DANGER = "#FF8FA3"
COLOR_DANGER_SOFT = "#45222E"
COLOR_INFO = "#8FB8FF"
COLOR_INFO_SOFT = "#1F2F4D"

# ----------------------------------------------------------------------
# Typography
# ----------------------------------------------------------------------
# Windows ships Segoe UI; the later names are fallbacks for other systems.
FONT_FAMILY = '"Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif'

FONT_SIZE_CAPTION = 11   # px - tags, timestamps
FONT_SIZE_SMALL = 12     # px - helper text
FONT_SIZE_BODY = 14      # px - default text
FONT_SIZE_LEAD = 16      # px - emphasised body, card titles
FONT_SIZE_H3 = 18        # px
FONT_SIZE_H2 = 22        # px
FONT_SIZE_H1 = 28        # px - page titles

FONT_WEIGHT_REGULAR = 400
FONT_WEIGHT_MEDIUM = 500
FONT_WEIGHT_SEMIBOLD = 600
FONT_WEIGHT_BOLD = 700

# ----------------------------------------------------------------------
# Spacing (4 px grid) and corner radii
# ----------------------------------------------------------------------
SPACE_0 = 0
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 20
SPACE_6 = 24
SPACE_8 = 32
SPACE_10 = 40
SPACE_12 = 48

RADIUS_SM = 6      # small chips, checkboxes
RADIUS_MD = 10     # inputs, buttons
RADIUS_LG = 14     # cards
RADIUS_XL = 20     # large panels, dialogs
RADIUS_PILL = 999  # status pills, avatars

# Control heights keep buttons and inputs aligned.
CONTROL_HEIGHT_SM = 32
CONTROL_HEIGHT_MD = 40
CONTROL_HEIGHT_LG = 48
