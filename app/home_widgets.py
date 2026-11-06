"""Building blocks for the redesigned Dashboard home page (Stage 2A).

They only get object names / properties; every color lives in app/home_theme.py. They are
separate from app/dashboard_widgets.py on purpose, so the older widgets (still used by other
screens) are untouched. The attributes older tests rely on keep their names:
HomeCard._subtitle_label / ._rows and HomeStat.number_label.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.dashboard_widgets import ElidedLabel

CARD_PADDING = (20, 16, 20, 18)   # one padding for every card and tile
ROW_SPACING = 8


def _set_property(widget: QWidget, name: str, value):
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class HomePill(QLabel):
    """A small status tag. tone: lavender / pink / mint / amber / rose / muted."""

    def __init__(self, text: str, tone: str = "muted", parent=None):
        super().__init__(text, parent)
        self.setObjectName("homePill")
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class HomeDot(QLabel):
    def __init__(self, tone: str = "muted", parent=None):
        super().__init__(parent)
        self.setObjectName("homeDot")
        self.setProperty("tone", tone)
        self.setFixedSize(8, 8)


class HomeRow(QFrame):
    """One row: [dot] title / meta [progress] ........ [pill]."""

    def __init__(self, title: str, meta: str = "", pill_text: str = "", pill_tone: str = "muted",
                 progress: int | None = None, dot_tone: str = "", unread: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("homeRow")
        self.setProperty("unread", unread)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)

        if dot_tone:
            layout.addWidget(HomeDot(dot_tone), alignment=Qt.AlignVCenter)

        texts = QVBoxLayout()
        texts.setSpacing(3)
        title_label = ElidedLabel(title)
        title_label.setObjectName("homeRowTitle")
        texts.addWidget(title_label)
        if meta:
            meta_label = ElidedLabel(meta)
            meta_label.setObjectName("homeRowMeta")
            texts.addWidget(meta_label)
        if progress is not None:
            bar = QProgressBar()
            bar.setObjectName("homeProgress")
            bar.setRange(0, 100)
            bar.setValue(progress)
            bar.setTextVisible(False)
            bar.setFixedHeight(4)
            texts.addSpacing(2)
            texts.addWidget(bar)
        layout.addLayout(texts, 1)

        if pill_text:
            layout.addWidget(HomePill(pill_text, pill_tone), alignment=Qt.AlignVCenter)


class HomeCard(QFrame):
    """A dark card: title, optional subtitle and 'View all' link, then rows or a note."""

    action_clicked = Signal()

    def __init__(self, title: str, subtitle: str = "", action_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("homeCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*CARD_PADDING)
        outer.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("homeCardTitle")
        titles.addWidget(title_label)
        self._subtitle_label = None
        if subtitle:
            self._subtitle_label = ElidedLabel(subtitle)
            self._subtitle_label.setObjectName("homeCardSubtitle")
            titles.addWidget(self._subtitle_label)
        header.addLayout(titles, 1)
        if action_text:
            action = QPushButton(action_text)
            action.setObjectName("homeLink")
            action.setCursor(Qt.PointingHandCursor)
            action.clicked.connect(self.action_clicked.emit)
            header.addWidget(action, alignment=Qt.AlignTop)
        outer.addLayout(header)

        self._rows = QVBoxLayout()
        self._rows.setSpacing(ROW_SPACING)
        outer.addLayout(self._rows)
        outer.addStretch()

    def add_row(self, widget: QWidget):
        self._rows.addWidget(widget)

    def add_note(self, text: str):
        note = QLabel(text)
        note.setObjectName("homeNote")
        note.setWordWrap(True)
        self._rows.addWidget(note)

    def set_subtitle(self, text: str):
        if self._subtitle_label is not None:
            self._subtitle_label.setText(text)

    def clear_rows(self):
        while self._rows.count():
            widget = self._rows.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def set_rows(self, rows, empty_text: str, limit: int):
        """Show up to `limit` RowView items, or the empty-state note when there are none."""
        self.clear_rows()
        rows = list(rows)
        for row in rows[:limit]:
            self.add_row(HomeRow(row.title, row.meta, row.pill_text, row.pill_tone,
                                 row.progress, row.dot_tone, row.unread))
        if not rows:
            self.add_note(empty_text)
        elif len(rows) > limit:
            self.add_note(f"+ {len(rows) - limit} more. Use View all to see everything.")


class HomeStat(QFrame):
    """A clickable summary tile: small label, big number, one-line hint."""

    clicked = Signal()

    def __init__(self, label: str, number: int, hint: str, parent=None):
        super().__init__(parent)
        self.setObjectName("homeStat")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*CARD_PADDING)
        layout.setSpacing(4)
        self.label_widget = ElidedLabel(label)
        self.label_widget.setObjectName("homeStatLabel")
        layout.addWidget(self.label_widget)
        self.number_label = QLabel(str(number))
        self.number_label.setObjectName("homeStatNumber")
        layout.addWidget(self.number_label)
        self.hint_label = ElidedLabel(hint)
        self.hint_label.setObjectName("homeStatHint")
        layout.addWidget(self.hint_label)

    def set_number(self, number: int):
        self.number_label.setText(str(number))

    def set_hint(self, hint: str):
        self.hint_label.setText(hint)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
