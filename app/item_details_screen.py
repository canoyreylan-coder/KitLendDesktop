"""KitLend Item Details page and Report Listing dialog (Step 19).

The page only SHOWS what the CatalogItem really has (title, creator, kind, category,
owner, pickup place, copies, collections) plus recorded Student Owner fields when present.
Missing condition or photos are shown as "Not recorded" / a placeholder - nothing is invented.

It owns no state beyond the item on screen: Request Now, Save to My List and Report
Listing are only SIGNALS, handled by the Dashboard with the existing borrowing, My List
and report services.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QButtonGroup,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.catalog_screen import (
    KIND_ICONS,
    CatalogItem,
    ItemImageSlot,
    StatusTag,
    _cover_tone,
)
from app.catalog_theme import ITEM_DETAILS_STYLESHEET
from app.dashboard_widgets import ElidedLabel, ReflowGrid
from app.my_list_screen import approver_text, get_max_borrow_days, get_pickup_availability, plural
from app.report_service import (
    MAX_DESCRIPTION_LENGTH,
    REASON_OTHER,
    REPORT_REASONS,
    ReportError,
    validate_report,
)
from app.photo_service import MAX_PHOTOS

MAIN_PHOTO_SIZE = (260, 200)   # compact main image
THUMB_SIZE = 44
NOT_RECORDED = "Not recorded"
CONTENT_MAX_WIDTH = 1080
REASON_PLACEHOLDER = "Select a reason..."


def make_flag_icon(color: str = "#FF8FA3", size: int = 16) -> QIcon:
    """A small flag drawn with Qt (no image file, no emoji font needed)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(3.5, 2), QPointF(3.5, size - 2))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawPolygon(QPolygonF([QPointF(4.5, 2.5), QPointF(size - 2.5, 5.0),
                                   QPointF(4.5, 8.5)]))
    painter.end()
    return QIcon(pixmap)


def _label(text: str, name: str, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    return label


def item_facts(item: CatalogItem) -> dict:
    """The rows shown on the page, as plain text (also used by the tests).

    Returns {section title: [(label, value), ...]}. Only real data or "Not recorded".
    """
    condition = (getattr(item, "condition", "") or "").strip()
    category = getattr(item, "category_label", item.category)
    copies_ok = (isinstance(item.copies_total, int) and isinstance(item.copies_available, int)
                 and not isinstance(item.copies_available, bool) and item.copies_available >= 0)
    pickup = get_pickup_availability(item)
    student_owned = item.ownership == "student"
    about = [
        ("Type", item.kind),
        ("Category", category),
        ("Condition", condition or NOT_RECORDED),
        ("Collections", ", ".join(item.collections) if item.collections else "None"),
    ]
    owner = [
        ("Ownership", item.ownership_label),
        ("Owner" if student_owned else "Held by",
         item.owner_note.removeprefix("Shared by ") if student_owned else item.owner_note),
    ]
    if not student_owned:
        owner.append(("Pickup location", item.owner_note))
    owner.append(("Pickup hours", pickup.schedule_text[:1].upper() + pickup.schedule_text[1:]))
    availability = [("Status", item.availability_text)]
    if copies_ok:
        availability.append(("Copies available", f"{item.copies_available} of {item.copies_total}"))
    else:
        availability.append(("Copies available", NOT_RECORDED))
    rules = [
        ("Maximum loan", plural(get_max_borrow_days(item), "day")),
        ("Approval", approver_text(item)),
        ("Borrowing starts", "When the handover at pickup is confirmed"),
        ("Unavailable items", "Cannot be requested, but can be saved to My List"),
    ]
    facts = {
        "About this item": about,
        "Owner and pickup": owner,
        "Availability": availability,
        "Borrowing rules": rules,
    }
    description = (getattr(item, "description", "") or "").strip()
    extra_rules = (getattr(item, "extra_rules", "") or "").strip()
    if description:
        facts["Description"] = [("Details", description)]
    if extra_rules:
        facts["Owner's borrowing rules"] = [("Rules", extra_rules)]
    return facts


class _ThumbButton(QPushButton):
    """A small square picture button; the checked one gets a highlighted border."""

    def __init__(self, pixmap: QPixmap, tone: str, parent=None):
        super().__init__(parent)
        self.setObjectName("detThumb")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(THUMB_SIZE, THUMB_SIZE)
        self._pixmap = pixmap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        scaled = self._pixmap.scaled(int(rect.width()), int(rect.height()),
                                     Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 8, 8)
        painter.save()
        painter.setClipPath(clip)
        painter.drawPixmap(int(rect.x() + (rect.width() - scaled.width()) / 2),
                           int(rect.y() + (rect.height() - scaled.height()) / 2), scaled)
        if not self.isChecked():  # dim the thumbnails that are not shown
            painter.fillRect(rect, QColor(20, 23, 42, 90))
        painter.restore()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#8B8FFF" if self.isChecked() else "#343A5C"),
                            2 if self.isChecked() else 1))
        painter.drawRoundedRect(rect, 8, 8)
        if self.hasFocus():
            painter.setPen(QPen(QColor("#8B8FFF"), 1, Qt.DotLine))
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 6, 6)


class _ClickableItemImageSlot(ItemImageSlot):
    clicked = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("View full photo")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ItemDetailsScreen(QWidget):
    back_requested = Signal()
    request_clicked = Signal(object)           # Request Now (available items only)
    bookmark_toggled = Signal(object, bool)    # Save to My List star
    report_requested = Signal(object)          # Report Listing pressed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("itemDetailsScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(ITEM_DETAILS_STYLESHEET)
        self._item = None
        self._reported = False
        self._photo_paths = []
        self._photo_pixmaps = []
        self._photo_index = 0
        self.thumb_buttons = []
        self._image_scale = 1.0
        self._viewer_pixmap = QPixmap()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 0)
        root.setSpacing(12)

        top = QHBoxLayout()
        self.back_button = QPushButton("←  Back to Catalog")
        self.back_button.setObjectName("detBackButton")
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.clicked.connect(self.back_requested.emit)
        top.addWidget(self.back_button)
        top.addStretch()
        self.menu_button = QToolButton()
        self.menu_button.setObjectName("detMenuButton")
        self.menu_button.setText("⋮")
        self.menu_button.setToolTip("More actions")
        self.menu_button.setCursor(Qt.PointingHandCursor)
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        self.menu_button.setAccessibleName("More actions")
        self.menu = QMenu(self.menu_button)
        self.menu.setObjectName("detMenu")
        self.report_action = QAction(make_flag_icon(), "Report Listing", self.menu)
        self.report_action.triggered.connect(self._on_report_clicked)
        self.menu.addAction(self.report_action)
        self.menu_button.setMenu(self.menu)
        self.menu_button.setEnabled(False)   # nothing to act on until an item is shown
        top.addWidget(self.menu_button)
        root.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("detScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)
        self._content = None
        self.image_viewer = self._build_image_viewer()
        self.image_viewer.hide()

    # ---------- public ----------
    @property
    def item(self):
        return self._item

    @property
    def is_reported(self) -> bool:
        return self._reported

    def show_item(self, item: CatalogItem, bookmarked: bool = False, reported: bool = False,
                  photos=()):
        """Build the page for ONE item (the old content is thrown away)."""
        self._item = item
        self._reported = reported
        self._refresh_report_button()
        content = QWidget()
        content.setObjectName("detContent")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 6, 24)
        outer.setSpacing(16)
        column = QWidget()
        column.setMaximumWidth(CONTENT_MAX_WIDTH)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        outer.addWidget(column, 1, Qt.AlignTop)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_column = QVBoxLayout()
        title_column.setSpacing(4)
        title_column.addWidget(_label(item.title, "detTitle"))
        title_column.addWidget(_label(f"{item.kind} · {item.category}", "detCreator"))
        title_row.addLayout(title_column, 1)
        title_row.addWidget(StatusTag(item.ownership_label, item.ownership), 0, Qt.AlignTop)
        title_row.addWidget(StatusTag(item.availability_text, item.availability_tone),
                            0, Qt.AlignTop)
        header_layout.addLayout(title_row)
        header_layout.addLayout(self._build_borrower_actions(item, bookmarked))
        layout.addWidget(header, 0, Qt.AlignTop)

        gallery = self._build_gallery(item, photos)
        information = self._build_information(item)
        grid = ReflowGrid(
            [gallery, information], min_item_width=320, spacing=16)
        grid.setObjectName("detAdaptiveGrid")
        grid.layout().setAlignment(gallery, Qt.AlignTop)
        grid.layout().setAlignment(information, Qt.AlignTop)
        self.gallery_widget = gallery
        self.information_widget = information
        self.content_grid = grid
        layout.addWidget(grid, 0, Qt.AlignTop)

        facts = item_facts(item)
        description = (getattr(item, "description", "") or "").strip()
        self.description_section = self._build_text_section(
            "Description", description or NOT_RECORDED)
        layout.addWidget(self.description_section, 0, Qt.AlignTop)

        borrowing_rules = facts.pop("Borrowing rules", [])
        extra_rules = (getattr(item, "extra_rules", "") or "").strip()
        if extra_rules:
            borrowing_rules.append(("Owner's rules", extra_rules))
        self.borrowing_rules_section = self._build_section(
            "Borrowing Rules", borrowing_rules)
        layout.addWidget(self.borrowing_rules_section, 0, Qt.AlignTop)

        availability = facts.pop("Availability", [])
        availability.append(("Pickup availability", get_pickup_availability(item).schedule_text))
        self.availability_section = self._build_section("Availability", availability)
        layout.addWidget(self.availability_section, 0, Qt.AlignTop)

        old = self.scroll.takeWidget()
        self.scroll.setWidget(content)
        if old is not None:
            old.deleteLater()
        self._content = content
        self.scroll.verticalScrollBar().setValue(0)

    def clear(self):
        """Forget the item (used on logout so nothing is left on screen)."""
        self._item = None
        self._reported = False
        self._photo_paths = []
        self._photo_pixmaps = []
        self._photo_index = 0
        self._viewer_pixmap = QPixmap()
        self.image_viewer.hide()
        self._refresh_report_button()
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self._content = None

    def set_bookmarked(self, bookmarked: bool):
        """Sync the Save button WITHOUT sending a signal."""
        button = getattr(self, "save_button", None)
        if button is None or self._item is None:
            return
        button.blockSignals(True)
        button.setChecked(bookmarked)
        button.blockSignals(False)
        self._refresh_save_look(bookmarked)

    def set_reported(self, reported: bool):
        self._reported = reported
        self._refresh_report_button()

    # ---------- building ----------
    def _build_borrower_actions(self, item: CatalogItem, bookmarked: bool):
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.request_button = QPushButton("Request to Borrow")
        self.request_button.setObjectName("catRequestButton")
        self.request_button.setFixedHeight(36)
        self.request_button.setMinimumWidth(150)
        if item.is_available and item.request_enabled:
            self.request_button.setCursor(Qt.PointingHandCursor)
            self.request_button.setToolTip("Request to borrow this item")
            self.request_button.clicked.connect(self._on_request_clicked)
        else:
            self.request_button.setEnabled(False)
            self.request_button.setToolTip(
                item.request_disabled_reason or
                "Currently unavailable - you can still save it to My List")
        actions.addWidget(self.request_button)
        self.save_button = QPushButton()
        self.save_button.setObjectName("detSaveButton")
        self.save_button.setCheckable(True)
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.setChecked(bookmarked)
        self.save_button.toggled.connect(self._on_save_toggled)
        self._refresh_save_look(bookmarked)
        actions.addWidget(self.save_button)
        actions.addStretch()
        return actions

    def _build_information(self, item: CatalogItem) -> QFrame:
        facts = item_facts(item)
        details = facts.pop("About this item", [])
        details.extend(facts.pop("Owner and pickup", []))
        return self._build_section("Item Details", details)

    def _build_text_section(self, title, text):
        frame = QFrame()
        frame.setObjectName("detSection")
        section_layout = QVBoxLayout(frame)
        section_layout.setContentsMargins(18, 14, 18, 16)
        section_layout.setSpacing(6)
        section_layout.addWidget(_label(title, "detSectionTitle"))
        section_layout.addWidget(_label(text, "detValueMuted" if text == NOT_RECORDED else "detValue"))
        return frame

    # ---------- Step 21: compact photo gallery ----------
    @property
    def photo_paths(self) -> list:
        """The photos that are really shown (unreadable files already dropped)."""
        return list(self._photo_paths)

    @property
    def main_photo_path(self):
        return self._photo_paths[self._photo_index] if self._photo_paths else None

    def _build_gallery(self, item: CatalogItem, photos) -> QWidget:
        """One main image, plus small clickable thumbnails underneath when there are 2+ photos.
        Clicking a thumbnail swaps the main image in place (no new window)."""
        # Keep only files Qt can really read; a missing/damaged file never shows up.
        loaded = []
        for path in list(photos or ())[:MAX_PHOTOS]:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                loaded.append((str(path), pixmap))
        self._photo_paths = [path for path, _ in loaded]
        self._photo_index = 0

        box = QFrame()
        box.setObjectName("detGallery")
        box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
        column = QVBoxLayout(box)
        column.setContentsMargins(12, 12, 12, 12)
        column.setSpacing(8)

        self.image_slot = _ClickableItemImageSlot(
            KIND_ICONS.get(item.kind, "📦"),
            "No photos yet" if not loaded else "",
            _cover_tone(item))
        self.image_slot.setFixedSize(*MAIN_PHOTO_SIZE)
        self.image_slot.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.image_slot.clicked.connect(lambda: self.show_full_image(self._photo_index))
        if loaded:
            self.image_slot.set_photo(loaded[0][1])
        column.addWidget(self.image_slot)

        self.thumb_buttons = []
        self.thumb_group = QButtonGroup(box)
        self.thumb_group.setExclusive(True)
        if len(loaded) > 1:
            strip = QHBoxLayout()
            strip.setContentsMargins(0, 0, 0, 0)
            strip.setSpacing(6)
            for index, (path, pixmap) in enumerate(loaded):
                button = _ThumbButton(pixmap, _cover_tone(item))
                button.setToolTip("Primary photo" if index == 0 else f"Photo {index + 1}")
                button.setChecked(index == 0)
                button.clicked.connect(lambda _c=False, i=index: self.show_full_image(i))
                self.thumb_group.addButton(button, index)
                self.thumb_buttons.append(button)
                strip.addWidget(button)
            strip.addStretch()
            column.addLayout(strip)
        self._photo_pixmaps = [pixmap for _, pixmap in loaded]
        return box

    def select_photo(self, index: int):
        """Show photo `index` as the main image (used by the thumbnails)."""
        if not 0 <= index < len(self._photo_pixmaps):
            return
        self._photo_index = index
        self.image_slot.set_photo(self._photo_pixmaps[index])
        for i, button in enumerate(self.thumb_buttons):
            button.setChecked(i == index)

    def _build_image_viewer(self):
        viewer = QFrame(self)
        viewer.setObjectName("detImageViewer")
        layout = QVBoxLayout(viewer)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(_label("Photo viewer", "detSectionTitle"))
        header.addStretch()
        self.viewer_close_button = QPushButton("Close")
        self.viewer_close_button.setObjectName("detViewerAction")
        self.viewer_close_button.clicked.connect(viewer.hide)
        header.addWidget(self.viewer_close_button)
        layout.addLayout(header)
        self.viewer_scroll = QScrollArea()
        self.viewer_scroll.setObjectName("detViewerScroll")
        self.viewer_scroll.setWidgetResizable(False)
        self.viewer_scroll.setAlignment(Qt.AlignCenter)
        self.viewer_scroll.setFrameShape(QFrame.NoFrame)
        self.viewer_scroll.viewport().setAutoFillBackground(False)
        self.viewer_image = QLabel()
        self.viewer_image.setObjectName("detViewerImage")
        self.viewer_image.setAlignment(Qt.AlignCenter)
        self.viewer_scroll.setWidget(self.viewer_image)
        layout.addWidget(self.viewer_scroll, 1)
        actions = QHBoxLayout()
        actions.addStretch()
        for text, callback in (
                ("Zoom Out", self._zoom_out), ("Fit / Reset", self._fit_image),
                ("Zoom In", self._zoom_in)):
            button = QPushButton(text)
            button.setObjectName("detViewerAction")
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
            self._image_scale = min(
                available.width() / self._viewer_pixmap.width(),
                available.height() / self._viewer_pixmap.height(), 1.0)
        width = max(1, round(self._viewer_pixmap.width() * self._image_scale))
        height = max(1, round(self._viewer_pixmap.height() * self._image_scale))
        self.viewer_image.setPixmap(self._viewer_pixmap.scaled(
            width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.viewer_image.resize(width, height)

    def show_full_image(self, index):
        if not 0 <= index < len(self._photo_pixmaps):
            return
        self.select_photo(index)
        pixmap = self._photo_pixmaps[index]
        self._viewer_pixmap = pixmap
        self._image_scale = 1.0
        self.image_viewer.setGeometry(self.rect())
        self.image_viewer.show()
        self.image_viewer.raise_()
        self._render_viewer_image(fit=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.image_viewer.setGeometry(self.rect())
        if self.image_viewer.isVisible():
            self._render_viewer_image(fit=True)

    def _build_section(self, title: str, rows) -> QFrame:
        frame = QFrame()
        frame.setObjectName("detSection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(6)
        layout.addWidget(_label(title, "detSectionTitle"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(5)
        grid.setColumnMinimumWidth(0, 130)
        grid.setColumnStretch(1, 1)
        for index, (key, value) in enumerate(rows):
            grid.addWidget(_label(key, "detKey"), index, 0, Qt.AlignTop)
            grid.addWidget(_label(value, "detValueMuted" if value == NOT_RECORDED else "detValue"),
                           index, 1, Qt.AlignTop)
        layout.addLayout(grid)
        return frame

    # ---------- handlers ----------
    def _on_request_clicked(self, _checked=False):
        if (self._item is not None and self._item.is_available
                and self._item.request_enabled):
            self.request_clicked.emit(self._item)

    def _on_save_toggled(self, checked: bool):
        self._refresh_save_look(checked)
        if self._item is not None:
            self.bookmark_toggled.emit(self._item, checked)

    def _refresh_save_look(self, bookmarked: bool):
        self.save_button.setText("★  Saved to My List" if bookmarked else "☆  Save to My List")
        self.save_button.setToolTip(
            "Saved to My List - click to remove" if bookmarked else "Save to My List")

    def _on_report_clicked(self, _checked=False):
        if self._item is not None and not self._reported:
            self.report_requested.emit(self._item)

    def _refresh_report_button(self):
        self.menu_button.setEnabled(self._item is not None)
        self.report_action.setEnabled(not self._reported)
        self.report_action.setText("Listing Reported" if self._reported else "Report Listing")


class ReportListingDialog(QDialog):
    """Reason + optional description (required for Other). Saves through `submit_handler`.

    submit_handler(reason, description) must raise ReportError (message safe to show) when
    the report cannot be saved. Without a handler the dialog only validates.
    """

    def __init__(self, item: CatalogItem, parent=None, submit_handler=None):
        super().__init__(parent)
        self.setObjectName("detReportDialog")
        self.setWindowTitle("Report Listing")
        self.setModal(True)
        self.setFixedWidth(400)
        self.setStyleSheet(ITEM_DETAILS_STYLESHEET)
        self.item = item
        self._submit_handler = submit_handler
        self.submitted = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(6)
        layout.addWidget(_label("Report Listing", "detDialogTitle", wrap=False))
        subtitle = ElidedLabel(item.title)
        subtitle.setObjectName("detCreator")
        layout.addWidget(subtitle)
        layout.addSpacing(6)

        layout.addWidget(_label("Reason", "detKey", wrap=False))
        self.reason_combo = QComboBox()
        self.reason_combo.setObjectName("detReasonCombo")
        self.reason_combo.addItem(REASON_PLACEHOLDER)
        self.reason_combo.addItems(REPORT_REASONS)
        self.reason_combo.currentIndexChanged.connect(self._on_reason_changed)
        layout.addWidget(self.reason_combo)

        self.description_caption = _label("Description (optional)", "detKey", wrap=False)
        layout.addWidget(self.description_caption)
        self.description_edit = QPlainTextEdit()
        self.description_edit.setObjectName("detDescription")
        self.description_edit.setPlaceholderText("What is wrong with this listing?")
        self.description_edit.setFixedHeight(84)
        self.description_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.description_edit)
        self.counter_label = _label("", "detHint", wrap=False)
        self.counter_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.counter_label)

        self.error_label = _label("", "detError")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("detCancelButton")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.submit_button = QPushButton("Submit Report")
        self.submit_button.setObjectName("detReportButton")
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self.submit)
        buttons.addWidget(self.submit_button)
        layout.addLayout(buttons)
        self._update_counter()
        self.adjustSize()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:  # centre over the window it belongs to
            top = parent.window()
            center = top.mapToGlobal(top.rect().center())
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

    # ---------- state ----------
    @property
    def reason(self) -> str:
        return "" if self.reason_combo.currentIndex() <= 0 else self.reason_combo.currentText()

    @property
    def description(self) -> str:
        return self.description_edit.toPlainText().strip()

    def _on_reason_changed(self, _index=0):
        other = self.reason == REASON_OTHER
        self.description_caption.setText(
            "Description (required for Other)" if other else "Description (optional)")
        self._clear_error()

    def _on_text_changed(self):
        text = self.description_edit.toPlainText()
        if len(text) > MAX_DESCRIPTION_LENGTH:  # hard limit while typing
            self.description_edit.blockSignals(True)
            self.description_edit.setPlainText(text[:MAX_DESCRIPTION_LENGTH])
            self.description_edit.moveCursor(QTextCursor.MoveOperation.End)
            self.description_edit.blockSignals(False)
        self._update_counter()
        self._clear_error()

    def _update_counter(self):
        self.counter_label.setText(
            f"{len(self.description_edit.toPlainText())} / {MAX_DESCRIPTION_LENGTH}")

    def _clear_error(self):
        self.error_label.hide()
        self.error_label.setText("")

    def _show_error(self, message: str):
        self.error_label.setText(message)
        self.error_label.show()

    # ---------- submit ----------
    def submit(self):
        """Validate, save through the handler, then close. Errors stay in the dialog."""
        try:
            reason, description = validate_report(self.reason, self.description)
            if self._submit_handler is not None:
                self._submit_handler(reason, description)
        except ReportError as exc:
            self._show_error(str(exc))
            return False
        except Exception:
            self._show_error("Something went wrong. Your report was not sent.")
            return False
        self.submitted = True
        self.accept()
        return True
