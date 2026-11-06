"""The floating app container (Step 30A).

FloatingShell holds the sidebar and the pages. Child widgets draw square backgrounds, which
a rounded frame cannot clip by itself, so a see-through overlay sits on top and paints ONLY
the four outside corners in the window color (anti-aliased) plus a hairline outline. It
ignores the mouse, so dragging sidebar icons and clicking pages work exactly as before.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QWidget

from app import design_tokens as tk
from app.floating_layout import SHELL_RADIUS


class _CornerOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("floatingShellOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        outer = QPainterPath()
        outer.addRect(rect)
        inner = QPainterPath()
        inner.addRoundedRect(rect, SHELL_RADIUS, SHELL_RADIUS)
        painter.fillPath(outer.subtracted(inner), QBrush(QColor(tk.COLOR_BG_WINDOW)))

        outline = QColor(tk.COLOR_BORDER)
        outline.setAlpha(150)
        painter.setPen(QPen(outline, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), SHELL_RADIUS, SHELL_RADIUS)


class FloatingShell(QFrame):
    """A rounded container. Give it a layout; the corner overlay is handled here."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("floatingShell")
        self._overlay = _CornerOverlay(self)
        self._overlay.setGeometry(self.rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())
        self._overlay.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        self._overlay.raise_()

    def raise_overlay(self):
        """Call after adding children, so the corners stay on top."""
        self._overlay.raise_()
