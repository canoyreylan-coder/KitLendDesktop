"""The "New category" / "New subcategory" dialog (Step 31D).

Shown from Add/Edit Listing. While the owner types, it checks the SHARED registry (through the
`source` object, see OwnerCategoryAccess) and tells them what would happen:
  * the name already exists (ignoring capitals and spaces) -> it cannot be created; the existing
    category is offered ("Use existing");
  * similar names exist -> they are listed; the owner can pick one of them, or press
    "Create anyway" after having seen the warning;
  * the name is free -> "Create category".
It never touches the database itself. `result_name` is the category that was created or chosen.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout,
)

from app import design_tokens as tk
from app.header_style import ACCENT_LAVENDER
from app.listing_category_service import (
    MAX_NAME, STATUS_EMPTY, STATUS_EXISTS, STATUS_OK, STATUS_SIMILAR, CategoryError,
    CategoryExistsError, SimilarCategoryError,
)

_D = "QDialog#categoryDialog"
CATEGORY_DIALOG_QSS = f"""
{_D} {{ background-color: {tk.COLOR_BG_SURFACE}; }}
{_D} QLabel {{ background: transparent; border: none; }}
{_D} QLabel#categoryDialogTitle {{
    color: {tk.COLOR_TEXT_PRIMARY}; font-size: {tk.FONT_SIZE_LEAD}px;
    font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_D} QLabel#categoryDialogText {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_SMALL + 1}px; }}
{_D} QLabel#categoryDialogHint {{ color: {tk.COLOR_TEXT_SECONDARY}; font-size: {tk.FONT_SIZE_BODY - 1}px; }}
{_D} QLabel#categoryDialogHint[tone="warn"] {{ color: #F2C98A; }}
{_D} QLabel#categoryDialogHint[tone="error"] {{ color: {tk.COLOR_DANGER}; }}
{_D} QLabel#categoryDialogHint[tone="good"] {{ color: {tk.COLOR_SUCCESS}; }}
{_D} QLabel#categoryDialogSection {{
    color: {ACCENT_LAVENDER}; font-size: {tk.FONT_SIZE_SMALL}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_D} QLineEdit {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER}; border-radius: {tk.RADIUS_MD}px;
    padding: 8px 12px; font-size: {tk.FONT_SIZE_BODY}px;
    selection-background-color: {tk.COLOR_ACCENT};
}}
{_D} QLineEdit:hover {{ border-color: {tk.COLOR_BORDER_STRONG}; }}
{_D} QLineEdit:focus {{ border-color: {tk.COLOR_FOCUS_RING}; }}
{_D} QListWidget {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY};
    border: 1px solid {tk.COLOR_BORDER}; border-radius: {tk.RADIUS_MD}px;
    padding: 4px; outline: none; font-size: {tk.FONT_SIZE_BODY}px;
}}
{_D} QListWidget::item {{ padding: 7px 10px; border-radius: 6px; }}
{_D} QListWidget::item:hover {{ background-color: {tk.COLOR_BG_OVERLAY}; }}
{_D} QListWidget::item:selected {{ background-color: {tk.COLOR_ACCENT_SOFT}; color: #D5D7FF; }}
{_D} QPushButton {{
    border-radius: {tk.RADIUS_MD}px; padding: 9px 18px;
    font-size: {tk.FONT_SIZE_BODY - 1}px; font-weight: {tk.FONT_WEIGHT_SEMIBOLD};
}}
{_D} QPushButton#categoryPrimary {{
    background-color: {tk.COLOR_ACCENT_SOFT}; color: #D5D7FF; border: 1px solid {tk.COLOR_BORDER_STRONG};
}}
{_D} QPushButton#categoryPrimary:hover {{ background-color: #353A78; border-color: {tk.COLOR_FOCUS_RING}; }}
{_D} QPushButton#categoryPrimary:disabled {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_DISABLED}; border: 1px solid {tk.COLOR_BORDER};
}}
{_D} QPushButton#categoryQuiet {{
    background-color: transparent; color: {tk.COLOR_TEXT_SECONDARY}; border: 1px solid {tk.COLOR_BORDER};
}}
{_D} QPushButton#categoryQuiet:hover {{
    background-color: {tk.COLOR_BG_RAISED}; color: {tk.COLOR_TEXT_PRIMARY}; border-color: {tk.COLOR_BORDER_STRONG};
}}
{_D} QPushButton#categoryQuiet:disabled {{ color: {tk.COLOR_TEXT_DISABLED}; border-color: {tk.COLOR_BORDER}; }}
"""


class NewCategoryDialog(QDialog):
    def __init__(self, source, parent_name=None, parent=None):
        super().__init__(parent)
        self._source = source
        self._parent_name = parent_name or None
        self._status = STATUS_EMPTY
        self.result_name = None   # the category created or chosen (None = cancelled)

        noun = "subcategory" if self._parent_name else "category"
        self.setObjectName("categoryDialog")
        self.setWindowTitle(f"New {noun}")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(CATEGORY_DIALOG_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        title = QLabel(f"New {noun}" + (f" in {self._parent_name}" if self._parent_name else ""))
        title.setObjectName("categoryDialogTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        intro = QLabel(
            "Categories are shared by all Student Owners, so please check that it does not "
            "already exist." if not self._parent_name else
            f"Subcategories help students find items inside {self._parent_name}. "
            "They are shared by all Student Owners.")
        intro.setObjectName("categoryDialogText")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.name_input = QLineEdit()
        self.name_input.setMaxLength(MAX_NAME + 20)  # longer text is explained, not silently cut
        self.name_input.setPlaceholderText("For example: Origami" if not self._parent_name
                                           else "For example: Fantasy")
        self.name_input.setAccessibleName(f"New {noun} name")
        self.name_input.textChanged.connect(self._refresh)
        self.name_input.returnPressed.connect(self._on_enter)
        layout.addWidget(self.name_input)

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("categoryDialogHint")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        self.suggestions_title = QLabel("")
        self.suggestions_title.setObjectName("categoryDialogSection")
        layout.addWidget(self.suggestions_title)
        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumHeight(120)
        self.suggestion_list.currentRowChanged.connect(self._on_suggestion_selected)
        self.suggestion_list.itemDoubleClicked.connect(lambda _item: self._use_selected())
        layout.addWidget(self.suggestion_list)

        layout.addSpacing(6)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("categoryQuiet")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.use_button = QPushButton("Use selected")
        self.use_button.setObjectName("categoryQuiet")
        self.use_button.clicked.connect(self._use_selected)
        buttons.addWidget(self.use_button)
        self.create_button = QPushButton(f"Create {noun}")
        self.create_button.setObjectName("categoryPrimary")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._create)
        buttons.addWidget(self.create_button)
        layout.addLayout(buttons)
        self._noun = noun
        self._refresh()

    # ---------- reading the situation ----------
    def suggestion_names(self) -> list:
        return [self.suggestion_list.item(i).text() for i in range(self.suggestion_list.count())]

    def _set_hint(self, text: str, tone: str = ""):
        self.hint_label.setText(text)
        self.hint_label.setProperty("tone", tone)
        self.hint_label.style().unpolish(self.hint_label)
        self.hint_label.style().polish(self.hint_label)

    def _show_suggestions(self, title: str, names, select_first: bool):
        self.suggestion_list.blockSignals(True)
        self.suggestion_list.clear()
        self.suggestion_list.addItems(list(names))
        self.suggestion_list.blockSignals(False)
        has = bool(names)
        self.suggestions_title.setText(title if has else "")
        self.suggestions_title.setVisible(has)
        self.suggestion_list.setVisible(has)
        if has and select_first:
            self.suggestion_list.setCurrentRow(0)
        else:
            self.suggestion_list.setCurrentRow(-1)
        self.use_button.setEnabled(has and select_first)

    def _refresh(self, _text=None):
        try:
            check = self._source.check(self.name_input.text(), self._parent_name)
        except CategoryError as exc:
            self._status = "error"
            self._set_hint(str(exc), "error")
            self._show_suggestions("", (), False)
            self.create_button.setEnabled(False)
            return
        self._status = check.status
        self.create_button.setText(f"Create {self._noun}")
        if check.status == STATUS_EMPTY:
            self._set_hint("")
            self._show_suggestions("", (), False)
            self.create_button.setEnabled(False)
        elif check.status == STATUS_EXISTS:
            self._set_hint(f"“{check.existing}” already exists, so it cannot be created again.",
                           "warn")
            self._show_suggestions("Existing", [check.existing], True)
            self.use_button.setText("Use existing")
            self.create_button.setEnabled(False)
        elif check.status == STATUS_SIMILAR:
            self._set_hint("Similar categories already exist. If one of them fits, please "
                           "use it, so items stay easy to find.", "warn")
            self._show_suggestions("Did you mean one of these?", check.similar, False)
            self.use_button.setText("Use selected")
            self.create_button.setText("Create anyway")
            self.create_button.setEnabled(True)
        elif check.status == STATUS_OK:
            self._set_hint("This name is available.", "good")
            self._show_suggestions("", (), False)
            self.create_button.setEnabled(True)
        else:  # too short / too long / invalid
            messages = {
                "too_short": "The name needs at least 2 characters.",
                "too_long": f"Please keep the name under {MAX_NAME + 1} characters.",
                "invalid": "The name needs at least one letter or number.",
            }
            self._set_hint(messages.get(check.status, "Please check the name."), "error")
            self._show_suggestions("", (), False)
            self.create_button.setEnabled(False)

    # ---------- actions ----------
    def _on_suggestion_selected(self, row: int):
        self.use_button.setEnabled(row >= 0)

    def _use_selected(self):
        item = self.suggestion_list.currentItem()
        if item is None:
            return
        self.result_name = item.text()
        self.accept()

    def _on_enter(self):
        if self.create_button.isEnabled():
            self._create()

    def _create(self):
        if not self.create_button.isEnabled():
            return
        try:
            name = self._source.create(
                self.name_input.text(), self._parent_name,
                confirm_similar=(self._status == STATUS_SIMILAR))
        except (CategoryExistsError, SimilarCategoryError):
            self._refresh()      # somebody else was faster: show the up-to-date situation
            return
        except CategoryError as exc:
            self._set_hint(str(exc), "error")
            return
        self.result_name = name
        self.accept()
