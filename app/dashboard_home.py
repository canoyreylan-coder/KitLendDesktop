"""The main page of the Student Dashboard (Stage 2A redesign: soft-dark minimalism).

It only DISPLAYS data it is given. It cannot borrow, reserve, log in, or open any
lender/administrator area. When something is clicked it just emits `navigate_requested`
with a page name, and the dashboard screen decides what to show.

Where the numbers come from
  * Demo mode: the clearly-labelled sample DemoData given to the constructor.
  * Signed-in student: the dashboard calls set_requests(...) with that student's real saved
    requests and set_notifications(...) with their real notifications. Until then (and for
    students with no records) every list shows its empty state. Nothing is invented.
Choosing which request is a borrowing / reservation / pending is done in
app/dashboard_view.py with the same rules the other pages use.
"""
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from html import escape

from app.header_style import ACCENT_LAVENDER, HEADER_QSS
from app.catalog_screen import HAPPY_MASCOT_PATH
from app.dashboard_view import DUE_SOON_DAYS, EMPTY_VIEW, view_from_demo, view_from_requests
from app.dashboard_widgets import ReflowGrid
from app.home_theme import HOME_STYLESHEET
from app.home_widgets import HomeCard, HomeStat
from app.sample_data import DemoData

SECTION_SPACING = 16
MASCOT_SIZE = 72

# (button text, page key). The first one is the main action.
QUICK_ACTIONS = (
    ("Browse Catalog", "catalog"),
    ("My List", "my_list"),
    ("My Requests", "my_requests"),
    ("My Borrowings", "borrowings"),
)


def _greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


class DashboardHomePage(QScrollArea):
    """Scrollable page, so nothing gets cut off on small laptop screens (e.g. 1366x768)."""

    navigate_requested = Signal(str)  # "catalog", "borrowings", "reservations", ...

    def __init__(self, data: DemoData, role_label: str = "Student · Demo", parent=None):
        super().__init__(parent)
        self._role_label = role_label
        self._first_name = data.student.first_name
        self.setObjectName("homeScroll")
        self.setStyleSheet(HOME_STYLESHEET + HEADER_QSS)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("homeContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(SECTION_SPACING)

        layout.addWidget(self._build_welcome())
        layout.addWidget(self._build_stats(data))
        layout.addWidget(self._two_columns(self._build_borrowings_card(),
                                           self._build_pending_card()))
        layout.addWidget(self._two_columns(self._build_reservations_card(),
                                           self._build_notifications_card(data)))
        layout.addWidget(self._two_columns(self._build_activity_card(),
                                           self._build_quick_actions_card()))
        layout.addStretch()
        self.setWidget(content)

        self._notification_entries = [(n.title, n.message, n.unread) for n in data.notifications]
        self._apply_view(view_from_demo(data))
        self.set_notifications(self._notification_entries, data.unread_count)

    # ---------- small helpers ----------
    def _go(self, page: str):
        self.navigate_requested.emit(page)

    @staticmethod
    def _two_columns(left: QWidget, right: QWidget) -> ReflowGrid:
        return ReflowGrid([left, right], min_item_width=340, spacing=SECTION_SPACING)

    # ---------- welcome bar ----------
    def _build_welcome(self) -> QFrame:
        today = date.today()
        bar = QFrame()
        bar.setObjectName("homeWelcome")
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 6, 2, 10)
        row.setSpacing(16)

        texts = QVBoxLayout()
        texts.setSpacing(4)
        eyebrow = QLabel(f"{today:%A}, {today:%B} {today.day}  ·  {self._role_label}")
        eyebrow.setObjectName("homeEyebrow")
        texts.addWidget(eyebrow)
        title = QLabel(f'{_greeting()}, <span style="color:{ACCENT_LAVENDER};">'
                       f"{escape(self._first_name)}</span>")
        title.setObjectName("homeTitle")
        title.setWordWrap(True)
        texts.addWidget(title)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("homeSummary")
        self.summary_label.setWordWrap(True)
        texts.addWidget(self.summary_label)
        row.addLayout(texts, 1)

        browse = QPushButton("Browse Catalog")
        browse.setObjectName("homePrimary")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(lambda: self._go("catalog"))
        row.addWidget(browse, alignment=Qt.AlignVCenter)

        pixmap = QPixmap(str(HAPPY_MASCOT_PATH))  # Kit appears once, here, and only if present
        if not pixmap.isNull():
            mascot = QLabel()
            mascot.setObjectName("homeMascot")
            mascot.setFixedSize(MASCOT_SIZE, MASCOT_SIZE)
            mascot.setAlignment(Qt.AlignCenter)
            mascot.setPixmap(pixmap.scaled(MASCOT_SIZE, MASCOT_SIZE, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation))
            row.addWidget(mascot, alignment=Qt.AlignVCenter)
        return bar

    # ---------- summary tiles ----------
    def _build_stats(self, data: DemoData) -> QWidget:
        self.borrowings_stat = HomeStat("Active Borrowings", 0, "")
        self.pending_stat = HomeStat("Pending Requests", 0, "")
        self.reservations_stat = HomeStat("Reservations", 0, "")
        self.notification_stat = HomeStat("Unread Notifications", data.unread_count,
                                          "Unread messages")
        tiles = ((self.borrowings_stat, "borrowings"), (self.pending_stat, "my_requests"),
                 (self.reservations_stat, "reservations"),
                 (self.notification_stat, "notifications"))
        for tile, page in tiles:
            tile.clicked.connect(lambda page=page: self._go(page))
        return ReflowGrid([tile for tile, _ in tiles], min_item_width=190,
                          spacing=SECTION_SPACING)

    # ---------- cards ----------
    def _build_borrowings_card(self) -> HomeCard:
        self.borrowings_card = HomeCard("Active Borrowings", "Items you have, soonest due first",
                                        "View all")
        self.borrowings_card.action_clicked.connect(lambda: self._go("borrowings"))
        return self.borrowings_card

    def _build_pending_card(self) -> HomeCard:
        self.pending_card = HomeCard("Pending Requests", "Waiting for review", "View all")
        self.pending_card.action_clicked.connect(lambda: self._go("my_requests"))
        return self.pending_card

    def _build_reservations_card(self) -> HomeCard:
        self.reservations_card = HomeCard("Reservations", "Approved items waiting for you",
                                          "View all")
        self.reservations_card.action_clicked.connect(lambda: self._go("reservations"))
        return self.reservations_card

    def _build_notifications_card(self, data: DemoData) -> HomeCard:
        card = HomeCard("Notifications", f"{data.unread_count} unread", "View all")
        card.action_clicked.connect(lambda: self._go("notifications"))
        self.notifications_card = card
        return card

    def _build_activity_card(self) -> HomeCard:
        self.activity_card = HomeCard("Recent Activity", "Your latest request activity")
        return self.activity_card

    def _build_quick_actions_card(self) -> HomeCard:
        card = HomeCard("Quick Actions", "Jump straight to what you need")
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        for index, (text, page) in enumerate(QUICK_ACTIONS):
            button = QPushButton(text)
            button.setObjectName("homeAction")
            button.setCursor(Qt.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda _=False, page=page: self._go(page))
            grid.addWidget(button, index // 2, index % 2)
        card.add_row(holder)
        self.quick_actions_card = card
        return card

    # ---------- showing data ----------
    def set_requests(self, requests):
        """Show THIS student's real requests (all statuses are fine; the rules sort them).

        Called by the dashboard after every load from SQLite. An empty list shows the
        empty states. Nothing here changes a request.
        """
        self._apply_view(view_from_requests(requests))

    def _apply_view(self, view):
        self.summary_label.setText(view.summary)
        self.borrowings_stat.set_number(len(view.borrowings))
        self.borrowings_stat.set_hint(
            f"{view.due_soon_count} due within {DUE_SOON_DAYS} days"
            if view.borrowings else "Nothing borrowed")
        self.pending_stat.set_number(len(view.pending))
        self.pending_stat.set_hint("Waiting for review" if view.pending else "Nothing waiting")
        self.reservations_stat.set_number(len(view.reservations))
        self.reservations_stat.set_hint(
            f"{view.ready_count} ready for pickup" if view.reservations else "None right now")
        self.borrowings_card.set_rows(view.borrowings, "You have no active borrowings.", 4)
        self.pending_card.set_rows(view.pending, "You have no pending requests.", 4)
        self.reservations_card.set_rows(view.reservations, "You have no reservations.", 4)
        self.activity_card.set_rows(view.activity, "No recent activity.", 5)

    def _fill_notifications_card(self, entries):
        """entries: (title, message, unread) tuples, newest first. Shows the first three."""
        from app.dashboard_view import RowView
        rows = [RowView(title, message, dot_tone="pink" if unread else "muted", unread=unread)
                for title, message, unread in entries]
        self.notifications_card.set_rows(rows, "No notifications yet.", 3)

    def set_notifications(self, entries, unread_count: int):
        """Show the student's REAL notifications (called by the dashboard).

        `entries` are (title, message, unread) tuples, newest first; `unread_count`
        counts every unread notification, not just the three that are previewed.
        """
        entries = list(entries)
        self.notification_stat.set_number(unread_count)
        self.notifications_card.set_subtitle(f"{unread_count} unread")
        self._fill_notifications_card(entries)
