"""KitLend Settings screen (Step 12).

Sections, top to bottom (Step 28 groups them under text headings):
  PROFILE        - round profile picture (photo or initials), Upload / Change / Remove.
  ACCOUNT        - Account Information (name + registered school email, read-only) and
                   Change Password.
  APPEARANCE     - sidebar customization (Step 14F).
  NOTIFICATIONS  - on/off for "request submitted" and "request cancelled".
  WORKSPACES     - the workspaces this account is authorized to use, followed
                   (Step 13) by "Become a Student Owner": the student's current
                   application status and, when allowed, the application form.

Step 28: the profile photo is only ASKED for here (signals). The dashboard saves it with
ProfilePhotoService and tells this screen the result. The screen never touches files or the
database itself. Look: app/settings_theme.py (scoped to QWidget#settingsScreen).

Rules this screen follows (same as the Notifications screen):
  * It only DISPLAYS what it is given and ASKS for changes through signals. It never
    touches the database. The dashboard calls AuthService / NotificationService and
    then reports the outcome back with show_password_result / show_preferences_message.
  * Passwords are only ever held in the three input boxes. They are cleared after every
    attempt and when the screen is cleared, and they are never printed or stored here.
  * Name and email are plain labels. Email changes are not offered because email
    ownership is not verified yet.
  * Step 13: the application form only ASKS (a signal) to submit. The screen cannot set,
    change or approve a status; it just shows the applications it is given. Submitting
    never adds a workspace and never changes borrowing.
  * The workspace list is data from WorkspaceService. The screen has no way to add,
    unlock or switch to a workspace; the real rights will come from the backend.

It reuses the Catalog/My Requests header, info box, banner and button styles.
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.auth_service import MAX_STUDENT_ID_LENGTH
from app.floating_layout import MAX_OUTER_MARGIN, MIN_OUTER_MARGIN
from app.header_style import HEADER_QSS, accent_html
from app.dashboard_widgets import StatusPill
from app.profile_avatar import ProfileAvatar
from app.settings_theme import SETTINGS_V2_QSS
from app.notification_service import (
    EVENT_LABELS,
    format_notification_time,
    EVENT_REQUEST_CANCELLED,
    EVENT_REQUEST_SUBMITTED,
)
from app.student_owner_service import (
    MAX_ITEMS_LENGTH,
    MAX_REASON_LENGTH,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    STUDENT_OWNER_RULES,
)
from app.sidebar_editor_panel import SidebarEditorPanel
from app.workspace_service import (
    HOW_TO_GET_ACCESS,
    WORKSPACE_STUDENT,
    WORKSPACE_STUDENT_OWNER,
)

PREFERENCE_DESCRIPTIONS = {
    EVENT_REQUEST_SUBMITTED: "Tell me when I submit a borrowing request.",
    EVENT_REQUEST_CANCELLED: "Tell me when I cancel a borrowing request.",
}
PREFERENCES_INFO_TEXT = (
    "Turning a type off only stops NEW notifications of that type. Notifications you "
    "already have stay in your list, and your requests are not affected. Notifications "
    "that were skipped while a type was off are not created later."
)


class SettingsScreen(QWidget):
    """Account information, password change, notification preferences and workspaces.

    Signals:
      change_password_requested(str, str, str) - current, new, confirmation
      preference_changed(str, bool)            - event type, new on/off value
      owner_application_submitted(str, str, bool) - reason, items, agreed to the rules
      sidebar_edit_requested()                 - Appearance: start Sidebar Editing Mode
      profile_photo_chosen(str)                - Profile: a picture file was picked
      profile_photo_remove_requested()         - Profile: remove the photo
      student_id_submitted(str)                - Profile: add the missing Student ID Number
    """

    change_password_requested = Signal(str, str, str)
    preference_changed = Signal(str, bool)
    owner_application_submitted = Signal(str, str, bool)  # reason, items, agreed to rules
    sidebar_edit_requested = Signal()  # Step 14F: "Customize Sidebar" was pressed
    profile_photo_chosen = Signal(str)  # Step 28: path of the picture the student picked
    outer_margin_changed = Signal(int)  # Appearance: slider moved / Cancel / Reset (0 = automatic); live preview only
    outer_margin_save_requested = Signal(int)  # Appearance: Save pressed (0 = back to the automatic default)
    profile_photo_remove_requested = Signal()  # Step 28: "Remove photo" was pressed
    workspace_switch_requested = Signal(str)  # Step 31A: "student" or "student_owner"
    student_id_submitted = Signal(str)  # Step 29D: the Student ID Number to add (already confirmed)

    def __init__(self, parent=None, *, stored_locally: bool = False):
        super().__init__(parent)
        self._stored_locally = stored_locally
        self._saved_photo = None  # Step 29B: the saved picture (what Cancel returns to)
        self._pending_photo = None  # Step 29B: a chosen picture being previewed, not saved
        self.setObjectName("settingsScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(HEADER_QSS + SETTINGS_V2_QSS)  # soft-dark, scoped to this screen
        self._workspace_names = []
        self._current_workspace = WORKSPACE_STUDENT
        self._workspace_switch_buttons = {}
        self._owner_application_ids = []
        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(6000)
        self._banner_timer.timeout.connect(lambda: self.banner.hide())
        self._loading_preferences = False  # True while we set the boxes ourselves
        self._student_id_enabled = False
        self._build_ui()

    # ---------- public API (the dashboard and the tests use these) ----------
    def set_account(self, full_name: str, email: str):
        self.name_value.setText(full_name or "")
        self.email_value.setText(email or "")
        self.profile_name.setText(full_name or "")
        self.profile_email.setText(email or "")

    def set_student_id(self, student_id_number):
        """Show the Student ID Number privately (this page only), or the form to add it.

        `None` / empty = an older account that has no ID yet: the add form appears. Once an ID
        exists it is shown as text only; this page has no way to change it.
        """
        has_id = bool(student_id_number)
        self.profile_student_id.setText(
            f"Student ID · {student_id_number}" if has_id else "Student ID · not added yet")
        self.profile_student_id.setVisible(True)
        self.student_id_form.setVisible(not has_id and self._student_id_enabled)

    def set_student_id_enabled(self, enabled: bool):
        """Only a signed-in account can add its ID (not the demo)."""
        self._student_id_enabled = bool(enabled)
        if not enabled:
            self.profile_student_id.setVisible(False)
        self.student_id_form.setVisible(
            bool(enabled) and self.profile_student_id.text().endswith("not added yet"))
        self.student_id_input.setEnabled(bool(enabled))
        self.student_id_button.setEnabled(bool(enabled))

    def _confirm_student_id(self, student_id_number: str) -> bool:
        """Ask first: a registered Student ID cannot be changed afterwards."""
        answer = QMessageBox.question(
            self, "Save Student ID Number?",
            f"Save “{student_id_number}” as your Student ID Number?\n\n"
            "Once saved it cannot be changed here, so please check it carefully.",
            QMessageBox.Save | QMessageBox.Cancel, QMessageBox.Cancel)
        return answer == QMessageBox.Save

    def _submit_student_id(self):
        value = " ".join(self.student_id_input.text().split())
        if not value:
            self.show_message("Please enter your Student ID Number.")
            return
        if self._confirm_student_id(value):
            self.student_id_submitted.emit(value)

    def set_profile(self, initials: str, photo_path=None):
        """Show the round profile picture: the photo if there is one, otherwise the initials."""
        self.avatar.set_initials(initials)
        self.avatar.set_photo(photo_path)
        self._saved_photo = photo_path  # Step 29B: what Cancel goes back to
        self._pending_photo = None  # a fresh state from the dashboard ends any preview
        self._show_preview_buttons(False)
        has_photo = self.avatar.has_photo
        self.photo_button.setText("Change photo" if has_photo else "Upload photo")
        self.photo_remove_button.setVisible(has_photo)

    def set_profile_photo_enabled(self, enabled: bool):
        """Only a signed-in account can save a photo (not the demo)."""
        for button in (self.photo_button, self.photo_remove_button):
            button.setEnabled(bool(enabled))
        self.photo_button.setToolTip(
            "" if enabled else "Log in with your school account to add a profile photo.")

    def show_photo_result(self, text: str, *, error: bool):
        self.photo_message.setText(text)
        self.photo_message.setProperty("error", error)
        self.photo_message.style().unpolish(self.photo_message)
        self.photo_message.style().polish(self.photo_message)
        self.photo_message.setVisible(bool(text))

    def set_preferences(self, preferences: dict):
        """Show saved choices without emitting preference_changed."""
        self._loading_preferences = True
        try:
            for event_type, box in self.preference_boxes.items():
                box.setChecked(bool(preferences.get(event_type, True)))
        finally:
            self._loading_preferences = False

    def preferences(self) -> dict:
        return {event: box.isChecked() for event, box in self.preference_boxes.items()}

    def set_workspaces(self, workspaces, current=WORKSPACE_STUDENT):
        """Show the workspaces this account is authorized to use.

        Step 31A: when the account may use more than one (Student + Student Owner), each row
        that is not the current one gets a Switch button. The button only ASKS the dashboard
        (workspace_switch_requested); the dashboard re-checks the right before switching, so this
        screen can never unlock a workspace.
        """
        workspaces = list(workspaces)
        self._workspace_names = [w.label for w in workspaces]
        self._current_workspace = current
        self._workspace_switch_buttons = {}
        while self.workspace_list.count():
            widget = self.workspace_list.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        can_switch = len(workspaces) > 1
        for workspace in workspaces:
            self.workspace_list.addWidget(self._workspace_row(workspace, current, can_switch))

    @property
    def workspace_switch_buttons(self) -> dict:
        """{workspace key: Switch button} for the rows that can be switched to."""
        return dict(self._workspace_switch_buttons)

    @property
    def workspace_names(self) -> list:
        return list(self._workspace_names)

    def set_student_owner_state(self, applications, block_reason=None):
        """Show the student's own applications (newest first) and, if allowed, the form.

        `block_reason` is None when the student may apply now, otherwise the reason why
        the form is hidden. Display only: nothing here can change a status.
        """
        applications = list(applications)
        self._owner_application_ids = [a.application_id for a in applications]
        current = applications[0] if applications else None
        if current is None:
            self.owner_status_label.setText("You have not applied yet.")
            self.owner_status_pill.hide()
        else:
            self.owner_status_label.setText(self._owner_status_text(current))
            text, tone = self._OWNER_PILL[current.status]
            self.owner_status_pill.setText(text)
            self.owner_status_pill.setProperty("tone", tone)
            self.owner_status_pill.style().unpolish(self.owner_status_pill)
            self.owner_status_pill.style().polish(self.owner_status_pill)
            self.owner_status_pill.show()
        form_visible = block_reason is None
        self.owner_form.setVisible(form_visible)
        self.owner_block_label.setText("" if form_visible else block_reason)
        self.owner_block_label.setVisible(not form_visible)
        while self.owner_history.count():
            widget = self.owner_history.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.owner_history_title.setVisible(bool(applications))
        for application in applications:
            self.owner_history.addWidget(self._owner_history_row(application))

    @property
    def owner_application_ids(self) -> list:
        return list(self._owner_application_ids)

    def set_student_owner_enabled(self, enabled: bool):
        for widget in (self.owner_reason_input, self.owner_items_input,
                       self.owner_agree_box, self.owner_submit_button):
            widget.setEnabled(enabled)

    def show_owner_result(self, text: str, *, error: bool):
        """Report the outcome of a submission. A successful one also clears the form."""
        if not error:
            self.clear_owner_form()
        self.owner_message.setText(text)
        self.owner_message.setProperty("error", error)
        self.owner_message.style().unpolish(self.owner_message)
        self.owner_message.style().polish(self.owner_message)
        self.owner_message.show()

    def clear_owner_form(self):
        self.owner_reason_input.clear()
        self.owner_items_input.clear()
        self.owner_agree_box.setChecked(False)

    def set_password_enabled(self, enabled: bool):
        for widget in (self.current_input, self.new_input, self.confirm_input,
                       self.password_button):
            widget.setEnabled(enabled)

    def set_preferences_enabled(self, enabled: bool):
        for box in self.preference_boxes.values():
            box.setEnabled(enabled)

    def show_password_result(self, text: str, *, error: bool):
        """Report the outcome of a password change. The boxes are always cleared."""
        self.clear_password_fields()
        self.password_message.setText(text)
        self.password_message.setProperty("error", error)
        self.password_message.style().unpolish(self.password_message)
        self.password_message.style().polish(self.password_message)
        self.password_message.show()

    def show_preferences_message(self, text: str):
        self.preference_message.setText(text)
        self.preference_message.show()

    def show_message(self, text: str):
        self.banner.setText(text)
        self.banner.show()
        self._banner_timer.start()

    def clear_password_fields(self):
        for box in (self.current_input, self.new_input, self.confirm_input):
            box.clear()

    def clear(self):
        """Forget everything about the signed-in student (used at logout)."""
        self.clear_password_fields()
        self.password_message.hide()
        self.preference_message.hide()
        self.banner.hide()
        self.set_account("", "")
        self.set_profile("", None)  # no photo or initials of the last student left
        self.photo_message.hide()
        self.set_workspaces([])
        self.clear_owner_form()
        self.owner_message.hide()
        self.set_student_owner_state([], None)  # no applications of the last student left
        self._margin_saved = self._margin_pending = 0  # forget the last student's margin
        self.margin_message.hide()
        self._refresh_margin_controls()

    # ---------- building ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)

        scroll = QScrollArea()
        scroll.setObjectName("catalogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("catalogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 8)
        layout.setSpacing(14)

        layout.addWidget(self._build_header())

        self.banner = QLabel("")
        self.banner.setObjectName("myListBanner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        layout.addWidget(self.banner)

        self._add_section(layout, "Profile")
        layout.addWidget(self._build_profile_card())
        self._add_section(layout, "Account")
        layout.addWidget(self._build_account_card())
        layout.addWidget(self._build_password_card())
        self._add_section(layout, "Appearance")
        layout.addWidget(self._build_appearance_card())
        self._add_section(layout, "Notifications")
        layout.addWidget(self._build_preferences_card())
        self._add_section(layout, "Workspaces")
        layout.addWidget(self._build_workspaces_card())
        layout.addWidget(self._build_student_owner_card())
        layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("catalogHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(2, 6, 2, 10)
        layout.setSpacing(12)

        texts = QVBoxLayout()
        texts.setSpacing(8)
        tag = QLabel(
            "Stored locally · Not sent to school administrators"
            if self._stored_locally else "Preview · Sample data only"
        )
        tag.setObjectName("catalogTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        texts.addWidget(tag, alignment=Qt.AlignLeft)

        title = QLabel(accent_html("Settings & Profile", "Profile"))
        title.setObjectName("catalogTitle")
        texts.addWidget(title)

        subtitle = QLabel("Your profile, account, appearance, notifications and workspaces.")
        subtitle.setObjectName("catalogSubtitle")
        subtitle.setWordWrap(True)
        texts.addWidget(subtitle)
        texts.addStretch()
        layout.addLayout(texts, 1)

        return header

    @staticmethod
    def _add_section(layout, text: str):
        """A text-only heading with a hairline under it (no box)."""
        heading = QLabel(text.upper())
        heading.setObjectName("settingsSection")
        layout.addWidget(heading)
        line = QFrame()
        line.setObjectName("settingsSectionLine")
        line.setFrameShape(QFrame.NoFrame)
        layout.addWidget(line)

    @staticmethod
    def _card(title: str, subtitle: str = ""):
        card = QFrame()
        card.setObjectName("settingsCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(22, 18, 22, 20)
        box.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("settingsCardTitle")
        box.addWidget(heading)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("settingsCardText")
            sub.setWordWrap(True)
            box.addWidget(sub)
        return card, box

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingsFieldLabel")
        return label

    def _build_profile_card(self) -> QFrame:
        card, box = self._card("Profile photo")
        row = QHBoxLayout()
        row.setSpacing(20)
        self.avatar = ProfileAvatar(96)
        row.addWidget(self.avatar, alignment=Qt.AlignTop)

        column = QVBoxLayout()
        column.setSpacing(4)
        self.profile_name = QLabel("")
        self.profile_name.setObjectName("profileName")
        column.addWidget(self.profile_name)
        self.profile_email = QLabel("")
        self.profile_email.setObjectName("profileEmail")
        column.addWidget(self.profile_email)

        # Step 29D: the Student ID Number, shown only here (private to this page)
        self.profile_student_id = QLabel("")
        self.profile_student_id.setObjectName("profileEmail")
        self.profile_student_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.profile_student_id.hide()
        column.addWidget(self.profile_student_id)
        self.student_id_form = QWidget()
        form = QHBoxLayout(self.student_id_form)
        form.setContentsMargins(0, 4, 0, 0)
        form.setSpacing(8)
        self.student_id_input = QLineEdit()
        self.student_id_input.setPlaceholderText("Add your Student ID Number")
        self.student_id_input.setMaxLength(MAX_STUDENT_ID_LENGTH + 10)
        self.student_id_input.setAccessibleName("Student ID Number")
        self.student_id_input.returnPressed.connect(self._submit_student_id)
        form.addWidget(self.student_id_input, 1)
        self.student_id_button = QPushButton("Save Student ID")
        self.student_id_button.setObjectName("catalogPrimaryButton")
        self.student_id_button.setCursor(Qt.PointingHandCursor)
        self.student_id_button.setToolTip("You can add it once; it cannot be changed afterwards")
        self.student_id_button.clicked.connect(lambda _checked=False: self._submit_student_id())
        form.addWidget(self.student_id_button)
        self.student_id_form.hide()
        column.addWidget(self.student_id_form)
        column.addSpacing(8)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.photo_button = QPushButton("Upload photo")
        self.photo_button.setObjectName("catalogPrimaryButton")
        self.photo_button.setCursor(Qt.PointingHandCursor)
        self.photo_button.clicked.connect(self._choose_photo)
        buttons.addWidget(self.photo_button)
        self.photo_remove_button = QPushButton("Remove photo")
        self.photo_remove_button.setObjectName("profileRemoveButton")
        self.photo_remove_button.setCursor(Qt.PointingHandCursor)
        self.photo_remove_button.clicked.connect(self._on_remove_clicked)
        self.photo_remove_button.hide()
        buttons.addWidget(self.photo_remove_button)
        # Step 29B: shown only while a chosen picture is being previewed (not saved yet)
        self.photo_save_button = QPushButton("Save photo")
        self.photo_save_button.setObjectName("catalogPrimaryButton")
        self.photo_save_button.setCursor(Qt.PointingHandCursor)
        self.photo_save_button.clicked.connect(self._on_save_clicked)
        self.photo_save_button.hide()
        buttons.addWidget(self.photo_save_button)
        self.photo_cancel_button = QPushButton("Cancel")
        self.photo_cancel_button.setObjectName("profileRemoveButton")
        self.photo_cancel_button.setCursor(Qt.PointingHandCursor)
        self.photo_cancel_button.clicked.connect(self._on_cancel_clicked)
        self.photo_cancel_button.hide()
        buttons.addWidget(self.photo_cancel_button)
        buttons.addStretch()
        column.addLayout(buttons)

        hint = QLabel("JPG, PNG or WEBP, up to 10 MB. Your picture is cropped to a circle "
                      "and shown in Settings and the sidebar. Without a photo, your initials "
                      "are shown.")
        hint.setObjectName("profileHint")
        hint.setWordWrap(True)
        column.addWidget(hint)
        self.photo_message = QLabel("")
        self.photo_message.setObjectName("settingsMessage")
        self.photo_message.setWordWrap(True)
        self.photo_message.hide()
        column.addWidget(self.photo_message)
        row.addLayout(column, 1)
        box.addLayout(row)
        return card

    def _choose_photo(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "Choose a profile photo", "",
            "Pictures (*.jpg *.jpeg *.png *.webp)")
        if not path:  # an empty path means the student cancelled
            return
        # Step 29B: only PREVIEW it. Nothing is saved until the student confirms.
        self.avatar.set_photo(path)
        if not self.avatar.has_photo:
            self.avatar.set_photo(self._saved_photo)
            self.show_photo_result(
                "That file could not be read as a picture. Choose a JPG, PNG or WEBP.",
                error=True)
            return
        self._pending_photo = path
        self.photo_message.hide()
        self._show_preview_buttons(True)

    def _show_preview_buttons(self, previewing: bool):
        self.photo_save_button.setVisible(previewing)
        self.photo_cancel_button.setVisible(previewing)
        self.photo_button.setVisible(not previewing)
        self.photo_remove_button.setVisible(
            not previewing and self._saved_photo is not None and self.avatar.has_photo)

    def _end_preview(self):
        """Back to the saved photo (or the initials); the saved picture is untouched."""
        self._pending_photo = None
        self.avatar.set_photo(self._saved_photo)
        self._show_preview_buttons(False)

    def _on_cancel_clicked(self):
        self._end_preview()

    def _on_save_clicked(self):
        path = self._pending_photo
        if path is None or not self._confirm_save_photo():
            return  # still previewing; nothing saved
        self.profile_photo_chosen.emit(path)
        if self._pending_photo is not None:  # the save failed: keep the previous photo
            self._end_preview()

    def _on_remove_clicked(self):
        if self._confirm_remove_photo():
            self.profile_photo_remove_requested.emit()

    def _confirm_save_photo(self) -> bool:
        return self._confirm("Save profile photo", "Save this as your profile photo?",
                             "It will replace your current picture in Settings and the sidebar.",
                             "Save")

    def _confirm_remove_photo(self) -> bool:
        return self._confirm("Remove profile photo", "Remove your profile photo?",
                             "Your initials will be shown instead.", "Remove")

    def _confirm(self, title, text, detail, action_text) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setInformativeText(detail)
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        action = box.addButton(action_text, QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is action

    def _build_account_card(self) -> QFrame:
        card, box = self._card(
            "Account Information",
            "These details come from your registration and cannot be edited here. "
            "Changing your email will be possible after email verification is added.",
        )
        box.addWidget(self._field_label("Full name"))
        self.name_value = QLabel("")
        self.name_value.setObjectName("settingsReadOnlyValue")
        self.name_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.name_value)
        box.addWidget(self._field_label("Registered school email"))
        self.email_value = QLabel("")
        self.email_value.setObjectName("settingsReadOnlyValue")
        self.email_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(self.email_value)
        return card

    def _password_input(self, placeholder: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.Password)
        edit.setPlaceholderText(placeholder)
        edit.setMaxLength(128)
        edit.returnPressed.connect(self._submit_password)
        return edit

    def _build_password_card(self) -> QFrame:
        card, box = self._card(
            "Change Password",
            "Enter your current password, then your new one twice. "
            "Your new password must be 8-128 characters.",
        )
        box.addWidget(self._field_label("Current password"))
        self.current_input = self._password_input("Current password")
        box.addWidget(self.current_input)
        box.addWidget(self._field_label("New password"))
        self.new_input = self._password_input("New password")
        box.addWidget(self.new_input)
        box.addWidget(self._field_label("Confirm new password"))
        self.confirm_input = self._password_input("Repeat the new password")
        box.addWidget(self.confirm_input)

        self.password_message = QLabel("")
        self.password_message.setObjectName("settingsMessage")
        self.password_message.setWordWrap(True)
        self.password_message.hide()
        box.addWidget(self.password_message)

        self.password_button = QPushButton("Change Password")
        self.password_button.setObjectName("catalogPrimaryButton")
        self.password_button.setCursor(Qt.PointingHandCursor)
        self.password_button.clicked.connect(self._submit_password)
        box.addWidget(self.password_button, alignment=Qt.AlignLeft)
        return card

    def _submit_password(self):
        self.change_password_requested.emit(
            self.current_input.text(), self.new_input.text(), self.confirm_input.text())

    def _build_preferences_card(self) -> QFrame:
        card, box = self._card("Notification Preferences", PREFERENCES_INFO_TEXT)
        self.preference_boxes = {}
        for event_type in (EVENT_REQUEST_SUBMITTED, EVENT_REQUEST_CANCELLED):
            check = QCheckBox(f"{EVENT_LABELS[event_type]} — "
                              f"{PREFERENCE_DESCRIPTIONS[event_type]}")
            check.setObjectName("settingsCheck")
            check.setChecked(True)
            check.setCursor(Qt.PointingHandCursor)
            check.toggled.connect(
                lambda checked, key=event_type: self._on_preference_toggled(key, checked))
            self.preference_boxes[event_type] = check
            box.addWidget(check)
        self.preference_message = QLabel("")
        self.preference_message.setObjectName("settingsMessage")
        self.preference_message.setWordWrap(True)
        self.preference_message.hide()
        box.addWidget(self.preference_message)
        return card

    # ---------- Step 14F: Appearance (sidebar customization) ----------
    def _build_appearance_card(self) -> QFrame:
        card, box = self._card(
            "Appearance",
            "Customize the sidebar: choose the size of each icon and drag it exactly where "
            "you want it. Your layout is saved for this account only.",
        )
        self.sidebar_edit_button = QPushButton("Customize Sidebar")
        self.sidebar_edit_button.setObjectName("catalogPrimaryButton")
        self.sidebar_edit_button.setCursor(Qt.PointingHandCursor)
        self.sidebar_edit_button.clicked.connect(
            lambda _checked=False: self.sidebar_edit_requested.emit())
        box.addWidget(self.sidebar_edit_button, alignment=Qt.AlignLeft)
        self.sidebar_editor = SidebarEditorPanel()
        self.sidebar_editor.hide()
        box.addWidget(self.sidebar_editor)
        self._build_outer_margin_controls(box)
        return card

    # ---------- Appearance: Outer Margin (size of the floating app container) ----------
    # 0 means "automatic" (the default: the gap grows with the window). The slider only
    # PREVIEWS (outer_margin_changed); nothing is saved until Save is pressed.
    def _build_outer_margin_controls(self, box):
        self._margin_saved = 0    # what is saved for this account (0 = automatic)
        self._margin_pending = 0  # what the slider shows right now
        self._auto_margin = 30    # the automatic gap for the current window (set by the dashboard)
        self._margin_enabled = True

        box.addSpacing(10)
        label = QLabel("Outer margin")
        label.setObjectName("settingsFieldLabel")
        box.addWidget(label)
        hint = QLabel(
            "Larger margins make the whole app container smaller. In a small window the margin "
            "is reduced automatically so nothing is clipped.")
        hint.setObjectName("settingsCardText")
        hint.setWordWrap(True)
        box.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.margin_slider = QSlider(Qt.Horizontal)
        self.margin_slider.setRange(MIN_OUTER_MARGIN, MAX_OUTER_MARGIN)
        self.margin_slider.setSingleStep(1)
        self.margin_slider.setPageStep(4)
        self.margin_slider.setAccessibleName("Outer margin")
        self.margin_slider.valueChanged.connect(self._on_margin_slider)
        row.addWidget(self.margin_slider, 1)
        self.margin_value_label = QLabel("")
        self.margin_value_label.setObjectName("settingsMessage")
        self.margin_value_label.setMinimumWidth(130)
        self.margin_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.margin_value_label)
        box.addLayout(row)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.margin_save_button = QPushButton("Save")
        self.margin_save_button.setObjectName("catalogPrimaryButton")
        self.margin_cancel_button = QPushButton("Cancel")
        self.margin_cancel_button.setObjectName("catalogClearButton")
        self.margin_reset_button = QPushButton("Reset to Default")
        self.margin_reset_button.setObjectName("catalogClearButton")
        for button in (self.margin_save_button, self.margin_cancel_button, self.margin_reset_button):
            button.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(button)
        buttons.addStretch()
        box.addLayout(buttons)
        self.margin_save_button.clicked.connect(
            lambda _checked=False: self.outer_margin_save_requested.emit(self._margin_pending))
        self.margin_cancel_button.clicked.connect(lambda _checked=False: self._revert_margin())
        self.margin_reset_button.clicked.connect(lambda _checked=False: self._reset_margin())

        self.margin_message = QLabel("")
        self.margin_message.setObjectName("settingsMessage")
        self.margin_message.setWordWrap(True)
        self.margin_message.hide()
        box.addWidget(self.margin_message)
        self._refresh_margin_controls()

    def _refresh_margin_controls(self):
        """Make the slider, label and buttons agree with the pending/saved state. Sends nothing."""
        shown = self._margin_pending or max(MIN_OUTER_MARGIN, min(MAX_OUTER_MARGIN, self._auto_margin))
        self.margin_slider.blockSignals(True)
        self.margin_slider.setValue(shown)
        self.margin_slider.blockSignals(False)
        self.margin_value_label.setText(
            f"Automatic ({self._auto_margin} px)" if not self._margin_pending
            else f"{self._margin_pending} px")
        changed = self._margin_pending != self._margin_saved
        self.margin_save_button.setEnabled(self._margin_enabled and changed)
        self.margin_cancel_button.setEnabled(changed)
        self.margin_reset_button.setEnabled(self._margin_enabled and self._margin_pending != 0)
        self.margin_slider.setEnabled(self._margin_enabled)

    def _on_margin_slider(self, value: int):
        self._margin_pending = int(value)
        self.margin_message.hide()
        self._refresh_margin_controls()
        self.outer_margin_changed.emit(self._margin_pending)

    def _revert_margin(self):
        """Cancel: go back to what is saved and show it at once."""
        self._margin_pending = self._margin_saved
        self.margin_message.hide()
        self._refresh_margin_controls()
        self.outer_margin_changed.emit(self._margin_pending)

    def _reset_margin(self):
        """Reset to Default: the automatic margin (previewed; Save makes it permanent)."""
        self._margin_pending = 0
        self.margin_message.hide()
        self._refresh_margin_controls()
        self.outer_margin_changed.emit(0)

    def set_outer_margin(self, saved: int):
        """Show this account's saved margin (0 = automatic). Sends no signal."""
        self._margin_saved = self._margin_pending = int(saved or 0)
        self._refresh_margin_controls()

    def set_auto_margin(self, value: int):
        """The automatic gap for the current window (only used to label/position the slider)."""
        if int(value) != self._auto_margin:
            self._auto_margin = int(value)
            self._refresh_margin_controls()

    def set_outer_margin_enabled(self, enabled: bool):
        self._margin_enabled = bool(enabled)
        self._refresh_margin_controls()

    def mark_margin_saved(self, value: int):
        """The dashboard saved `value`; it is now this account's margin."""
        self._margin_saved = self._margin_pending = int(value or 0)
        self._refresh_margin_controls()
        self.show_margin_result("Outer margin saved." if value else "Outer margin reset to the default.",
                                error=False)

    def show_margin_result(self, text: str, *, error: bool):
        self.margin_message.setText(text)
        self.margin_message.setProperty("error", error)
        self.margin_message.style().unpolish(self.margin_message)
        self.margin_message.style().polish(self.margin_message)
        self.margin_message.setVisible(bool(text))

    def revert_unsaved_margin(self):
        """Leaving Settings throws away an unsaved preview (only the saved margin stays)."""
        if self._margin_pending != self._margin_saved:
            self._revert_margin()

    def set_sidebar_editing(self, editing: bool):
        """Show the editor controls while Sidebar Editing Mode is on."""
        self.sidebar_editor.setVisible(bool(editing))
        self.sidebar_edit_button.setVisible(not editing)

    def set_sidebar_edit_enabled(self, enabled: bool):
        """Only a signed-in account with a saved layout can customize (not the demo)."""
        self.sidebar_edit_button.setEnabled(bool(enabled))
        self.sidebar_edit_button.setToolTip(
            "" if enabled else "Log in with your school account to customize the sidebar.")

    def _on_preference_toggled(self, event_type: str, checked: bool):
        if not self._loading_preferences:
            self.preference_changed.emit(event_type, checked)

    def _build_workspaces_card(self) -> QFrame:
        card, box = self._card(
            "Workspaces",
            "A workspace is a part of KitLend you are authorized to use with this account. "
            "Only the workspaces assigned to your account are listed.",
        )
        self.workspace_list = QVBoxLayout()
        self.workspace_list.setSpacing(8)
        box.addLayout(self.workspace_list)
        note = QLabel(HOW_TO_GET_ACCESS)
        note.setObjectName("settingsCardText")
        note.setWordWrap(True)
        box.addWidget(note)
        return card

    # (pill text, pill tone) for each status. Same pill widget the rest of the app uses.
    _OWNER_PILL = {
        STATUS_PENDING: ("Pending", "purple"),
        STATUS_APPROVED: ("Approved", "mint"),
        STATUS_REJECTED: ("Rejected", "alert"),
    }

    @staticmethod
    def _owner_status_text(application) -> str:
        if application.is_pending:
            return (f"Application {application.application_id} is waiting for review. "
                    "You cannot send another one until it is reviewed.")
        if application.is_approved:
            return (f"Application {application.application_id} was approved. "
                    "You can switch to the Student Owner workspace in Workspaces above.")
        return (f"Application {application.application_id} was rejected. "
                "You may apply again.")

    def _build_student_owner_card(self) -> QFrame:
        card, box = self._card(
            "Become a Student Owner",
            "Student Owners can lend their own items to other students. Applying does not "
            "change anything else: you can keep borrowing normally whatever happens to your "
            "application, and sending it does not make you a Student Owner.",
        )
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.owner_status_label = QLabel("You have not applied yet.")
        self.owner_status_label.setObjectName("settingsMessage")
        self.owner_status_label.setWordWrap(True)
        status_row.addWidget(self.owner_status_label, 1)
        self.owner_status_pill = StatusPill("Pending", "sun")
        self.owner_status_pill.hide()
        status_row.addWidget(self.owner_status_pill, alignment=Qt.AlignTop)
        box.addLayout(status_row)

        self.owner_block_label = QLabel("")
        self.owner_block_label.setObjectName("settingsCardText")
        self.owner_block_label.setWordWrap(True)
        self.owner_block_label.hide()
        box.addWidget(self.owner_block_label)

        self.owner_form = QWidget()
        form = QVBoxLayout(self.owner_form)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        form.addWidget(self._field_label("Why do you want to become a Student Owner?"))
        self.owner_reason_input = self._owner_text_box(
            "Tell us why you would like to lend items.", MAX_REASON_LENGTH)
        form.addWidget(self.owner_reason_input)
        form.addWidget(self._field_label("Which items do you intend to lend?"))
        self.owner_items_input = self._owner_text_box(
            "For example: a scientific calculator, a drawing tablet, two textbooks.",
            MAX_ITEMS_LENGTH)
        form.addWidget(self.owner_items_input)

        rules_title = QLabel("Student Owner lending rules")
        rules_title.setObjectName("settingsFieldLabel")
        form.addWidget(rules_title)
        rules = QLabel("\n".join(f"•  {rule}" for rule in STUDENT_OWNER_RULES))
        rules.setObjectName("settingsCardText")
        rules.setWordWrap(True)
        form.addWidget(rules)
        self.owner_agree_box = QCheckBox("I have read and agree to the Student Owner lending rules.")
        self.owner_agree_box.setObjectName("settingsCheck")
        self.owner_agree_box.setCursor(Qt.PointingHandCursor)
        form.addWidget(self.owner_agree_box)

        self.owner_message = QLabel("")
        self.owner_message.setObjectName("settingsMessage")
        self.owner_message.setWordWrap(True)
        self.owner_message.hide()
        form.addWidget(self.owner_message)

        self.owner_submit_button = QPushButton("Submit Application")
        self.owner_submit_button.setObjectName("catalogPrimaryButton")
        self.owner_submit_button.setCursor(Qt.PointingHandCursor)
        self.owner_submit_button.clicked.connect(self._submit_owner_application)
        form.addWidget(self.owner_submit_button, alignment=Qt.AlignLeft)
        box.addWidget(self.owner_form)

        self.owner_history_title = QLabel("Your applications")
        self.owner_history_title.setObjectName("settingsFieldLabel")
        self.owner_history_title.hide()
        box.addWidget(self.owner_history_title)
        self.owner_history = QVBoxLayout()
        self.owner_history.setSpacing(8)
        box.addLayout(self.owner_history)
        return card

    @staticmethod
    def _owner_text_box(placeholder: str, max_length: int) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setObjectName("settingsTextBox")
        edit.setPlaceholderText(placeholder)
        edit.setFixedHeight(84)
        edit.setTabChangesFocus(True)
        edit.setProperty("maxLength", max_length)
        edit.textChanged.connect(lambda e=edit: SettingsScreen._limit_text(e))
        return edit

    @staticmethod
    def _limit_text(edit: QPlainTextEdit):
        limit = edit.property("maxLength")
        text = edit.toPlainText()
        if limit and len(text) > limit:
            edit.blockSignals(True)
            edit.setPlainText(text[:limit])
            edit.moveCursor(edit.textCursor().MoveOperation.End)
            edit.blockSignals(False)

    def _submit_owner_application(self):
        self.owner_application_submitted.emit(
            self.owner_reason_input.toPlainText(), self.owner_items_input.toPlainText(),
            self.owner_agree_box.isChecked())

    def _owner_history_row(self, application) -> QFrame:
        row = QFrame()
        row.setObjectName("settingsWorkspaceRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        name = QLabel(f"{application.application_id} · "
                      f"{format_notification_time(application.submitted_at)}")
        name.setObjectName("settingsWorkspaceName")
        texts.addWidget(name)
        items = QLabel(f"Items: {application.items_to_lend}")
        items.setObjectName("settingsCardText")
        items.setWordWrap(True)
        texts.addWidget(items)
        if application.is_rejected:
            why = QLabel("Reason for rejection: "
                         + (application.review_note or "No reason was recorded."))
            why.setObjectName("settingsCardText")
            why.setWordWrap(True)
            texts.addWidget(why)
        layout.addLayout(texts, 1)
        layout.addWidget(StatusPill(*self._OWNER_PILL[application.status]),
                         alignment=Qt.AlignTop)
        return row

    def _workspace_row(self, workspace, current=WORKSPACE_STUDENT, can_switch=False) -> QFrame:
        row = QFrame()
        row.setObjectName("settingsWorkspaceRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        name = QLabel(workspace.label)
        name.setObjectName("settingsWorkspaceName")
        description = QLabel(workspace.description)
        description.setObjectName("settingsCardText")
        description.setWordWrap(True)
        texts.addWidget(name)
        texts.addWidget(description)
        layout.addLayout(texts, 1)
        if workspace.key == current:
            text = "Default · Current" if workspace.is_default else "Current"
            layout.addWidget(StatusPill(text, "mint"), alignment=Qt.AlignTop)
        elif workspace.is_default:
            layout.addWidget(StatusPill("Default", "purple"), alignment=Qt.AlignTop)
        if can_switch and workspace.key != current and workspace.key in (
                WORKSPACE_STUDENT, WORKSPACE_STUDENT_OWNER):
            button = QPushButton(f"Switch to {workspace.label}")
            button.setObjectName("catalogPrimaryButton")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _c=False, key=workspace.key: self.workspace_switch_requested.emit(key))
            layout.addWidget(button, alignment=Qt.AlignTop)
            self._workspace_switch_buttons[workspace.key] = button
        return row
