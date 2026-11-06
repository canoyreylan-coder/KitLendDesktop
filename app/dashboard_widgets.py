"""Small reusable building blocks for the dashboard (cards, rows, pills...).

Colors and fonts are NOT set here. Each widget only gets an objectName (and
sometimes a "property"), and the matching style lives in theme.py (QSS).
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class ElidedLabel(QLabel):
    """A one-line label that shows '...' instead of forcing the layout wider.

    Normal labels refuse to be narrower than their text, which makes cards
    overflow on small windows. This one shortens itself to fit (hover to see
    the full text).
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        self._apply_elide()

    def setText(self, text: str):
        self._full_text = text
        self._apply_elide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        shown = self.fontMetrics().elidedText(
            self._full_text, Qt.ElideRight, max(self.width(), 0)
        )
        if shown != self.text():
            super().setText(shown)
        self.setToolTip(self._full_text if shown != self._full_text else "")


class IconBadge(QLabel):
    """A small rounded square holding an emoji. accent: mint/pink/purple/cream."""

    def __init__(self, glyph: str, accent: str = "mint", size: int = 40,
                 big: bool = False, parent=None):
        super().__init__(glyph, parent)
        self.setObjectName("iconBadge")
        self.setProperty("accent", accent)
        self.setProperty("big", big)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)


class StatusPill(QLabel):
    """A tiny colored tag such as 'Due tomorrow'. tone: mint/pink/purple/alert."""

    def __init__(self, text: str, tone: str = "mint", parent=None):
        super().__init__(text, parent)
        self.setObjectName("statusPill")
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class ReflowGrid(QWidget):
    """Lays widgets out in columns and re-arranges them when the window resizes.

    Wide window -> side by side. Narrow window -> stacked. This is what makes
    the dashboard comfortable on both big and small laptop screens.
    """

    def __init__(self, widgets, min_item_width: int, spacing: int = 16, parent=None):
        super().__init__(parent)
        self._widgets = list(widgets)
        self._min_item_width = min_item_width
        self._spacing = spacing
        self._columns = 0

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)
        self._relayout(len(self._widgets))  # start with everything in one row

    def minimumSizeHint(self):
        # Let the scroll area shrink us freely; resizeEvent re-flows the items.
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout(self._columns_for_width(self.width()))

    def _columns_for_width(self, width: int) -> int:
        count = len(self._widgets)
        columns = (width + self._spacing) // (self._min_item_width + self._spacing)
        columns = max(1, min(columns, count))
        # Avoid ugly leftovers (e.g. 3 + 1 cards): step down to an even split.
        while columns > 1 and count % columns != 0:
            columns -= 1
        return columns

    def _relayout(self, columns: int):
        if columns == self._columns or columns < 1:
            return
        self._columns = columns
        while self._grid.count():
            self._grid.takeAt(0)  # detach from the layout (widgets stay alive)
        for index, widget in enumerate(self._widgets):
            self._grid.addWidget(widget, index // columns, index % columns)
        for column in range(len(self._widgets)):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)


class DashCard(QFrame):
    """A rounded cream card with a title, optional subtitle and 'View all' link."""

    action_clicked = Signal()

    def __init__(self, title: str, subtitle: str = "", action_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("dashCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 18, 22, 20)
        outer.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        titles.addWidget(title_label)
        self._subtitle_label = None
        if subtitle:
            subtitle_label = ElidedLabel(subtitle)
            subtitle_label.setObjectName("cardSubtitle")
            titles.addWidget(subtitle_label)
            self._subtitle_label = subtitle_label
        header.addLayout(titles, 1)

        if action_text:
            action = QPushButton(action_text)
            action.setObjectName("linkButton")
            action.setCursor(Qt.PointingHandCursor)
            action.clicked.connect(self.action_clicked.emit)
            header.addWidget(action, alignment=Qt.AlignTop)
        outer.addLayout(header)

        self._rows = QVBoxLayout()
        self._rows.setSpacing(10)
        outer.addLayout(self._rows)
        outer.addStretch()  # keeps rows at the top when the card is taller

    def add_row(self, widget: QWidget):
        self._rows.addWidget(widget)

    def set_subtitle(self, text: str):
        """Change the subtitle (only for cards that were created with one)."""
        if self._subtitle_label is not None:
            self._subtitle_label.setText(text)

    def clear_rows(self):
        """Remove every row and note so the card can be refilled."""
        while self._rows.count():
            widget = self._rows.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def add_note(self, text: str):
        note = QLabel(text)
        note.setObjectName("mutedNote")
        note.setWordWrap(True)
        self._rows.addWidget(note)


class ListRow(QFrame):
    """One row inside a card: [icon] title / meta ... [pill] / optional progress."""

    def __init__(self, title: str, meta: str = "", icon: str = "", icon_accent: str = "mint",
                 pill_text: str = "", pill_tone: str = "mint",
                 progress: int | None = None, unread: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("rowItem")
        self.setProperty("unread", unread)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        if icon:
            layout.addWidget(IconBadge(icon, icon_accent, 40), alignment=Qt.AlignVCenter)

        text_column = QVBoxLayout()
        text_column.setSpacing(4)

        title_label = ElidedLabel(title)
        title_label.setObjectName("rowTitle")
        text_column.addWidget(title_label)

        if meta or pill_text:
            bottom = QHBoxLayout()
            bottom.setSpacing(8)
            meta_label = ElidedLabel(meta)
            meta_label.setObjectName("rowMeta")
            bottom.addWidget(meta_label, 1)
            if pill_text:
                bottom.addWidget(StatusPill(pill_text, pill_tone))
            text_column.addLayout(bottom)

        if progress is not None:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(progress)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            text_column.addWidget(bar)

        layout.addLayout(text_column, 1)


class StatCard(QFrame):
    """A clickable summary tile: icon + big number + label + small hint."""

    clicked = Signal()

    def __init__(self, icon: str, accent: str, number: int, label: str, hint: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(IconBadge(icon, accent, 44))
        number_label = QLabel(str(number))
        number_label.setObjectName("statNumber")
        self.number_label = number_label
        top.addWidget(number_label)
        top.addStretch()
        layout.addLayout(top)

        label_widget = ElidedLabel(label)
        label_widget.setObjectName("statLabel")
        hint_widget = ElidedLabel(hint)
        hint_widget.setObjectName("statHint")
        self.hint_label = hint_widget
        layout.addWidget(label_widget)
        layout.addWidget(hint_widget)

    def set_number(self, number: int):
        self.number_label.setText(str(number))

    def set_hint(self, hint: str):
        self.hint_label.setText(hint)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class PlaceholderPage(QWidget):
    """Friendly 'coming soon' page shown for sidebar options we haven't built yet."""

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setObjectName("dashCard")
        card.setMaximumWidth(520)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 32, 36, 30)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignHCenter)

        self.badge = IconBadge("🚧", "pink", 72, big=True)
        layout.addWidget(self.badge, alignment=Qt.AlignHCenter)

        self.title_label = QLabel("")
        self.title_label.setObjectName("placeholderTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        self.message_label = QLabel("")
        self.message_label.setObjectName("placeholderMessage")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        note = QLabel("Demo Mode - nothing here is real yet")
        note.setObjectName("pill")  # existing mint pill style from theme.py
        note.setAlignment(Qt.AlignCenter)
        layout.addWidget(note, alignment=Qt.AlignHCenter)
        layout.addSpacing(6)

        back = QPushButton("Back to Dashboard")
        back.setObjectName("mintButton")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(self.back_requested.emit)
        layout.addWidget(back, alignment=Qt.AlignHCenter)

        outer.addWidget(card)

    def set_content(self, title: str, message: str):
        self.title_label.setText(title)
        self.message_label.setText(message)
