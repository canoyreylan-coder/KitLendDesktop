"""KitLend Student Registration Screen (UI only; the window saves via AuthService)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.auth_service import MAX_STUDENT_ID_LENGTH
from app.login_screen import MascotPlaceholder, PasswordField
from app.theme import PINK, AUTH_STYLESHEET

SCHOOL_DOMAIN = "@csucc.edu.ph"


class RegisterScreen(QWidget):
    """The registration screen. Emits a signal; the window handles navigation."""

    back_to_login_requested = Signal()
    # name, email, password, confirm, student id number
    register_requested = Signal(str, str, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("loginScreen")  # reuse the login screen's background style
        self.setStyleSheet(AUTH_STYLESHEET)  # Stage 1A-2: soft-dark look, only for this screen
        self._build_ui()

    # ---------- UI construction ----------
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_brand_panel(), 5)
        root.addWidget(self._build_form_panel(), 6)

    def _build_brand_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("brandPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(10)
        layout.addStretch()

        logo = QLabel(f"Kit<span style='color:{PINK}'>Lend</span>")
        logo.setObjectName("brandLogo")
        logo.setAlignment(Qt.AlignCenter)

        slogan = QLabel("Join the community.\nBorrow today, brighter tomorrows.")
        slogan.setObjectName("brandSlogan")
        slogan.setAlignment(Qt.AlignCenter)

        layout.addWidget(logo)
        layout.addWidget(slogan)
        layout.addSpacing(8)
        layout.addWidget(MascotPlaceholder(), alignment=Qt.AlignHCenter)
        layout.addSpacing(8)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addStretch()
        for text in ("Students only", "Free to join"):
            chip = QLabel(text)
            chip.setObjectName("chip")
            chips.addWidget(chip)
        chips.addStretch()
        layout.addLayout(chips)
        layout.addStretch()
        return panel

    def _build_form_panel(self) -> QWidget:
        wrapper = QFrame()
        wrapper.setObjectName("formPanel")
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("formScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        wrapper_layout.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("formInner")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(30, 20, 30, 20)
        inner_layout.setAlignment(Qt.AlignCenter)
        scroll.setWidget(inner)

        card = QFrame()
        card.setObjectName("loginCard")
        card.setMaximumWidth(420)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(34, 26, 34, 22)
        layout.setSpacing(5)

        heading = QLabel("Create your account")
        heading.setObjectName("heading")
        subheading = QLabel("Register with your official CSUCC school email.")
        subheading.setObjectName("subheading")
        subheading.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(subheading)
        layout.addSpacing(8)

        # Full name
        layout.addWidget(self._field_label("Full name"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Juan Dela Cruz")
        self.name_input.setClearButtonEnabled(True)
        layout.addWidget(self.name_input)

        # Email
        layout.addWidget(self._field_label("Official school email"))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText(f"yourname{SCHOOL_DOMAIN}")
        self.email_input.setClearButtonEnabled(True)
        layout.addWidget(self.email_input)

        # Student ID Number (required; any format the school uses)
        layout.addWidget(self._field_label("Student ID Number"))
        self.student_id_input = QLineEdit()
        self.student_id_input.setPlaceholderText("Your school-issued ID number")
        self.student_id_input.setMaxLength(MAX_STUDENT_ID_LENGTH + 10)
        self.student_id_input.setClearButtonEnabled(True)
        layout.addWidget(self.student_id_input)

        # Password
        layout.addWidget(self._field_label("Password"))
        self.password_input = PasswordField()
        self.password_input.setPlaceholderText("Create a password")
        layout.addWidget(self.password_input)

        # Confirm password
        layout.addWidget(self._field_label("Confirm password"))
        self.confirm_input = PasswordField()
        self.confirm_input.setPlaceholderText("Type your password again")
        layout.addWidget(self.confirm_input)

        # Status message
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(34)
        layout.addWidget(self.status_label)

        # Register button
        self.register_button = QPushButton("Register")
        self.register_button.setObjectName("primaryButton")
        self.register_button.setCursor(Qt.PointingHandCursor)
        self.register_button.setDefault(True)
        layout.addWidget(self.register_button)
        layout.addSpacing(6)

        # Back to login row
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addStretch()
        prompt = QLabel("Already have an account?")
        prompt.setObjectName("subheading")
        self.back_button = QPushButton("Back to Login")
        self.back_button.setObjectName("linkButton")
        self.back_button.setCursor(Qt.PointingHandCursor)
        row.addWidget(prompt)
        row.addWidget(self.back_button)
        row.addStretch()
        layout.addLayout(row)

        inner_layout.addWidget(card)

        # Wiring (Enter key moves to the next field, last field submits)
        self.register_button.clicked.connect(self._on_register_clicked)
        self.back_button.clicked.connect(self.back_to_login_requested.emit)
        self.name_input.returnPressed.connect(self.email_input.setFocus)
        self.email_input.returnPressed.connect(self.student_id_input.setFocus)
        self.student_id_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.confirm_input.setFocus)
        self.confirm_input.returnPressed.connect(self._on_register_clicked)
        return wrapper

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    # ---------- behavior ----------
    def _on_register_clicked(self):
        # Validation and saving are done by AuthService (see MainWindow).
        self.register_requested.emit(
            self.name_input.text(),
            self.email_input.text(),
            self.password_input.text(),
            self.confirm_input.text(),
            self.student_id_input.text(),
        )

    def show_message(self, text: str, error: bool = False):
        self.status_label.setProperty("error", error)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(text)

    def reset_form(self):
        """Clear everything (used when leaving this screen)."""
        for field in (self.name_input, self.email_input, self.student_id_input,
                      self.password_input, self.confirm_input):
            field.clear()
        for field in (self.password_input, self.confirm_input):
            field.toggle_button.setChecked(False)  # back to hidden
        self.status_label.setText("")
