"""The Student Owner workspace shell: its own icon rail and owner-only pages.

  OwnerRail            - the narrow icon rail shown INSTEAD of the student sidebar while the
                         Owner workspace is open (same look, same 72 px width). The student
                         sidebar and its saved customisation are never touched: it is only hidden.
  OwnerDashboardPage   - overview + the "one account, two workspaces" explanation.
  OwnerListingsPage    - My Listings empty state.
  OwnerIncomingRequestsPage - owner-scoped borrower request review.

The pages only render saved listing and inventory data; authorization and persistence belong to
WorkspaceService and OwnerListingService, never to these widgets.
"""
from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import design_tokens as tk
from app.catalog_screen import CURIOUS_MASCOT_PATH, HAPPY_MASCOT_PATH
from app.catalog_theme import CHEVRON_PATH
from app.dashboard_widgets import ReflowGrid
from app.home_theme import LAVENDER_TEXT
from app.owner_availability import (
    DAY_MINUTES,
    WEEKDAY_NAMES,
    AvailabilityError,
    AvailabilitySchedule,
    format_minute,
)
from app.owner_icons import owner_icon
from app.owner_listing_service import MAX_STOCK_QUANTITY
from app.photo_service import MAX_PHOTOS
from app.sidebar_icons import circular_pixmap
from app.theme import AVATAR_SIZE, NAV_BUTTON_SIZE, NAV_ICON_SIZE, SIDEBAR_STYLESHEET, SIDEBAR_WIDTH

OWNER_DASHBOARD = "owner_dashboard"
OWNER_LISTINGS = "my_listings"
OWNER_REQUESTS = "incoming_requests"
CATEGORY_PLACEHOLDER = "Select a category..."
CONDITION_PLACEHOLDER = "Select a condition..."
SUBCATEGORY_PLACEHOLDER = "No subcategory"
OWNER_PAGE_KEYS = (OWNER_DASHBOARD, OWNER_LISTINGS, OWNER_REQUESTS)
PHOTO_FILE_FILTER = "Photos (*.jpg *.jpeg *.png *.webp)"
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_PICKUP = (9 * 60, 17 * 60)   # 9:00 AM - 5:00 PM, offered when a day is first ticked
TIME_STEP = 30
OWNER_LABELS = {OWNER_DASHBOARD: "Owner Dashboard", OWNER_LISTINGS: "My Listings",
                OWNER_REQUESTS: "Incoming Requests",
                "settings": "Settings", "switch": "Switch to Student workspace",
                "logout": "Log Out"}


# ======================================================================
# Rail
# ======================================================================
class OwnerRail(QFrame):
    """Icon rail for Owner Dashboard, My Listings, Incoming Requests, Settings and exit."""

    nav_requested = Signal(str)       # an owner page key or "settings"
    switch_requested = Signal()       # back to the Student workspace
    logout_requested = Signal()
    avatar_clicked = Signal()

    def __init__(self, initials: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")   # same object name = same soft-dark rail style
        self.setStyleSheet(SIDEBAR_STYLESHEET)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self._initials = initials
        self._photo = None
        self._avatar_size = AVATAR_SIZE

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 14)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignHCenter)

        self.avatar_button = QPushButton(initials)
        self.avatar_button.setObjectName("avatar")
        self.avatar_button.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self.avatar_button.setCursor(Qt.PointingHandCursor)
        self.avatar_button.setFocusPolicy(Qt.TabFocus)
        self.avatar_button.setToolTip("Open Settings")
        self.avatar_button.setAccessibleName("Profile: open Settings")
        self.avatar_button.clicked.connect(lambda _c=False: self.avatar_clicked.emit())
        layout.addWidget(self.avatar_button, 0, Qt.AlignHCenter)
        layout.addSpacing(8)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons = {}
        for key in (OWNER_DASHBOARD, OWNER_LISTINGS, OWNER_REQUESTS, "settings"):
            button = self._make_button(key, "navButton", checkable=True)
            button.clicked.connect(lambda _c=False, k=key: self.nav_requested.emit(k))
            self._group.addButton(button)
            self.buttons[key] = button
            layout.addWidget(button, 0, Qt.AlignHCenter)

        layout.addStretch(1)
        switch = self._make_button("switch", "sidebarExitButton")
        switch.clicked.connect(lambda _c=False: self.switch_requested.emit())
        self.buttons["switch"] = switch
        layout.addWidget(switch, 0, Qt.AlignHCenter)
        logout = self._make_button("logout", "sidebarExitButton")
        logout.clicked.connect(lambda _c=False: self.logout_requested.emit())
        self.buttons["logout"] = logout
        layout.addWidget(logout, 0, Qt.AlignHCenter)

    def _make_button(self, key: str, object_name: str, checkable: bool = False) -> QPushButton:
        button = QPushButton()
        button.setObjectName(object_name)
        button.setFixedSize(NAV_BUTTON_SIZE, NAV_BUTTON_SIZE)
        button.setIcon(owner_icon(key, NAV_ICON_SIZE))
        button.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        button.setToolTip(OWNER_LABELS[key])
        button.setAccessibleName(OWNER_LABELS[key])
        button.setCheckable(checkable)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.TabFocus)
        return button

    def select(self, key: str):
        """Highlight one page button (None clears the highlight)."""
        for name, button in self.buttons.items():
            if button.isCheckable():
                button.setChecked(name == key)

    @property
    def selected_key(self):
        for name, button in self.buttons.items():
            if button.isCheckable() and button.isChecked():
                return name
        return None

    def set_profile(self, initials: str, photo=None):
        """Same picture/initials as the student sidebar's avatar (one shared profile)."""
        self._initials = initials
        self._photo = photo
        inner = self._avatar_size - 2
        pixmap = circular_pixmap(photo, inner) if photo is not None else None
        if pixmap is None:
            self.avatar_button.setIcon(QIcon())
            self.avatar_button.setText(initials)
        else:
            self.avatar_button.setText("")
            self.avatar_button.setIcon(QIcon(pixmap))
            self.avatar_button.setIconSize(QSize(inner, inner))


# ======================================================================
# Pages
# ======================================================================
_O = "QScrollArea#ownerPage"

OWNER_PAGE_QSS = f"""
{_O}, {_O} QWidget#ownerContent {{ background-color: {tk.COLOR_BG_APP}; border: none; }}
{_O} QLabel {{ background: transparent; border: none; }}
{_O} QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
{_O} QScrollBar::handle:vertical {{ background: {tk.COLOR_BORDER_STRONG}; border-radius: 3px; min-height: 30px; }}
{_O} QScrollBar::add-line:vertical, {_O} QScrollBar::sub-line:vertical {{ height: 0px; }}
{_O} QScrollBar::add-page:vertical, {_O} QScrollBar::sub-page:vertical {{ background: transparent; }}

{_O} QFrame#ownerHeader, {_O} QFrame#ownerCard, {_O} QFrame#ownerTile, {_O} QFrame#ownerEmpty {{
    background-color: {tk.COLOR_BG_SURFACE};
    border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
{_O} QFrame#ownerEmpty {{ border-style: solid; }}
{_O} QLabel#ownerTag {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: {LAVENDER_TEXT};
    border-radius: 9px; padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QLabel#ownerTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: 24px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QLabel#ownerSubtitle {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY - 1}px; }}
{_O} QLabel#ownerCardTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_LEAD}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QLabel#ownerCardText {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY - 1}px; }}
{_O} QLabel#ownerTileLabel {{
    color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{_O} QLabel#ownerTileValue {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: 28px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QLabel#ownerTileValue[muted="true"] {{ color: {tk.COLOR_TEXT_DISABLED}; }}
{_O} QLabel#ownerTileNote {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_CAPTION}px; }}
{_O} QLabel#ownerEmptyTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_H3}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QLabel#ownerEmptyText {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY - 1}px; }}
{_O} QFrame#ownerListingCard {{
    background-color: {tk.COLOR_BG_SURFACE}; border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_LG}px;
}}
{_O} QFrame#ownerListingCard:hover {{ background-color: #20253F; border-color: {tk.COLOR_BORDER_STRONG}; }}
{_O} QLabel#ownerListingTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QLabel#ownerListingMeta {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_SMALL}px; }}
{_O} QLabel#ownerListingNote {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px; }}
{_O} QLabel#ownerDraftPill {{
    background-color: {tk.COLOR_WARNING_SOFT}; color: {tk.COLOR_WARNING};
    border-radius: 9px; padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QLabel#ownerPublishedPill {{
    background-color: {tk.COLOR_SUCCESS_SOFT}; color: {tk.COLOR_SUCCESS};
    border-radius: 9px; padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QLabel#ownerPausedPill {{
    background-color: {tk.COLOR_WARNING_SOFT}; color: {tk.COLOR_WARNING};
    border-radius: 9px; padding: 2px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QToolButton#ownerListingMenu {{
    background-color: transparent; color: {tk.COLOR_TEXT_MUTED};
    border: 0; border-radius: {tk.RADIUS_MD}px;
    min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
    font-size: 18px; font-weight: {tk.FONT_WEIGHT_BOLD};
}}
{_O} QToolButton#ownerListingMenu::menu-indicator {{ image: none; width: 0; }}
{_O} QToolButton#ownerListingMenu:hover {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY};
}}
{_O} QMenu#ownerListingMenu {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER_STRONG}; border-radius: {tk.RADIUS_MD}px;
    padding: 4px;
}}
{_O} QMenu#ownerListingMenu::item {{
    padding: 7px 16px 7px 10px; border-radius: {tk.RADIUS_SM}px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{_O} QMenu#ownerListingMenu::item:selected {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: #D5D7FF;
}}
{_O} QLabel#ownerCount {{
    color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY - 1}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{_O} QLabel#ownerBanner {{
    background-color: {tk.COLOR_SUCCESS_SOFT}; color: {tk.COLOR_SUCCESS};
    border: 1px solid #25584A; border-radius: {tk.RADIUS_MD}px; padding: 10px 14px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{_O} QLabel#ownerFieldLabel {{
    color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_MEDIUM}; padding-top: 4px;
}}
{_O} QLabel#ownerFormError {{
    background-color: {tk.COLOR_DANGER_SOFT}; color: {tk.COLOR_DANGER};
    border: 1px solid #6A3342; border-radius: {tk.RADIUS_MD}px; padding: 10px 14px;
    font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{_O} QLineEdit#ownerInput, {_O} QPlainTextEdit#ownerTextBox, {_O} QSpinBox#ownerSpin,
{_O} QComboBox#ownerCombo {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER}; border-radius: {tk.RADIUS_MD}px;
    padding: 8px 12px; font-size: {tk.FONT_SIZE_BODY - 1}px;
    selection-background-color: {tk.COLOR_ACCENT};
}}
{_O} QLineEdit#ownerInput:hover, {_O} QPlainTextEdit#ownerTextBox:hover,
{_O} QSpinBox#ownerSpin:hover, {_O} QComboBox#ownerCombo:hover {{ border-color: {tk.COLOR_BORDER_STRONG}; }}
{_O} QLineEdit#ownerInput:focus, {_O} QPlainTextEdit#ownerTextBox:focus,
{_O} QSpinBox#ownerSpin:focus, {_O} QComboBox#ownerCombo:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{_O} QComboBox#ownerCombo::drop-down {{ border: none; width: 24px; }}
{_O} QComboBox#ownerCombo::down-arrow {{ image: url({CHEVRON_PATH}); width: 12px; height: 12px; }}
{_O} QComboBox#ownerCombo QAbstractItemView {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER_STRONG};
    selection-background-color: {tk.COLOR_ACCENT_SOFT}; selection-color: #D5D7FF; outline: none;
}}
{_O} QPushButton#ownerPrimaryButton:disabled {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_DISABLED};
    border-color: {tk.COLOR_BORDER};
}}
{_O} QPushButton#ownerPrimaryButton {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: #D5D7FF;
    border: 1px solid {tk.COLOR_BORDER_STRONG}; border-radius: {tk.RADIUS_MD}px;
    padding: 0px 18px; min-height: 36px;
    font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_O} QPushButton#ownerPrimaryButton:hover {{ background-color: #353A78; border-color: {tk.COLOR_FOCUS_RING}; }}
{_O} QPushButton#ownerPrimaryButton:pressed {{ background-color: {tk.COLOR_BG_OVERLAY}; }}
{_O} QPushButton#ownerPrimaryButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{_O} QPushButton#ownerGhostButton {{
    background-color: transparent; color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER}; border-radius: {tk.RADIUS_MD}px;
    padding: 0px 18px; min-height: 36px;
    font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{_O} QPushButton#ownerGhostButton:hover {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY};
    border-color: {tk.COLOR_BORDER_STRONG};
}}
{_O} QPushButton#ownerGhostButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{_O} QPushButton#ownerGhostButton:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; border-color: {tk.COLOR_BORDER}; }}
{_O} QPushButton#ownerDangerButton {{
    background-color: transparent; color: {tk.COLOR_DANGER};
    border: 1px solid #5A3040; border-radius: {tk.RADIUS_MD}px;
    padding: 0px 18px; min-height: 36px;
    font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{_O} QPushButton#ownerDangerButton:hover {{ background-color: {tk.COLOR_DANGER_SOFT}; border-color: {tk.COLOR_DANGER}; }}
{_O} QPushButton#ownerDangerButton:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{_O} QPushButton#ownerDangerButton:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; border-color: {tk.COLOR_BORDER}; }}
{_O} QPushButton#ownerChip {{
    background-color: transparent; color: {tk.COLOR_TEXT_SECONDARY};
    border: 1px solid {tk.COLOR_BORDER}; border-radius: 13px; padding: 4px 14px;
    font-size: {tk.FONT_SIZE_SMALL}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{_O} QPushButton#ownerChip:hover {{ background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY}; }}
{_O} QPushButton#ownerChip:checked {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: #D5D7FF;
    border-color: {tk.COLOR_BORDER_STRONG};
}}
{_O} QPushButton#ownerChip:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{_O} QFrame#ownerRequestCard {{
    background-color: {tk.COLOR_BG_SURFACE}; border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_MD}px;
}}
{_O} QLabel#ownerBanner[error="true"] {{ color: {tk.COLOR_DANGER}; }}
{_O} QLabel#ownerCardThumbEmpty {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_DISABLED};
    border-radius: 10px; font-size: {tk.FONT_SIZE_CAPTION}px;
}}
{_O} QLabel#ownerHint {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px; }}
{_O} QLabel#ownerSummary {{
    color: #D5D7FF; font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_MEDIUM};
}}
{_O} QLabel#ownerPhotoNote {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_SMALL}px; }}
{_O} QLabel#ownerPhotoNote[error="true"] {{ color: {tk.COLOR_DANGER}; }}
{_O} QCheckBox#ownerDayCheck {{
    background: transparent; color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY - 1}px;
    spacing: 10px;
}}
{_O} QCheckBox#ownerDayCheck::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {tk.COLOR_BORDER_STRONG}; background-color: {tk.COLOR_BG_RAISED};
}}
{_O} QCheckBox#ownerDayCheck::indicator:checked {{
    background-color: {tk.COLOR_ACCENT}; border-color: {tk.COLOR_ACCENT};
}}
{_O} QCheckBox#ownerDayCheck:focus {{ color: #D5D7FF; }}
{_O} QLabel#ownerDayTo {{ color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_SMALL}px; }}
{_O} QComboBox#ownerCombo:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; background-color: transparent; }}
"""


def _label(text: str, name: str, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    return label


class _OwnerPage(QScrollArea):
    """Scrollable soft-dark page with a header card (shared by both owner pages)."""

    def __init__(self, tag: str, title: str, subtitle: str, mascot_path, parent=None):
        super().__init__(parent)
        self.setObjectName("ownerPage")
        self.setStyleSheet(OWNER_PAGE_QSS)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("ownerContent")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(24, 22, 24, 24)
        self.body.setSpacing(14)
        self.setWidget(content)

        header = QFrame()
        header.setObjectName("ownerHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 18, 20, 20)
        row.setSpacing(16)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        tag_label = _label(tag, "ownerTag", wrap=False)
        tag_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        texts.addWidget(tag_label, alignment=Qt.AlignLeft)
        texts.addSpacing(4)
        self.title_label = _label(title, "ownerTitle", wrap=False)
        texts.addWidget(self.title_label)
        self.subtitle_label = _label(subtitle, "ownerSubtitle")
        texts.addWidget(self.subtitle_label)
        row.addLayout(texts, 1)
        pixmap = QPixmap(str(mascot_path))
        self.mascot_label = None
        if not pixmap.isNull():  # a missing picture must never crash the app
            mascot = QLabel()
            mascot.setFixedSize(72, 72)
            mascot.setPixmap(pixmap.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            mascot.setAlignment(Qt.AlignCenter)
            row.addWidget(mascot, 0, Qt.AlignVCenter | Qt.AlignRight)
            self.mascot_label = mascot
        self.body.addWidget(header)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.mascot_label is not None:
            self.mascot_label.setVisible(self.width() >= 640)

    @staticmethod
    def _card(title: str, text: str):
        card = QFrame()
        card.setObjectName("ownerCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 16, 20, 18)
        box.setSpacing(8)
        box.addWidget(_label(title, "ownerCardTitle"))
        body = _label(text, "ownerCardText")
        box.addWidget(body)
        return card, box, body


# ======================================================================
# Step 31C: photo manager and availability editor (used by the listing form)
# ======================================================================
def _rounded_cover(pixmap: QPixmap, width: int, height: int, radius: int = 8) -> QPixmap:
    """The picture scaled to FILL width x height (cropped, never stretched), rounded corners."""
    scale = 2
    out = QPixmap(width * scale, height * scale)
    out.fill(Qt.transparent)
    out.setDevicePixelRatio(scale)
    scaled = pixmap.scaled(width * scale, height * scale, Qt.KeepAspectRatioByExpanding,
                           Qt.SmoothTransformation)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap(QRectF(0, 0, width, height), scaled,
                       QRectF((scaled.width() - width * scale) / 2,
                              (scaled.height() - height * scale) / 2,
                              width * scale, height * scale))
    painter.end()
    return out


class _PreviewLabel(QWidget):
    """The big preview of the selected photo: fitted inside a soft frame, never stretched."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setMaximumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(210)
        self._pixmap = None

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    @property
    def has_picture(self) -> bool:
        return self._pixmap is not None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tk.COLOR_BG_APP))
        painter.drawRoundedRect(rect, 12, 12)
        if self._pixmap is None:
            painter.setPen(QColor(tk.COLOR_TEXT_MUTED))
            painter.drawText(rect, Qt.AlignCenter, "No photos yet")
            return
        inner = rect.adjusted(8, 8, -8, -8)
        scaled = self._pixmap.scaled(int(inner.width()), int(inner.height()),
                                     Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = inner.x() + (inner.width() - scaled.width()) / 2
        y = inner.y() + (inner.height() - scaled.height()) / 2
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(x, y, scaled.width(), scaled.height()), 8, 8)
        painter.setClipPath(clip)
        painter.drawPixmap(int(x), int(y), scaled)


class _PhotoThumb(QPushButton):
    """A small square thumbnail; the selected one has a lavender edge, the primary a badge."""

    SIZE = 72

    def __init__(self, key, pixmap: QPixmap, is_primary: bool, parent=None):
        super().__init__(parent)
        self.key = key
        self.is_primary = is_primary
        self._cover = _rounded_cover(pixmap, self.SIZE - 4, self.SIZE - 4, 8)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setToolTip("Primary photo" if is_primary else "Photo")
        self.setAccessibleName("Primary photo" if is_primary else "Photo")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(2, 2, self._cover)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        if not self.isChecked():   # dim the ones that are not shown in the preview
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(20, 23, 42, 90))
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#8B8FFF" if self.isChecked() else "#343A5C"),
                            2 if self.isChecked() else 1))
        painter.drawRoundedRect(rect, 8, 8)
        if self.is_primary:
            badge = QRectF(6, self.height() - 21, 46, 15)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(139, 143, 255, 235))
            painter.drawRoundedRect(badge, 7, 7)
            font = painter.font()
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor("#10142A"))
            painter.drawText(badge, Qt.AlignCenter, "Primary")
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#8B8FFF"), 1, Qt.DotLine))
            painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 6, 6)


class OwnerPhotoManager(QFrame):
    """Photos card: a preview, up to 5 thumbnails and Add / Make Primary / Remove.

    It only SHOWS the photos it is given (set_photos) and ASKS for changes through signals;
    the form (new listing) or the dashboard (saved listing) decides what really happens.
    """

    add_requested = Signal(list)      # file paths the student picked
    remove_requested = Signal(object)  # the key of the selected photo
    primary_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ownerCard")
        box = QVBoxLayout(self)
        box.setContentsMargins(20, 16, 20, 18)
        box.setSpacing(10)
        box.addWidget(_label("Photos", "ownerCardTitle"))
        self.hint_label = _label("", "ownerCardText")
        box.addWidget(self.hint_label)

        self.preview = _PreviewLabel()
        box.addWidget(self.preview)

        self.thumb_row = QHBoxLayout()
        self.thumb_row.setSpacing(8)
        box.addLayout(self.thumb_row)
        self.count_label = _label("", "ownerHint", wrap=False)
        box.addWidget(self.count_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.add_button = QPushButton("Add Photos")
        self.add_button.setObjectName("ownerPrimaryButton")
        self.primary_button = QPushButton("Make Primary")
        self.primary_button.setObjectName("ownerGhostButton")
        self.remove_button = QPushButton("Remove Photo")
        self.remove_button.setObjectName("ownerDangerButton")
        for button in (self.add_button, self.primary_button, self.remove_button):
            button.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch()
        box.addLayout(buttons)
        self.add_button.clicked.connect(self._on_add)
        self.primary_button.clicked.connect(self._on_primary)
        self.remove_button.clicked.connect(self._on_remove)

        self.note = _label("", "ownerPhotoNote")
        self.note.hide()
        box.addWidget(self.note)

        self._items = []      # [(key, path, is_primary, pixmap)]
        self._thumbs = []
        self._selected = None
        self.set_photos([])

    # ---------- public ----------
    def set_hint(self, text: str):
        self.hint_label.setText(text)

    def set_note(self, text: str, error: bool = False):
        self.note.setText(text)
        self.note.setProperty("error", bool(error))
        self.note.style().unpolish(self.note)
        self.note.style().polish(self.note)
        self.note.setVisible(bool(text))

    def set_photos(self, items):
        """Show these photos: an iterable of (key, path, is_primary). Unreadable files are
        skipped. The selection is kept when its photo is still there."""
        loaded = []
        for key, path, is_primary in items:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                loaded.append((key, str(path), bool(is_primary), pixmap))
        loaded.sort(key=lambda entry: not entry[2])   # primary first, like the gallery
        self._items = loaded
        keys = [entry[0] for entry in loaded]
        if self._selected not in keys:
            self._selected = keys[0] if keys else None
        while self.thumb_row.count():
            widget = self.thumb_row.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self._thumbs = []
        for key, _path, is_primary, pixmap in loaded:
            thumb = _PhotoThumb(key, pixmap, is_primary)
            thumb.setChecked(key == self._selected)
            thumb.clicked.connect(lambda _c=False, k=key: self.select(k))
            self.thumb_row.addWidget(thumb)
            self._thumbs.append(thumb)
        self.thumb_row.addStretch()
        self._refresh()

    def select(self, key):
        if key not in self.keys:
            return
        self._selected = key
        for thumb in self._thumbs:
            thumb.setChecked(thumb.key == key)
            thumb.update()
        self._refresh()

    @property
    def keys(self) -> list:
        return [entry[0] for entry in self._items]

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def selected_key(self):
        return self._selected

    @property
    def primary_key(self):
        for key, _path, is_primary, _pixmap in self._items:
            if is_primary:
                return key
        return None

    @property
    def thumb_buttons(self) -> list:
        return list(self._thumbs)

    def pick_files(self) -> list:
        """Ask for photo files (an empty list if cancelled)."""
        paths, _filter = QFileDialog.getOpenFileNames(
            self, "Choose photos", "", PHOTO_FILE_FILTER)
        return list(paths or [])

    # ---------- internals ----------
    def _refresh(self):
        selected = next((e for e in self._items if e[0] == self._selected), None)
        self.preview.set_pixmap(selected[3] if selected else None)
        count = len(self._items)
        self.count_label.setText(
            f"{count} of {MAX_PHOTOS} photos" if count else f"No photos yet · up to {MAX_PHOTOS}")
        full = count >= MAX_PHOTOS
        self.add_button.setEnabled(not full)
        self.add_button.setToolTip(f"A listing can have at most {MAX_PHOTOS} photos." if full else "")
        self.primary_button.setEnabled(selected is not None and not selected[2])
        self.remove_button.setEnabled(selected is not None)

    def _on_add(self, _checked=False):
        paths = self.pick_files()
        if paths:
            self.add_requested.emit(paths)

    def _on_primary(self, _checked=False):
        if self._selected is not None:
            self.primary_requested.emit(self._selected)

    def _on_remove(self, _checked=False):
        if self._selected is not None:
            self.remove_requested.emit(self._selected)


class OwnerAvailabilityEditor(QWidget):
    """Seven day rows: tick the days an item can be collected and pick a pickup time range.

    schedule() gives {weekday: [(start_minute, end_minute)]} for the ticked days (the format
    OwnerListingService saves); set_schedule() shows a saved one. `changed` is emitted only
    for the student's own edits.
    """

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)

        presets = QHBoxLayout()
        presets.setSpacing(8)
        for text, days in (("Weekdays", range(0, 5)), ("Every day", range(0, 7)), ("Clear", ())):
            chip = QPushButton(text)
            chip.setObjectName("ownerChip")
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _c=False, d=tuple(days): self._apply_days(d))
            presets.addWidget(chip)
            if text == "Weekdays":
                self.weekdays_button = chip
            elif text == "Every day":
                self.every_day_button = chip
            else:
                self.clear_button = chip
        presets.addStretch()
        box.addLayout(presets)

        self.day_boxes, self.start_combos, self.end_combos = {}, {}, {}
        self._extras = {}   # windows beyond the first of a day (kept, never lost on save)
        for weekday, name in enumerate(WEEKDAY_NAMES):
            row = QHBoxLayout()
            row.setSpacing(10)
            check = QCheckBox(name)
            check.setObjectName("ownerDayCheck")
            check.setCursor(Qt.PointingHandCursor)
            check.setMinimumWidth(112)
            start = self._time_combo(range(0, DAY_MINUTES, TIME_STEP))
            end = self._time_combo(range(TIME_STEP, DAY_MINUTES + 1, TIME_STEP))
            to_label = _label("to", "ownerDayTo", wrap=False)
            row.addWidget(check)
            row.addWidget(start)
            row.addWidget(to_label)
            row.addWidget(end)
            row.addStretch()
            box.addLayout(row)
            self.day_boxes[weekday], self.start_combos[weekday] = check, start
            self.end_combos[weekday] = end
            self._set_minute(start, DEFAULT_PICKUP[0])
            self._set_minute(end, DEFAULT_PICKUP[1])
            for combo in (start, end):
                combo.setEnabled(False)
            check.toggled.connect(lambda on, w=weekday: self._on_day_toggled(w, on))
            start.currentIndexChanged.connect(lambda _i, w=weekday: self._on_time_changed(w, True))
            end.currentIndexChanged.connect(lambda _i, w=weekday: self._on_time_changed(w, False))

        self.summary_label = _label("", "ownerSummary")
        box.addSpacing(2)
        box.addWidget(self.summary_label)
        self._update_summary()

    # ---------- building blocks ----------
    @staticmethod
    def _time_combo(minutes) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("ownerCombo")
        combo.setFixedWidth(124)
        combo.setMaxVisibleItems(10)
        for minute in minutes:
            combo.addItem(format_minute(minute), minute)
        return combo

    @staticmethod
    def _set_minute(combo: QComboBox, minute: int):
        """Select `minute`, adding it to the list (in order) if it is not a 30-minute step."""
        index = combo.findData(minute)
        if index < 0:
            index = 0
            while index < combo.count() and combo.itemData(index) < minute:
                index += 1
            combo.insertItem(index, format_minute(minute), minute)
        combo.setCurrentIndex(index)

    @staticmethod
    def _minute(combo: QComboBox) -> int:
        return int(combo.currentData())

    # ---------- public ----------
    def schedule(self) -> dict:
        result = {}
        for weekday, check in self.day_boxes.items():
            if check.isChecked():
                window = (self._minute(self.start_combos[weekday]),
                          self._minute(self.end_combos[weekday]))
                result[weekday] = [window] + list(self._extras.get(weekday, ()))
        return result

    def set_schedule(self, schedule):
        """Show a saved schedule (a dict or an AvailabilitySchedule); no `changed` signal."""
        if not isinstance(schedule, AvailabilitySchedule):
            try:
                schedule = AvailabilitySchedule.from_dict(schedule)
            except AvailabilityError:
                schedule = AvailabilitySchedule.empty()
        self._extras = {}
        for weekday in range(7):
            windows = schedule.windows_on(weekday)
            check = self.day_boxes[weekday]
            start, end = self.start_combos[weekday], self.end_combos[weekday]
            for widget in (check, start, end):
                widget.blockSignals(True)
            check.setChecked(bool(windows))
            first = windows[0] if windows else DEFAULT_PICKUP
            self._set_minute(start, first[0])
            self._set_minute(end, first[1])
            start.setEnabled(bool(windows))
            end.setEnabled(bool(windows))
            for widget in (check, start, end):
                widget.blockSignals(False)
            if len(windows) > 1:
                self._extras[weekday] = list(windows[1:])
        self._update_summary()

    # ---------- reacting to the student ----------
    def _first_enabled(self, except_day=None):
        for weekday, check in self.day_boxes.items():
            if check.isChecked() and weekday != except_day:
                return weekday
        return None

    def _on_day_toggled(self, weekday: int, on: bool):
        start, end = self.start_combos[weekday], self.end_combos[weekday]
        if on:
            source = self._first_enabled(except_day=weekday)
            if source is not None:   # a new day starts with the hours already chosen
                for combo, src in ((start, self.start_combos[source]),
                                   (end, self.end_combos[source])):
                    combo.blockSignals(True)
                    self._set_minute(combo, self._minute(src))
                    combo.blockSignals(False)
        else:
            self._extras.pop(weekday, None)
        start.setEnabled(on)
        end.setEnabled(on)
        self._update_summary()
        self.changed.emit()

    def _on_time_changed(self, weekday: int, start_changed: bool):
        start, end = self.start_combos[weekday], self.end_combos[weekday]
        low, high = self._minute(start), self._minute(end)
        if high <= low:   # keep the range sensible instead of showing an error
            if start_changed:
                target, value = end, min(low + 60, DAY_MINUTES)
            else:
                target, value = start, max(high - 60, 0)
            target.blockSignals(True)
            self._set_minute(target, value)
            target.blockSignals(False)
        self._update_summary()
        self.changed.emit()

    def _apply_days(self, days):
        days = set(days)
        base = self._first_enabled()
        values = ((self._minute(self.start_combos[base]), self._minute(self.end_combos[base]))
                  if base is not None else DEFAULT_PICKUP)
        for weekday, check in self.day_boxes.items():
            start, end = self.start_combos[weekday], self.end_combos[weekday]
            on = weekday in days
            for widget in (check, start, end):
                widget.blockSignals(True)
            if on and not check.isChecked():
                self._set_minute(start, values[0])
                self._set_minute(end, values[1])
            check.setChecked(on)
            start.setEnabled(on)
            end.setEnabled(on)
            for widget in (check, start, end):
                widget.blockSignals(False)
            if not on:
                self._extras.pop(weekday, None)
        self._update_summary()
        self.changed.emit()

    def _update_summary(self):
        try:
            text = AvailabilitySchedule.from_dict(self.schedule()).summary()
        except AvailabilityError:
            text = "Check the pickup times"
        self.summary_label.setText(text if self.schedule() else "No pickup days selected yet")


class OwnerDashboardPage(_OwnerPage):
    switch_to_student_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(
            "Student Owner workspace", "Owner Dashboard",
            "This is where you will manage the items you lend.", HAPPY_MASCOT_PATH, parent)

        self.listings_tile = self._tile("Listings", "0", "You have no listings yet", muted=False)
        self.requests_tile = self._tile(
            "Incoming requests", "0", "No pending requests", muted=False)
        tiles = [
            self.listings_tile,
            self.requests_tile,
            self._tile("Items on loan", "—", "Coming in a later step", muted=True),
        ]
        self.body.addWidget(ReflowGrid(tiles, min_item_width=200, spacing=14))

        card, box, self.account_text = self._card(
            "One account, two workspaces",
            "Your profile, Student ID and Settings are shared with the Student workspace. "
            "You can keep borrowing as a student at any time.")
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.switch_button = QPushButton("Switch to Student workspace")
        self.switch_button.setObjectName("ownerPrimaryButton")
        self.switch_button.setCursor(Qt.PointingHandCursor)
        self.switch_button.clicked.connect(self.switch_to_student_requested.emit)
        buttons.addWidget(self.switch_button)
        self.settings_button = QPushButton("Open Settings")
        self.settings_button.setObjectName("ownerGhostButton")
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.clicked.connect(self.settings_requested.emit)
        buttons.addWidget(self.settings_button)
        buttons.addStretch()
        box.addSpacing(4)
        box.addLayout(buttons)
        self.body.addWidget(card)

        card, _box, _text = self._card(
            "What is coming",
            "You can review incoming requests from the owner rail. Pickup confirmation, "
            "active loans and returns will arrive in a later step.")
        self.body.addWidget(card)
        self.body.addStretch()

    @staticmethod
    def _tile(label: str, value: str, note: str, muted: bool) -> QFrame:
        tile = QFrame()
        tile.setObjectName("ownerTile")
        box = QVBoxLayout(tile)
        box.setContentsMargins(18, 14, 18, 14)
        box.setSpacing(2)
        box.addWidget(_label(label, "ownerTileLabel", wrap=False))
        value_label = _label(value, "ownerTileValue", wrap=False)
        value_label.setProperty("muted", muted)
        box.addWidget(value_label)
        note_label = _label(note, "ownerTileNote")
        box.addWidget(note_label)
        tile.value_label = value_label
        tile.note_label = note_label
        return tile

    def set_draft_count(self, count: int):
        """Show how many drafts the owner has (nothing is published yet)."""
        self.listings_tile.value_label.setText(str(count))
        self.listings_tile.note_label.setText(
            "You have no listings yet" if count == 0
            else f"{count} draft{'s' if count != 1 else ''} · none published")

    def set_pending_request_count(self, count: int):
        self.requests_tile.value_label.setText(str(count))
        self.requests_tile.note_label.setText(
            f"{count} pending request{'s' if count != 1 else ''}")

    def set_identity(self, full_name: str, email: str):
        first = (full_name or "").split(" ")[0] if full_name else ""
        self.subtitle_label.setText(
            (f"Welcome, {first}. " if first else "") + "This is where you will manage the items you lend.")
        base = ("Your profile, Student ID and Settings are shared with the Student workspace. "
                "You can keep borrowing as a student at any time.")
        self.account_text.setText((f"Signed in as {email}. " if email else "") + base)


class OwnerIncomingRequestsPage(_OwnerPage):
    """Review requests attached to the signed-in owner's saved listings."""

    approve_requested = Signal(str)
    reject_requested = Signal(str)

    _FILTERS = (
        ("pending", "Pending", {"pending_owner_approval"}),
        ("approved", "Approved", {"approved"}),
        ("rejected", "Rejected", {"rejected"}),
        ("history", "History", {"borrowed", "return_pending", "returned",
                                "cancelled", "expired"}),
    )

    def __init__(self, parent=None):
        super().__init__(
            "Student Owner workspace", "Incoming Requests",
            "Review requests for your published listings. Approval reserves a copy; "
            "the borrowing period starts only after confirmed handover.",
            HAPPY_MASCOT_PATH, parent)
        self._requests = []
        self._filter = "pending"
        self._selected = None

        self.banner = _label("", "ownerBanner")
        self.banner.hide()
        self.body.addWidget(self.banner)

        self.list_view = QWidget()
        list_box = QVBoxLayout(self.list_view)
        list_box.setContentsMargins(0, 0, 0, 0)
        list_box.setSpacing(12)
        self.filter_row = QHBoxLayout()
        self.filter_row.setSpacing(8)
        self.filter_buttons = {}
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        for key, title, _statuses in self._FILTERS:
            button = QPushButton(title)
            button.setObjectName("ownerChip")
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, selected=key: self._set_filter(selected))
            self.filter_group.addButton(button)
            self.filter_buttons[key] = button
            self.filter_row.addWidget(button)
        self.filter_row.addStretch()
        list_box.addLayout(self.filter_row)

        self.rows_widget = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_widget)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)
        list_box.addWidget(self.rows_widget)
        self.empty_label = _label("No requests in this section yet.", "ownerHint")
        self.empty_label.setAlignment(Qt.AlignCenter)
        list_box.addWidget(self.empty_label)
        self.body.addWidget(self.list_view)

        self.detail_view = QWidget()
        detail_box = QVBoxLayout(self.detail_view)
        detail_box.setContentsMargins(0, 0, 0, 0)
        detail_box.setSpacing(12)
        self.detail_back_button = QPushButton("← Back to Incoming Requests")
        self.detail_back_button.setObjectName("ownerGhostButton")
        self.detail_back_button.clicked.connect(self._show_list)
        detail_box.addWidget(self.detail_back_button, 0, Qt.AlignLeft)

        self.detail_card = QFrame()
        self.detail_card.setObjectName("ownerCard")
        card_box = QVBoxLayout(self.detail_card)
        card_box.setContentsMargins(20, 18, 20, 20)
        card_box.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(16)
        self.photo_label = QLabel()
        self.photo_label.setObjectName("ownerCardThumbEmpty")
        self.photo_label.setFixedSize(96, 96)
        self.photo_label.setAlignment(Qt.AlignCenter)
        self.detail_title = _label("", "ownerCardTitle")
        self.detail_title.setStyleSheet(
            f"font-size: {tk.FONT_SIZE_H2}px; color: {tk.COLOR_TEXT_PRIMARY};")
        self.detail_subtitle = _label("", "ownerHint")
        title_stack = QVBoxLayout()
        title_stack.setSpacing(6)
        title_stack.addWidget(self.detail_title)
        title_stack.addWidget(self.detail_subtitle)
        top.addWidget(self.photo_label, 0, Qt.AlignTop)
        top.addLayout(title_stack, 1)
        card_box.addLayout(top)
        self.detail_facts = _label("", "ownerCardText")
        self.detail_facts.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_box.addWidget(self.detail_facts)
        self.detail_note = _label("", "ownerHint")
        card_box.addWidget(self.detail_note)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.approve_button = QPushButton("Approve Request")
        self.approve_button.setObjectName("ownerPrimaryButton")
        self.approve_button.clicked.connect(
            lambda: self._emit_decision(self.approve_requested))
        self.reject_button = QPushButton("Reject Request")
        self.reject_button.setObjectName("ownerDangerButton")
        self.reject_button.clicked.connect(
            lambda: self._emit_decision(self.reject_requested))
        actions.addWidget(self.approve_button)
        actions.addWidget(self.reject_button)
        actions.addStretch()
        card_box.addLayout(actions)
        detail_box.addWidget(self.detail_card)
        detail_box.addStretch(1)
        self.body.addWidget(self.detail_view)
        self.detail_view.hide()
        self.filter_buttons["pending"].setChecked(True)
        self._render_rows()

    def set_requests(self, incoming_requests):
        """Refresh the view from persisted requests without retaining stale records."""
        self._requests = list(incoming_requests or [])
        if self._selected is not None:
            selected_id = self._selected.request.request_id
            self._selected = next(
                (entry for entry in self._requests
                 if entry.request.request_id == selected_id), None)
            if self._selected is None:
                self._show_list()
            else:
                self._render_detail(self._selected)
        self._render_rows()

    def show_message(self, text: str, error: bool = False):
        self.banner.setText(text)
        self.banner.setProperty("error", error)
        self.banner.setVisible(bool(text))

    def open_request(self, entry):
        self._selected = entry
        self._render_detail(entry)
        self.list_view.hide()
        self.detail_view.show()

    def _set_filter(self, key: str):
        self._filter = key
        self._render_rows()

    def _visible_requests(self):
        statuses = dict((key, values) for key, _title, values in self._FILTERS)[self._filter]
        visible = [entry for entry in self._requests
                   if entry.request.status.value in statuses]
        return sorted(
            visible,
            key=lambda entry: (
                entry.request.status.value != "pending_owner_approval",
                -entry.request.submitted_at.timestamp(),
            ),
        )

    def _render_rows(self):
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        counts = {
            key: sum(entry.request.status.value in statuses for entry in self._requests)
            for key, _title, statuses in self._FILTERS
        }
        for key, title, _statuses in self._FILTERS:
            self.filter_buttons[key].setText(f"{title} · {counts[key]}")
        visible = self._visible_requests()
        self.empty_label.setVisible(not visible)
        for entry in visible:
            request = entry.request
            card = QFrame()
            card.setObjectName("ownerRequestCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 12, 14, 12)
            row.setSpacing(14)
            photo = QLabel()
            photo.setFixedSize(54, 54)
            photo.setAlignment(Qt.AlignCenter)
            photo.setObjectName("ownerCardThumbEmpty")
            pixmap = QPixmap(request.item_photo_path or "")
            if not pixmap.isNull():
                photo.setPixmap(pixmap.scaled(
                    54, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                photo.setText("No photo")
            row.addWidget(photo, 0, Qt.AlignTop)
            labels = QVBoxLayout()
            labels.setSpacing(4)
            labels.addWidget(_label(request.item.title, "ownerCardTitle"))
            labels.addWidget(_label(
                f"{entry.borrower_name} · {request.status.info.label}", "ownerCardText"))
            pickup = request.preferred_pickup_at
            pickup_text = pickup.strftime("%b %d, %Y · %I:%M %p") if pickup else "Not provided"
            labels.addWidget(_label(
                f"Pickup {pickup_text} · {request.requested_days} day(s)", "ownerHint"))
            row.addLayout(labels, 1)
            review = QPushButton("Review")
            review.setObjectName("ownerGhostButton")
            review.clicked.connect(
                lambda _checked=False, selected=entry: self.open_request(selected))
            row.addWidget(review, 0, Qt.AlignVCenter)
            self.rows_layout.addWidget(card)

    def _render_detail(self, entry):
        request = entry.request
        self.detail_title.setText(request.item.title)
        self.detail_subtitle.setText(
            f"{request.status.info.label} · Request {request.request_id}")
        pixmap = QPixmap(request.item_photo_path or "")
        self.photo_label.setPixmap(
            pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not pixmap.isNull() else QPixmap())
        self.photo_label.setText("" if not pixmap.isNull() else "No photo")
        pickup = request.preferred_pickup_at
        pickup_text = pickup.strftime("%b %d, %Y · %I:%M %p") if pickup else "Not provided"
        self.detail_facts.setText(
            f"Borrower: {entry.borrower_name}\n"
            f"Email: {entry.borrower_email}\n"
            f"Requested pickup: {pickup_text}\n"
            f"Borrowing duration: {request.requested_days} day(s)\n"
            f"Maximum duration: {request.max_days} day(s)\n"
            f"Category: {request.item.category}\n"
            f"Status: {request.status.info.label}"
        )
        is_pending = request.status.value == "pending_owner_approval"
        self.approve_button.setVisible(is_pending)
        self.reject_button.setVisible(is_pending)
        self.approve_button.setEnabled(
            is_pending and entry.listing_status == "Published")
        warning = (is_pending and entry.listing_status != "Published")
        self.detail_note.setText(
            "This listing is no longer published; approval is disabled."
            if warning else request.status_note)
        self.detail_note.setVisible(warning or bool(request.status_note))

    def _emit_decision(self, signal):
        if self._selected is not None:
            signal.emit(self._selected.request.request_id)

    def _show_list(self):
        self._selected = None
        self.detail_view.hide()
        self.list_view.show()


_P = "QWidget#ownerListingPreviewPage"
OWNER_LISTING_PREVIEW_QSS = f"""
{_P} {{ background-color: {tk.COLOR_BG_APP}; }}
{_P} QLabel {{ background: transparent; border: none; }}
{_P} QScrollArea#ownerPreviewScroll,
{_P} QScrollArea#ownerPreviewScroll QWidget#qt_scrollarea_viewport,
{_P} QWidget#ownerPreviewContent {{
    background-color: {tk.COLOR_BG_APP}; border: none;
}}
{_P} QScrollArea#ownerPreviewScroll QScrollBar:vertical {{
    background: transparent; width: 9px; margin: 3px 1px;
}}
{_P} QScrollArea#ownerPreviewScroll QScrollBar::handle:vertical {{
    background: {tk.COLOR_BORDER_STRONG}; border-radius: 4px; min-height: 28px;
}}
{_P} QScrollArea#ownerPreviewScroll QScrollBar::add-line:vertical,
{_P} QScrollArea#ownerPreviewScroll QScrollBar::sub-line:vertical {{
    height: 0px;
}}
{_P} QScrollArea#ownerPreviewScroll QScrollBar::add-page:vertical,
{_P} QScrollArea#ownerPreviewScroll QScrollBar::sub-page:vertical {{
    background: transparent;
}}
{_P} QLabel#ownerPreviewEyebrow {{
    color: {LAVENDER_TEXT}; font-size: {tk.FONT_SIZE_CAPTION}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_P} QLabel#ownerPreviewTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_H2}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_P} QPushButton#ownerPreviewBack {{
    background-color: transparent; color: {LAVENDER_TEXT};
    border: 1px solid {tk.COLOR_BORDER}; border-radius: {tk.RADIUS_MD}px;
    padding: 0px 14px; min-height: 36px;
    font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_P} QPushButton#ownerPreviewBack:hover {{
    background-color: {tk.COLOR_BG_RAISED}; border-color: {tk.COLOR_BORDER_STRONG};
    color: {tk.COLOR_TEXT_PRIMARY};
}}
{_P} QLabel#ownerPreviewPill {{
    background-color: {tk.COLOR_WARNING_SOFT}; color: {tk.COLOR_WARNING};
    border-radius: 9px; padding: 3px 10px;
    font-size: {tk.FONT_SIZE_CAPTION}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_P} QFrame#ownerPreviewCard {{
    background-color: {tk.COLOR_BG_SURFACE}; border: none;
    border-radius: {tk.RADIUS_MD}px;
}}
{_P} QFrame#ownerPreviewHero {{
    background-color: {tk.COLOR_BG_RAISED}; border: none;
    border-radius: {tk.RADIUS_SM}px;
}}
{_P} QLabel#ownerPreviewPhotoEmpty {{
    color: {tk.COLOR_TEXT_MUTED}; font-size: {tk.FONT_SIZE_BODY}px;
}}
{_P} QPushButton#ownerPreviewThumbnail {{
    background-color: {tk.COLOR_BG_RAISED}; border: 1px solid {tk.COLOR_BORDER};
    border-radius: {tk.RADIUS_SM}px; padding: 3px;
}}
{_P} QPushButton#ownerPreviewThumbnail:hover {{
    border-color: {tk.COLOR_BORDER_STRONG};
}}
{_P} QPushButton#ownerPreviewThumbnail[selected="true"] {{
    border: 2px solid {tk.COLOR_FOCUS_RING};
}}
{_P} QLabel#ownerPreviewSection {{
    color: {LAVENDER_TEXT}; font-size: {tk.FONT_SIZE_SMALL}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_P} QLabel#ownerPreviewValue {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_BODY}px;
}}
{_P} QLabel#ownerPreviewMuted {{
    color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY - 1}px;
}}
{_P} QPushButton#ownerPreviewMainPhoto {{
    background-color: transparent; border: none; padding: 0;
}}
{_P} QFrame#ownerPreviewImageViewer {{
    background-color: {tk.COLOR_BG_APP}; border: 1px solid {tk.COLOR_BORDER};
}}
{_P} QLabel#ownerPreviewViewerImage {{
    background-color: {tk.COLOR_BG_APP}; color: {tk.COLOR_TEXT_MUTED};
}}
{_P} QPushButton#ownerPreviewViewerAction {{
    background-color: {tk.COLOR_BG_SURFACE}; color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER}; border-radius: {tk.RADIUS_MD}px;
    padding: 0px 14px; min-height: 36px;
}}
{_P} QPushButton#ownerPreviewViewerAction:hover {{
    background-color: {tk.COLOR_BG_RAISED}; border-color: {tk.COLOR_BORDER_STRONG};
}}
"""


class OwnerListingPreviewPage(QWidget):
    """Responsive, read-only page for one saved Student Owner draft."""

    back_requested = Signal()

    def __init__(self, listing, photo_paths=(), schedule=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ownerListingPreviewPage")
        self.setStyleSheet(OWNER_LISTING_PREVIEW_QSS)
        self._photo_paths = list(photo_paths)
        self._selected_photo = -1
        self.photo_buttons = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(16)

        top = QVBoxLayout()
        top.setSpacing(8)
        self.back_button = QPushButton("← Back to My Listings")
        self.back_button.setObjectName("ownerPreviewBack")
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.clicked.connect(self.back_requested.emit)
        top.addWidget(self.back_button, 0, Qt.AlignLeft)
        heading_row = QHBoxLayout()
        heading_row.setSpacing(12)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        eyebrow = QLabel("LISTING PREVIEW")
        eyebrow.setObjectName("ownerPreviewEyebrow")
        heading.addWidget(eyebrow)
        self.title_label = QLabel(listing.title)
        self.title_label.setObjectName("ownerPreviewTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        heading.addWidget(self.title_label)
        heading_row.addLayout(heading, 1)
        listing_status = getattr(listing, "status", "Draft")
        self.draft_pill = QLabel(listing_status.upper())
        self.draft_pill.setObjectName("ownerPreviewPill")
        self.draft_pill.setProperty("status", listing_status)
        self.draft_pill.setAlignment(Qt.AlignCenter)
        heading_row.addWidget(self.draft_pill, 0, Qt.AlignTop)
        top.addLayout(heading_row)
        outer.addLayout(top)

        scroll = QScrollArea()
        scroll.setObjectName("ownerPreviewScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setObjectName("ownerPreviewContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(16)
        content_layout.setAlignment(Qt.AlignTop)

        gallery = QFrame()
        gallery.setObjectName("ownerPreviewCard")
        gallery.setMinimumWidth(0)
        gallery.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        gallery_layout = QVBoxLayout(gallery)
        gallery_layout.setContentsMargins(20, 20, 20, 20)
        gallery_layout.setSpacing(12)
        hero = QFrame()
        hero.setObjectName("ownerPreviewHero")
        hero.setFixedHeight(220)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(8, 8, 8, 8)
        self.photo_label = QPushButton()
        self.photo_label.setObjectName("ownerPreviewMainPhoto")
        self.photo_label.setMinimumSize(0, 0)
        self.photo_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.photo_label.setCursor(Qt.PointingHandCursor)
        self.photo_label.setAccessibleName("View full listing photo")
        self.photo_label.clicked.connect(
            lambda: self.show_full_image(self._selected_photo))
        self.photo_empty_label = QLabel("No photos added yet")
        self.photo_empty_label.setObjectName("ownerPreviewPhotoEmpty")
        self.photo_empty_label.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(self.photo_label)
        hero_layout.addWidget(self.photo_empty_label)
        gallery_layout.addWidget(hero)
        self.thumbnails = QHBoxLayout()
        self.thumbnails.setSpacing(8)
        gallery_layout.addLayout(self.thumbnails)

        details = QFrame()
        details.setObjectName("ownerPreviewCard")
        details.setMinimumWidth(0)
        details.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(20, 20, 20, 20)
        details_layout.setSpacing(5)
        details_layout.addWidget(self._section("ITEM DETAILS"))
        self.category_label = self._value("")
        self.condition_label = self._value("")
        self.total_copies_label = self._value("")
        self.available_copies_label = self._value("")
        for label in (self.category_label, self.condition_label,
                      self.total_copies_label, self.available_copies_label):
            label.setWordWrap(True)
            details_layout.addWidget(label)

        description = QFrame()
        description.setObjectName("ownerPreviewCard")
        description.setMinimumWidth(0)
        description.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        description_layout = QVBoxLayout(description)
        description_layout.setContentsMargins(20, 20, 20, 20)
        description_layout.setSpacing(8)
        description_layout.addWidget(self._section("DESCRIPTION"))
        self.description_label = self._value("", muted=True)
        self.description_label.setWordWrap(True)
        description_layout.addWidget(self.description_label)

        rules = QFrame()
        self.rules_card = rules
        rules.setObjectName("ownerPreviewCard")
        rules.setMinimumWidth(0)
        rules.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        rules_layout = QVBoxLayout(rules)
        rules_layout.setContentsMargins(20, 20, 20, 20)
        rules_layout.setSpacing(8)
        self.rules_section = self._section("BORROWING RULES")
        rules_layout.addWidget(self.rules_section)
        self.rules_label = self._value("", muted=True)
        self.rules_label.setWordWrap(True)
        rules_layout.addWidget(self.rules_label)

        availability = QFrame()
        availability.setObjectName("ownerPreviewCard")
        availability.setMinimumWidth(0)
        availability.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        availability_layout = QVBoxLayout(availability)
        availability_layout.setContentsMargins(20, 20, 20, 20)
        availability_layout.setSpacing(8)
        availability_layout.addWidget(self._section("AVAILABILITY"))
        self.availability_label = self._value("", muted=True)
        self.availability_label.setWordWrap(True)
        availability_layout.addWidget(self.availability_label)
        self.loan_label = self._value("", muted=True)
        self.loan_label.setWordWrap(True)
        availability_layout.addWidget(self.loan_label)

        self.information_widget = QWidget()
        self.information_widget.setObjectName("ownerPreviewInformation")
        self.information_widget.setMinimumWidth(0)
        self.information_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        information_layout = QVBoxLayout(self.information_widget)
        information_layout.setContentsMargins(0, 0, 0, 0)
        information_layout.setSpacing(12)
        information_layout.setAlignment(Qt.AlignTop)
        self.information_sections = (details, description, rules, availability)
        for section in self.information_sections:
            information_layout.addWidget(section, alignment=Qt.AlignTop)

        self.main_grid = ReflowGrid(
            [gallery, self.information_widget], min_item_width=340, spacing=16)
        self.main_grid.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.main_grid.layout().setAlignment(gallery, Qt.AlignTop)
        self.main_grid.layout().setAlignment(self.information_widget, Qt.AlignTop)
        content_layout.addWidget(self.main_grid, alignment=Qt.AlignTop)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        self._image_scale = 1.0
        self._viewer_pixmap = QPixmap()
        self.image_viewer = self._build_image_viewer()
        self.image_viewer.hide()
        self.set_listing(listing, photo_paths, schedule)

    def _build_image_viewer(self):
        viewer = QFrame(self)
        viewer.setObjectName("ownerPreviewImageViewer")
        layout = QVBoxLayout(viewer)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("Photo viewer")
        title.setObjectName("ownerPreviewTitle")
        header.addWidget(title)
        header.addStretch()
        self.viewer_close_button = QPushButton("Close")
        self.viewer_close_button.setObjectName("ownerPreviewViewerAction")
        self.viewer_close_button.clicked.connect(viewer.hide)
        header.addWidget(self.viewer_close_button)
        layout.addLayout(header)
        self.viewer_scroll = QScrollArea()
        self.viewer_scroll.setWidgetResizable(False)
        self.viewer_scroll.setAlignment(Qt.AlignCenter)
        self.viewer_scroll.setFrameShape(QFrame.NoFrame)
        self.viewer_scroll.viewport().setAutoFillBackground(False)
        self.viewer_image = QLabel()
        self.viewer_image.setObjectName("ownerPreviewViewerImage")
        self.viewer_image.setAlignment(Qt.AlignCenter)
        self.viewer_scroll.setWidget(self.viewer_image)
        layout.addWidget(self.viewer_scroll, 1)
        actions = QHBoxLayout()
        actions.addStretch()
        for text, callback in (
                ("Zoom Out", self._zoom_out), ("Reset / Fit", self._fit_image),
                ("Zoom In", self._zoom_in)):
            button = QPushButton(text)
            button.setObjectName("ownerPreviewViewerAction")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        return viewer

    def _fit_image(self):
        self._image_scale = 1.0
        self._render_viewer_image(fit=True)

    def _zoom_in(self):
        self._image_scale = min(self._image_scale * 1.25, 8.0)
        self._render_viewer_image()

    def _zoom_out(self):
        self._image_scale = max(self._image_scale / 1.25, 0.1)
        self._render_viewer_image()

    def _render_viewer_image(self, fit=False):
        if self._viewer_pixmap.isNull():
            return
        available = self.viewer_scroll.viewport().size()
        if available.width() <= 0 or available.height() <= 0:
            return
        if fit:
            ratio = min(available.width() / self._viewer_pixmap.width(),
                        available.height() / self._viewer_pixmap.height(), 1.0)
            self._image_scale = ratio
        width = max(1, round(self._viewer_pixmap.width() * self._image_scale))
        height = max(1, round(self._viewer_pixmap.height() * self._image_scale))
        self.viewer_image.setPixmap(self._viewer_pixmap.scaled(
            width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.viewer_image.resize(width, height)

    def show_full_image(self, index):
        if not 0 <= index < len(self._photo_paths):
            return
        pixmap = QPixmap(self._photo_paths[index])
        if pixmap.isNull():
            return
        self._selected_photo = index
        self._viewer_pixmap = pixmap
        self._image_scale = 1.0
        self.image_viewer.setGeometry(self.rect())
        self.image_viewer.show()
        self.image_viewer.raise_()
        self._render_viewer_image(fit=True)

    def set_listing(self, listing, photo_paths=(), schedule=None):
        """Refresh the page for the selected saved draft without writing to storage."""
        self.title_label.setText(listing.title)
        self.category_label.setText(f"Category · {listing.category_path}")
        self.condition_label.setText(f"Condition · {listing.condition}")
        self.description_label.setText(listing.description)
        self.rules_label.setText(listing.extra_rules)
        self.rules_card.setVisible(bool(listing.extra_rules))
        availability_text = (schedule.summary() if schedule is not None and not schedule.is_empty
                             else "Pickup days not set yet")
        self.availability_label.setText(f"Pickup · {availability_text}")
        self.loan_label.setText(
            f"Longest loan · {listing.max_borrow_days} day"
            f"{'s' if listing.max_borrow_days != 1 else ''}")
        self.total_copies_label.setText(f"Total copies · {listing.stock_quantity}")
        available_text = f"Available copies · {listing.available_copies}"
        if listing.stock_quantity == 0:
            available_text += " (Out of Stock)"
        self.available_copies_label.setText(available_text)
        self.set_photo_paths(photo_paths)

    @staticmethod
    def _section(text):
        label = QLabel(text)
        label.setObjectName("ownerPreviewSection")
        return label

    @staticmethod
    def _value(text, muted=False):
        label = QLabel(text)
        label.setObjectName("ownerPreviewMuted" if muted else "ownerPreviewValue")
        return label

    def _set_photo(self, index):
        self._selected_photo = index if 0 <= index < len(self._photo_paths) else -1
        self.photo_label.setIcon(QIcon())
        self.photo_label.setText("")
        self.photo_empty_label.setVisible(self._selected_photo < 0)
        if self._selected_photo >= 0:
            pixmap = QPixmap(self._photo_paths[self._selected_photo])
            if not pixmap.isNull():
                fitted = pixmap.scaled(max(1, self.photo_label.width() - 16), 190,
                                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.photo_label.setIcon(QIcon(fitted))
                self.photo_label.setIconSize(fitted.size())
                self.photo_label.setAccessibleName(f"View full photo {self._selected_photo + 1}")
            else:
                self.photo_empty_label.setText("This photo is no longer available")
                self.photo_empty_label.setVisible(True)
        for position, button in enumerate(self.photo_buttons):
            button.setProperty("selected", position == self._selected_photo)
            button.style().unpolish(button)
            button.style().polish(button)

    def set_photo_paths(self, paths):
        """Populate the saved-photo gallery; only reads the supplied files."""
        self._photo_paths = list(paths)
        self.photo_empty_label.setText("No photos added yet")
        self.photo_empty_label.setVisible(not self._photo_paths)
        while self.thumbnails.count():
            item = self.thumbnails.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.photo_buttons = []
        for index, path in enumerate(self._photo_paths):
            pixmap = QPixmap(path)
            if pixmap.isNull():
                continue
            button = QPushButton()
            button.setObjectName("ownerPreviewThumbnail")
            button.setProperty("selected", False)
            button.setFixedSize(54, 54)
            button.setIcon(QIcon(pixmap))
            button.setIconSize(QSize(44, 44))
            button.setAccessibleName(f"Show photo {index + 1}")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, n=index: self.show_full_image(n))
            self.thumbnails.addWidget(button)
            self.photo_buttons.append(button)
        self.thumbnails.addStretch()
        self._set_photo(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.image_viewer.setGeometry(self.rect())
        if self._selected_photo >= 0:
            self._set_photo(self._selected_photo)
        if self.image_viewer.isVisible():
            self._render_viewer_image(fit=True)


class _ListingCard(QFrame):
    """One saved listing in My Listings, with status-appropriate actions."""

    edit_clicked = Signal(str)   # listing_id
    preview_clicked = Signal(str)
    publish_clicked = Signal(str)
    pause_clicked = Signal(str)
    resume_clicked = Signal(str)
    delete_clicked = Signal(str)
    THUMB = 60

    def __init__(self, listing, photo_path=None, schedule=None, parent=None):
        super().__init__(parent)
        self.listing_id = listing.listing_id
        self.setObjectName("ownerListingCard")
        self.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 16, 12)
        row.setSpacing(14)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(self.THUMB, self.THUMB)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(photo_path)) if photo_path else QPixmap()
        self.has_photo = not pixmap.isNull()
        if self.has_photo:
            self.thumb_label.setPixmap(_rounded_cover(pixmap, self.THUMB, self.THUMB, 10))
        else:
            self.thumb_label.setObjectName("ownerCardThumbEmpty")
            self.thumb_label.setText("No photo")
        row.addWidget(self.thumb_label, 0, Qt.AlignVCenter)

        texts = QVBoxLayout()
        texts.setSpacing(3)
        title = _label(listing.title, "ownerListingTitle")
        texts.addWidget(title)
        texts.addWidget(_label(
            f"{getattr(listing, 'category_path', listing.category)} · {listing.condition} · up to "
            f"{listing.max_borrow_days} day{'s' if listing.max_borrow_days != 1 else ''}",
            "ownerListingMeta"))
        self.stock_label = _label(
            f"Total copies: {listing.stock_quantity} · "
            f"Available copies: {listing.available_copies}"
            f"{' (Out of Stock)' if listing.stock_quantity == 0 else ''}",
            "ownerListingMeta")
        texts.addWidget(self.stock_label)
        self.pickup_label = _label(
            "Pickup: " + schedule.summary() if schedule is not None and not schedule.is_empty
            else "Pickup days not set yet", "ownerListingNote")
        texts.addWidget(self.pickup_label)
        row.addLayout(texts, 1)
        status = getattr(listing, "status", "Draft")
        is_draft = status == "Draft"
        pill = QLabel(status)
        self.status_label = pill
        pill.setObjectName({
            "Draft": "ownerDraftPill",
            "Published": "ownerPublishedPill",
            "Paused": "ownerPausedPill",
        }.get(status, "ownerDraftPill"))
        pill.setAlignment(Qt.AlignCenter)
        pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        row.addWidget(pill, 0, Qt.AlignVCenter)
        self.preview_button = QPushButton("Preview")
        self.preview_button.setObjectName("ownerGhostButton")
        self.preview_button.setCursor(Qt.PointingHandCursor)
        self.preview_button.clicked.connect(
            lambda _checked=False: self.preview_clicked.emit(self.listing_id))
        row.addWidget(self.preview_button, 0, Qt.AlignVCenter)
        self.publish_button = QPushButton("Publish Listing")
        self.publish_button.setObjectName("ownerGhostButton")
        self.publish_button.setCursor(Qt.PointingHandCursor)
        self.publish_button.clicked.connect(
            lambda _checked=False: self.publish_clicked.emit(self.listing_id))
        self.publish_button.setVisible(is_draft)
        row.addWidget(self.publish_button, 0, Qt.AlignVCenter)
        self.edit_button = QPushButton("Edit")
        self.edit_button.setObjectName("ownerGhostButton")
        self.edit_button.setCursor(Qt.PointingHandCursor)
        self.edit_button.clicked.connect(lambda _c=False: self.edit_clicked.emit(self.listing_id))
        self.edit_button.setVisible(True)
        row.addWidget(self.edit_button, 0, Qt.AlignVCenter)
        self.actions_button = QToolButton()
        self.actions_button.setObjectName("ownerListingMenu")
        self.actions_button.setText("⋯")
        self.actions_button.setToolTip("Manage listing")
        self.actions_button.setAccessibleName("Manage listing")
        self.actions_menu = QMenu(self.actions_button)
        self.actions_menu.setObjectName("ownerListingMenu")
        if status == "Published":
            self.pause_action = self.actions_menu.addAction("Pause Listing")
            self.pause_action.triggered.connect(
                lambda _checked=False: self.pause_clicked.emit(self.listing_id))
        elif status == "Paused":
            self.resume_action = self.actions_menu.addAction("Resume Listing")
            self.resume_action.triggered.connect(
                lambda _checked=False: self.resume_clicked.emit(self.listing_id))
        self.delete_action = self.actions_menu.addAction("Delete Listing")
        self.delete_action.triggered.connect(
            lambda _checked=False: self.delete_clicked.emit(self.listing_id))
        self.actions_button.setMenu(self.actions_menu)
        self.actions_button.setPopupMode(QToolButton.InstantPopup)
        row.addWidget(self.actions_button, 0, Qt.AlignVCenter)
        self._is_draft = is_draft

    def mousePressEvent(self, event):
        point = event.position().toPoint()
        if (self._is_draft and event.button() == Qt.LeftButton
                and not self.edit_button.geometry().contains(point)
                and not self.preview_button.geometry().contains(point)
                and not self.publish_button.geometry().contains(point)
                and not self.actions_button.geometry().contains(point)):
            self.edit_clicked.emit(self.listing_id)
        super().mousePressEvent(event)


class OwnerListingsPage(_OwnerPage):
    """My Listings: the owner's saved drafts (or an empty state) and the Add Listing button."""

    back_requested = Signal()
    add_requested = Signal()
    edit_requested = Signal(str)   # listing_id
    preview_requested = Signal(str)
    publish_requested = Signal(str)
    pause_requested = Signal(str)
    resume_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(
            "Student Owner workspace", "My Listings",
            "Your drafts stay private until you publish them. You can edit your published "
            "listings to keep their Catalog details up to date.",
            HAPPY_MASCOT_PATH, parent)
        self.listings = []   # this owner's drafts and published listings

        bar = QHBoxLayout()
        bar.setContentsMargins(2, 0, 2, 0)
        self.count_label = _label("", "ownerCount", wrap=False)
        bar.addWidget(self.count_label)
        bar.addStretch()
        self.add_button = QPushButton("+  Add Listing")
        self.add_button.setObjectName("ownerPrimaryButton")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self.add_requested.emit)
        bar.addWidget(self.add_button)
        self.body.addLayout(bar)

        self.banner = _label("", "ownerBanner")
        self.banner.hide()
        self.body.addWidget(self.banner)

        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(10)
        self.body.addLayout(self.cards_layout)

        box = QFrame()
        box.setObjectName("ownerEmpty")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignHCenter)
        icon = QLabel()
        icon.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(CURIOUS_MASCOT_PATH))
        if not pixmap.isNull():
            icon.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon.setText("📦")
        layout.addWidget(icon)
        self.empty_title = _label("No listings yet", "ownerEmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_title)
        self.empty_text = _label(
            "Add your first listing with photos and pickup times. It is saved as a private draft "
            "until you publish it.", "ownerEmptyText")
        self.empty_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_text)
        layout.addSpacing(6)
        self.empty_add_button = QPushButton("+  Add Listing")
        self.empty_add_button.setObjectName("ownerPrimaryButton")
        self.empty_add_button.setCursor(Qt.PointingHandCursor)
        self.empty_add_button.clicked.connect(self.add_requested.emit)
        layout.addWidget(self.empty_add_button, alignment=Qt.AlignHCenter)
        self.back_button = QPushButton("Back to Owner Dashboard")
        self.back_button.setObjectName("ownerGhostButton")
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.clicked.connect(self.back_requested.emit)
        layout.addWidget(self.back_button, alignment=Qt.AlignHCenter)
        self.empty_state = box
        self.body.addWidget(box)
        self.body.addStretch()

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(5000)
        self._banner_timer.timeout.connect(self.banner.hide)
        self.set_listings([])

    def set_listings(self, listings, photos=None, schedules=None):
        """Show this owner's listings (newest edit first). An empty list shows the empty state.

        photos: {listing_id: path of its primary photo}; schedules: {listing_id: schedule}.
        Both are optional and only change how each card looks."""
        photos, schedules = photos or {}, schedules or {}
        self.listings = list(listings)
        while self.cards_layout.count():
            widget = self.cards_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.cards = []
        for listing in self.listings:
            card = _ListingCard(listing, photos.get(listing.listing_id),
                                schedules.get(listing.listing_id))
            card.edit_clicked.connect(self.edit_requested.emit)
            card.preview_clicked.connect(self.preview_requested.emit)
            card.publish_clicked.connect(self.publish_requested.emit)
            card.pause_clicked.connect(self.pause_requested.emit)
            card.resume_clicked.connect(self.resume_requested.emit)
            card.delete_clicked.connect(self.delete_requested.emit)
            self.cards_layout.addWidget(card)
            self.cards.append(card)
        count = len(self.listings)
        drafts = sum(getattr(listing, "status", "Draft") == "Draft"
                     for listing in self.listings)
        self.count_label.setText(
            f"{count} listing{'s' if count != 1 else ''} · {drafts} draft"
            f"{'s' if drafts != 1 else ''}" if count else "")
        self.empty_state.setVisible(count == 0)
        self.add_button.setVisible(count > 0)

    def show_message(self, text: str):
        self.banner.setText(text)
        self.banner.setVisible(bool(text))
        if text:
            self._banner_timer.start()


class _RefreshingCombo(QComboBox):
    """A combo box that re-reads its choices just before its list opens.

    Used for the SHARED categories: if another owner added one while this form was open, it
    is there as soon as the list is opened."""

    def __init__(self, before_popup=None, parent=None):
        super().__init__(parent)
        self._before_popup = before_popup

    def showPopup(self):
        if self._before_popup is not None:
            self._before_popup()
        super().showPopup()


class OwnerListingFormPage(_OwnerPage):
    """The dedicated Add Listing / Edit Draft form (one page for both)."""

    save_requested = Signal(dict, object)   # (fields, listing_id or None when adding)
    cancel_requested = Signal()
    back_requested = Signal()
    # Step 31C: photo changes of an already SAVED listing (a new listing keeps them in the
    # form until it is saved). (listing_id, file paths) / (listing_id, photo key)
    photo_add_requested = Signal(str, list)
    photo_remove_requested = Signal(str, object)
    photo_primary_requested = Signal(str, object)

    def __init__(self, categories, conditions, min_days=1, max_days=30, parent=None,
                 category_source=None):
        # category_source (Step 31D): the shared category registry as seen by this owner
        # (app.listing_category_service.OwnerCategoryAccess). Without it the form shows the plain
        # `categories` list only, with no subcategory and no "New category" buttons.
        super().__init__(
            "Student Owner workspace", "Add Listing",
            "Describe the item you want to lend. It is saved as a private draft.",
            HAPPY_MASCOT_PATH, parent)
        self._category_source = category_source
        self._listing_id = None
        self._listing_status = "Draft"
        self._staged = []            # photo files picked for a NEW listing, not saved yet
        self._staged_primary = None
        self._original_photos = []
        self._editing_photos = []
        self._dirty_baseline = None
        self._availability_known = True   # False if a saved schedule could not be loaded

        card, box, _text = self._card(
            "Item details", "Tell students what this item is and what shape it is in.")
        box.addWidget(_label("Item name", "ownerFieldLabel", wrap=False))
        self.title_input = QLineEdit()
        self.title_input.setObjectName("ownerInput")
        self.title_input.setMaxLength(80)
        self.title_input.setPlaceholderText("For example: Casio fx-991EX Scientific Calculator")
        box.addWidget(self.title_input)

        row = QHBoxLayout()
        row.setSpacing(12)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.setSpacing(4)
        right.setSpacing(4)
        left.addWidget(_label("Category", "ownerFieldLabel", wrap=False))
        self.category_combo = _RefreshingCombo(
            (lambda: self.refresh_categories()) if category_source is not None else None)
        self.category_combo.setObjectName("ownerCombo")
        self.category_combo.addItem(CATEGORY_PLACEHOLDER)
        self.category_combo.addItems(list(categories))
        left.addWidget(self.category_combo)
        self.new_category_button = QPushButton("+ New category")
        self.new_category_button.setObjectName("ownerGhostButton")
        self.new_category_button.setCursor(Qt.PointingHandCursor)
        self.new_category_button.clicked.connect(lambda _c=False: self._open_category_dialog(None))
        left.addWidget(self.new_category_button, alignment=Qt.AlignLeft)
        right.addWidget(_label("Condition", "ownerFieldLabel", wrap=False))
        self.condition_combo = QComboBox()
        self.condition_combo.setObjectName("ownerCombo")
        self.condition_combo.addItem(CONDITION_PLACEHOLDER)
        self.condition_combo.addItems(list(conditions))
        right.addWidget(self.condition_combo)
        row.addLayout(left, 1)
        row.addLayout(right, 1)
        box.addLayout(row)

        # Optional subcategory (Books > Fantasy), from the same shared registry.
        sub_row = QHBoxLayout()
        sub_row.setSpacing(12)
        sub_left = QVBoxLayout()
        sub_left.setSpacing(4)
        self.subcategory_label = _label("Subcategory (optional)", "ownerFieldLabel", wrap=False)
        sub_left.addWidget(self.subcategory_label)
        self.subcategory_combo = _RefreshingCombo(
            (lambda: self._reload_subcategories()) if category_source is not None else None)
        self.subcategory_combo.setObjectName("ownerCombo")
        self.subcategory_combo.addItem(SUBCATEGORY_PLACEHOLDER)
        self.subcategory_combo.setEnabled(False)
        sub_left.addWidget(self.subcategory_combo)
        self.new_subcategory_button = QPushButton("+ New subcategory")
        self.new_subcategory_button.setObjectName("ownerGhostButton")
        self.new_subcategory_button.setCursor(Qt.PointingHandCursor)
        self.new_subcategory_button.setEnabled(False)
        self.new_subcategory_button.clicked.connect(self._new_subcategory)
        sub_left.addWidget(self.new_subcategory_button, alignment=Qt.AlignLeft)
        sub_row.addLayout(sub_left, 1)
        sub_row.addStretch(1)
        box.addLayout(sub_row)
        if category_source is None:   # no shared registry: the form works exactly as before
            for widget in (self.new_category_button, self.subcategory_label,
                           self.subcategory_combo, self.new_subcategory_button):
                widget.hide()
        else:
            self.category_combo.currentIndexChanged.connect(
                lambda _index: self._reload_subcategories(select=""))

        box.addWidget(_label("Description", "ownerFieldLabel", wrap=False))
        self.description_input = QPlainTextEdit()
        self.description_input.setObjectName("ownerTextBox")
        self.description_input.setPlaceholderText(
            "What it is, what is included, anything a borrower should know.")
        self.description_input.setFixedHeight(110)
        self.description_input.setTabChangesFocus(True)
        box.addWidget(self.description_input)
        self.body.addWidget(card)

        self.back_button = QPushButton("← Back to My Listings")
        self.back_button.setObjectName("ownerGhostButton")
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.clicked.connect(self.back_requested.emit)
        self.body.insertWidget(1, self.back_button, alignment=Qt.AlignLeft)

        # Step 31C: photos (preview, primary, remove)
        self.photos = OwnerPhotoManager()
        self.photos.add_requested.connect(self._on_photos_add)
        self.photos.remove_requested.connect(self._on_photo_remove)
        self.photos.primary_requested.connect(self._on_photo_primary)
        self.body.addWidget(self.photos)

        card, box, _text = self._card(
            "Inventory",
            "Set the number of physical copies. Pending requests do not reduce availability.")
        box.addWidget(_label(
            "Total Copies / Stock Quantity", "ownerFieldLabel", wrap=False))
        self.stock_input = QSpinBox()
        self.stock_input.setObjectName("ownerSpin")
        self.stock_input.setRange(0, MAX_STOCK_QUANTITY)
        self.stock_input.setValue(1)
        self.stock_input.setSuffix(" copies")
        self.stock_input.setFixedWidth(160)
        box.addWidget(self.stock_input, alignment=Qt.AlignLeft)
        self.body.addWidget(card)

        # Step 31C: when the item can be collected, and the longest loan
        card, box, _text = self._card(
            "Availability",
            "Tick the days students can collect this item and choose the pickup hours. "
            "You can change this at any time.")
        self.availability_editor = OwnerAvailabilityEditor()
        self.availability_editor.changed.connect(self._on_availability_edited)
        box.addWidget(self.availability_editor)
        box.addSpacing(4)
        box.addWidget(_label("Longest loan (days)", "ownerFieldLabel", wrap=False))
        self.days_input = QSpinBox()
        self.days_input.setObjectName("ownerSpin")
        self.days_input.setRange(min_days, max_days)
        self.days_input.setValue(min(3, max_days))
        self.days_input.setSuffix(" days")
        self.days_input.setFixedWidth(140)
        box.addWidget(self.days_input, alignment=Qt.AlignLeft)
        self.body.addWidget(card)

        card, box, _text = self._card(
            "Borrowing rules", "Add any extra rules students agree to when they borrow this item.")
        box.addWidget(_label("Additional rules (optional)", "ownerFieldLabel", wrap=False))
        self.rules_input = QPlainTextEdit()
        self.rules_input.setObjectName("ownerTextBox")
        self.rules_input.setPlaceholderText("For example: return with the cover and batteries.")
        self.rules_input.setFixedHeight(84)
        self.rules_input.setTabChangesFocus(True)
        box.addWidget(self.rules_input)
        self.body.addWidget(card)

        self.message = _label("", "ownerFormError")
        self.message.hide()
        self.body.addWidget(self.message)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.save_button = QPushButton("Save Draft")
        self.save_button.setObjectName("ownerPrimaryButton")
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.clicked.connect(self._on_save)
        buttons.addWidget(self.save_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("ownerGhostButton")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.clicked.connect(self.back_requested.emit)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        self.body.addLayout(buttons)
        self.body.addStretch()

    # ---------- public ----------
    @property
    def listing_id(self):
        return self._listing_id

    @property
    def is_editing(self) -> bool:
        return self._listing_id is not None

    @property
    def is_published(self) -> bool:
        return self.is_editing and self._listing_status in ("Published", "Paused")

    def start_new(self):
        """An empty form for a new listing."""
        self._listing_id = None
        self._listing_status = "Draft"
        self.title_label.setText("Add Listing")
        self.subtitle_label.setText(
            "Describe the item you want to lend. It is saved as a private draft.")
        self.save_button.setText("Save Draft")
        self.title_input.clear()
        self.category_combo.setCurrentIndex(0)
        self.refresh_categories(select="", select_sub="")
        self.condition_combo.setCurrentIndex(0)
        self.description_input.clear()
        self.stock_input.setValue(1)
        self.days_input.setValue(min(3, self.days_input.maximum()))
        self.rules_input.clear()
        self.availability_editor.set_schedule(AvailabilitySchedule.empty())
        self._availability_known = True
        self._staged = []
        self._staged_primary = None
        self.photos.set_photos([])
        self._original_photos = []
        self._editing_photos = []
        self.photos.set_note("")
        self.photos.set_hint(
            f"Add up to {MAX_PHOTOS} photos (JPG, PNG or WEBP). The primary photo is shown "
            "first. Photos are saved when you save the draft.")
        self.show_error("")
        self.verticalScrollBar().setValue(0)
        self._dirty_baseline = self._snapshot()

    def load(self, listing, photos=(), schedule=None):
        """Fill the form with a saved draft so it can be edited.

        photos: (photo key, file path, is_primary) of its saved photos; schedule: its saved
        availability (an AvailabilitySchedule or a dict)."""
        self.start_new()
        self._listing_id = listing.listing_id
        self.photos.set_hint(
            f"Add up to {MAX_PHOTOS} photos (JPG, PNG or WEBP). The primary photo is shown "
            "first. Photo changes are saved with the draft.")
        self.photos.set_photos(photos)
        self._original_photos = [tuple(item) for item in photos]
        self._editing_photos = [tuple(item) for item in photos]
        if schedule is not None:
            self.availability_editor.set_schedule(schedule)
        else:   # the saved schedule could not be read: do not overwrite it unless it is edited
            self._availability_known = False
        self._listing_status = listing.status
        self.title_label.setText(
            "Edit Published Listing" if self.is_published else "Edit Draft")
        self.subtitle_label.setText(
            "Update the details borrowers see. Saving will keep this listing published."
            if self._listing_status == "Published" else
            "Update this paused listing. Saving will keep it hidden until you resume it."
            if self._listing_status == "Paused" else
            "Describe the item you want to lend. It is saved as a private draft.")
        self.save_button.setText("Save Changes")
        self.title_input.setText(listing.title)
        index = self.category_combo.findText(listing.category)
        self.category_combo.setCurrentIndex(max(index, 0))
        self._reload_subcategories(select=getattr(listing, "subcategory", "") or "")
        index = self.condition_combo.findText(listing.condition)
        self.condition_combo.setCurrentIndex(max(index, 0))
        self.description_input.setPlainText(listing.description)
        self.stock_input.setValue(listing.stock_quantity)
        self.days_input.setValue(listing.max_borrow_days)
        self.rules_input.setPlainText(listing.extra_rules)
        self._dirty_baseline = self._snapshot()

    def fields(self) -> dict:
        category = self.category_combo.currentIndex()
        condition = self.condition_combo.currentIndex()
        return {
            "title": self.title_input.text(),
            "category": self.category_combo.currentText() if category > 0 else "",
            "subcategory": (self.subcategory_combo.currentText()
                            if self.subcategory_combo.currentIndex() > 0 else ""),
            "condition": self.condition_combo.currentText() if condition > 0 else "",
            "description": self.description_input.toPlainText(),
            "stock_quantity": self.stock_input.value(),
            "max_borrow_days": self.days_input.value(),
            "extra_rules": self.rules_input.toPlainText(),
        }

    @property
    def has_unsaved_changes(self) -> bool:
        return self._dirty_baseline is not None and self._snapshot() != self._dirty_baseline

    def _snapshot(self):
        photo_state = self._editing_photos if self.is_editing else [
            (path, path, path == self._staged_primary) for path in self._staged]
        availability = self.availability()
        return (
            tuple(sorted(self.fields().items())),
            None if availability is None else tuple(sorted(availability.items())),
            tuple((key, path, bool(primary)) for key, path, primary in photo_state),
        )

    def mark_saved(self):
        self._dirty_baseline = self._snapshot()

    def adopt_created_listing(self, listing):
        """Keep an Add form tied to the draft if a later staged photo write fails."""
        self._listing_id = listing.listing_id
        self.title_label.setText("Edit Draft")
        self.save_button.setText("Save Changes")
        self._original_photos = []
        self._editing_photos = [
            (path, path, path == self._staged_primary) for path in self._staged]
        self.photos.set_photos(self._editing_photos)
        saved_snapshot = list(self._snapshot())
        saved_snapshot[2] = ()
        self._dirty_baseline = tuple(saved_snapshot)

    def mark_fields_saved(self):
        """Update the baseline for fields persisted before pending photo operations."""
        if self._dirty_baseline is None:
            self._dirty_baseline = self._snapshot()
            return
        baseline = list(self._dirty_baseline)
        current = self._snapshot()
        baseline[0] = current[0]
        baseline[1] = current[1]
        self._dirty_baseline = tuple(baseline)

    def _sync_photo_baseline(self):
        if self._dirty_baseline is not None:
            baseline = list(self._dirty_baseline)
            baseline[2] = tuple(
                (key, path, bool(primary))
                for key, path, primary in self._original_photos)
            self._dirty_baseline = tuple(baseline)

    def photo_change_plan(self):
        """Pending saved-listing photo operations, still unapplied to storage."""
        current_keys = {photo[0] for photo in self._editing_photos}
        removed = [photo[0] for photo in self._original_photos
                   if photo[0] not in current_keys]
        primary = next((photo[0] for photo in self._editing_photos if photo[2]), None)
        return {"add": self.staged_photos(), "remove": removed, "primary": primary}

    def photo_added_committed(self, source_path, photo):
        existing = next((item for item in self._editing_photos
                         if item[0] == source_path), None)
        if existing is None:
            return
        replacement = (photo.photo_id, photo.path, existing[2])
        self._editing_photos = [replacement if item[0] == source_path else item
                                for item in self._editing_photos]
        self._original_photos.append((photo.photo_id, photo.path, photo.is_primary))
        self._staged = [path for path in self._staged if path != source_path]
        if self._staged_primary == source_path:
            self._staged_primary = photo.photo_id
        self.photos.set_photos(self._editing_photos)
        self._sync_photo_baseline()

    def photo_removed_committed(self, photo_id):
        self._original_photos = [item for item in self._original_photos if item[0] != photo_id]
        self._editing_photos = [item for item in self._editing_photos if item[0] != photo_id]
        self.photos.set_photos(self._editing_photos)
        self._sync_photo_baseline()

    def photo_primary_committed(self, photo_id):
        self._original_photos = [
            (key, path, key == photo_id) for key, path, _primary in self._original_photos]
        self._editing_photos = [
            (key, path, key == photo_id) for key, path, _primary in self._editing_photos]
        self.photos.set_photos(self._editing_photos)
        self._sync_photo_baseline()

    def discard_photo_changes(self):
        if self.is_editing:
            self._staged = []
            self._staged_primary = None
            self._editing_photos = [tuple(item) for item in self._original_photos]
            self.photos.set_photos(self._editing_photos)
        else:
            self._staged = []
            self._staged_primary = None
            self.photos.set_photos([])

    # ---------- Step 31D: shared categories ----------
    def refresh_categories(self, select=None, select_sub=None):
        """Re-read the shared category list (other owners may have added some).

        The current choice is kept unless `select` / `select_sub` say otherwise."""
        if self._category_source is None:
            return
        keep = (select if select is not None else
                (self.category_combo.currentText() if self.category_combo.currentIndex() > 0 else ""))
        try:
            names = list(self._category_source.top_names())
        except Exception:
            return   # keep what is shown rather than break the form
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem(CATEGORY_PLACEHOLDER)
        self.category_combo.addItems(names)
        self.category_combo.setCurrentIndex(max(self.category_combo.findText(keep), 0) if keep else 0)
        self.category_combo.blockSignals(False)
        self._reload_subcategories(select=select_sub)

    def _reload_subcategories(self, select=None):
        """Fill the subcategory list for the chosen category (kept unless `select` is given)."""
        if self._category_source is None:
            return
        category = (self.category_combo.currentText()
                    if self.category_combo.currentIndex() > 0 else "")
        keep = (select if select is not None else
                (self.subcategory_combo.currentText()
                 if self.subcategory_combo.currentIndex() > 0 else ""))
        try:
            names = list(self._category_source.sub_names(category)) if category else []
        except Exception:
            names = []
        self.subcategory_combo.blockSignals(True)
        self.subcategory_combo.clear()
        self.subcategory_combo.addItem(SUBCATEGORY_PLACEHOLDER)
        self.subcategory_combo.addItems(names)
        self.subcategory_combo.setCurrentIndex(
            max(self.subcategory_combo.findText(keep), 0) if keep else 0)
        self.subcategory_combo.blockSignals(False)
        self.subcategory_combo.setEnabled(bool(category))
        self.new_subcategory_button.setEnabled(bool(category))

    def _new_subcategory(self):
        if self.category_combo.currentIndex() > 0:
            self._open_category_dialog(self.category_combo.currentText())

    def _open_category_dialog(self, parent_name):
        """New general category (parent_name None) or a subcategory of `parent_name`."""
        if self._category_source is None:
            return
        from app.owner_category_dialog import NewCategoryDialog
        dialog = NewCategoryDialog(self._category_source, parent_name, self)
        self._run_dialog(dialog)
        name = dialog.result_name
        if not name:
            return   # cancelled
        if parent_name is None:
            self.refresh_categories(select=name, select_sub="")
        else:
            self.refresh_categories(select=parent_name, select_sub=name)

    def _run_dialog(self, dialog):
        return dialog.exec()

    def availability(self):
        """The chosen pickup days and hours: {weekday: [(start_minute, end_minute)]}.
        None means "leave the saved schedule alone" (it could not be loaded and was not edited)."""
        return self.availability_editor.schedule() if self._availability_known else None

    def _on_availability_edited(self):
        self._availability_known = True

    def staged_photos(self) -> list:
        """Photo files picked for a NEW listing, primary first (saved after the draft is)."""
        ordered = [p for p in self._staged if p == self._staged_primary]
        return ordered + [p for p in self._staged if p != self._staged_primary]

    def set_photos(self, photos):
        """Show the saved photos of the listing being edited: (key, path, is_primary)."""
        self.photos.set_photos(photos)

    def show_photo_note(self, text: str, error: bool = False):
        self.photos.set_note(text, error)

    def show_error(self, text: str):
        self.message.setText(text)
        self.message.setVisible(bool(text))

    # ---------- photos: saved listing -> ask the dashboard; new listing -> keep in the form ----------
    def _on_photos_add(self, paths):
        problems = []
        for raw in paths:
            path = str(raw)
            name = path.replace("\\", "/").rsplit("/", 1)[-1]
            if not path.lower().endswith(PHOTO_EXTENSIONS):
                problems.append(f"{name}: use JPG, PNG or WEBP.")
            elif path in self._staged:
                continue
            elif self.photos.count >= MAX_PHOTOS:
                problems.append(f"A listing can have at most {MAX_PHOTOS} photos.")
                break
            elif QPixmap(path).isNull():
                problems.append(f"{name}: that file is not a readable picture.")
            else:
                self._staged.append(path)
                if self.is_editing:
                    key = path
                    primary = not self._editing_photos
                    self._editing_photos.append((key, path, primary))
                    if primary:
                        self._staged_primary = key
        if self._staged_primary not in self._staged:
            self._staged_primary = self._staged[0] if self._staged and not self.is_editing else None
        self._show_staged()
        self.photos.set_note(" ".join(problems), error=bool(problems))

    def _on_photo_remove(self, key):
        if self.is_editing:
            self._editing_photos = [photo for photo in self._editing_photos if photo[0] != key]
            self._staged = [path for path in self._staged if path != key]
            if self._staged_primary == key:
                self._staged_primary = None
            if not any(photo[2] for photo in self._editing_photos) and self._editing_photos:
                first = self._editing_photos[0]
                self._editing_photos[0] = (first[0], first[1], True)
            self._show_staged()
            self.photos.set_note("")
            return
        if key in self._staged:
            self._staged.remove(key)
        if self._staged_primary not in self._staged:
            self._staged_primary = self._staged[0] if self._staged else None
        self._show_staged()
        self.photos.set_note("")

    def _on_photo_primary(self, key):
        if self.is_editing:
            self._editing_photos = [
                (photo_key, path, photo_key == key)
                for photo_key, path, _primary in self._editing_photos]
            self._staged_primary = key
            self._show_staged()
            self.photos.set_note("")
        elif key in self._staged:
            self._staged_primary = key
            self._show_staged()
            self.photos.set_note("")

    def _show_staged(self):
        if self.is_editing:
            self.photos.set_photos(self._editing_photos)
        else:
            self.photos.set_photos([(p, p, p == self._staged_primary) for p in self._staged])

    def set_saving_enabled(self, enabled: bool):
        self.save_button.setEnabled(enabled)

    def _on_save(self):
        self.show_error("")
        self.save_requested.emit(self.fields(), self._listing_id)
