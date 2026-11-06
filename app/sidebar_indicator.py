"""A small "unread" dot for a sidebar icon (Step 29C). No numbers, no counts.

The dot is a CHILD of the icon's own button, so it moves with the icon when it is dragged in
Sidebar Editing Mode and is re-placed whenever the button is resized (the icon size changes
the button size). It ignores the mouse, so clicking or dragging the icon works exactly as before.
"""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from app import design_tokens as tk

DOT_COLOR = "#9EA3FF"       # soft lavender-blue (between periwinkle and lavender)
MIN_DOT = 8                 # px, the dot itself
RING = 2                    # px, a rail-colored ring so the dot reads cleanly over the icon


class UnreadDot(QWidget):
    """Shows a dot at the top-right corner of the icon drawn in `button`. Hidden by default."""

    def __init__(self, button):
        super().__init__(button)
        self.setObjectName("unreadDot")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)
        self._button = button
        self._watcher = _ResizeWatcher(self)
        button.installEventFilter(self._watcher)
        self.hide()
        self.reposition()

    def set_unread(self, unread: bool):
        self.setVisible(bool(unread))
        if unread:
            self.reposition()
            self.raise_()

    def reposition(self):
        """Top-right corner of the ICON (not of the whole button), for any icon size."""
        button = self._button
        icon = max(button.iconSize().width(), 1)
        dot = max(MIN_DOT, round(icon * 0.34))
        side = dot + 2 * RING
        self.setFixedSize(side, side)
        centre_x, centre_y = button.width() / 2.0, button.height() / 2.0
        x = round(centre_x + icon / 2.0 - side * 0.65)
        y = round(centre_y - icon / 2.0 - side * 0.35)
        self.move(max(0, min(x, button.width() - side)), max(0, y))
        self._dot = dot

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(tk.COLOR_BG_SIDEBAR))
        painter.drawEllipse(0, 0, self.width(), self.height())
        painter.setBrush(QColor(DOT_COLOR))
        painter.drawEllipse(RING, RING, self.width() - 2 * RING, self.height() - 2 * RING)
        painter.end()


class _ResizeWatcher(QObject):
    """Re-places the dot whenever its button is resized (icon size changes)."""

    def __init__(self, dot: UnreadDot):
        super().__init__(dot)
        self._dot = dot

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Show):
            self._dot.reposition()
        return False
