"""KitLend Student Dashboard screen.

Two modes:
  * Demo (default, `signed_in_email=None`): sample data, not logged in.
  * Authenticated (`signed_in_email="..."`): shows the real student with
    their own (currently empty) data and a Logout button.

Safety notes (by design):
  * This screen is built from a `DemoData` object and nothing else. It has no
    user account, no role, and no login state.
  * The sidebar only contains student pages. There are no lender or
    administrator pages, and nothing here can switch to them.
  * The only way out is the `exit_demo_requested` signal -> back to Login.
  * Workspace switching will be added ONLY inside Settings in a later step.
"""
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.dashboard_home import DashboardHomePage
from app.dashboard_widgets import ElidedLabel, PlaceholderPage
from app.sample_data import DemoData
from app.theme import PINK


@dataclass(frozen=True)
class NavItem:
    key: str
    icon: str
    label: str
    message: str  # shown on the placeholder page ("" for the real Dashboard page)


NAV_ITEMS = [
    NavItem("dashboard", "🏠", "Dashboard", ""),
    NavItem("catalog", "🔍", "Browse Catalog",
            "Browse Catalog is coming in a later step. Soon you will be able to "
            "search and filter books, gadgets, and tools here."),
    NavItem("borrowings", "📚", "My Borrowings",
            "My Borrowings is coming in a later step. Your full borrowing "
            "history and return details will appear here."),
    NavItem("reservations", "🔖", "Reservations",
            "Reservations is coming in a later step. You will be able to view "
            "and manage your reserved items here."),
    NavItem("notifications", "🔔", "Notifications",
            "Notifications is coming in a later step. Reminders and updates "
            "will appear here."),
    NavItem("settings", "⚙️", "Settings",
            "Settings is coming in a later step."),
]


class StudentDashboard(QWidget):
    """Banner + sidebar + a content area that shows one page at a time."""

    exit_demo_requested = Signal()
    logout_requested = Signal()

    def __init__(self, data: DemoData, signed_in_email: str | None = None, parent=None):
        super().__init__(parent)
        self._signed_in_email = signed_in_email
        self.setObjectName("dashboardScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._data = data
        self._nav_items = {item.key: item for item in NAV_ITEMS}
        self._nav_buttons = {}
        self._build_ui()
        self.go_to("dashboard")

    @property
    def is_authenticated(self) -> bool:
        return self._signed_in_email is not None

    def _emit_exit(self):
        if self.is_authenticated:
            self.logout_requested.emit()
        else:
            self.exit_demo_requested.emit()

    # ---------- UI construction ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_demo_banner())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        self.content_stack = QStackedWidget()
        self.home_page = DashboardHomePage(
            self._data,
            role_label="Student" if self.is_authenticated else "Student · Demo",
        )
        self.placeholder_page = PlaceholderPage()
        self.content_stack.addWidget(self.home_page)
        self.content_stack.addWidget(self.placeholder_page)
        body.addWidget(self.content_stack, 1)
        root.addLayout(body, 1)

        self.home_page.navigate_requested.connect(self.go_to)
        self.placeholder_page.back_requested.connect(lambda: self.go_to("dashboard"))

    def _build_demo_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("demoBanner")
        row = QHBoxLayout(banner)
        row.setContentsMargins(20, 8, 12, 8)
        row.setSpacing(12)

        tag = QLabel("SIGNED IN" if self.is_authenticated else "DEMO MODE")
        tag.setObjectName("demoTag")
        row.addWidget(tag)

        if self.is_authenticated:
            banner_text = f"Signed in as {self._signed_in_email} · Local development account"
        else:
            banner_text = "Sample data only · You are not logged in · Nothing is saved or borrowed"
        text = ElidedLabel(banner_text)
        text.setObjectName("demoBannerText")
        row.addWidget(text, 1)

        self.exit_button = QPushButton("Log Out" if self.is_authenticated else "Exit Demo")
        self.exit_button.setObjectName("exitDemoButton")
        self.exit_button.setCursor(Qt.PointingHandCursor)
        self.exit_button.clicked.connect(self._emit_exit)
        row.addWidget(self.exit_button)
        return banner

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 22, 16, 16)
        layout.setSpacing(6)

        logo = QLabel(f"Kit<span style='color:{PINK}'>Lend</span>")
        logo.setObjectName("sidebarLogo")
        role = QLabel("Student Dashboard")
        role.setObjectName("sidebarRole")
        layout.addWidget(logo)
        layout.addWidget(role)
        layout.addSpacing(14)

        # Exclusive group: exactly one nav button is highlighted at a time
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for item in NAV_ITEMS:
            button = QPushButton(f"{item.icon}   {item.label}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, key=item.key: self.go_to(key))
            self._nav_group.addButton(button)
            self._nav_buttons[item.key] = button
            layout.addWidget(button)

        layout.addStretch()
        layout.addWidget(self._build_profile_card())
        layout.addSpacing(4)

        back = QPushButton("↩   Log Out" if self.is_authenticated else "↩   Back to Login")
        back.setObjectName("sidebarExitButton")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(self._emit_exit)
        layout.addWidget(back)
        return sidebar

    def _build_profile_card(self) -> QFrame:
        """A plain, non-clickable name tag (no menu, no account switching)."""
        card = QFrame()
        card.setObjectName("profileCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(10, 10, 10, 10)
        row.setSpacing(10)

        avatar = QLabel(self._data.student.initials)
        avatar.setObjectName("avatar")
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignCenter)
        row.addWidget(avatar)

        names = QVBoxLayout()
        names.setSpacing(0)
        name = ElidedLabel(self._data.student.full_name)
        name.setObjectName("profileName")
        subtitle = ElidedLabel(self._signed_in_email if self.is_authenticated else "Demo student")
        subtitle.setObjectName("profileRole")
        names.addWidget(name)
        names.addWidget(subtitle)
        row.addLayout(names, 1)
        return card

    # ---------- navigation ----------
    def go_to(self, key: str):
        """Show a page. Real page for 'dashboard', placeholder for the rest."""
        item = self._nav_items.get(key)
        if item is None:
            return  # unknown page names are ignored
        self._nav_buttons[key].setChecked(True)
        if key == "dashboard":
            self.content_stack.setCurrentWidget(self.home_page)
        else:
            self.placeholder_page.set_content(item.label, item.message)
            self.content_stack.setCurrentWidget(self.placeholder_page)
