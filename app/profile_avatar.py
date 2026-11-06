"""A round profile picture: the student's photo, or their initials when there is none (Step 28).

Painted by hand (not a QLabel with a pixmap) so it is always a clean circle. Photos are
scaled to FILL the circle and the overflow is cropped, so they are never stretched.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from app import design_tokens as tk
from app.header_style import ACCENT_LAVENDER
from app.sidebar_icons import circular_pixmap


class ProfileAvatar(QWidget):
    def __init__(self, diameter: int = 96, parent=None):
        super().__init__(parent)
        self._diameter = diameter
        self._initials = ""
        self._pixmap = None
        self.setFixedSize(diameter, diameter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAccessibleName("Profile picture")

    @property
    def has_photo(self) -> bool:
        return self._pixmap is not None

    @property
    def initials(self) -> str:
        return self._initials

    def set_initials(self, initials: str):
        self._initials = initials or ""
        self.update()

    def set_photo(self, source):
        """Show a photo (file path or QPixmap). None, or a picture that cannot be read,
        goes back to the initials."""
        self._pixmap = (circular_pixmap(source, self._diameter - 2)
                        if source is not None else None)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self._diameter - 1, self._diameter - 1)
        if self._pixmap is not None:
            painter.drawPixmap(1, 1, self._pixmap)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(tk.COLOR_BORDER_STRONG), 1))
            painter.drawEllipse(rect)
        else:
            painter.setBrush(QColor(tk.COLOR_ACCENT_SOFT))
            painter.setPen(QPen(QColor(tk.COLOR_BORDER_STRONG), 1))
            painter.drawEllipse(rect)
            painter.setPen(QColor(ACCENT_LAVENDER))
            font = QFont(self.font())
            font.setPixelSize(max(12, self._diameter // 3))
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, self._initials)
        painter.end()
