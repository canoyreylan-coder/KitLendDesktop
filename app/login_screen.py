"""KitLend Login Screen (UI only; credentials are checked by the window via AuthService)."""
import re
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
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

from app.theme import CREAM, NAVY, PERIWINKLE, PINK, AUTH_STYLESHEET

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
MASCOT_PATH = ASSETS_DIR / "mascot.png"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MascotPlaceholder(QWidget):
    """Shows assets/mascot.png if it exists, otherwise a dashed placeholder."""

    def __init__(self, size: int = 220, parent=None):
        super().__init__(parent)
        self._size = size
        self._pixmap = QPixmap(str(MASCOT_PATH)) if MASCOT_PATH.exists() else QPixmap()
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            return

        rect = QRectF(4, 4, self.width() - 8, self.height() - 8)
        painter.setBrush(QColor(255, 255, 255, 18))
        pen = QPen(QColor(PINK), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 36, 36)
        painter.setPen(QColor(PINK))
        painter.drawText(
            rect, Qt.AlignCenter, "Mascot\nplaceholder\n(assets/mascot.png)"
        )


class PasswordField(QLineEdit):
    """Password input with a built-in Show/Hide button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)

        self.toggle_button = QPushButton("Show")
        self.toggle_button.setObjectName("toggleButton")
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setFocusPolicy(Qt.NoFocus)
        self.toggle_button.toggled.connect(self._on_toggled)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.addStretch()
        layout.addWidget(self.toggle_button)
        self.setTextMargins(0, 0, 64, 0)

    def _on_toggled(self, visible: bool):
        self.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.toggle_button.setText("Hide" if visible else "Show")


class LoginScreen(QWidget):
    """The login screen. Emits signals; the window decides what happens next."""

    login_requested = Signal(str, str)  # email, password
    register_requested = Signal()
    forgot_password_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("loginScreen")
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

        slogan = QLabel("Borrow today,\nbrighter tomorrows.")
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
        for text in ("Books", "Gadgets", "Tools"):
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
        layout.setContentsMargins(34, 30, 34, 26)
        layout.setSpacing(6)

        heading = QLabel("Welcome back!")
        heading.setObjectName("heading")
        subheading = QLabel("Log in with your school email to start borrowing.")
        subheading.setObjectName("subheading")
        subheading.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(subheading)
        layout.addSpacing(12)

        # Email
        layout.addWidget(self._field_label("School email"))
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("yourname@csucc.edu.ph")
        self.email_input.setClearButtonEnabled(True)
        layout.addWidget(self.email_input)
        layout.addSpacing(6)

        # Password
        layout.addWidget(self._field_label("Password"))
        self.password_input = PasswordField()
        self.password_input.setPlaceholderText("Enter your password")
        layout.addWidget(self.password_input)

        # Forgot password
        self.forgot_button = QPushButton("Forgot password?")
        self.forgot_button.setObjectName("linkButton")
        self.forgot_button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.forgot_button, alignment=Qt.AlignRight)

        # Status message
        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setMinimumHeight(22)
        layout.addWidget(self.status_label)

        # Login
        self.login_button = QPushButton("Log In")
        self.login_button.setObjectName("primaryButton")
        self.login_button.setCursor(Qt.PointingHandCursor)
        self.login_button.setDefault(True)
        layout.addWidget(self.login_button)
        layout.addSpacing(8)

        # Register row
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addStretch()
        prompt = QLabel("New to KitLend?")
        prompt.setObjectName("subheading")
        self.register_button = QPushButton("Register")
        self.register_button.setObjectName("linkButton")
        self.register_button.setCursor(Qt.PointingHandCursor)
        row.addWidget(prompt)
        row.addWidget(self.register_button)
        row.addStretch()
        layout.addLayout(row)


        inner_layout.addWidget(card)

        # Wiring
        self.login_button.clicked.connect(self._on_login_clicked)
        self.email_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self._on_login_clicked)
        self.register_button.clicked.connect(self.register_requested.emit)
        self.forgot_button.clicked.connect(self.forgot_password_requested.emit)
        return wrapper

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    # ---------- behavior ----------
    def _on_login_clicked(self):
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email or not password:
            self.show_message("Please enter your email and password.", error=True)
            return
        if not EMAIL_PATTERN.match(email):
            self.show_message("That doesn't look like a valid email.", error=True)
            return

        self.login_requested.emit(email, password)

    def prefill_email(self, email: str):
        """Put an email in the field and move focus to the password box."""
        self.email_input.setText(email)
        self.password_input.clear()
        self.password_input.setFocus()

    def reset_form(self):
        """Clear credentials (used after logout)."""
        self.email_input.clear()
        self.password_input.clear()
        self.password_input.toggle_button.setChecked(False)
        self.status_label.setText("")

    def show_message(self, text: str, error: bool = False):
        self.status_label.setProperty("error", error)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.setText(text)
