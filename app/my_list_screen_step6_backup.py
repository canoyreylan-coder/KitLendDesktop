"""KitLend My List screen (UI only - sample data, no database, no real requests).

What this file contains, from top to bottom:
  1. SAMPLE DATA    - a few saved items, picked from the Catalog's own sample items
  2. SMALL HELPERS  - who approves an item, plus the little icon badge
  3. ROW WIDGETS    - one saved-item row, one row of the confirmation preview
  4. PREVIEW DIALOG - "Review your requests" (shows the selected items, sends nothing)
  5. MY LIST SCREEN - the whole screen that puts everything together
  6. STYLES (QSS)   - only the NEW My List styles; Catalog styles are reused

Future borrowing rule (not built yet, only explained in the preview):
  One batch submission creates SEPARATE borrowing requests. Each item's lender
  or administrator approves it on their own. One rejection does not cancel
  the others.

Ready for Catalog bookmarks later: the Catalog can call `add_item(item)` or
`set_saved_items(items)` on this screen. Nothing here touches a database,
logs anyone in, or opens the dashboard.
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Reuse the Catalog's item model, sample items, pills and styles.
from app.catalog_screen import (
    CATALOG_STYLESHEET,
    CATEGORY_BY_NAME,
    CURIOUS_MASCOT_PATH,
    HAPPY_MASCOT_PATH,
    KIND_ICONS,
    LIGHT_PERIWINKLE,
    SAMPLE_ITEMS,
    SOFT_LAVENDER,
    CatalogItem,
    TagPill,
)
from app.dashboard_widgets import ElidedLabel
from app.theme import CREAM, MINT, NAVY, PERIWINKLE, PINK

UNAVAILABLE_HINT = "Unavailable items can stay in your list, but can't be requested yet."


# ======================================================================
# 1. SAMPLE DATA
# ======================================================================
# Titles of Catalog sample items that start out "saved". A mix of available,
# low-stock and unavailable items, from both school and students.
SAMPLE_SAVED_TITLES = (
    "Introduction to Algorithms (CLRS)",
    "Grokking Algorithms",
    "TI-84 Plus Graphing Calculator",      # unavailable (currently borrowed)
    "Arduino Uno Starter Kit",
    "Clean Code",                          # unavailable (currently borrowed)
    "Digital Multimeter",
)


def sample_saved_items() -> list:
    """Return the sample saved list (real CatalogItem objects from the Catalog)."""
    by_title = {item.title: item for item in SAMPLE_ITEMS}
    return [by_title[title] for title in SAMPLE_SAVED_TITLES if title in by_title]


# ======================================================================
# 2. SMALL HELPERS
# ======================================================================
def lender_name(item: CatalogItem) -> str:
    """'Shared by Ana M.' -> 'Ana M.'"""
    return item.owner_note.removeprefix("Shared by ")


def approver_text(item: CatalogItem) -> str:
    """Who would approve a request for this item (used in the preview)."""
    if item.ownership == "student":
        return f"Approved by lender: {lender_name(item)}"
    return f"Approved by school administrator · Pickup: {item.owner_note}"


def make_icon_badge(item: CatalogItem) -> QLabel:
    """Small colored square with the item's kind icon (stands in for a cover)."""
    category = CATEGORY_BY_NAME.get(item.category)
    color = category.cover_color if category else LIGHT_PERIWINKLE
    badge = QLabel(KIND_ICONS.get(item.kind, "📦"))
    badge.setObjectName("myListIcon")
    badge.setStyleSheet(f"background-color: {color};")  # only the color differs per item
    badge.setAlignment(Qt.AlignCenter)
    badge.setFixedSize(54, 54)
    return badge


# ======================================================================
# 3. ROW WIDGETS
# ======================================================================
class SavedItemRow(QFrame):
    """One saved item: checkbox, icon, title, category, owner, availability, Remove."""

    selection_changed = Signal(object, bool)  # (CatalogItem, is_selected)
    remove_clicked = Signal(object)           # CatalogItem

    def __init__(self, item: CatalogItem, selected: bool = False, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("myListRow")
        self.setProperty("unavailable", not item.is_available)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        # --- selection check (disabled for unavailable items) ---
        self.check = QPushButton("")
        self.check.setObjectName("myListCheck")
        self.check.setCheckable(True)
        self.check.setFixedSize(30, 30)
        self.check.setAccessibleName(f"Select {item.title}")
        if item.is_available:
            self.check.setCursor(Qt.PointingHandCursor)
            self.check.setToolTip("Select this item to request it")
            self.check.toggled.connect(self._on_toggled)
            self.set_checked(selected)
        else:
            self.check.setEnabled(False)
            self.check.setToolTip(UNAVAILABLE_HINT)
        layout.addWidget(self.check, alignment=Qt.AlignVCenter)

        layout.addWidget(make_icon_badge(item), alignment=Qt.AlignVCenter)

        # --- title / category / owner ---
        texts = QVBoxLayout()
        texts.setSpacing(3)

        title = ElidedLabel(item.title)
        title.setObjectName("catalogItemTitle")
        texts.addWidget(title)

        category = CATEGORY_BY_NAME.get(item.category)
        icon = f"{category.icon} " if category else ""
        category_line = ElidedLabel(f"{icon}{item.category} · {item.kind}")
        category_line.setObjectName("catalogItemCreator")
        texts.addWidget(category_line)

        owner_row = QHBoxLayout()
        owner_row.setSpacing(8)
        owner_row.addWidget(TagPill(item.ownership_label, item.ownership))
        note = ElidedLabel(item.owner_note)
        note.setObjectName("catalogItemNote")
        owner_row.addWidget(note, 1)
        texts.addLayout(owner_row)
        layout.addLayout(texts, 1)

        # --- availability + remove ---
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(TagPill(item.availability_text, item.availability_tone),
                        alignment=Qt.AlignRight)
        remove = QPushButton("Remove")
        remove.setObjectName("myListRemoveButton")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setToolTip("Remove from My List")
        remove.clicked.connect(lambda: self.remove_clicked.emit(self.item))
        right.addWidget(remove, alignment=Qt.AlignRight)
        layout.addLayout(right)

    def set_checked(self, checked: bool):
        """Change the check without sending a signal (the screen already knows)."""
        if not self.item.is_available:
            return
        self.check.blockSignals(True)
        self.check.setChecked(checked)
        self.check.setText("✓" if checked else "")
        self.check.blockSignals(False)

    def _on_toggled(self, checked: bool):
        self.check.setText("✓" if checked else "")
        self.selection_changed.emit(self.item, checked)


class PreviewRow(QFrame):
    """One selected item inside the confirmation preview."""

    def __init__(self, item: CatalogItem, parent=None):
        super().__init__(parent)
        self.setObjectName("myListPreviewRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        layout.addWidget(make_icon_badge(item), alignment=Qt.AlignVCenter)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = ElidedLabel(item.title)
        title.setObjectName("catalogItemTitle")
        texts.addWidget(title)
        meta = ElidedLabel(f"{item.category} · {item.ownership_label}")
        meta.setObjectName("catalogItemCreator")
        texts.addWidget(meta)
        approver = ElidedLabel(approver_text(item))
        approver.setObjectName("catalogItemNote")
        texts.addWidget(approver)
        layout.addLayout(texts, 1)


# ======================================================================
# 4. PREVIEW DIALOG
# ======================================================================
class RequestPreviewDialog(QDialog):
    """'Review your requests' - shows the selected items. Submits nothing.

    exec() returns Accepted if the student pressed the confirm button.
    """

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setObjectName("myListDialog")
        self.setWindowTitle("Review your requests")
        self.setModal(True)
        self.resize(580, 600)
        self.setMinimumSize(460, 420)
        self.setStyleSheet(CATALOG_STYLESHEET + MY_LIST_STYLESHEET)

        items = list(items)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        tag = QLabel("Preview only · Nothing is sent yet")
        tag.setObjectName("catalogTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout.addWidget(tag, alignment=Qt.AlignLeft)

        title = QLabel("Review your requests")
        title.setObjectName("myListDialogTitle")
        layout.addWidget(title)

        info = QFrame()
        info.setObjectName("myListInfo")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(14, 10, 14, 10)
        info_text = QLabel(
            "Each item becomes its own separate borrowing request. Each lender "
            "or administrator approves their item independently, so one "
            "rejection won't cancel the others."
        )
        info_text.setObjectName("myListInfoText")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        layout.addWidget(info)

        # The selected items (scrolls if there are many)
        scroll = QScrollArea()
        scroll.setObjectName("catalogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("catalogContent")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 6, 0)
        inner_layout.setSpacing(8)
        for item in items:
            inner_layout.addWidget(PreviewRow(item))
        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        count = len(items)
        summary = QLabel(f"{count} separate request{'s' if count != 1 else ''} would be created")
        summary.setObjectName("myListDialogSummary")
        layout.addWidget(summary)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        back = QPushButton("Back to My List")
        back.setObjectName("myListBackButton")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(self.reject)
        buttons.addWidget(back)
        confirm = QPushButton("Confirm (Preview Only)")
        confirm.setObjectName("catalogPrimaryButton")
        confirm.setCursor(Qt.PointingHandCursor)
        confirm.setDefault(True)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)


# ======================================================================
# 5. MY LIST SCREEN
# ======================================================================
class MyListScreen(QWidget):
    """Saved items with selection, removal and a request-confirmation preview.

    Signals (nothing is connected to them yet):
      browse_catalog_requested   - "Browse Catalog" button in the empty state
      item_removed(item)         - an item was removed from the saved list
      request_preview_confirmed(items) - confirm pressed in the preview.
                                   NO request is created; this is the hook
                                   the real borrowing step will use later.
    """

    browse_catalog_requested = Signal()
    item_removed = Signal(object)
    request_preview_confirmed = Signal(list)

    def __init__(self, saved_items=None, parent=None):
        super().__init__(parent)
        self.setObjectName("myListScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(CATALOG_STYLESHEET + MY_LIST_STYLESHEET)  # only this screen

        self._saved_items = []   # CatalogItem objects, in the order they were saved
        self._selected = set()   # the selected ones (always available items)
        self._rows = {}          # CatalogItem -> SavedItemRow

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(4000)
        self._banner_timer.timeout.connect(lambda: self.banner.hide())

        self._build_ui()
        self.set_saved_items(saved_items if saved_items is not None else [])

    # ---------- public API (for the Catalog / tests) ----------
    @property
    def saved_items(self) -> list:
        return list(self._saved_items)

    @property
    def selected_items(self) -> list:
        """Selected items, in the same order as the list."""
        return [item for item in self._saved_items if item in self._selected]

    def set_saved_items(self, items):
        """Replace the whole saved list (duplicates are ignored)."""
        unique = []
        for item in items:
            if item not in unique:
                unique.append(item)
        self._saved_items = unique
        self._selected = {item for item in self._selected
                          if item in unique and item.is_available}
        self._refresh()

    def add_item(self, item: CatalogItem):
        """Bookmark an item (does nothing if it is already saved)."""
        if item not in self._saved_items:
            self.set_saved_items(self._saved_items + [item])

    def remove_item(self, item: CatalogItem):
        if item in self._saved_items:
            self._selected.discard(item)
            self._saved_items.remove(item)
            self._refresh()
            self.item_removed.emit(item)

    # ---------- building ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Header, toolbar, rows and empty state all scroll together;
        # only the action bar stays fixed at the bottom.
        scroll = QScrollArea()
        scroll.setObjectName("catalogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("catalogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 8)
        layout.setSpacing(14)

        layout.addWidget(self._build_header())

        self.banner = QLabel("")
        self.banner.setObjectName("myListBanner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        layout.addWidget(self.banner)

        self.toolbar = self._build_toolbar()
        layout.addWidget(self.toolbar)

        self.rows_container = QWidget()
        self.rows_container.setObjectName("catalogContent")
        self._rows_layout = QVBoxLayout(self.rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(10)
        layout.addWidget(self.rows_container)

        self.empty_state = self._build_empty_state()
        layout.addWidget(self.empty_state)
        layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.action_bar = self._build_action_bar()
        root.addWidget(self.action_bar)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("catalogHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(26, 18, 26, 18)
        layout.setSpacing(12)

        texts = QVBoxLayout()
        texts.setSpacing(8)
        tag = QLabel("Preview · Sample data only")
        tag.setObjectName("catalogTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        texts.addWidget(tag, alignment=Qt.AlignLeft)

        title = QLabel("My List")
        title.setObjectName("catalogTitle")
        texts.addWidget(title)

        subtitle = QLabel(
            "Items you saved for later. Select the available ones and request "
            "them together."
        )
        subtitle.setObjectName("catalogSubtitle")
        subtitle.setWordWrap(True)
        texts.addWidget(subtitle)
        texts.addStretch()
        layout.addLayout(texts, 1)

        pixmap = QPixmap(str(HAPPY_MASCOT_PATH))
        if not pixmap.isNull():
            mascot = QLabel()
            mascot.setPixmap(pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(mascot, 0, Qt.AlignTop | Qt.AlignRight)
        return header

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("myListToolbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(12)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("myListSummary")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label, 1)

        self.select_all_button = QPushButton("Select all eligible")
        self.select_all_button.setObjectName("myListSelectAll")
        self.select_all_button.setCursor(Qt.PointingHandCursor)
        self.select_all_button.clicked.connect(self._on_select_all_clicked)
        layout.addWidget(self.select_all_button)
        return bar

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("myListActionBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 10, 12, 10)
        layout.setSpacing(12)

        self.selected_label = QLabel("")
        self.selected_label.setObjectName("myListSelectedLabel")
        layout.addWidget(self.selected_label, 1)

        self.request_button = QPushButton("Request Selected")
        self.request_button.setObjectName("myListRequestButton")
        self.request_button.setCursor(Qt.PointingHandCursor)
        self.request_button.clicked.connect(self._on_request_clicked)
        layout.addWidget(self.request_button)
        return bar

    def _build_empty_state(self) -> QFrame:
        box = QFrame()
        box.setObjectName("catalogEmpty")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignHCenter)

        pixmap = QPixmap(str(CURIOUS_MASCOT_PATH))
        icon = QLabel()
        icon.setObjectName("catalogEmptyIcon")
        icon.setAlignment(Qt.AlignCenter)
        if not pixmap.isNull():
            icon.setPixmap(pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon.setText("🔖")  # a missing image file must never crash the app
        layout.addWidget(icon)

        title = QLabel("Your list is empty")
        title.setObjectName("catalogEmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        text = QLabel(
            "Found something you like? Save it from the catalog and it will "
            "wait for you here, ready to request whenever you are."
        )
        text.setObjectName("catalogEmptyText")
        text.setAlignment(Qt.AlignCenter)
        text.setWordWrap(True)
        layout.addWidget(text)

        button = QPushButton("Browse Catalog")
        button.setObjectName("catalogPrimaryButton")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.browse_catalog_requested.emit)
        layout.addWidget(button, alignment=Qt.AlignHCenter)
        return box

    # ---------- refreshing what is shown ----------
    def _eligible_items(self) -> list:
        return [item for item in self._saved_items if item.is_available]

    def _refresh(self):
        """Rebuild the rows and update every label/button from the current state."""
        while self._rows_layout.count():
            widget = self._rows_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = {}

        for item in self._saved_items:
            row = SavedItemRow(item, selected=item in self._selected)
            row.selection_changed.connect(self._on_row_selection_changed)
            row.remove_clicked.connect(self._on_remove_clicked)
            self._rows_layout.addWidget(row)
            self._rows[item] = row

        has_items = bool(self._saved_items)
        self.rows_container.setVisible(has_items)
        self.toolbar.setVisible(has_items)
        self.action_bar.setVisible(has_items)
        self.empty_state.setVisible(not has_items)
        self._update_status()

    def _update_status(self):
        """Update counts, the Select-all button and the Request button."""
        saved = len(self._saved_items)
        eligible = self._eligible_items()
        selected = len(self._selected)
        unavailable = saved - len(eligible)

        parts = [f"{saved} saved", f"{len(eligible)} can be requested"]
        if unavailable:
            parts.append(f"{unavailable} unavailable")
        self.summary_label.setText(" · ".join(parts))

        all_selected = bool(eligible) and all(item in self._selected for item in eligible)
        self.select_all_button.setEnabled(bool(eligible))
        self.select_all_button.setText("Clear selection" if all_selected else "Select all eligible")

        if selected:
            self.selected_label.setText(f"{selected} item{'s' if selected != 1 else ''} selected")
            self.request_button.setText(f"Request Selected ({selected})")
        else:
            self.selected_label.setText("Select available items to request them")
            self.request_button.setText("Request Selected")
        self.request_button.setEnabled(selected > 0)

    def show_message(self, text: str):
        """Show a short friendly banner that hides itself after a few seconds."""
        self.banner.setText(text)
        self.banner.show()
        self._banner_timer.start()

    # ---------- reacting to clicks ----------
    def _on_row_selection_changed(self, item, checked: bool):
        if checked:
            self._selected.add(item)
        else:
            self._selected.discard(item)
        self._update_status()

    def _on_select_all_clicked(self):
        eligible = self._eligible_items()
        if eligible and all(item in self._selected for item in eligible):
            self._selected.clear()
        else:
            self._selected = set(eligible)
        for item, row in self._rows.items():
            row.set_checked(item in self._selected)
        self._update_status()

    def _on_remove_clicked(self, item):
        self.remove_item(item)
        self.show_message(f"Removed “{item.title}” from your list.")

    def _on_request_clicked(self):
        chosen = self.selected_items
        if not chosen:
            return
        dialog = RequestPreviewDialog(chosen, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.request_preview_confirmed.emit(chosen)
            count = len(chosen)
            self.show_message(
                f"Preview only: {count} separate request{'s' if count != 1 else ''} "
                "would be created. Nothing was sent."
            )


# ======================================================================
# 6. STYLES (QSS) - only what is NEW here; the Catalog styles are reused
# ======================================================================
MY_LIST_STYLESHEET = f"""
QWidget#myListScreen {{
    background-color: {NAVY};
}}

QDialog#myListDialog {{
    background-color: {NAVY};
}}

/* ---------- Saved item rows ---------- */
QFrame#myListRow {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 22px;
}}

QFrame#myListRow:hover {{
    background-color: white;
    border-color: {PINK};
}}

QFrame#myListRow[unavailable="true"] {{
    background-color: #ECEDFA;
    border: 3px dashed #B5B7D6;
}}

QFrame#myListRow[unavailable="true"]:hover {{
    background-color: #ECEDFA;
    border-color: #B5B7D6;
}}

QLabel#myListIcon {{
    border: 2px solid {NAVY};
    border-radius: 16px;
    font-size: 24px;
}}

QPushButton#myListCheck {{
    background-color: white;
    color: {NAVY};
    border: 3px solid {NAVY};
    border-radius: 10px;
    padding: 0px;
    font-size: 16px;
    font-weight: bold;
}}

QPushButton#myListCheck:hover {{
    border-color: {PERIWINKLE};
}}

QPushButton#myListCheck:checked {{
    background-color: {MINT};
    border-color: {NAVY};
}}

QPushButton#myListCheck:disabled {{
    background-color: #E3E4FA;
    border: 3px dashed #B5B7D6;
}}

QPushButton#myListRemoveButton {{
    background: transparent;
    color: #C2386B;
    border: 2px solid #C2386B;
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: bold;
}}

QPushButton#myListRemoveButton:hover {{
    background-color: #FFD9E6;
}}

/* ---------- Toolbar (summary + select all) ---------- */
QFrame#myListToolbar {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 18px;
}}

QLabel#myListSummary {{
    color: {NAVY};
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#myListSelectAll {{
    background-color: {SOFT_LAVENDER};
    color: {NAVY};
    border: 2px solid {PERIWINKLE};
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#myListSelectAll:hover {{
    background-color: {MINT};
    border-color: {NAVY};
}}

QPushButton#myListSelectAll:disabled {{
    color: #B5B7D6;
    border-color: #DDDFFA;
}}

/* ---------- Banner ---------- */
QLabel#myListBanner {{
    background-color: {MINT};
    color: {NAVY};
    border: 2px solid {NAVY};
    border-radius: 14px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: bold;
}}

/* ---------- Bottom action bar ---------- */
QFrame#myListActionBar {{
    background-color: #3A3D7A;
    border: 2px solid {PINK};
    border-radius: 18px;
}}

QLabel#myListSelectedLabel {{
    color: {CREAM};
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#myListRequestButton {{
    background-color: {MINT};
    color: {NAVY};
    border: 3px solid {NAVY};
    border-radius: 16px;
    padding: 10px 22px;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#myListRequestButton:hover {{
    background-color: {PINK};
}}

QPushButton#myListRequestButton:disabled {{
    background-color: #5A5C8F;
    color: #B5B7D6;
    border: 3px dashed #8D90BD;
}}

/* ---------- Confirmation preview ---------- */
QLabel#myListDialogTitle {{
    color: {CREAM};
    font-size: 26px;
    font-weight: bold;
}}

QFrame#myListInfo {{
    background-color: rgba(183, 241, 225, 30);
    border: 2px solid {MINT};
    border-radius: 16px;
}}

QLabel#myListInfoText {{
    color: {MINT};
    font-size: 13px;
}}

QFrame#myListPreviewRow {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 18px;
}}

QLabel#myListDialogSummary {{
    color: {CREAM};
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#myListBackButton {{
    background: transparent;
    color: {PINK};
    border: 3px solid {PINK};
    border-radius: 16px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#myListBackButton:hover {{
    background-color: {PINK};
    color: {NAVY};
}}
"""
