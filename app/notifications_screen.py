"""KitLend Notifications screen (Step 11, redesigned in Step 26).

Shows the student's own notifications, newest first: the message, when it happened,
and whether it is read or unread.

Rules this screen follows:
  * It only DISPLAYS the notifications it is given and ASKS for changes through
    signals. It never creates notifications and never touches the database; the
    dashboard saves "mark as read" through NotificationService and then hands the
    refreshed list back. (Notifications are created only by real request events,
    inside RequestService.)
  * Nothing here is sample data. A brand-new student sees the empty state.
  * Step 11 notifications cover two real events: request submitted and request
    cancelled. Approval, rejection, pickup, return and reminder notifications come
    later, when those events can actually happen.

Step 26: All / Unread / Read tabs of compact rows (unread ones carry a lavender accent);
the soft-dark styles live in app/notifications_theme.py and apply to this screen only.
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.catalog_screen import CATALOG_STYLESHEET
from app.dashboard_widgets import ElidedLabel
from app.header_style import HEADER_QSS, accent_html
from app.my_list_screen import MY_LIST_STYLESHEET
from app.my_requests_screen import MY_REQUESTS_STYLESHEET
from app.notification_service import format_notification_time
from app.notifications_theme import NOTIFICATIONS_V2_QSS

NOTIFICATIONS_INFO_TEXT = (
    "Notifications tell you when something happens to your borrowing requests on this "
    "computer. For now that means a request you submitted or cancelled. Updates from "
    "lenders and administrators, such as approvals, will appear here once that part of "
    "KitLend exists."
)


TAB_ALL = "all"
TAB_UNREAD = "unread"
TAB_READ = "read"
TAB_LABELS = {TAB_ALL: "All", TAB_UNREAD: "Unread", TAB_READ: "Read"}


class NotificationCard(QFrame):
    """One notification as a compact row: title, message, date/time, state, Mark as read.

    (The class keeps its old name; it is a row now, not a box.)
    """

    mark_read_clicked = Signal(int)  # sends the notification id

    def __init__(self, notification, parent=None):
        super().__init__(parent)
        self.notification = notification
        unread = notification.is_unread
        self.setObjectName("notifRow")
        self.setProperty("unread", unread)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 12, 8, 12)
        row.setSpacing(10)

        dot = QLabel("●")
        dot.setObjectName("notifDot")
        dot.setProperty("unread", unread)
        dot.setFixedWidth(12)
        row.addWidget(dot, alignment=Qt.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(10)
        title = ElidedLabel(notification.title)
        title.setObjectName("notifTitle")
        title.setProperty("unread", unread)
        top.addWidget(title, 1)
        self.status_pill = QLabel("Unread" if unread else "Read")
        self.status_pill.setObjectName("notifState")
        self.status_pill.setProperty("unread", unread)
        top.addWidget(self.status_pill)
        self.time_label = QLabel(format_notification_time(notification.created_at))
        self.time_label.setObjectName("notifTime")
        top.addWidget(self.time_label)
        texts.addLayout(top)

        self.message_label = QLabel(notification.message)
        self.message_label.setObjectName("notifMessage")
        self.message_label.setProperty("unread", unread)
        self.message_label.setWordWrap(True)
        texts.addWidget(self.message_label)
        row.addLayout(texts, 1)

        self.mark_read_button = None
        if unread:
            button = QPushButton("Mark as read")
            button.setObjectName("notifMarkButton")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda: self.mark_read_clicked.emit(notification.id))
            row.addWidget(button, alignment=Qt.AlignTop)
            self.mark_read_button = button


class NotificationsScreen(QWidget):
    """All / Unread / Read tabs, a 'Mark all as read' button and compact notification rows.

    Signals:
      mark_read_requested(int)  - 'Mark as read' on one notification (its id)
      mark_all_read_requested   - 'Mark all as read'
      browse_catalog_requested  - button in the empty state
    """

    mark_read_requested = Signal(int)
    mark_all_read_requested = Signal()
    browse_catalog_requested = Signal()

    def __init__(self, notifications=None, parent=None, *, stored_locally: bool = False):
        super().__init__(parent)
        self._stored_locally = stored_locally
        self.setObjectName("notificationsScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            CATALOG_STYLESHEET + MY_LIST_STYLESHEET + MY_REQUESTS_STYLESHEET
            + HEADER_QSS + NOTIFICATIONS_V2_QSS
        )
        self._notifications = []
        self._tab = TAB_ALL
        self._visible = []

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(5000)
        self._banner_timer.timeout.connect(lambda: self.banner.hide())

        self._build_ui()
        self.set_notifications(notifications if notifications is not None else [])

    # ---------- public API ----------
    @property
    def notifications(self) -> list:
        """Everything the screen holds, newest first, whatever tab is open (for tests)."""
        return list(self._notifications)

    @property
    def visible_notifications(self) -> list:
        """The notifications shown in the selected tab."""
        return list(self._visible)

    @property
    def unread_count(self) -> int:
        return sum(1 for note in self._notifications if note.is_unread)

    @property
    def current_tab(self) -> str:
        return self._tab

    @property
    def counts_text(self) -> str:
        return self.counts_label.text()

    def set_notifications(self, notifications):
        """Replace everything shown (the list should already be this student's only)."""
        notifications = list(notifications)
        ids = [note.id for note in notifications]
        if len(ids) != len(set(ids)):
            raise ValueError("Notification IDs must be unique.")
        self._notifications = notifications
        self._refresh()

    def set_tab(self, tab: str):
        """TAB_ALL, TAB_UNREAD or TAB_READ."""
        if tab not in TAB_LABELS:
            raise ValueError(f"Unknown tab: {tab}")
        self._tab = tab
        self._tab_buttons[tab].setChecked(True)
        self._refresh()

    def cards(self) -> list:
        """The notification rows currently on screen, top to bottom (for tests)."""
        return [self.list_layout.itemAt(i).widget() for i in range(self.list_layout.count())]

    def show_message(self, text: str):
        self.banner.setText(text)
        self.banner.show()
        self._banner_timer.start()

    # ---------- building ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)

        scroll = QScrollArea()
        scroll.setObjectName("catalogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("catalogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 10, 8)
        layout.setSpacing(12)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_guide())

        self.banner = QLabel("")
        self.banner.setObjectName("myListBanner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        layout.addWidget(self.banner)

        layout.addLayout(self._build_toolbar())

        self.list_section = QWidget()
        self.list_section.setObjectName("catalogContent")
        section_box = QVBoxLayout(self.list_section)
        section_box.setContentsMargins(0, 0, 0, 0)
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(0)
        section_box.addLayout(self.list_layout)
        layout.addWidget(self.list_section)

        self.empty_state = self._build_empty_state()
        layout.addWidget(self.empty_state)
        layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("catalogHeader")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(2, 4, 2, 6)
        layout.setSpacing(6)

        if not self._stored_locally:
            tag = QLabel("Preview · Sample data only")
            tag.setObjectName("catalogTag")
            tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            layout.addWidget(tag, alignment=Qt.AlignLeft)

        title = QLabel(accent_html("Notifications", ""))
        title.setObjectName("catalogTitle")
        layout.addWidget(title)

        subtitle = QLabel("Updates about your borrowing requests, newest first.")
        subtitle.setObjectName("catalogSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.local_notice = QLabel(
            "Stored on this computer only. Not sent to school administrators.")
        self.local_notice.setObjectName("notifNotice")
        self.local_notice.setWordWrap(True)
        self.local_notice.setVisible(self._stored_locally)
        layout.addWidget(self.local_notice)

        self.counts_label = QLabel("")
        self.counts_label.setObjectName("notifCounts")
        self.counts_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.counts_label)
        return header

    def _build_guide(self) -> QWidget:
        """A collapsed 'About notifications' that opens to the explanation text."""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.guide_toggle = QPushButton("▸  About notifications")
        self.guide_toggle.setObjectName("notifGuideToggle")
        self.guide_toggle.setCheckable(True)
        self.guide_toggle.setCursor(Qt.PointingHandCursor)
        self.guide_toggle.toggled.connect(self._on_guide_toggled)
        layout.addWidget(self.guide_toggle, alignment=Qt.AlignLeft)

        self.guide_body = QFrame()
        self.guide_body.setObjectName("myListInfo")
        body = QVBoxLayout(self.guide_body)
        body.setContentsMargins(16, 12, 16, 12)
        text = QLabel(NOTIFICATIONS_INFO_TEXT)
        text.setObjectName("myListInfoText")
        text.setWordWrap(True)
        body.addWidget(text)
        self.guide_body.hide()
        layout.addWidget(self.guide_body)
        return holder

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_buttons = {}
        for tab in (TAB_ALL, TAB_UNREAD, TAB_READ):
            button = QPushButton(TAB_LABELS[tab])
            button.setObjectName("notifTab")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, tab=tab: self.set_tab(tab))
            self._tab_group.addButton(button)
            self._tab_buttons[tab] = button
            row.addWidget(button)
        self._tab_buttons[TAB_ALL].setChecked(True)
        row.addStretch()
        self.mark_all_button = QPushButton("Mark all as read")
        self.mark_all_button.setObjectName("notifMarkAll")
        self.mark_all_button.setCursor(Qt.PointingHandCursor)
        self.mark_all_button.clicked.connect(self.mark_all_read_requested.emit)
        row.addWidget(self.mark_all_button)
        return row

    def _build_empty_state(self) -> QFrame:
        box = QFrame()
        box.setObjectName("catalogEmpty")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignHCenter)

        icon = QLabel("◌")  # Kit appears on the Dashboard only
        icon.setObjectName("catalogEmptyIcon")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        self.empty_title = QLabel("")
        self.empty_title.setObjectName("catalogEmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_title)

        self.empty_text = QLabel("")
        self.empty_text.setObjectName("catalogEmptyText")
        self.empty_text.setAlignment(Qt.AlignCenter)
        self.empty_text.setWordWrap(True)
        layout.addWidget(self.empty_text)

        self.empty_button = QPushButton("Browse Catalog")
        self.empty_button.setObjectName("catalogPrimaryButton")
        self.empty_button.setCursor(Qt.PointingHandCursor)
        self.empty_button.clicked.connect(self.browse_catalog_requested.emit)
        layout.addWidget(self.empty_button, alignment=Qt.AlignHCenter)
        return box

    # ---------- refreshing what is shown ----------
    @staticmethod
    def _clear(layout):
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def _in_tab(self, tab: str) -> list:
        if tab == TAB_UNREAD:
            return [n for n in self._notifications if n.is_unread]
        if tab == TAB_READ:
            return [n for n in self._notifications if n.is_read]
        return list(self._notifications)

    def _refresh(self):
        notes = self._notifications
        unread = self.unread_count
        counts = {tab: len(self._in_tab(tab)) for tab in TAB_LABELS}

        if unread:
            first = f'<b style="color:#B9A8F5;">{unread}</b> unread'
        else:
            first = "<b>0</b> unread"
        self.counts_label.setText(f"{first}  ·  <b>{len(notes)}</b> total")
        for tab, button in self._tab_buttons.items():
            button.setText(f"{TAB_LABELS[tab]}  {counts[tab]}")

        self._visible = self._in_tab(self._tab)
        self._clear(self.list_layout)
        for note in self._visible:
            card = NotificationCard(note)
            card.mark_read_clicked.connect(self.mark_read_requested.emit)
            self.list_layout.addWidget(card)

        self.mark_all_button.setEnabled(unread > 0)
        self.list_section.setVisible(bool(self._visible))
        self.empty_state.setVisible(not self._visible)
        if not self._visible:
            self._update_empty_state()

    def _update_empty_state(self):
        if not self._notifications:
            self.empty_title.setText("No notifications yet")
            self.empty_text.setText(
                "When you submit or cancel a borrowing request, a notification will appear "
                "here. Nothing has happened on your account yet.")
            self.empty_button.setVisible(True)
            return
        self.empty_button.setVisible(False)
        if self._tab == TAB_UNREAD:
            self.empty_title.setText("You are all caught up")
            self.empty_text.setText("Notifications you have not read yet will show up here.")
        else:
            self.empty_title.setText("No read notifications yet")
            self.empty_text.setText("Notifications you mark as read will move here.")

    def _on_guide_toggled(self, expanded: bool):
        self.guide_body.setVisible(expanded)
        self.guide_toggle.setText(("▾" if expanded else "▸") + "  About notifications")
