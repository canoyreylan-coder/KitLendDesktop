"""KitLend Browse Catalog screen.

What this file contains, from top to bottom:
  1. SAMPLE DATA   - existing school/demo listings (plain Python)
  2. FILTER LOGIC  - one small function that decides which items match
  3. SMALL WIDGETS - image slot, status tags, adaptive grid, item card
  4. FILTER BAR    - Step 18: horizontal dropdowns + removable chips (FilterBar)
  5. CATALOG SCREEN- the whole screen that puts everything together
  6. OLD STYLES    - Pixel Pop QSS kept only for the other screens that import it

The screen can also receive saved published Student Owner listings from the Dashboard.
Clicking an item card only emits the `item_selected` signal; the Dashboard opens Item Details.
Each card also has a bookmark button; see `bookmark_toggled` and
`set_bookmarked_items()` on CatalogScreen (bookmarks live in memory only).
Available cards have a Request Now button that only emits
`direct_request_requested`; the owner of the screen decides what happens.

Step 16: the Catalog screen itself uses the soft-dark look from app/catalog_theme.py
(`CATALOG_V2_STYLESHEET`, `cat*` object names). The old Pixel Pop `CATALOG_STYLESHEET`,
`TagPill` and `AdaptiveGrid` stay in this file UNCHANGED because My List, My Requests,
My Borrowings, Reservations, Notifications and Settings still import them.
"""
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import design_tokens as tk
from app.catalog_theme import CATALOG_V2_STYLESHEET, COVER_TINTS
from app.header_style import HEADER_QSS, accent_html
from app.dashboard_widgets import ElidedLabel
from app.preference_service import DEFAULT_CATALOG_VIEW, VIEW_GRID, VIEW_LIST, VIEW_MODES
from app.theme import CREAM, MINT, NAVY, PERIWINKLE, PINK

# Extra shades used only by the Catalog (same ones the dashboard uses)
MUTED_TEXT = "#5A5C80"
SOFT_LAVENDER = "#F4F5FF"
LIGHT_PERIWINKLE = "#D6D8FF"
HAPPY_MASCOT_PATH = Path(__file__).resolve().parent.parent / "assets" / "happy_neon_robot_cat_mascot.png"
CURIOUS_MASCOT_PATH = Path(__file__).resolve().parent.parent / "assets" / "curious_chibi_robot_cat_mascot.png"

# Catalog layout numbers (Step 16)
CATALOG_MASCOT_SIZE = 72   # same size as the Dashboard welcome bar
CARD_MIN_WIDTH = 220       # a card never gets narrower than this; columns are added as space allows
CARD_SPACING = 16



# ======================================================================
# 1. SAMPLE DATA
# ======================================================================
ALL_CATEGORIES = "All"
OWNERSHIP_ALL = "all"
OWNERSHIP_SCHOOL = "school"
OWNERSHIP_STUDENT = "student"

# Step 18: availability filter values
AVAILABILITY_ANY = "any"
AVAILABILITY_AVAILABLE = "available"
AVAILABILITY_UNAVAILABLE = "unavailable"
AVAILABILITY_UNKNOWN = "unknown"   # missing / invalid copy counts: never counted as available

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
    record_id: str | None = None
    subcategory: str = ""
    condition: str = ""
    description: str = ""
    extra_rules: str = ""
    max_borrow_days: int | None = None
    pickup_schedule_text: str = ""
    pickup_schedule: dict | None = field(default=None, compare=False, hash=False)
    request_enabled: bool = True
    owner_student_id: int | None = None
    request_disabled_reason: str = ""

    @property
    def listing_key(self) -> str:
        """Stable database identity when available, otherwise the legacy Catalog identity."""
        if self.record_id:
            return self.record_id
        return f"{self.ownership}|{self.owner_note}|{self.title}"

    @property
    def creator_line(self) -> str:
        if self.record_id:
            return f"Shared by {self.creator}"
        return f"by {self.creator}" if self.kind == "Book" else f"Brand: {self.creator}"

    @property
    def category_label(self) -> str:
        return f"{self.category} › {self.subcategory}" if self.subcategory else self.category

    @property
    def ownership_label(self) -> str:
        return OWNERSHIP_LABELS.get(self.ownership, "Unknown owner")

    @property
    def availability_status(self) -> str:
        """'available', 'unavailable' or 'unknown' (Step 18).

        Only a real, non-negative whole number of copies counts. A missing or invalid
        number is 'unknown' - it is never treated as available.
        """
        copies = self.copies_available
        if not isinstance(copies, int) or isinstance(copies, bool) or copies < 0:
            return AVAILABILITY_UNKNOWN
        return AVAILABILITY_AVAILABLE if copies > 0 else AVAILABILITY_UNAVAILABLE

    @property
    def is_available(self) -> bool:
        return self.availability_status == AVAILABILITY_AVAILABLE

    @property
    def availability_text(self) -> str:
        if self.availability_status == AVAILABILITY_UNKNOWN:
            return "Availability unknown"
        if self.copies_total == 0:
            return "Out of Stock"
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
        if self.availability_status != AVAILABILITY_AVAILABLE:
            return "none"
        if self.copies_total > 1 and self.copies_available == 1:
            return "low"
        return "ok"

    @property
    def search_text(self) -> str:
        """Everything a student might type to find this item, in lowercase."""
        parts = [
            self.title, self.creator, self.category_label, self.kind, self.condition,
            self.description, self.extra_rules,
            self.ownership_label, self.owner_note, self.pickup_schedule_text,
            *(self.collections or ()),
        ]
        return " ".join(str(part) for part in parts if part).lower()


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
                 collection=None, available_only=False, availability=AVAILABILITY_ANY):
    """Return only the items that match EVERY active filter (AND logic).

    This is the ONE filtering pipeline: Grid view, List view and the result count all use
    it, and nothing else decides what matches.

    Search works word by word: typing "python book" finds items whose text
    contains both "python" and "book" (in any order, any letter case).
    An item with a missing or unknown value only matches the "any/all" choice of that
    filter. For availability, 'unknown' is neither Available nor Unavailable.
    `available_only=True` is the older spelling of availability="available".
    """
    if available_only:
        availability = AVAILABILITY_AVAILABLE
    words = (search or "").lower().split()
    matches = []
    for item in items:
        if category != ALL_CATEGORIES and item.category != category:
            continue
        if ownership != OWNERSHIP_ALL and item.ownership != ownership:
            continue
        if collection is not None and collection not in (item.collections or ()):
            continue
        if availability != AVAILABILITY_ANY and item.availability_status != availability:
            continue
        if not all(word in item.search_text for word in words):
            continue
        matches.append(item)
    return matches


# ======================================================================
# 3. SMALL WIDGETS
# ======================================================================
class ItemImageSlot(QWidget):
    """The picture area at the top of an item card (a tinted placeholder for now).

    Real item images will fill this same rounded slot later, so the card layout will not
    need to change. It shows the kind's emoji and a "Kind · Category" caption.
    """

    HEIGHT = 96

    def __init__(self, glyph: str, caption: str, tone: str, parent=None):
        super().__init__(parent)
        self._glyph = glyph
        self._caption = caption
        background, foreground, border = COVER_TINTS.get(tone, COVER_TINTS["lavender"])
        self._background = QColor(background)
        self._foreground = QColor(foreground)
        self._border = QColor(border)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._photo = None          # a real picture (QPixmap), or None -> placeholder
        self._scaled = None         # (size, pixmap) cache of the cover-cropped picture

    # ---------- Step 21: real photo (falls back to the placeholder) ----------
    @property
    def has_photo(self) -> bool:
        return self._photo is not None

    def set_photo(self, source):
        """Show a picture: `source` is a file path, a QPixmap, or None for the placeholder.
        A missing or unreadable file silently keeps the placeholder."""
        pixmap = None
        if isinstance(source, QPixmap):
            pixmap = source if not source.isNull() else None
        elif source:
            try:
                loaded = QPixmap(str(source))
            except Exception:
                loaded = None
            pixmap = loaded if loaded is not None and not loaded.isNull() else None
        self._photo = pixmap
        self._scaled = None
        self.update()

    def _paint_photo(self, painter, rect, radius: float) -> bool:
        """Draw the photo cropped to fill the rounded frame. False if there is no photo."""
        if self._photo is None:
            return False
        size = QSize(max(1, int(rect.width())), max(1, int(rect.height())))
        if self._scaled is None or self._scaled[0] != size:
            scaled = self._photo.scaled(size, Qt.KeepAspectRatioByExpanding,
                                        Qt.SmoothTransformation)
            self._scaled = (size, scaled)
        scaled = self._scaled[1]
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        painter.save()
        painter.setClipPath(clip)
        painter.drawPixmap(int(rect.x() + (rect.width() - scaled.width()) / 2),
                           int(rect.y() + (rect.height() - scaled.height()) / 2), scaled)
        painter.restore()
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self._border, 1))
        painter.drawRoundedRect(rect, radius, radius)
        return True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._paint_photo(painter, rect, 10):
            return
        painter.setBrush(self._background)
        painter.setPen(QPen(self._border, 1))
        painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(self._foreground)
        glyph_font = painter.font()
        glyph_font.setPointSize(22)
        painter.setFont(glyph_font)
        painter.drawText(
            QRectF(rect.x(), rect.y() + 6, rect.width(), rect.height() - 32),
            Qt.AlignCenter, self._glyph,
        )

        caption_font = painter.font()
        caption_font.setPointSize(8)
        caption_font.setBold(True)
        painter.setFont(caption_font)
        caption = painter.fontMetrics().elidedText(
            self._caption, Qt.ElideRight, int(rect.width()) - 16
        )
        painter.drawText(
            QRectF(rect.x() + 8, rect.bottom() - 26, rect.width() - 16, 22),
            Qt.AlignCenter, caption,
        )


class StatusTag(QLabel):
    """A small rounded tag for the Catalog cards. `tone`: school, student, ok, low, none."""

    def __init__(self, text: str, tone: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("catPill")
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


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


# Which cover tint each category's old pastel color maps to (data stays as it was).
_TONE_BY_COVER_COLOR = {LIGHT_PERIWINKLE: "lavender", PINK: "pink", MINT: "mint"}


class CatalogItemWidget(QFrame):
    """What a Grid card and a List row have in common (Step 17).

    ONE implementation of the item's signals, Request Now button, bookmark star and click
    handling. ItemCard (Grid) and ItemRow (List) only differ in how they LAY OUT the same
    item, so borrowing and My List behave identically in both views.
    """

    clicked = Signal(object)  # sends the CatalogItem
    bookmark_toggled = Signal(object, bool)  # (CatalogItem, is_bookmarked)
    request_clicked = Signal(object)  # Request Now pressed (available items only)

    def __init__(self, item: CatalogItem, parent=None):
        super().__init__(parent)
        self.item = item
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{item.title}\n{item.creator_line}")

    # ---------- shared buttons ----------
    def _make_request_button(self) -> QPushButton:
        # Request Now: starts a direct request preview, no bookmark needed.
        # Unavailable items get a disabled button (they can still be bookmarked).
        self.request_button = QPushButton("Request Now")
        self.request_button.setObjectName("catRequestButton")
        self.request_button.setFixedHeight(34)
        if self.item.is_available and self.item.request_enabled:
            self.request_button.setCursor(Qt.PointingHandCursor)
            self.request_button.setToolTip("Request this item now")
            self.request_button.clicked.connect(self._on_request_clicked)
        else:
            self.request_button.setEnabled(False)
            self.request_button.setToolTip(
                self.item.request_disabled_reason or
                "Currently unavailable - you can still save it to My List"
            )
        return self.request_button

    def _make_bookmark_button(self) -> QPushButton:
        # Bookmark button (any item can be saved, even unavailable ones).
        # A QPushButton swallows the mouse press, so clicking it never reaches
        # mousePressEvent below and never triggers the normal click.
        self.bookmark_button = QPushButton("☆")
        self.bookmark_button.setObjectName("catBookmarkButton")
        self.bookmark_button.setCheckable(True)
        self.bookmark_button.setFixedSize(38, 34)
        self.bookmark_button.setCursor(Qt.PointingHandCursor)
        self.bookmark_button.toggled.connect(self._on_bookmark_toggled)
        self._refresh_bookmark_look(False)
        return self.bookmark_button

    # ---------- Step 21: primary photo ----------
    def set_photo(self, path):
        """Show this item's primary photo (None = placeholder). Same for Grid and List."""
        slot = getattr(self, "image_slot", None) or getattr(self, "thumb", None)
        if slot is not None:
            slot.set_photo(path)

    # ---------- request ----------
    def _on_request_clicked(self, _checked=False):
        if self.item.is_available:  # an unavailable item can never start a request
            self.request_clicked.emit(self.item)

    # ---------- bookmark ----------
    def set_bookmarked(self, bookmarked: bool):
        """Change the saved look WITHOUT sending bookmark_toggled (used to sync)."""
        self.bookmark_button.blockSignals(True)
        self.bookmark_button.setChecked(bookmarked)
        self.bookmark_button.blockSignals(False)
        self._refresh_bookmark_look(bookmarked)

    def _on_bookmark_toggled(self, checked: bool):
        self._refresh_bookmark_look(checked)
        self.bookmark_toggled.emit(self.item, checked)

    def _refresh_bookmark_look(self, bookmarked: bool):
        # Filled star + pink = saved. Empty star = not saved.
        self.bookmark_button.setText("★" if bookmarked else "☆")
        self.bookmark_button.setToolTip(
            "Saved to My List - click to remove" if bookmarked else "Save to My List"
        )

    def mousePressEvent(self, event):
        # A disabled button does not swallow the press, so check its area too:
        # clicking Request Now (enabled or not) is never a normal click.
        over_request_button = self.request_button.geometry().contains(event.position().toPoint())
        if event.button() == Qt.LeftButton and not over_request_button:
            self.clicked.emit(self.item)
        super().mousePressEvent(event)


class ItemCard(CatalogItemWidget):
    """One catalog item card (Grid view), built from three parts: image slot, details, actions.

    Shows: image slot, item name, creator, recorded condition/availability, owner and pickup.
    The buttons, signals and bookmark behaviour come from CatalogItemWidget.
    """

    def __init__(self, item: CatalogItem, parent=None):
        super().__init__(item, parent)
        self.setObjectName("catItemCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(self._build_image_slot())
        layout.addSpacing(4)
        self._build_details(layout)
        layout.addStretch()
        self._build_actions(layout)

    # ---------- parts ----------
    def _build_image_slot(self) -> ItemImageSlot:
        self.image_slot = ItemImageSlot(
            KIND_ICONS.get(self.item.kind, "📦"),
            f"{self.item.kind} · {self.item.category_label}",
            _cover_tone(self.item),
        )
        return self.image_slot

    def _build_details(self, layout: QVBoxLayout):
        # The name may use two lines; the fixed height keeps every card the same size.
        title = QLabel(self.item.title)
        title.setObjectName("catItemTitle")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        title.setMinimumWidth(0)
        title.setFixedHeight(40)
        layout.addWidget(title)

        creator = ElidedLabel(self.item.creator_line)
        creator.setObjectName("catItemCreator")
        layout.addWidget(creator)
        condition_text = (getattr(self.item, "condition", "") or "").strip()
        if condition_text:
            condition = ElidedLabel(f"Condition: {condition_text}")
            condition.setObjectName("catItemNote")
            layout.addWidget(condition)
        if self.item.pickup_schedule_text:
            pickup = ElidedLabel(f"Pickup: {self.item.pickup_schedule_text}")
            pickup.setObjectName("catItemNote")
            layout.addWidget(pickup)
        layout.addSpacing(2)

        # School-owned / Student-owned + where to pick it up (or who shares it)
        owner_row = QHBoxLayout()
        owner_row.setSpacing(8)
        owner_row.addWidget(StatusTag(self.item.ownership_label, self.item.ownership))
        note = ElidedLabel(self.item.owner_note)
        note.setObjectName("catItemNote")
        owner_row.addWidget(note, 1)
        layout.addLayout(owner_row)

        availability_row = QHBoxLayout()
        availability_row.addWidget(
            StatusTag(self.item.availability_text, self.item.availability_tone),
            alignment=Qt.AlignVCenter,
        )
        availability_row.addStretch()
        layout.addLayout(availability_row)

    def _build_actions(self, layout: QVBoxLayout):
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self._make_request_button(), 1)
        actions.addWidget(self._make_bookmark_button())
        layout.addLayout(actions)


def _cover_tone(item: CatalogItem) -> str:
    category = CATEGORY_BY_NAME.get(item.category)
    return _TONE_BY_COVER_COLOR.get(category.cover_color if category else None, "lavender")


class ItemThumb(ItemImageSlot):
    """The small picture tile at the left of a List row (same tints as the Grid image slot)."""

    SIZE = 48

    def __init__(self, glyph: str, tone: str, parent=None):
        super().__init__(glyph, "", tone, parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        if self._paint_photo(painter, rect, 10):
            return
        painter.setBrush(self._background)
        painter.setPen(QPen(self._border, 1))
        painter.drawRoundedRect(rect, 10, 10)
        painter.setPen(self._foreground)
        font = painter.font()
        font.setPointSize(16)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, self._glyph)


# Row layouts (List view). The list picks one from the width it is given.
DENSITY_WIDE, DENSITY_COMPACT, DENSITY_TINY = "wide", "compact", "tiny"
ROW_COMPACT_BELOW = 820   # px: below this, category/ownership columns fold into one line
ROW_TINY_BELOW = 540      # px: below this, the small picture tile is dropped too


class ItemRow(CatalogItemWidget):
    """One catalog item as a compact horizontal row (List view).

    Shows exactly what the Grid card shows - name, creator, kind and category, ownership
    and pickup place, availability, Request Now and the star - plus any recorded condition.
    On narrow lists the
    category/ownership columns fold into a single muted line under the name.
    """

    def __init__(self, item: CatalogItem, parent=None):
        super().__init__(item, parent)
        self.setObjectName("catItemRow")
        self._density = DENSITY_WIDE
        self.condition = (getattr(item, "condition", "") or "").strip()
        self.setToolTip(self._tooltip())

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(14)

        self.thumb = ItemThumb(KIND_ICONS.get(item.kind, "📦"), _cover_tone(item))
        row.addWidget(self.thumb, 0, Qt.AlignVCenter)

        # name + author/brand (+ the folded details when the row is narrow)
        main = QVBoxLayout()
        main.setSpacing(2)
        main.addStretch(1)
        title = ElidedLabel(item.title)
        title.setObjectName("catItemTitle")
        main.addWidget(title)
        creator = ElidedLabel(item.creator_line)
        creator.setObjectName("catItemCreator")
        main.addWidget(creator)
        self.meta_line = ElidedLabel(self._folded_text())
        self.meta_line.setObjectName("catItemNote")
        self.meta_line.hide()
        main.addWidget(self.meta_line)
        main.addStretch(1)
        row.addLayout(main, 5)

        # kind + category (+ condition, when recorded)
        self.category_cell = QWidget()
        cell = QVBoxLayout(self.category_cell)
        cell.setContentsMargins(0, 0, 0, 0)
        cell.setSpacing(2)
        cell.addStretch(1)
        category = ElidedLabel(f"{item.kind} · {item.category_label}")
        category.setObjectName("catRowCell")
        cell.addWidget(category)
        if self.condition:
            condition = ElidedLabel(f"Condition: {self.condition}")
            condition.setObjectName("catItemNote")
            cell.addWidget(condition)
        cell.addStretch(1)
        row.addWidget(self.category_cell, 3)

        # ownership + pickup place / sharer
        self.owner_cell = QWidget()
        owner = QVBoxLayout(self.owner_cell)
        owner.setContentsMargins(0, 0, 0, 0)
        owner.setSpacing(3)
        owner.addStretch(1)
        owner.addWidget(StatusTag(item.ownership_label, item.ownership), 0, Qt.AlignLeft)
        note = ElidedLabel(item.owner_note)
        note.setObjectName("catItemNote")
        owner.addWidget(note)
        if item.pickup_schedule_text:
            pickup = ElidedLabel(f"Pickup: {item.pickup_schedule_text}")
            pickup.setObjectName("catItemNote")
            owner.addWidget(pickup)
        owner.addStretch(1)
        row.addWidget(self.owner_cell, 3)

        # availability (a fixed-width column keeps the tags lined up from row to row)
        availability = QWidget()
        availability.setFixedWidth(136)
        avail_layout = QHBoxLayout(availability)
        avail_layout.setContentsMargins(0, 0, 0, 0)
        avail_layout.addWidget(StatusTag(item.availability_text, item.availability_tone),
                               0, Qt.AlignVCenter)
        avail_layout.addStretch(1)
        row.addWidget(availability, 0, Qt.AlignVCenter)

        # the same actions as the Grid card
        request = self._make_request_button()
        request.setFixedWidth(112)
        row.addWidget(request, 0, Qt.AlignVCenter)
        row.addWidget(self._make_bookmark_button(), 0, Qt.AlignVCenter)

    # ---------- text ----------
    def _tooltip(self) -> str:
        item = self.item
        lines = [item.title, item.creator_line, f"{item.kind} · {item.category_label}",
                 f"{item.ownership_label} · {item.owner_note}", item.availability_text]
        if self.condition:
            lines.append(f"Condition: {self.condition}")
        return "\n".join(lines)

    def _folded_text(self) -> str:
        item = self.item
        parts = [f"{item.kind} · {item.category_label}", item.ownership_label, item.owner_note]
        if self.condition:
            parts.append(f"Condition: {self.condition}")
        return "  ·  ".join(parts)

    # ---------- width-dependent layout ----------
    @property
    def density(self) -> str:
        return self._density

    def set_density(self, density: str):
        if density == self._density:
            return
        self._density = density
        folded = density != DENSITY_WIDE
        self.category_cell.setVisible(not folded)
        self.owner_cell.setVisible(not folded)
        self.meta_line.setVisible(folded)
        self.thumb.setVisible(density != DENSITY_TINY)


class ItemList(QWidget):
    """Stacks ItemRows one under another and tells them how much room there is.

    Like AdaptiveGrid it can hold any widgets (set_widgets), hides the ones that are not
    wanted, and lets the scroll area shrink it freely. Rows get a layout (wide / compact /
    tiny) from THIS widget's width, so a row can never be forced wider than the window.
    """

    def __init__(self, spacing: int = 10, parent=None):
        super().__init__(parent)
        self._widgets = []
        self._density = DENSITY_WIDE
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(spacing)

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def set_widgets(self, widgets):
        keep = {id(widget) for widget in widgets}
        for widget in self._widgets:
            if id(widget) not in keep:
                widget.hide()
        while self._layout.count():
            self._layout.takeAt(0)  # detach from the layout; widgets stay alive
        self._widgets = list(widgets)
        for widget in self._widgets:
            self._layout.addWidget(widget)
            widget.show()
        self._apply_density()

    @staticmethod
    def density_for_width(width: int) -> str:
        if width < ROW_TINY_BELOW:
            return DENSITY_TINY
        if width < ROW_COMPACT_BELOW:
            return DENSITY_COMPACT
        return DENSITY_WIDE

    @property
    def density(self) -> str:
        return self._density

    def resizeEvent(self, event):
        super().resizeEvent(event)
        density = self.density_for_width(self.width())
        if density != self._density:
            self._density = density
            self._apply_density()

    def _apply_density(self):
        for widget in self._widgets:
            if isinstance(widget, ItemRow):
                widget.set_density(self._density)


# ======================================================================
# 4. FILTER PANEL (left side)
# ======================================================================
class FlowLayout(QLayout):
    """Left-to-right layout that wraps onto new lines when the width runs out
    (used for the filter chips, whose widths differ)."""

    def __init__(self, parent=None, spacing: int = 8):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line_height = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > area.right() + 1 and line_height > 0:
                x = area.x()
                y += line_height + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class FilterChip(QFrame):
    """A small removable tag for one active filter, e.g. 'School-Owned  ×'."""

    remove_clicked = Signal(str)  # which filter: "category", "ownership", ...

    def __init__(self, filter_key: str, text: str, parent=None):
        super().__init__(parent)
        self.filter_key = filter_key
        self.setObjectName("catChip")
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 3, 4, 3)
        row.setSpacing(4)
        self.label = QLabel(text)
        self.label.setObjectName("catChipText")
        row.addWidget(self.label)
        self.remove_button = QToolButton()
        self.remove_button.setObjectName("catChipRemove")
        self.remove_button.setText("×")
        self.remove_button.setCursor(Qt.PointingHandCursor)
        self.remove_button.setToolTip(f"Remove filter: {text}")
        self.remove_button.setAccessibleName(f"Remove filter {text}")
        self.remove_button.clicked.connect(lambda: self.remove_clicked.emit(self.filter_key))
        row.addWidget(self.remove_button)


class FilterBar(QFrame):
    """Step 18: compact horizontal filters - Category, Ownership, Availability (+ Collection).

    It remembers the current choices and emits `filters_changed` whenever one of them
    changes. It knows nothing about items or cards: the screen feeds the choices into the
    shared `filter_items` pipeline. Below the dropdowns, removable chips show every filter
    that is not on its default, with a "Clear all filters" link (it resets the dropdown
    filters only - never the search text or the Grid/List choice).

    Collection is the existing Step 16 'collections' filter, kept as a fourth dropdown so
    no existing function is lost.
    """

    filters_changed = Signal()
    clear_requested = Signal()

    CATEGORY_DEFAULT = "All Categories"
    OWNERSHIP_DEFAULT = "All Owners"
    AVAILABILITY_DEFAULT = "Any Status"
    COLLECTION_DEFAULT = "All Collections"

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setObjectName("catFilterBar")
        self._combos = {}      # filter key -> QComboBox
        self._defaults = {}    # filter key -> label of the default choice
        self._build_ui(items)

    # ---------- the current choices (same names the old panel used) ----------
    @property
    def category(self) -> str:
        return self._combos["category"].currentData()

    @property
    def ownership(self) -> str:
        return self._combos["ownership"].currentData()

    @property
    def availability(self) -> str:
        return self._combos["availability"].currentData()

    @property
    def collection(self):
        return self._combos["collection"].currentData()

    @property
    def available_only(self) -> bool:
        return self.availability == AVAILABILITY_AVAILABLE

    # ---------- building ----------
    @staticmethod
    def category_options(items):
        """Real categories only: the catalog's own list first, then any other category
        that actually appears on an item. Nothing is invented."""
        names = [category.name for category in CATEGORIES]
        for item in items:
            if isinstance(item.category, str) and item.category.strip() \
                    and item.category not in names:
                names.append(item.category)
        return names

    def _build_ui(self, items):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.dropdown_row = AdaptiveGrid(min_item_width=170, spacing=10)
        outer.addWidget(self.dropdown_row)

        category_choices = [(self.CATEGORY_DEFAULT, ALL_CATEGORIES)] + [
            (name, name) for name in self.category_options(items)]
        ownership_choices = [
            (self.OWNERSHIP_DEFAULT, OWNERSHIP_ALL),
            ("School-Owned", OWNERSHIP_SCHOOL),
            ("Student-Owned", OWNERSHIP_STUDENT),
        ]
        availability_choices = [
            (self.AVAILABILITY_DEFAULT, AVAILABILITY_ANY),
            ("Available", AVAILABILITY_AVAILABLE),
            ("Unavailable", AVAILABILITY_UNAVAILABLE),
        ]
        collection_choices = [(self.COLLECTION_DEFAULT, None)] + [
            (collection.name, collection.name) for collection in COLLECTIONS]
        boxes = [
            self._make_dropdown("category", "Category", category_choices),
            self._make_dropdown("ownership", "Ownership", ownership_choices),
            self._make_dropdown("availability", "Availability", availability_choices),
            self._make_dropdown("collection", "Collection", collection_choices),
        ]
        self.dropdown_row.set_widgets(boxes)

        # Chips row: only visible while at least one filter is selected.
        self.chip_area = QWidget()
        self.chip_area.setObjectName("catChipArea")
        chip_row = QHBoxLayout(self.chip_area)
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(10)
        self.chip_flow_host = QWidget()
        self.chip_flow = FlowLayout(self.chip_flow_host, spacing=8)
        chip_row.addWidget(self.chip_flow_host, 1)
        self.clear_button = QPushButton("Clear all filters")
        self.clear_button.setObjectName("catLink")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self.clear_requested.emit)
        chip_row.addWidget(self.clear_button, 0, Qt.AlignTop)
        outer.addWidget(self.chip_area)
        self.chip_area.hide()
        self._refresh_chips()

    def _make_dropdown(self, key: str, caption: str, choices) -> QWidget:
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        label = QLabel(caption)
        label.setObjectName("catFilterCaption")
        column.addWidget(label)
        combo = QComboBox()
        combo.setObjectName("catFilterCombo")
        combo.setCursor(Qt.PointingHandCursor)
        combo.setAccessibleName(f"{caption} filter")
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(10)
        for text, value in choices:
            combo.addItem(text, value)
        combo.currentIndexChanged.connect(lambda _index: self._on_changed())
        column.addWidget(combo)
        self._combos[key] = combo
        self._defaults[key] = choices[0][0]
        return box

    # ---------- reacting ----------
    def _restyle_combos(self):
        for combo in self._combos.values():
            combo.setProperty("active", combo.currentIndex() != 0)
            combo.style().unpolish(combo)
            combo.style().polish(combo)

    def _on_changed(self):
        self._restyle_combos()
        self._refresh_chips()
        self.filters_changed.emit()

    def _active_filters(self):
        """[(key, chip text)] for every dropdown that is not on its default."""
        active = []
        for key, combo in self._combos.items():
            if combo.currentIndex() != 0:
                active.append((key, combo.currentText()))
        return active

    def _refresh_chips(self):
        while self.chip_flow.count():
            item = self.chip_flow.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()          # gone from the screen right now, not at the next event loop
                widget.setParent(None)
                widget.deleteLater()
        active = self._active_filters()
        for key, text in active:
            chip = FilterChip(key, text)
            chip.remove_clicked.connect(self.remove_filter)
            self.chip_flow.addWidget(chip)
        self.chip_area.setVisible(bool(active))
        self.chip_flow_host.updateGeometry()

    def chips(self):
        """The chips currently shown, left to right (handy for tests)."""
        return [self.chip_flow.itemAt(i).widget() for i in range(self.chip_flow.count())]

    def combo(self, key: str) -> QComboBox:
        return self._combos[key]

    def remove_filter(self, key: str):
        """Put ONE dropdown back to its default; the others keep their choices."""
        if key in self._combos and self._combos[key].currentIndex() != 0:
            self._combos[key].setCurrentIndex(0)  # triggers chips + filters_changed

    # ---------- used by the screen ----------
    def has_active_filters(self) -> bool:
        return bool(self._active_filters())

    def reset(self):
        """Put every dropdown back to its default (does not emit a signal)."""
        for combo in self._combos.values():
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self._restyle_combos()
        self._refresh_chips()


def _make_search_icon(color: str = "#8C92B5") -> QIcon:
    """A small magnifier drawn in code (no image file, so nothing can be missing)."""
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.8)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawEllipse(QRectF(2, 2, 10, 10))
    painter.drawLine(11, 11, 15, 15)
    painter.end()
    return QIcon(pixmap)


def _make_view_icon(mode: str) -> QIcon:
    """Grid (2 x 2 squares) or List (three lines with bullets), drawn in code like the sidebar's
    outline icons: a quiet color normally, the accent color while that view is selected."""
    scale = 2
    icon = QIcon()
    for color, state in ((tk.COLOR_TEXT_SECONDARY, QIcon.Off), (tk.COLOR_ACCENT_HOVER, QIcon.On)):
        pixmap = QPixmap(18 * scale, 18 * scale)
        pixmap.fill(Qt.transparent)
        pixmap.setDevicePixelRatio(scale)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(color), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if mode == VIEW_GRID:
            for x in (2.5, 10.5):
                for y in (2.5, 10.5):
                    painter.drawRoundedRect(QRectF(x, y, 5, 5), 1.2, 1.2)
        else:
            for y in (4, 9, 14):
                painter.drawPoint(3, y)
                painter.drawLine(7, y, 15, y)
        painter.end()
        icon.addPixmap(pixmap, QIcon.Normal, state)
        icon.addPixmap(pixmap, QIcon.Active, state)
    return icon


# ======================================================================
# 5. CATALOG SCREEN
# ======================================================================
class CatalogScreen(QWidget):
    """Browse Catalog: header + search, filter panel, and a grid of item cards.

    `item_selected` is emitted when a card is clicked. The Dashboard opens the
    shared Item Details page for both sample and published listings.

    Layout map: the results column is
        header (title + search)  ->  results bar (`self.results_bar`)  ->  results
    The results bar holds the result count and (Step 17) the Grid/List toggle; active-filter
    chips are meant to join that row later. The results are shown either as a grid of cards
    (`self.grid`) or as a list of rows (`self.list_view`) - the SAME items, the SAME filtering
    and the SAME item handlers; only the layout of each item differs.
    """

    item_selected = Signal(object)
    # Sent when the student clicks a card's bookmark button (NOT when
    # set_bookmarked_items() syncs the screen from outside).
    bookmark_toggled = Signal(object, bool)  # (CatalogItem, is_bookmarked)
    # Sent when Request Now is clicked on an AVAILABLE item. It does not
    # bookmark anything and does not send item_selected.
    direct_request_requested = Signal(object)
    # Step 17: sent when the student picks Grid or List (not when set_view_mode(emit=False)
    # restores a saved choice). The value is "grid" or "list".
    view_mode_changed = Signal(str)

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self.setObjectName("catalogScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(CATALOG_V2_STYLESHEET + HEADER_QSS)  # affects only this screen

        self._items = list(items) if items is not None else list(SAMPLE_ITEMS)
        self._bookmarked = set()  # saved CatalogItems (a set cannot hold duplicates)
        self._cards = []
        self._rows = []
        self._build_item_widgets()
        self._visible_cards = []
        self._visible_rows = []
        self._view_mode = DEFAULT_CATALOG_VIEW

        self._build_ui()
        self._apply_filters()

    @property
    def visible_items(self):
        """The items currently shown (handy for testing)."""
        return [card.item for card in self._visible_cards]

    @property
    def bookmarked_items(self):
        """The saved items, in catalog order (handy for testing)."""
        return [card.item for card in self._cards if card.item in self._bookmarked]

    @property
    def view_mode(self) -> str:
        """'grid' or 'list' (Step 17)."""
        return self._view_mode

    @property
    def visible_rows(self):
        """The List rows that match the current search and filters (handy for testing)."""
        return list(self._visible_rows)

    def set_primary_photos(self, photo_paths):
        """Step 21: {listing_key: file path} of each listing's primary photo.

        Listings not in the dict (or whose file cannot be read) keep the placeholder.
        Cards and rows are updated in place, so filters, view and scroll are untouched."""
        photo_paths = photo_paths or {}
        for widget in self._cards + self._rows:
            widget.set_photo(photo_paths.get(widget.item.listing_key))

    def set_items(self, items):
        """Replace Catalog data while retaining search, filters, bookmarks and view mode."""
        search = self.search_input.text()
        filters = {
            "category": self.filter_panel.category,
            "ownership": self.filter_panel.ownership,
            "availability": self.filter_panel.availability,
            "collection": self.filter_panel.collection,
        }
        scroll_position = self.scroll_position()
        bookmarked_keys = {item.listing_key for item in self._bookmarked}
        old_widgets = self._cards + self._rows
        self._items = list(items)

        old_filter = self.filter_panel
        self.filter_panel = FilterBar(self._items)
        self.filter_panel.filters_changed.connect(self._apply_filters)
        self.filter_panel.clear_requested.connect(self._clear_filters)
        self._content_layout.replaceWidget(old_filter, self.filter_panel)
        old_filter.deleteLater()
        for key, value in filters.items():
            combo = self.filter_panel.combo(key)
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)

        self.search_input.setText(search)
        self.sticky_search_input.setText(search)
        self._bookmarked = set()
        self._build_item_widgets()
        self._bookmarked = {
            item for item in self._items if item.listing_key in bookmarked_keys
        }
        for widget in self._cards + self._rows:
            widget.set_bookmarked(widget.item in self._bookmarked)
        self._apply_filters()
        for widget in old_widgets:
            widget.deleteLater()
        self.restore_scroll_position(scroll_position)

    def _build_item_widgets(self):
        self._cards = [ItemCard(item) for item in self._items]
        self._rows = [ItemRow(item) for item in self._items]
        for widget in self._cards + self._rows:
            widget.clicked.connect(self.item_selected.emit)
            widget.bookmark_toggled.connect(self._on_card_bookmark_toggled)
            widget.request_clicked.connect(self._on_card_request_clicked)

    def set_bookmarked_items(self, items):
        """Show exactly these items as saved. Sends no bookmark_toggled signal.

        Items that are not in this catalog are ignored. Cards and rows are built once
        and only hidden by filters, so the saved state survives searching,
        filtering, scrolling and switching between Grid and List.
        """
        wanted = set(items)
        wanted_keys = {item.listing_key for item in wanted}
        self._bookmarked = {
            card.item for card in self._cards if card.item.listing_key in wanted_keys
        }
        for widget in self._cards + self._rows:
            widget.set_bookmarked(widget.item in self._bookmarked)

    # ---------- Step 19: keep the place when the student opens an item and comes back ----------
    def scroll_position(self) -> int:
        return self.catalog_scroll.verticalScrollBar().value()

    def restore_scroll_position(self, value: int):
        """Scroll back to `value` (also again after layout settles, so it sticks)."""
        bar = self.catalog_scroll.verticalScrollBar()
        bar.setValue(value)
        QTimer.singleShot(0, lambda: bar.setValue(value))

    def _on_card_request_clicked(self, item):
        if item.is_available:  # second safety check; forwards exactly once per click
            self.direct_request_requested.emit(item)

    def _on_card_bookmark_toggled(self, item, is_bookmarked: bool):
        """Used by BOTH views. Keeps the card and the row of this item showing the same star."""
        if is_bookmarked:
            self._bookmarked = {
                existing for existing in self._bookmarked
                if existing.listing_key != item.listing_key
            }
            self._bookmarked.add(item)
        else:
            self._bookmarked = {
                existing for existing in self._bookmarked
                if existing.listing_key != item.listing_key
            }
        for widget in self._cards + self._rows:
            if widget.item.listing_key == item.listing_key:
                widget.set_bookmarked(is_bookmarked)  # no signal, so no echo
        self.bookmark_toggled.emit(item, is_bookmarked)

    # ---------- building ----------
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 24)  # same page margins as the Dashboard
        root.setSpacing(20)

        # Step 18: horizontal filters now live inside the results column (below the search).
        self.filter_panel = FilterBar(self._items)
        self.filter_panel.filters_changed.connect(self._apply_filters)
        self.filter_panel.clear_requested.connect(self._clear_filters)

        # The compact search floats at the top only AFTER the header scrolls out.
        right = QVBoxLayout()
        right.setSpacing(10)
        self.sticky_search_bar = self._build_sticky_search_bar()
        right.addWidget(self.sticky_search_bar)
        self.sticky_search_bar.hide()
        right.addWidget(self._build_results_area(), 1)
        root.addLayout(right, 1)

    def _make_search_field(self, object_name: str, placeholder: str, on_change) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName(object_name)
        field.setPlaceholderText(placeholder)
        field.setClearButtonEnabled(True)
        field.addAction(_make_search_icon(), QLineEdit.LeadingPosition)
        field.textChanged.connect(on_change)
        return field

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("catHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(2, 6, 2, 10)
        layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(16)
        text_column = QVBoxLayout()
        text_column.setSpacing(4)

        tag = QLabel("Browse available school and student listings")
        tag.setObjectName("catTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        text_column.addWidget(tag, alignment=Qt.AlignLeft | Qt.AlignTop)
        text_column.addSpacing(4)

        title = QLabel(accent_html("Browse Catalog", "Catalog"))
        title.setObjectName("catTitle")
        text_column.addWidget(title)

        subtitle = QLabel(
            "Find school items and published listings shared by fellow students.")
        subtitle.setObjectName("catSubtitle")
        subtitle.setWordWrap(True)
        text_column.addWidget(subtitle)
        top_row.addLayout(text_column, 1)

        layout.addLayout(top_row)

        # Main search bar: lives at the bottom of the scrolling header.
        self.search_input = self._make_search_field(
            "catSearch", "Search by title, author, brand, or category", self._on_search_changed
        )
        layout.addWidget(self.search_input)
        return header

    def _build_sticky_search_bar(self) -> QFrame:
        """Compact search bar shown only while the main header is offscreen."""
        bar = QFrame()
        bar.setObjectName("catStickyBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(10)
        label = QLabel("Search")
        label.setObjectName("catStickyLabel")
        row.addWidget(label)
        self.sticky_search_input = self._make_search_field(
            "catSearchCompact", "Search books, gadgets, tools...", self._on_sticky_search_changed
        )
        row.addWidget(self.sticky_search_input, 1)
        return bar

    def _build_results_area(self) -> QScrollArea:
        # This ONE scroll area contains the header AND the item cards.
        # When you scroll, the entire header moves upward out of view.
        scroll = QScrollArea()
        scroll.setObjectName("catScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("catContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 6, 8)
        layout.setSpacing(14)

        self.data_error_label = QLabel()
        self.data_error_label.setObjectName("catDataError")
        self.data_error_label.setStyleSheet(f"color: {tk.COLOR_DANGER};")
        self.data_error_label.setWordWrap(True)
        self.data_error_label.hide()
        layout.addWidget(self.data_error_label)
        layout.addWidget(self._build_header())
        layout.addWidget(self.filter_panel)
        self._content_layout = layout

        # Results bar: result count now; Grid/List toggle and filter chips join this row later.
        self.results_bar = QHBoxLayout()
        self.results_bar.setContentsMargins(2, 0, 2, 0)
        self.result_label = QLabel("")
        self.result_label.setObjectName("catResultLabel")
        self.results_bar.addWidget(self.result_label)
        self.results_bar.addStretch()
        self.results_bar.addWidget(self._build_view_toggle(), 0, Qt.AlignVCenter)
        layout.addLayout(self.results_bar)

        self.grid = AdaptiveGrid(min_item_width=CARD_MIN_WIDTH, spacing=CARD_SPACING)
        layout.addWidget(self.grid)
        self.list_view = ItemList(spacing=10)
        layout.addWidget(self.list_view)
        self.list_view.hide()  # Grid is the default; a saved preference may switch it

        self.empty_state = self._build_empty_state()
        layout.addWidget(self.empty_state)
        layout.addStretch()

        scroll.setWidget(content)
        self.catalog_scroll = scroll
        self.scroll_content = content
        scroll.verticalScrollBar().valueChanged.connect(self._update_sticky_search)
        return scroll

    def show_data_error(self, message: str):
        self.data_error_label.setText(message)
        self.data_error_label.setVisible(bool(message))

    def _build_view_toggle(self) -> QFrame:
        """Two compact, exclusive buttons: Grid and List."""
        box = QFrame()
        box.setObjectName("catViewToggle")
        row = QHBoxLayout(box)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self.grid_view_button = self._make_view_button(VIEW_GRID, "Grid view")
        self.list_view_button = self._make_view_button(VIEW_LIST, "List view")
        row.addWidget(self.grid_view_button)
        row.addWidget(self.list_view_button)
        self.grid_view_button.setChecked(True)  # matches the default mode
        self.view_toggle = box
        return box

    def _make_view_button(self, mode: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("catViewButton")
        button.setCheckable(True)
        button.setFixedSize(34, 28)
        button.setIcon(_make_view_icon(mode))
        button.setIconSize(QSize(18, 18))
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        self._view_group.addButton(button)
        button.clicked.connect(lambda _checked=False, mode=mode: self.set_view_mode(mode))
        return button

    def set_view_mode(self, mode: str, emit: bool = True):
        """Show the results as a Grid of cards or a List of rows.

        Nothing else changes: the search text, the filters, the matching items, the saved
        stars and the scroll position all stay as they are. An unknown value falls back to
        Grid. `emit=False` restores a saved choice without announcing it.
        """
        if mode not in VIEW_MODES:
            mode = DEFAULT_CATALOG_VIEW
        changed = mode != self._view_mode
        self._view_mode = mode
        self.grid_view_button.setChecked(mode == VIEW_GRID)
        self.list_view_button.setChecked(mode == VIEW_LIST)
        if changed:
            self._show_results()
            if emit:
                self.view_mode_changed.emit(mode)

    def _show_results(self):
        """Put the ALREADY filtered items into the active view (no filtering happens here)."""
        has_results = bool(self._visible_cards)
        use_grid = self._view_mode == VIEW_GRID
        content = self.scroll_content
        content.setUpdatesEnabled(False)  # one repaint, so switching never flickers
        try:
            if use_grid:
                self.grid.set_widgets(self._visible_cards)
            else:
                self.list_view.set_widgets(self._visible_rows)
            self.grid.setVisible(has_results and use_grid)
            self.list_view.setVisible(has_results and not use_grid)
            self.empty_state.setVisible(not has_results)
        finally:
            content.setUpdatesEnabled(True)

    def _build_empty_state(self) -> QFrame:
        box = QFrame()
        box.setObjectName("catEmpty")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignHCenter)

        # Curious mascot appears ONLY when the search/filters find nothing.
        curious_pixmap = QPixmap()  # Kit appears on the Dashboard only
        icon = QLabel()
        icon.setObjectName("catEmptyIcon")
        icon.setAlignment(Qt.AlignCenter)
        if not curious_pixmap.isNull():
            icon.setPixmap(curious_pixmap.scaled(
                100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        else:
            icon.setText("🔍")  # missing file should never crash the app
        layout.addWidget(icon)

        self.empty_title = QLabel("No items found")
        self.empty_title.setObjectName("catEmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_title)

        self.empty_text = QLabel("Try a different search word, or clear some filters.")
        self.empty_text.setObjectName("catEmptyText")
        self.empty_text.setAlignment(Qt.AlignCenter)
        self.empty_text.setWordWrap(True)
        layout.addWidget(self.empty_text)
        layout.addSpacing(6)

        self.empty_button = QPushButton("Clear search and filters")
        self.empty_button.setObjectName("catPrimaryButton")
        self.empty_button.setCursor(Qt.PointingHandCursor)
        self.empty_button.clicked.connect(self._clear_everything)
        layout.addWidget(self.empty_button, alignment=Qt.AlignHCenter)
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

    def _clear_filters(self):
        """'Clear all filters': resets the dropdown filters ONLY. The search text and the
        Grid/List choice stay exactly as they are."""
        self.filter_panel.reset()
        self._apply_filters()

    def _clear_everything(self):
        """Used by the empty-state button: clears the search text AND the filters."""
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
            availability=self.filter_panel.availability,
        ))
        self._visible_cards = [card for card in self._cards if card.item in matches]
        self._visible_rows = [row for row in self._rows if row.item in matches]
        self._show_results()  # grid or list, whichever is active

        total = len(self._items)
        shown = len(self._visible_cards)
        if total == 0:
            # Nothing is listed at all, so "clear filters" would be misleading.
            self.result_label.setText("No items to show yet")
            self.empty_title.setText("The catalog is empty")
            self.empty_text.setText("Nothing has been listed yet. Please check back soon.")
            self.empty_button.setVisible(False)
        elif shown == 0:
            self.result_label.setText("No items match your search")
            self.empty_title.setText("No items found")
            self.empty_text.setText("Try a different search word, or clear some filters.")
            self.empty_button.setVisible(True)
        else:
            self.result_label.setText(f"Showing {shown} of {total} items")


# ======================================================================
# 6. OLD PIXEL POP STYLES - NOT used by the Catalog any more (Step 16).
#    Still imported by My List, My Requests, My Borrowings, Reservations,
#    Notifications and Settings, so leave this alone until those are redesigned.
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

/* ---------- Bookmark button on item cards ---------- */
QPushButton#catalogBookmarkButton {{
    background-color: white;
    color: {PERIWINKLE};
    border: 2px solid {PERIWINKLE};
    border-radius: 12px;
    padding: 0px;
    font-size: 16px;
    font-weight: bold;
}}

QPushButton#catalogBookmarkButton:hover {{
    background-color: {SOFT_LAVENDER};
    color: {NAVY};
    border-color: {NAVY};
}}

QPushButton#catalogBookmarkButton:checked {{
    background-color: {PINK};
    color: {NAVY};
    border: 2px solid {NAVY};
}}

QPushButton#catalogBookmarkButton:checked:hover {{
    background-color: #F7BDD3;
}}

/* ---------- Request Now button on item cards ---------- */
QPushButton#catalogRequestButton {{
    background-color: {MINT};
    color: {NAVY};
    border: 2px solid {NAVY};
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: bold;
}}

QPushButton#catalogRequestButton:hover {{
    background-color: {PINK};
}}

QPushButton#catalogRequestButton:pressed {{
    background-color: {CREAM};
}}

QPushButton#catalogRequestButton:disabled {{
    background-color: #ECEDFA;
    color: #B5B7D6;
    border: 2px dashed #B5B7D6;
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
