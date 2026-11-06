"""KitLend Browse Catalog screen (UI only - sample data, no database).

What this file contains, from top to bottom:
  1. SAMPLE DATA   - made-up categories, collections and items (plain Python)
  2. FILTER LOGIC  - one small function that decides which items match
  3. SMALL WIDGETS - cover placeholder, pill tag, adaptive grid, item card
  4. FILTER PANEL  - the left side: categories, ownership, collections
  5. CATALOG SCREEN- the whole screen that puts everything together
  6. STYLES (QSS)  - every Catalog style lives here, so theme.py stays untouched

Nothing here can borrow, reserve, log in, or touch a database. Clicking an
item card only emits the `item_selected` signal, which nothing listens to yet.
"""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.dashboard_widgets import ElidedLabel
from app.theme import CREAM, MINT, NAVY, PERIWINKLE, PINK

# Extra shades used only by the Catalog (same ones the dashboard uses)
MUTED_TEXT = "#5A5C80"
SOFT_LAVENDER = "#F4F5FF"
LIGHT_PERIWINKLE = "#D6D8FF"
HAPPY_MASCOT_PATH = Path(__file__).resolve().parent.parent / "assets" / "happy_neon_robot_cat_mascot.png"
CURIOUS_MASCOT_PATH = Path(__file__).resolve().parent.parent / "assets" / "curious_chibi_robot_cat_mascot.png"



# ======================================================================
# 1. SAMPLE DATA
# ======================================================================
ALL_CATEGORIES = "All"
OWNERSHIP_ALL = "all"
OWNERSHIP_SCHOOL = "school"
OWNERSHIP_STUDENT = "student"

OWNERSHIP_LABELS = {
    OWNERSHIP_SCHOOL: "🏫 School-owned",
    OWNERSHIP_STUDENT: "🎒 Student-owned",
}

# What the placeholder cover shows for each kind of item
KIND_ICONS = {"Book": "📘", "Gadget": "🔌", "Tool": "🛠️", "Accessory": "🎒"}


@dataclass(frozen=True)
class CategoryInfo:
    name: str
    icon: str
    cover_color: str  # background color of the cover placeholder


@dataclass(frozen=True)
class CollectionInfo:
    name: str
    icon: str
    blurb: str  # short description (shown as a tooltip)


CATEGORIES = (
    CategoryInfo("Mathematics", "🧮", LIGHT_PERIWINKLE),
    CategoryInfo("Programming", "💻", MINT),
    CategoryInfo("Electronics", "⚡", PINK),
    CategoryInfo("Engineering", "📐", LIGHT_PERIWINKLE),
    CategoryInfo("Science", "🔬", MINT),
    CategoryInfo("Study Gear", "🎒", PINK),
)
CATEGORY_BY_NAME = {category.name: category for category in CATEGORIES}

COLLECTIONS = (
    CollectionInfo("DSA Final Project", "🌳", "Books and tools for your Data Structures and Algorithms project"),
    CollectionInfo("Electronics Lab Day", "🔌", "Everything for a hands-on circuits session"),
    CollectionInfo("Exam Survival Pack", "📝", "Calculators, textbooks and gear for exam week"),
    CollectionInfo("Maker Corner", "🧰", "Boards, kits and tools for weekend builds"),
)


@dataclass(frozen=True)
class CatalogItem:
    title: str
    creator: str          # author for books, brand for everything else
    category: str         # one of CATEGORIES
    kind: str             # "Book", "Gadget", "Tool" or "Accessory"
    ownership: str        # "school" or "student"
    owner_note: str       # pickup place (school) or "Shared by Ana M." (student)
    copies_total: int
    copies_available: int
    collections: tuple[str, ...] = ()

    @property
    def creator_line(self) -> str:
        return f"by {self.creator}" if self.kind == "Book" else f"Brand: {self.creator}"

    @property
    def ownership_label(self) -> str:
        return OWNERSHIP_LABELS[self.ownership]

    @property
    def is_available(self) -> bool:
        return self.copies_available > 0

    @property
    def availability_text(self) -> str:
        if self.copies_available == 0:
            return "Currently borrowed" if self.copies_total == 1 else "All copies borrowed"
        if self.copies_total == 1:
            return "Available"
        if self.copies_available == 1:
            return "Only 1 left"
        return f"{self.copies_available} of {self.copies_total} available"

    @property
    def availability_tone(self) -> str:
        """Pill color name: 'ok', 'low' or 'none' (see the QSS at the bottom)."""
        if self.copies_available == 0:
            return "none"
        if self.copies_total > 1 and self.copies_available == 1:
            return "low"
        return "ok"

    @property
    def search_text(self) -> str:
        """Everything a student might type to find this item, in lowercase."""
        parts = [
            self.title, self.creator, self.category, self.kind,
            self.ownership_label, self.owner_note, *self.collections,
        ]
        return " ".join(parts).lower()


# title, creator, category, kind, ownership, owner_note, total, available, collections
SAMPLE_ITEMS = [
    # --- Mathematics ---
    CatalogItem("Calculus: Early Transcendentals", "James Stewart", "Mathematics", "Book",
                "school", "Main Library", 4, 3, ("Exam Survival Pack",)),
    CatalogItem("Discrete Mathematics and Its Applications", "Kenneth H. Rosen", "Mathematics", "Book",
                "school", "Main Library", 3, 2, ("DSA Final Project", "Exam Survival Pack")),
    CatalogItem("Linear Algebra and Its Applications", "David C. Lay", "Mathematics", "Book",
                "student", "Shared by Ana M.", 1, 1),
    CatalogItem("Casio fx-991EX Scientific Calculator", "Casio", "Mathematics", "Gadget",
                "school", "Student Services Desk", 6, 4, ("Exam Survival Pack",)),
    CatalogItem("TI-84 Plus Graphing Calculator", "Texas Instruments", "Mathematics", "Gadget",
                "student", "Shared by Paolo R.", 1, 0, ("Exam Survival Pack",)),
    # --- Programming ---
    CatalogItem("Introduction to Algorithms (CLRS)", "Cormen, Leiserson, Rivest, Stein", "Programming", "Book",
                "school", "Main Library", 2, 1, ("DSA Final Project",)),
    CatalogItem("Data Structures and Algorithms in Python", "Goodrich, Tamassia, Goldwasser", "Programming", "Book",
                "school", "Main Library", 3, 2, ("DSA Final Project",)),
    CatalogItem("Python Crash Course", "Eric Matthes", "Programming", "Book",
                "student", "Shared by Ria L.", 1, 1),
    CatalogItem("Clean Code", "Robert C. Martin", "Programming", "Book",
                "student", "Shared by Mark D.", 1, 0),
    CatalogItem("Grokking Algorithms", "Aditya Bhargava", "Programming", "Book",
                "student", "Shared by Jenna T.", 1, 1, ("DSA Final Project",)),
    # --- Electronics ---
    CatalogItem("Arduino Uno Starter Kit", "Arduino", "Electronics", "Gadget",
                "school", "Electronics Lab", 5, 2, ("Electronics Lab Day", "Maker Corner")),
    CatalogItem("Digital Multimeter", "UNI-T", "Electronics", "Tool",
                "school", "Electronics Lab", 4, 3, ("Electronics Lab Day",)),
    CatalogItem("Soldering Iron Kit (60W)", "Weller", "Electronics", "Tool",
                "school", "Electronics Lab", 3, 1, ("Electronics Lab Day", "Maker Corner")),
    CatalogItem("Breadboard and Jumper Wire Set", "ELEGOO", "Electronics", "Gadget",
                "student", "Shared by Carlo V.", 1, 1, ("Electronics Lab Day",)),
    CatalogItem("Raspberry Pi 4 Model B Kit", "Raspberry Pi", "Electronics", "Gadget",
                "school", "Electronics Lab", 2, 0, ("Maker Corner",)),
    CatalogItem("ESP32 Development Board", "Espressif", "Electronics", "Gadget",
                "student", "Shared by Ana M.", 1, 1, ("Maker Corner",)),
    CatalogItem("Fundamentals of Electric Circuits", "Alexander and Sadiku", "Electronics", "Book",
                "school", "Main Library", 3, 2, ("Electronics Lab Day",)),
    # --- Engineering ---
    CatalogItem("Engineering Mechanics: Statics", "R. C. Hibbeler", "Engineering", "Book",
                "school", "Main Library", 3, 2),
    CatalogItem("Digital Vernier Caliper", "Mitutoyo", "Engineering", "Tool",
                "school", "Engineering Workshop", 3, 2, ("Maker Corner",)),
    CatalogItem("Drafting Set and T-Square", "Staedtler", "Engineering", "Tool",
                "student", "Shared by Paolo R.", 1, 1),
    # --- Science ---
    CatalogItem("University Physics", "Young and Freedman", "Science", "Book",
                "school", "Main Library", 4, 3, ("Exam Survival Pack",)),
    CatalogItem("Chemistry: The Central Science", "Brown, LeMay, Bursten", "Science", "Book",
                "student", "Shared by Jenna T.", 1, 1),
    CatalogItem("Digital Microscope (1000x)", "Andonstar", "Science", "Gadget",
                "school", "Science Lab", 2, 1, ("Maker Corner",)),
    # --- Study Gear ---
    CatalogItem("Portable Whiteboard and Markers", "Expo", "Study Gear", "Accessory",
                "school", "Student Services Desk", 3, 3, ("Exam Survival Pack",)),
    CatalogItem("Foldable Laptop Stand", "Nulaxy", "Study Gear", "Accessory",
                "student", "Shared by Ria L.", 1, 1),
    CatalogItem("Power Bank (10,000 mAh)", "Anker", "Study Gear", "Accessory",
                "school", "Student Services Desk", 5, 4),
]


# ======================================================================
# 2. FILTER LOGIC (plain Python - easy to read and to test)
# ======================================================================
def filter_items(items, search="", category=ALL_CATEGORIES, ownership=OWNERSHIP_ALL,
                 collection=None, available_only=False):
    """Return only the items that match EVERY active filter.

    Search works word by word: typing "python book" finds items whose text
    contains both "python" and "book" (in any order, any letter case).
    """
    words = search.lower().split()
    matches = []
    for item in items:
        if category != ALL_CATEGORIES and item.category != category:
            continue
        if ownership != OWNERSHIP_ALL and item.ownership != ownership:
            continue
        if collection is not None and collection not in item.collections:
            continue
        if available_only and not item.is_available:
            continue
        if not all(word in item.search_text for word in words):
            continue
        matches.append(item)
    return matches


# ======================================================================
# 3. SMALL WIDGETS
# ======================================================================
class CoverPlaceholder(QWidget):
    """A dashed placeholder where a book/item cover image will go later."""

    def __init__(self, glyph: str, caption: str, color: str, parent=None):
        super().__init__(parent)
        self._glyph = glyph
        self._caption = caption
        self._color = QColor(color)
        self.setFixedHeight(112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.setBrush(self._color)
        painter.setPen(QPen(QColor(NAVY), 2, Qt.DashLine))
        painter.drawRoundedRect(rect, 16, 16)

        painter.setPen(QColor(NAVY))
        big_font = painter.font()
        big_font.setPointSize(26)
        painter.setFont(big_font)
        painter.drawText(
            QRectF(rect.x(), rect.y() + 6, rect.width(), rect.height() - 34),
            Qt.AlignCenter, self._glyph,
        )

        small_font = painter.font()
        small_font.setPointSize(9)
        small_font.setBold(True)
        painter.setFont(small_font)
        painter.drawText(
            QRectF(rect.x(), rect.bottom() - 28, rect.width(), 22),
            Qt.AlignCenter, self._caption,
        )


class TagPill(QLabel):
    """A tiny rounded tag. `tone` picks the color (see the QSS at the bottom)."""

    def __init__(self, text: str, tone: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("catalogPill")
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class AdaptiveGrid(QWidget):
    """Arranges widgets in as many columns as fit, and re-flows on resize.

    Call set_widgets([...]) any time (for example after a filter changes).
    Widgets that are not in the new list are hidden.
    """

    def __init__(self, min_item_width: int, spacing: int = 16, parent=None):
        super().__init__(parent)
        self._min_item_width = min_item_width
        self._spacing = spacing
        self._widgets = []
        self._columns = 0
        self._stretch_slots = 0

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)

    def minimumSizeHint(self):
        # Let the scroll area shrink us; resizeEvent will re-flow the items.
        return QSize(0, super().minimumSizeHint().height())

    def set_widgets(self, widgets):
        keep = {id(widget) for widget in widgets}
        for widget in self._widgets:
            if id(widget) not in keep:
                widget.hide()
        self._widgets = list(widgets)
        self._rebuild()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._columns_for_width() != self._columns:
            self._rebuild()

    def _columns_for_width(self) -> int:
        return max(1, (self.width() + self._spacing) // (self._min_item_width + self._spacing))

    def _rebuild(self):
        self._columns = self._columns_for_width()
        while self._grid.count():
            self._grid.takeAt(0)  # detach from the layout; widgets stay alive
        for index, widget in enumerate(self._widgets):
            self._grid.addWidget(widget, index // self._columns, index % self._columns)
            widget.show()
        # Equal-width columns, and forget stretch values from earlier layouts
        for column in range(max(self._columns, self._stretch_slots)):
            self._grid.setColumnStretch(column, 1 if column < self._columns else 0)
        self._stretch_slots = self._columns


class ItemCard(QFrame):
    """One catalog item: cover, title, author/brand, owner label, availability."""

    clicked = Signal(object)  # sends the CatalogItem

    def __init__(self, item: CatalogItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("catalogItemCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{item.title}\n{item.creator_line}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 14)
        layout.setSpacing(6)

        category = CATEGORY_BY_NAME.get(item.category)
        layout.addWidget(CoverPlaceholder(
            KIND_ICONS.get(item.kind, "📦"),
            f"{item.kind} · {item.category}",
            category.cover_color if category else LIGHT_PERIWINKLE,
        ))
        layout.addSpacing(4)

        title = ElidedLabel(item.title)
        title.setObjectName("catalogItemTitle")
        layout.addWidget(title)

        creator = ElidedLabel(item.creator_line)
        creator.setObjectName("catalogItemCreator")
        layout.addWidget(creator)

        # School-owned / Student-owned label + where to pick it up (or who shares it)
        owner_row = QHBoxLayout()
        owner_row.setSpacing(8)
        owner_row.addWidget(TagPill(item.ownership_label, item.ownership))
        note = ElidedLabel(item.owner_note)
        note.setObjectName("catalogItemNote")
        owner_row.addWidget(note, 1)
        layout.addLayout(owner_row)

        availability_row = QHBoxLayout()
        availability_row.addWidget(TagPill(item.availability_text, item.availability_tone))
        availability_row.addStretch()
        layout.addLayout(availability_row)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.item)
        super().mousePressEvent(event)


# ======================================================================
# 4. FILTER PANEL (left side)
# ======================================================================
class FilterPanel(QFrame):
    """Category list, ownership list, availability toggle and collections.

    It remembers the current choices and emits `filters_changed` whenever one
    of them changes. It does not know anything about items or cards.
    """

    filters_changed = Signal()
    clear_requested = Signal()

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setObjectName("catalogFilters")
        self.setFixedWidth(270)

        # Current choices
        self.category = ALL_CATEGORIES
        self.ownership = OWNERSHIP_ALL
        self.collection = None        # None = no collection selected
        self.available_only = False

        self._category_buttons = {}
        self._ownership_buttons = {}
        self._collection_buttons = {}
        self._build_ui(items)

    # ---------- building ----------
    def _build_ui(self, items):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Filters")
        title.setObjectName("catalogFilterTitle")
        header.addWidget(title)
        header.addStretch()
        self.clear_button = QPushButton("Clear all")
        self.clear_button.setObjectName("catalogClearButton")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self.clear_requested.emit)
        header.addWidget(self.clear_button)
        outer.addLayout(header)

        # The lists can be taller than a small window, so they scroll
        scroll = QScrollArea()
        scroll.setObjectName("catalogFilterScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setObjectName("catalogFilterInner")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(6)

        # --- Category (pick exactly one) ---
        self._add_section_label(layout, "CATEGORY")
        self._category_group = QButtonGroup(self)
        self._category_group.setExclusive(True)
        category_options = [(ALL_CATEGORIES, "✨", "All categories", len(items))]
        for category in CATEGORIES:
            count = sum(1 for item in items if item.category == category.name)
            category_options.append((category.name, category.icon, category.name, count))
        for key, icon, label, count in category_options:
            button = self._make_filter_button(f"{icon}  {label}  ({count})", "catalogFilterButton")
            button.clicked.connect(lambda _checked=False, key=key: self._on_category(key))
            self._category_group.addButton(button)
            self._category_buttons[key] = button
            layout.addWidget(button)
        self._category_buttons[ALL_CATEGORIES].setChecked(True)

        # --- Ownership (pick exactly one) ---
        self._add_section_label(layout, "OWNERSHIP")
        self._ownership_group = QButtonGroup(self)
        self._ownership_group.setExclusive(True)
        ownership_options = [
            (OWNERSHIP_ALL, "📦  All items", len(items)),
            (OWNERSHIP_SCHOOL, "🏫  School-owned",
             sum(1 for item in items if item.ownership == OWNERSHIP_SCHOOL)),
            (OWNERSHIP_STUDENT, "🎒  Student-owned",
             sum(1 for item in items if item.ownership == OWNERSHIP_STUDENT)),
        ]
        for key, label, count in ownership_options:
            button = self._make_filter_button(f"{label}  ({count})", "catalogFilterButton")
            button.clicked.connect(lambda _checked=False, key=key: self._on_ownership(key))
            self._ownership_group.addButton(button)
            self._ownership_buttons[key] = button
            layout.addWidget(button)
        self._ownership_buttons[OWNERSHIP_ALL].setChecked(True)

        # --- Availability (on/off) ---
        self._add_section_label(layout, "AVAILABILITY")
        self.available_button = self._make_filter_button("✅  Available now only", "catalogFilterButton")
        self.available_button.clicked.connect(self._on_available)
        layout.addWidget(self.available_button)

        # --- Collections (pick one, click again to un-pick) ---
        self._add_section_label(layout, "COLLECTIONS")
        for collection in COLLECTIONS:
            count = sum(1 for item in items if collection.name in item.collections)
            button = self._make_filter_button(
                f"{collection.icon}  {collection.name}  ({count})", "catalogCollectionButton"
            )
            button.setToolTip(collection.blurb)
            button.clicked.connect(lambda _checked=False, name=collection.name: self._on_collection(name))
            self._collection_buttons[collection.name] = button
            layout.addWidget(button)

        layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def _add_section_label(self, layout, text: str):
        layout.addSpacing(6)
        label = QLabel(text)
        label.setObjectName("catalogSectionLabel")
        layout.addWidget(label)

    def _make_filter_button(self, text: str, object_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        return button

    # ---------- reacting to clicks ----------
    def _on_category(self, key: str):
        self.category = key
        self.filters_changed.emit()

    def _on_ownership(self, key: str):
        self.ownership = key
        self.filters_changed.emit()

    def _on_available(self, checked: bool):
        self.available_only = checked
        self.filters_changed.emit()

    def _on_collection(self, name: str):
        # Clicking the selected collection again clears it
        self.collection = None if self.collection == name else name
        self._sync_collection_buttons()
        self.filters_changed.emit()

    def _sync_collection_buttons(self):
        for name, button in self._collection_buttons.items():
            button.setChecked(name == self.collection)

    # ---------- used by the screen ----------
    def has_active_filters(self) -> bool:
        return (
            self.category != ALL_CATEGORIES
            or self.ownership != OWNERSHIP_ALL
            or self.collection is not None
            or self.available_only
        )

    def set_clear_enabled(self, enabled: bool):
        self.clear_button.setEnabled(enabled)

    def reset(self):
        """Put every filter back to 'show everything' (does not emit a signal)."""
        self.category = ALL_CATEGORIES
        self.ownership = OWNERSHIP_ALL
        self.collection = None
        self.available_only = False
        self._category_buttons[ALL_CATEGORIES].setChecked(True)
        self._ownership_buttons[OWNERSHIP_ALL].setChecked(True)
        self.available_button.setChecked(False)
        self._sync_collection_buttons()


# ======================================================================
# 5. CATALOG SCREEN
# ======================================================================
class CatalogScreen(QWidget):
    """Browse Catalog: search box, filters, and a grid of item cards.

    `item_selected` is emitted when a card is clicked. Nothing is connected to
    it yet - borrowing and item details come in later steps.
    """

    item_selected = Signal(object)

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self.setObjectName("catalogScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(CATALOG_STYLESHEET)  # affects only this screen

        self._items = list(items) if items is not None else list(SAMPLE_ITEMS)
        self._cards = [ItemCard(item) for item in self._items]  # built once, shown/hidden by filters
        for card in self._cards:
            card.clicked.connect(self.item_selected.emit)
        self._visible_cards = []

        self._build_ui()
        self._apply_filters()

    @property
    def visible_items(self):
        """The items currently shown (handy for testing)."""
        return [card.item for card in self._visible_cards]

    # ---------- building ----------
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(18)

        self.filter_panel = FilterPanel(self._items)
        self.filter_panel.filters_changed.connect(self._apply_filters)
        self.filter_panel.clear_requested.connect(self._clear_everything)
        root.addWidget(self.filter_panel)

        # The search floats at the top only AFTER the header scrolls out.
        right = QVBoxLayout()
        right.setSpacing(8)
        self.sticky_search_bar = self._build_sticky_search_bar()
        right.addWidget(self.sticky_search_bar)
        self.sticky_search_bar.hide()
        right.addWidget(self._build_results_area(), 1)
        root.addLayout(right, 1)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("catalogHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(26, 16, 26, 18)
        layout.setSpacing(10)

        # Put heading and 160px mascot SIDE BY SIDE. This keeps the header
        # compact instead of leaving a tall blank row above the title.
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        text_column = QVBoxLayout()
        text_column.setSpacing(8)

        tag = QLabel("Preview · Sample data only")
        tag.setObjectName("catalogTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        text_column.addWidget(tag, alignment=Qt.AlignLeft | Qt.AlignTop)
        text_column.addSpacing(6)

        title = QLabel("Browse Catalog")
        title.setObjectName("catalogTitle")
        text_column.addWidget(title)

        subtitle = QLabel("Find books, gadgets, and tools from the school and from fellow students.")
        subtitle.setObjectName("catalogSubtitle")
        subtitle.setWordWrap(True)
        text_column.addWidget(subtitle)
        text_column.addStretch()
        top_row.addLayout(text_column, 1)

        happy_pixmap = QPixmap(str(HAPPY_MASCOT_PATH))
        if not happy_pixmap.isNull():
            mascot_label = QLabel()
            mascot_label.setPixmap(happy_pixmap.scaled(
                160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
            mascot_label.setAlignment(Qt.AlignCenter)
            top_row.addWidget(mascot_label, 0, Qt.AlignTop | Qt.AlignRight)
        layout.addLayout(top_row)

        # Initial search bar: lives at the bottom of the scrolling hero.
        self.search_input = QLineEdit()
        self.search_input.setObjectName("catalogSearch")
        self.search_input.setPlaceholderText("🔍  Search by title, author, brand, or category")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_input)
        return header

    def _build_sticky_search_bar(self) -> QFrame:
        """Compact search bar shown only while the main header is offscreen."""
        bar = QFrame()
        bar.setObjectName("catalogStickyBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        label = QLabel("Search")
        label.setObjectName("catalogStickyLabel")
        row.addWidget(label)
        self.sticky_search_input = QLineEdit()
        self.sticky_search_input.setObjectName("catalogSearch")
        self.sticky_search_input.setPlaceholderText("🔍  Search books, gadgets, tools...")
        self.sticky_search_input.setClearButtonEnabled(True)
        self.sticky_search_input.textChanged.connect(self._on_sticky_search_changed)
        row.addWidget(self.sticky_search_input, 1)
        return bar

    def _build_results_area(self) -> QScrollArea:
        # This ONE scroll area contains the large header AND the item cards.
        # When you scroll, the entire header moves upward out of view.
        scroll = QScrollArea()
        scroll.setObjectName("catalogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName("catalogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 8)
        layout.setSpacing(14)

        layout.addWidget(self._build_header())

        self.result_label = QLabel("")
        self.result_label.setObjectName("catalogResultLabel")
        layout.addWidget(self.result_label)

        self.grid = AdaptiveGrid(min_item_width=210, spacing=16)
        layout.addWidget(self.grid)

        self.empty_state = self._build_empty_state()
        layout.addWidget(self.empty_state)
        layout.addStretch()

        scroll.setWidget(content)
        self.catalog_scroll = scroll
        self.scroll_content = content
        scroll.verticalScrollBar().valueChanged.connect(self._update_sticky_search)
        return scroll

    def _build_empty_state(self) -> QFrame:
        box = QFrame()
        box.setObjectName("catalogEmpty")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignHCenter)

        # Curious mascot appears ONLY when the search/filters find nothing.
        curious_pixmap = QPixmap(str(CURIOUS_MASCOT_PATH))
        icon = QLabel()
        icon.setObjectName("catalogEmptyIcon")
        icon.setAlignment(Qt.AlignCenter)
        if not curious_pixmap.isNull():
            icon.setPixmap(curious_pixmap.scaled(
                140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        else:
            icon.setText("🔍")  # missing file should never crash the app
        layout.addWidget(icon)

        title = QLabel("No items found")
        title.setObjectName("catalogEmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        text = QLabel("Try a different search word, or clear some filters.")
        text.setObjectName("catalogEmptyText")
        text.setAlignment(Qt.AlignCenter)
        text.setWordWrap(True)
        layout.addWidget(text)

        button = QPushButton("Clear filters")
        button.setObjectName("catalogPrimaryButton")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self._clear_everything)
        layout.addWidget(button, alignment=Qt.AlignHCenter)
        return box

    def _update_sticky_search(self, _value=0):
        """Switch to the sticky search only after the original disappears."""
        search_bottom = self.search_input.mapTo(
            self.scroll_content, QPoint(0, self.search_input.height())
        ).y()
        scrolled_past_search = self.catalog_scroll.verticalScrollBar().value() >= search_bottom
        self.sticky_search_bar.setVisible(scrolled_past_search)

    def _on_sticky_search_changed(self, text: str):
        # Both fields edit ONE query. blockSignals prevents duplicate updates.
        self.search_input.blockSignals(True)
        self.search_input.setText(text)
        self.search_input.blockSignals(False)
        self._apply_filters()

    # ---------- filtering ----------
    def _on_search_changed(self, text: str):
        self.sticky_search_input.blockSignals(True)
        self.sticky_search_input.setText(text)
        self.sticky_search_input.blockSignals(False)
        self._apply_filters()

    def _has_active_filters(self) -> bool:
        return self.filter_panel.has_active_filters() or bool(self.search_input.text().strip())

    def _clear_everything(self):
        self.search_input.clear()   # also triggers a refresh
        self.filter_panel.reset()
        self._apply_filters()

    def _apply_filters(self):
        matches = set(filter_items(
            self._items,
            search=self.search_input.text(),
            category=self.filter_panel.category,
            ownership=self.filter_panel.ownership,
            collection=self.filter_panel.collection,
            available_only=self.filter_panel.available_only,
        ))
        self._visible_cards = [card for card in self._cards if card.item in matches]

        self.grid.set_widgets(self._visible_cards)
        self.grid.setVisible(bool(self._visible_cards))
        self.empty_state.setVisible(not self._visible_cards)

        total = len(self._items)
        shown = len(self._visible_cards)
        if shown == 0:
            self.result_label.setText("No items match your search")
        else:
            self.result_label.setText(f"Showing {shown} of {total} items")
        self.filter_panel.set_clear_enabled(self._has_active_filters())


# ======================================================================
# 6. STYLES (QSS) - Pixel Pop, applied only to the Catalog screen
# ======================================================================
CATALOG_STYLESHEET = f"""
QWidget#catalogScreen {{
    background-color: {NAVY};
}}

/* ---------- Filter panel ---------- */
QFrame#catalogFilters {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 24px;
}}

QLabel#catalogFilterTitle {{
    color: {NAVY};
    font-size: 20px;
    font-weight: bold;
}}

QLabel#catalogSectionLabel {{
    color: {PERIWINKLE};
    font-size: 11px;
    font-weight: bold;
}}

QScrollArea#catalogFilterScroll, QWidget#catalogFilterInner {{
    background-color: {CREAM};
    border: none;
}}

QPushButton#catalogFilterButton {{
    background-color: {SOFT_LAVENDER};
    color: {NAVY};
    border: 2px solid #DDDFFA;
    border-radius: 12px;
    padding: 8px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#catalogFilterButton:hover {{
    background-color: #E3E4FA;
}}

QPushButton#catalogFilterButton:checked {{
    background-color: {PERIWINKLE};
    color: white;
    border-color: {NAVY};
}}

QPushButton#catalogCollectionButton {{
    background-color: #EAFBF6;
    color: {NAVY};
    border: 2px solid {MINT};
    border-radius: 12px;
    padding: 8px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#catalogCollectionButton:hover {{
    background-color: #D5F7EE;
}}

QPushButton#catalogCollectionButton:checked {{
    background-color: {MINT};
    border-color: {NAVY};
}}

QPushButton#catalogClearButton {{
    background: transparent;
    color: {PERIWINKLE};
    border: none;
    font-size: 13px;
    font-weight: bold;
    padding: 2px 4px;
}}

QPushButton#catalogClearButton:hover {{
    color: {NAVY};
    text-decoration: underline;
}}

QPushButton#catalogClearButton:disabled {{
    color: #B5B7D6;
}}

QScrollArea#catalogFilterScroll QScrollBar:vertical,
QScrollArea#catalogScroll QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 4px;
}}

QScrollArea#catalogFilterScroll QScrollBar::handle:vertical,
QScrollArea#catalogScroll QScrollBar::handle:vertical {{
    background: {PERIWINKLE};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollArea#catalogFilterScroll QScrollBar::add-line:vertical,
QScrollArea#catalogFilterScroll QScrollBar::sub-line:vertical,
QScrollArea#catalogScroll QScrollBar::add-line:vertical,
QScrollArea#catalogScroll QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollArea#catalogFilterScroll QScrollBar::add-page:vertical,
QScrollArea#catalogFilterScroll QScrollBar::sub-page:vertical,
QScrollArea#catalogScroll QScrollBar::add-page:vertical,
QScrollArea#catalogScroll QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* ---------- Header and search ---------- */
QFrame#catalogStickyBar {{
    background-color: #3A3D7A;
    border: 2px solid {PINK};
    border-radius: 16px;
}}

QLabel#catalogStickyLabel {{
    color: {CREAM};
    font-size: 13px;
    font-weight: bold;
}}

QFrame#catalogHeader {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #3A3D7A, stop:1 {PERIWINKLE});
    border: 3px solid {PINK};
    border-radius: 26px;
}}

QLabel#catalogTag {{
    background-color: rgba(183, 241, 225, 30);
    color: {MINT};
    border: 2px solid {MINT};
    border-radius: 14px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: bold;
}}

QLabel#catalogTitle {{
    color: {CREAM};
    font-size: 28px;
    font-weight: bold;
}}

QLabel#catalogSubtitle {{
    color: {CREAM};
    font-size: 14px;
}}

QLineEdit#catalogSearch {{
    background-color: white;
    color: {NAVY};
    border: 3px solid {NAVY};
    border-radius: 18px;
    padding: 10px 18px;
    font-size: 15px;
    selection-background-color: {PERIWINKLE};
}}

QLineEdit#catalogSearch:focus {{
    border-color: {PINK};
    background-color: {SOFT_LAVENDER};
}}

QLabel#catalogResultLabel {{
    color: {CREAM};
    font-size: 14px;
    font-weight: bold;
    padding-left: 6px;
}}

/* ---------- Results area ---------- */
QScrollArea#catalogScroll, QWidget#catalogContent {{
    background-color: {NAVY};
    border: none;
}}

QFrame#catalogItemCard {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 22px;
}}

QFrame#catalogItemCard:hover {{
    background-color: white;
    border-color: {PINK};
}}

QLabel#catalogItemTitle {{
    color: {NAVY};
    font-size: 14px;
    font-weight: bold;
}}

QLabel#catalogItemCreator {{
    color: {MUTED_TEXT};
    font-size: 12px;
}}

QLabel#catalogItemNote {{
    color: {MUTED_TEXT};
    font-size: 11px;
}}

/* ---------- Pills (ownership + availability) ---------- */
QLabel#catalogPill {{
    border: 2px solid {NAVY};
    border-radius: 11px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: bold;
}}

QLabel#catalogPill[tone="school"] {{ background-color: {PERIWINKLE}; color: white; }}
QLabel#catalogPill[tone="student"] {{ background-color: {PINK}; color: {NAVY}; }}
QLabel#catalogPill[tone="ok"] {{ background-color: {MINT}; color: {NAVY}; }}
QLabel#catalogPill[tone="low"] {{ background-color: #FFE3B3; color: {NAVY}; }}
QLabel#catalogPill[tone="none"] {{
    background-color: #FFD9E6;
    color: #C2386B;
    border-color: #C2386B;
}}

/* ---------- Empty state ---------- */
QFrame#catalogEmpty {{
    background-color: {CREAM};
    border: 3px dashed {PERIWINKLE};
    border-radius: 24px;
}}

QLabel#catalogEmptyIcon {{
    font-size: 40px;
}}

QLabel#catalogEmptyTitle {{
    color: {NAVY};
    font-size: 22px;
    font-weight: bold;
}}

QLabel#catalogEmptyText {{
    color: {MUTED_TEXT};
    font-size: 14px;
}}

QPushButton#catalogPrimaryButton {{
    background-color: {MINT};
    color: {NAVY};
    border: 3px solid {NAVY};
    border-radius: 16px;
    padding: 10px 22px;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#catalogPrimaryButton:hover {{
    background-color: {PINK};
}}
"""
