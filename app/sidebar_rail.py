"""The sidebar rail (Step 14F): a frame whose items are placed by a SidebarLayout.

The rail does NOT use a Qt layout. Each item (avatar, page icons, Log Out) is a normal
QPushButton that is simply moved to the pixel position the layout model says. The model
(app/sidebar_layout.py) holds the numbers; this widget only shows them.

Normal mode : buttons behave exactly as before (click = navigate). Dragging is off.
Edit mode   : a press selects an item, dragging moves it, and the click is swallowed so
              nothing navigates. A dashed outline shows every item; the selected one is
              outlined in the accent color. On drop the new position is checked:
              too much overlap puts the item back and `refused` explains why.

The rail never saves anything. It reports changes (`layout_edited`) and the dashboard decides
when to save.
"""
from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame

from app import design_tokens as tk
from app.sidebar_layout import SIDEBAR_WIDTH, SidebarLayout, box_for, clamp

REFUSED_TEXT = "That spot is too close to another icon. Pick a spot with a little more room."


class _Drag:
    def __init__(self, key: str, press: QPoint, start: QPoint):
        self.key = key
        self.press = press      # global mouse position when the button went down
        self.start = start      # the button's position inside the rail at that moment
        self.moved = False


class SidebarRail(QFrame):
    """Signals:
      selection_changed(str) - key of the selected item ("" when nothing is selected)
      layout_edited(str)     - an item's size or position changed (key; "" = several items)
      refused(str)           - a change was not allowed (text is safe to show)
    """

    selection_changed = Signal(str)
    layout_edited = Signal(str)
    refused = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._buttons = {}       # key -> QPushButton
        self._appliers = {}      # key -> callable(size) that redraws that item's icon
        self._applied_size = {}  # key -> the size the icon was last drawn at
        self._model = SidebarLayout()
        self._editing = False
        self._selected = ""
        self._drag = None
        self._edit_reference_height = None  # last height at which an edit was made

    # ---------- setting up ----------
    def register_item(self, key: str, button, apply_size):
        """Hand the rail one button. `apply_size(size)` must redraw its icon at that size."""
        if button.parentWidget() is not self:
            button.setParent(self)  # (the dashboard normally creates it with the rail as parent)
        button.show()
        button.installEventFilter(self)
        self._buttons[key] = button
        self._appliers[key] = apply_size
        self.relayout()

    # ---------- the layout model ----------
    def sidebar_layout(self) -> SidebarLayout:
        """A COPY of the layout being shown (editing it does not change the rail)."""
        return self._model.copy()

    def set_sidebar_layout(self, layout: SidebarLayout):
        self._model = layout.copy()
        self._edit_reference_height = None
        self.relayout()

    def geometry_of(self, key: str) -> tuple:
        """(x, y, box) of one item as it is shown right now."""
        return self._model.display_geometry(self.height())[key]

    def size_of(self, key: str) -> int:
        return self._model.size_of(key)

    def relayout(self):
        """Move and resize every button to where the model says (never a Qt layout)."""
        geometry = self._model.display_geometry(self.height())
        for key, (x, y, box) in geometry.items():
            button = self._buttons.get(key)
            if button is None:
                continue
            size = self._model.size_of(key)
            if self._applied_size.get(key) != size:
                self._appliers[key](size)
                self._applied_size[key] = size
            if button.width() != box or button.height() != box:
                button.setFixedSize(box, box)
            if self._drag is None or self._drag.key != key:
                button.move(x, y)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout()  # saved positions are kept; only the display adapts

    # ---------- changes made by the editor panel ----------
    def _edited_candidate(self) -> SidebarLayout:
        """Freeze displayed locations before the first edit at this window height.

        Pinning is committed only after a successful edit, so a refused drag does
        not silently rewrite any existing saved positions. This also handles
        editing again after resizing while Edit Mode is still open.
        """
        candidate = self._model.copy()
        if self._editing and self._edit_reference_height != self.height():
            candidate.pin_visible_positions(self.height())
        return candidate

    def _accept_edit(self, candidate: SidebarLayout, key: str, success: bool) -> bool:
        if success:
            self._model = candidate
            if self._editing:
                self._edit_reference_height = self.height()
        self._after_change(key, success)
        return success

    def set_item_size(self, key: str, size: int) -> bool:
        candidate = self._edited_candidate()
        changed = candidate.set_size(key, size, self.height())
        return self._accept_edit(candidate, key, changed)

    def set_item_position(self, key: str, x: int, y: int) -> bool:
        candidate = self._edited_candidate()
        changed = candidate.set_position(key, x, y, self.height())
        return self._accept_edit(candidate, key, changed)

    def reset_item(self, key: str) -> bool:
        candidate = self._edited_candidate()
        changed = candidate.reset_item(key)
        if changed:
            self._model = candidate
            if self._editing:
                self._edit_reference_height = self.height()
        self._after_change(key, True)
        return changed

    def reset_all(self) -> bool:
        changed = self._model.reset_all()
        self._edit_reference_height = None
        self._after_change("", True)
        return changed

    def _after_change(self, key: str, ok: bool):
        self.relayout()
        if ok:
            self.layout_edited.emit(key)
        else:
            self.refused.emit(REFUSED_TEXT)

    # ---------- edit mode ----------
    @property
    def editing(self) -> bool:
        return self._editing

    @property
    def selected_key(self) -> str:
        return self._selected

    def set_editing(self, editing: bool):
        self._editing = bool(editing)
        self._drag = None
        self._edit_reference_height = None
        if not self._editing:
            self.select("")
        self.relayout()

    def select(self, key: str):
        key = key if key in self._buttons else ""
        if key != self._selected:
            self._selected = key
            self.update()
            self.selection_changed.emit(key)

    # ---------- dragging ----------
    def _key_of(self, widget):
        for key, button in self._buttons.items():
            if button is widget:
                return key
        return None

    def eventFilter(self, watched, event):
        if not self._editing:
            return False  # normal mode: buttons work exactly as before
        key = self._key_of(watched)
        if key is None:
            return False
        kind = event.type()
        if kind == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                self.select(key)
                self._drag = _Drag(key, event.globalPosition().toPoint(),
                                   self._buttons[key].pos())
            return True
        if kind == QEvent.MouseMove:
            if self._drag is not None and self._drag.key == key:
                delta = event.globalPosition().toPoint() - self._drag.press
                if self._drag.moved or delta.manhattanLength() >= 4:
                    self._drag.moved = True
                    self._move_live(key, self._drag.start + delta)
            return True
        if kind == QEvent.MouseButtonRelease:
            if self._drag is not None and self._drag.key == key:
                self._finish_drag()
            return True
        if kind == QEvent.MouseButtonDblClick:
            return True
        return False

    def _move_live(self, key: str, target: QPoint):
        """Follow the mouse, but never leave the visible rail."""
        button = self._buttons[key]
        box = box_for(key, self._model.size_of(key))
        button.move(clamp(target.x(), 0, max(SIDEBAR_WIDTH - box, 0)),
                    clamp(target.y(), 0, max(self.height() - box, 0)))
        self.update()

    def _finish_drag(self):
        drag, self._drag = self._drag, None
        if drag is None or not drag.moved:
            return
        button = self._buttons[drag.key]
        # Use the visible dropped coordinates, not an old bottom-anchored saved
        # offset. Other icons keep exactly the spacing shown in this window.
        self.set_item_position(drag.key, button.x(), button.y())

    # ---------- drawing the edit-mode outlines ----------
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._editing:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for key, button in self._buttons.items():
            selected = key == self._selected
            pen = QPen(QColor(tk.COLOR_ACCENT_HOVER if selected else tk.COLOR_BORDER_STRONG))
            pen.setWidth(2 if selected else 1)
            pen.setStyle(Qt.SolidLine if selected else Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(button.geometry().adjusted(-1, -1, 0, 0), 8, 8)
        painter.end()

    def sizeHint(self):
        return QSize(SIDEBAR_WIDTH, 480)
