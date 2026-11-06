"""The controls for Sidebar Editing Mode (Step 14F). Shown inside Settings > Appearance.

Like the other screens it only DISPLAYS and ASKS: every control emits a signal and the
dashboard decides what happens. It never touches the sidebar or the database itself.

The size and position controls always describe the ONE selected icon. With nothing selected
they are disabled.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

NOTHING_SELECTED_TEXT = "Click an icon in the sidebar to select it. Drag it to move it."


class SidebarEditorPanel(QWidget):
    """Signals:
      size_changed(int)          - new size for the selected icon
      position_changed(int, int) - new x and y (pixels from the sidebar's top-left)
      reset_item_requested()     reset_all_requested()
      save_requested()           cancel_requested()        finish_requested()
    """

    size_changed = Signal(int)
    position_changed = Signal(int, int)
    reset_item_requested = Signal()
    reset_all_requested = Signal()
    save_requested = Signal()
    cancel_requested = Signal()
    finish_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebarEditorPanel")
        self._updating = False  # True while WE set the controls (so no signal is sent)
        self._build_ui()
        self.set_selection(None)
        self.set_unsaved(False)

    # ---------- public API ----------
    def set_selection(self, label, *, size=0, size_range=(0, 0), x=0, y=0, max_x=0, max_y=0):
        """Show the selected icon's numbers. label=None means nothing is selected."""
        self._updating = True
        try:
            has = label is not None
            self.selected_label.setText(f"Selected: {label}" if has else NOTHING_SELECTED_TEXT)
            for widget in (self.size_slider, self.size_minus, self.size_plus,
                           self.x_spin, self.y_spin, self.reset_item_button):
                widget.setEnabled(has)
            if has:
                self.size_slider.setRange(*size_range)
                self.size_slider.setValue(size)
                self.size_value.setText(f"{size} px")
                self.x_spin.setRange(0, max(max_x, 0))
                self.y_spin.setRange(0, max(max_y, 0))
                self.x_spin.setValue(x)
                self.y_spin.setValue(y)
            else:
                self.size_value.setText("")
        finally:
            self._updating = False

    def show_status(self, text: str, *, error: bool = False):
        self.status_label.setText(text)
        self.status_label.setProperty("error", error)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setVisible(bool(text))

    def set_unsaved(self, unsaved: bool):
        self.unsaved_label.setVisible(bool(unsaved))
        self.save_button.setEnabled(bool(unsaved))

    # ---------- building ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 0)
        root.setSpacing(10)

        self.selected_label = QLabel("")
        self.selected_label.setObjectName("settingsFieldLabel")
        self.selected_label.setWordWrap(True)
        root.addWidget(self.selected_label)

        # --- size: - [slider] + value ---
        root.addWidget(self._field("Size of this icon"))
        size_row = QHBoxLayout()
        self.size_minus = self._small_button("−", "Make this icon smaller")
        self.size_plus = self._small_button("+", "Make this icon bigger")
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setAccessibleName("Icon size")
        self.size_value = QLabel("")
        self.size_value.setObjectName("settingsFieldLabel")
        self.size_value.setMinimumWidth(48)
        for widget in (self.size_minus, self.size_slider, self.size_plus, self.size_value):
            size_row.addWidget(widget, 1 if widget is self.size_slider else 0)
        root.addLayout(size_row)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        self.size_minus.clicked.connect(lambda: self.size_slider.setValue(self.size_slider.value() - 1))
        self.size_plus.clicked.connect(lambda: self.size_slider.setValue(self.size_slider.value() + 1))

        # --- fine position ---
        root.addWidget(self._field("Fine position (pixels from the sidebar's top-left)"))
        position_row = QHBoxLayout()
        self.x_spin = QSpinBox()
        self.x_spin.setPrefix("X  ")
        self.x_spin.setAccessibleName("Icon X position")
        self.y_spin = QSpinBox()
        self.y_spin.setPrefix("Y  ")
        self.y_spin.setAccessibleName("Icon Y position")
        position_row.addWidget(self.x_spin)
        position_row.addWidget(self.y_spin)
        position_row.addStretch()
        root.addLayout(position_row)
        self.x_spin.valueChanged.connect(self._on_position_changed)
        self.y_spin.valueChanged.connect(self._on_position_changed)

        # --- messages ---
        self.unsaved_label = QLabel("You have unsaved changes.")
        self.unsaved_label.setObjectName("settingsMessage")
        self.unsaved_label.hide()
        root.addWidget(self.unsaved_label)
        self.status_label = QLabel("")
        self.status_label.setObjectName("settingsMessage")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        root.addWidget(self.status_label)

        # --- actions ---
        row_one = QHBoxLayout()
        self.save_button = self._button(
            "Save Changes", "catalogPrimaryButton", "Keep this layout and stay in editing mode",
            self.save_requested)
        self.cancel_button = self._button(
            "Cancel Changes", "catalogClearButton",
            "Go back to the last saved layout and leave editing mode", self.cancel_requested)
        self.finish_button = self._button(
            "Finish Editing", "catalogPrimaryButton", "Save and leave editing mode",
            self.finish_requested)
        for button in (self.save_button, self.cancel_button, self.finish_button):
            row_one.addWidget(button)
        row_one.addStretch()
        root.addLayout(row_one)

        row_two = QHBoxLayout()
        self.reset_item_button = self._button(
            "Reset Selected Icon", "catalogClearButton",
            "Put only the selected icon back to its default size and place",
            self.reset_item_requested)
        self.reset_all_button = self._button(
            "Reset All to Default", "catalogClearButton",
            "Put every icon back to its default size and place", self.reset_all_requested)
        row_two.addWidget(self.reset_item_button)
        row_two.addWidget(self.reset_all_button)
        row_two.addStretch()
        root.addLayout(row_two)

    @staticmethod
    def _field(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingsCardText")
        return label

    @staticmethod
    def _small_button(text: str, tip: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("catalogClearButton")
        button.setFixedWidth(34)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setCursor(Qt.PointingHandCursor)
        return button

    @staticmethod
    def _button(text: str, object_name: str, tip: str, signal) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setToolTip(tip)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda _checked=False: signal.emit())
        return button

    # ---------- reacting to the controls ----------
    def _on_size_changed(self, value: int):
        if self._updating:
            return
        self.size_value.setText(f"{value} px")
        self.size_changed.emit(value)

    def _on_position_changed(self, _value: int):
        if self._updating:
            return
        self.position_changed.emit(self.x_spin.value(), self.y_spin.value())
