"""KitLend My Borrowings screen (Step 9, redesigned in Step 25).

Shows the items the student ACTUALLY has (or had), and nothing else:
  * Active          - Borrowed (overdue ones are marked, and sort first)
  * Return Pending  - Return Verification Pending
  * History         - Returned

Rules this screen follows (see app/borrowing_rules.py):
  * Pending and Approved - Awaiting Pickup requests are NEVER shown here. They
    stay in My Requests. Borrowing starts only when a lender/administrator
    confirms the physical handover.
  * The due date is never invented here. Each card uses the existing
    BorrowRequest.due_at (actual confirmed pickup + requested days).
  * There is no Cancel button: a borrowed item follows the return process.
  * The screen only DISPLAYS data it is given. It never creates, changes or
    returns a borrowing, so it can be empty for a real student today (nobody
    can confirm a handover yet).

Step 25: three tabs (Active, Return Pending, History) of compact cards; the soft-dark
styles live in app/my_borrowings_theme.py and apply to this screen only.
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

from app.borrowing_rules import is_overdue, split_borrowings
from app.catalog_screen import CATALOG_STYLESHEET, AdaptiveGrid
from app.dashboard_widgets import ElidedLabel
from app.header_style import HEADER_QSS, accent_html
from app.my_borrowings_theme import MY_BORROWINGS_V2_QSS
from app.my_list_screen import MY_LIST_STYLESHEET, make_icon_badge
from app.my_requests_screen import (
    BORROWING_RULE_TEXT,
    MY_REQUESTS_STYLESHEET,
    BorrowRequest,
    RequestStatus,
    format_dt,
    format_span,
    now_local,
    responsible_text,
)
from app.theme import CREAM, NAVY

TAB_ACTIVE = "active"
TAB_RETURN_PENDING = "return_pending"
TAB_HISTORY = "history"
TAB_LABELS = {TAB_ACTIVE: "Active", TAB_RETURN_PENDING: "Return Pending", TAB_HISTORY: "History"}
TAB_HINTS = {
    TAB_ACTIVE: "Items you have collected and not yet returned, soonest due first.",
    TAB_RETURN_PENDING: "You reported these as returned. Waiting for the lender or "
                        "administrator to confirm. Your original dates are kept.",
    TAB_HISTORY: "Returns that were verified, most recent first.",
}
TAB_STATUS = {
    TAB_ACTIVE: RequestStatus.BORROWED,
    TAB_RETURN_PENDING: RequestStatus.RETURN_PENDING,
    TAB_HISTORY: RequestStatus.RETURNED,
}


class BorrowFact(QWidget):
    """A small 'LABEL / value' pair with no box around it."""

    def __init__(self, label: str, value: str, muted: bool = False, overdue: bool = False,
                 parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label_widget = QLabel(label.upper())
        label_widget.setObjectName("borrowFactLabel")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("borrowFactValue")
        self.value_label.setProperty("muted", muted)
        self.value_label.setProperty("overdue", overdue)
        self.value_label.setWordWrap(True)
        layout.addWidget(label_widget)
        layout.addWidget(self.value_label)


def borrowing_facts(request: BorrowRequest, now, overdue: bool) -> list:
    """(label, value, muted, overdue) for a card: pickup, due, and one status detail.

    Dates come straight from the record: the due date is BorrowRequest.due_at
    (actual confirmed pickup + requested days). Nothing is calculated here.
    """
    due = request.due_at
    facts = [
        ("Picked up", format_dt(request.picked_up_at), False, False),
        ("Due", format_dt(due) if due is not None else "Not set", due is None, overdue),
    ]
    status = request.status
    if status is RequestStatus.BORROWED and due is not None:
        if overdue:
            facts.append(("Overdue", f"Past due by {format_span(now - due)}", False, True))
        else:
            facts.append(("Time left", f"{format_span(due - now)} left", False, False))
    else:
        label = status.info.changed_label or "Status changed"
        if request.status_changed_at is not None:
            facts.append((label, format_dt(request.status_changed_at), False, False))
        else:
            facts.append((label, "Not recorded", True, False))
    return facts


class BorrowingCard(QFrame):
    """One borrowing, compact: item, pickup date, due date and status. No action buttons
    (a borrowed item follows the return process; nothing here changes a record)."""

    def __init__(self, request: BorrowRequest, now, parent=None):
        super().__init__(parent)
        self.request = request
        item = request.item
        self.is_overdue = is_overdue(request, now)
        self.setObjectName("borrowCard")
        self.setProperty("closed", not request.is_active)
        self.setProperty("overdue", self.is_overdue)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(make_icon_badge(item), alignment=Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = ElidedLabel(item.title)
        title.setObjectName("borrowTitle")
        texts.addWidget(title)
        sub = ElidedLabel(f"{item.category} · {responsible_text(item)} · {request.request_id}")
        sub.setObjectName("borrowSub")
        texts.addWidget(sub)
        top.addLayout(texts, 1)

        status_key = "overdue" if self.is_overdue else request.status.value
        self.status_pill = QLabel("Overdue" if self.is_overdue else request.status.info.label)
        self.status_pill.setObjectName("borrowStatus")
        self.status_pill.setProperty("status", status_key)
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        top.addWidget(self.status_pill, alignment=Qt.AlignTop)
        layout.addLayout(top)

        facts = AdaptiveGrid(min_item_width=150, spacing=16)
        facts.set_widgets([BorrowFact(label, value, muted, red)
                           for label, value, muted, red
                           in borrowing_facts(request, now, self.is_overdue)])
        layout.addWidget(facts)


class MyBorrowingsScreen(QWidget):
    """Active / Return Pending / History tabs of compact borrowing cards.

    Signals:
      my_requests_requested - button in the empty state (opens My Requests)
    """

    my_requests_requested = Signal()

    def __init__(self, borrowings=None, clock=now_local, parent=None, *,
                 stored_locally: bool = False):
        super().__init__(parent)
        self._stored_locally = stored_locally
        self.setObjectName("myBorrowingsScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            CATALOG_STYLESHEET + MY_LIST_STYLESHEET + MY_REQUESTS_STYLESHEET
            + MY_BORROWINGS_STYLESHEET + HEADER_QSS + MY_BORROWINGS_V2_QSS
        )

        self._clock = clock               # lets tests use a fixed "now"
        self._current = []                # Borrowed + Return Verification Pending
        self._history = []
        self._tab = TAB_ACTIVE
        self._visible = []

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(5000)
        self._banner_timer.timeout.connect(lambda: self.banner.hide())

        self._build_ui()
        self.set_borrowings(borrowings if borrowings is not None else [])

    # ---------- public API ----------
    @property
    def current_requests(self) -> list:
        """Borrowed + Return Verification Pending, soonest due first."""
        return list(self._current)

    @property
    def history_requests(self) -> list:
        """Returned, most recent first."""
        return list(self._history)

    @property
    def active_requests(self) -> list:
        return self._in_tab(TAB_ACTIVE)

    @property
    def return_pending_requests(self) -> list:
        return self._in_tab(TAB_RETURN_PENDING)

    @property
    def visible_requests(self) -> list:
        """The borrowings shown in the selected tab."""
        return list(self._visible)

    @property
    def current_tab(self) -> str:
        return self._tab

    @property
    def counts_text(self) -> str:
        return self.counts_label.text()

    def set_borrowings(self, requests):
        """Give the screen this student's requests (all of them is fine).

        Anything that is not a confirmed borrowing is ignored, so a Pending or
        Approved request can never appear here by mistake.
        """
        requests = list(requests)
        ids = [request.request_id for request in requests]
        if len(ids) != len(set(ids)):
            raise ValueError("Request IDs must be unique.")
        self._current, self._history = split_borrowings(requests)
        self._refresh()

    def set_tab(self, tab: str):
        """TAB_ACTIVE, TAB_RETURN_PENDING or TAB_HISTORY."""
        if tab not in TAB_LABELS:
            raise ValueError(f"Unknown tab: {tab}")
        self._tab = tab
        self._tab_buttons[tab].setChecked(True)
        self._refresh()

    def refresh(self):
        """Redraw with the current time (the 'time left' text changes)."""
        self._refresh()

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

        layout.addLayout(self._build_tabs())
        self.tab_hint = QLabel("")
        self.tab_hint.setObjectName("borrowTabHint")
        self.tab_hint.setWordWrap(True)
        layout.addWidget(self.tab_hint)

        self.rows_container = QWidget()
        self.rows_container.setObjectName("catalogContent")
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(10)
        layout.addWidget(self.rows_container)

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

        title = QLabel(accent_html("My Borrowings", "Borrowings"))
        title.setObjectName("catalogTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "What you have collected, when it is due, and your returned history. "
            "Pending and awaiting-pickup requests stay in My Requests."
        )
        subtitle.setObjectName("catalogSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.local_notice = QLabel(
            "Stored on this computer only. Not sent to school administrators.")
        self.local_notice.setObjectName("borrowNotice")
        self.local_notice.setWordWrap(True)
        self.local_notice.setVisible(self._stored_locally)
        layout.addWidget(self.local_notice)

        self.counts_label = QLabel("")
        self.counts_label.setObjectName("borrowCounts")
        self.counts_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.counts_label)
        return header

    def _build_guide(self) -> QWidget:
        """A collapsed 'Borrowing Guide' that opens to the borrowing-time rule."""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.guide_toggle = QPushButton("▸  Borrowing Guide")
        self.guide_toggle.setObjectName("borrowGuideToggle")
        self.guide_toggle.setCheckable(True)
        self.guide_toggle.setCursor(Qt.PointingHandCursor)
        self.guide_toggle.toggled.connect(self._on_guide_toggled)
        layout.addWidget(self.guide_toggle, alignment=Qt.AlignLeft)

        self.guide_body = QFrame()
        self.guide_body.setObjectName("myListInfo")
        body = QVBoxLayout(self.guide_body)
        body.setContentsMargins(16, 12, 16, 12)
        text = QLabel(BORROWING_RULE_TEXT)  # the same rule text My Requests shows
        text.setObjectName("myListInfoText")
        text.setWordWrap(True)
        body.addWidget(text)
        self.guide_body.hide()
        layout.addWidget(self.guide_body)
        return holder

    def _build_tabs(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_buttons = {}
        for tab in (TAB_ACTIVE, TAB_RETURN_PENDING, TAB_HISTORY):
            button = QPushButton(TAB_LABELS[tab])
            button.setObjectName("borrowTab")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, tab=tab: self.set_tab(tab))
            self._tab_group.addButton(button)
            self._tab_buttons[tab] = button
            row.addWidget(button)
        self._tab_buttons[TAB_ACTIVE].setChecked(True)
        row.addStretch()
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

        self.empty_button = QPushButton("View My Requests")
        self.empty_button.setObjectName("catalogPrimaryButton")
        self.empty_button.setCursor(Qt.PointingHandCursor)
        self.empty_button.clicked.connect(self.my_requests_requested.emit)
        layout.addWidget(self.empty_button, alignment=Qt.AlignHCenter)
        return box

    # ---------- refreshing what is shown ----------
    def _in_tab(self, tab: str) -> list:
        status = TAB_STATUS[tab]
        return [r for r in self._current + self._history if r.status is status]

    @staticmethod
    def _clear(layout):
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh(self):
        now = self._clock()
        counts = {tab: len(self._in_tab(tab)) for tab in TAB_LABELS}
        overdue = sum(1 for r in self._current if is_overdue(r, now))

        parts = [f"<b>{counts[TAB_ACTIVE]}</b> borrowed"]
        if overdue:
            parts.append(f'<b style="color:#FF8FA3;">{overdue}</b> overdue')
        parts.append(f"<b>{counts[TAB_RETURN_PENDING]}</b> return pending")
        parts.append(f"<b>{counts[TAB_HISTORY]}</b> returned")
        self.counts_label.setText("  ·  ".join(parts))
        for tab, button in self._tab_buttons.items():
            button.setText(f"{TAB_LABELS[tab]}  {counts[tab]}")

        self._visible = self._in_tab(self._tab)
        self._clear(self.rows_layout)
        for request in self._visible:
            self.rows_layout.addWidget(BorrowingCard(request, now))

        has_rows = bool(self._visible)
        self.rows_container.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)
        self.tab_hint.setVisible(has_rows)
        self.tab_hint.setText(TAB_HINTS[self._tab])
        if not has_rows:
            self._update_empty_state()

    def _update_empty_state(self):
        nothing_at_all = not self._current and not self._history
        if nothing_at_all:
            self.empty_title.setText("No borrowed items yet")
            self.empty_text.setText(
                "An item appears here only after a lender or administrator confirms "
                "that you collected it. Pending and approved requests are in My Requests.")
            self.empty_button.setVisible(True)
            return
        self.empty_button.setVisible(False)
        if self._tab == TAB_ACTIVE:
            self.empty_title.setText("Nothing borrowed right now")
            self.empty_text.setText("Items you have collected and not yet returned will show up here.")
        elif self._tab == TAB_RETURN_PENDING:
            self.empty_title.setText("No returns waiting")
            self.empty_text.setText("Items you reported as returned will wait here until they are verified.")
        else:
            self.empty_title.setText("No history yet")
            self.empty_text.setText("Items whose return was verified will show up here.")

    def _on_guide_toggled(self, expanded: bool):
        self.guide_body.setVisible(expanded)
        self.guide_toggle.setText(("▾" if expanded else "▸") + "  Borrowing Guide")


# ======================================================================
# STYLES (QSS) - only what is NEW here; everything else is reused
# ======================================================================
MY_BORROWINGS_STYLESHEET = f"""
QWidget#myBorrowingsScreen {{
    background-color: {NAVY};
}}

QLabel#myBorrowSectionTitle {{
    color: {CREAM};
    font-size: 18px;
    font-weight: bold;
}}
"""
