"""KitLend Reservations screen (Step 10, redesigned in Step 27).

Shows the items a lender/administrator APPROVED for the student:
  * Awaiting pickup       - Approved - Awaiting Pickup
  * Reservation history   - Reservation Expired, and requests Cancelled AFTER approval

Rules this screen follows (see app/reservation_rules.py):
  * Pending requests are NEVER shown here. They stay in My Requests.
  * Approval is not borrowing. No due date is shown until pickup is confirmed;
    the cards come from the existing request_facts(), which already says so.
  * It shows only what the saved request records contain (item, owner, confirmed
    pickup time, pickup deadline, status). Nothing is invented. In particular the
    item's copies/availability are NOT shown as live numbers: the record only holds
    a snapshot from when the request was made.
  * Cancelling stays in My Requests (one place, one confirmation dialog), so the
    Cancel button of the shared card is hidden here.
  * The screen only DISPLAYS data it is given. It never approves, collects, expires
    or cancels anything, so it is empty for a real student today (nobody can approve
    a request yet). It is NOT the full reservation system: administrator approval,
    pickup confirmation, the FIFO waitlist and pickup-expiration scheduling come later
    and will write the same request records.

Step 27: tabs by real status (Awaiting Pickup, Expired, Cancelled) of compact cards; the
soft-dark styles live in app/my_reservations_theme.py and apply to this screen only.
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

from app.catalog_screen import CATALOG_STYLESHEET, AdaptiveGrid
from app.dashboard_widgets import ElidedLabel
from app.header_style import HEADER_QSS, accent_html
from app.my_list_screen import MY_LIST_STYLESHEET, make_icon_badge
from app.my_reservations_theme import MY_RESERVATIONS_V2_QSS
from app.my_requests_screen import (
    MY_REQUESTS_STYLESHEET,
    BorrowRequest,
    RequestStatus,
    format_dt,
    format_span,
    now_local,
    responsible_text,
)
from app.reservation_rules import is_past_pickup_deadline, split_reservations

RESERVATION_RULE_TEXT = (
    "How reservations work: when a lender or administrator approves your request, the "
    "item is reserved for you. Approval does not mean you are borrowing it. Your "
    "borrowing period and due date start only when they confirm the handover at "
    "pickup. Pending requests are not reservations yet and stay in My Requests, "
    "where you can also cancel a request."
)


TAB_AWAITING = "awaiting"
TAB_EXPIRED = "expired"
TAB_CANCELLED = "cancelled"
TAB_LABELS = {TAB_AWAITING: "Awaiting Pickup", TAB_EXPIRED: "Expired", TAB_CANCELLED: "Cancelled"}
TAB_HINTS = {
    TAB_AWAITING: "Approved and reserved for you. Earliest pickup first. "
                  "Cancelling stays in My Requests.",
    TAB_EXPIRED: "Not collected within the pickup window, so the reservation was released.",
    TAB_CANCELLED: "Requests you cancelled after they were approved. The reservation was released.",
}


def _tab_of(request: BorrowRequest) -> str:
    if request.status is RequestStatus.APPROVED:
        return TAB_AWAITING
    if request.status is RequestStatus.EXPIRED:
        return TAB_EXPIRED
    return TAB_CANCELLED


class ReservationFact(QWidget):
    """A small 'LABEL / value' pair with no box around it."""

    def __init__(self, label: str, value: str, muted: bool = False, late: bool = False,
                 parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label_widget = QLabel(label.upper())
        label_widget.setObjectName("resvFactLabel")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("resvFactValue")
        self.value_label.setProperty("muted", muted)
        self.value_label.setProperty("late", late)
        self.value_label.setWordWrap(True)
        layout.addWidget(label_widget)
        layout.addWidget(self.value_label)


def reservation_facts(request: BorrowRequest, now, late: bool) -> list:
    """(label, value, muted, late) for a card, taken straight from the saved record.

    No due date appears: approval is not borrowing, and the due date starts only when
    the handover is confirmed (see the Borrowing Guide).
    """
    setter = "lender" if request.item.ownership == "student" else "administrator"
    facts = [("Reserved", format_dt(request.approved_at), False, False)]
    status = request.status
    suffix = {RequestStatus.CANCELLED: " · released", RequestStatus.EXPIRED: " · missed"}.get(status, "")
    if request.scheduled_pickup_at is not None:
        facts.append(("Confirmed pickup", format_dt(request.scheduled_pickup_at) + suffix,
                      False, False))
    if status is RequestStatus.APPROVED:
        if request.pickup_deadline is not None:
            facts.append(("Pickup deadline (sample)", format_dt(request.pickup_deadline),
                          False, late))
            if request.pickup_deadline >= now:
                facts.append(("Time to collect",
                              f"Pickup window closes in {format_span(request.pickup_deadline - now)}",
                              False, False))
            else:
                facts.append(("Time to collect",
                              f"Pickup deadline passed. Please contact the {setter}.", False, True))
    else:
        label = status.info.changed_label or "Status changed"
        if request.status_changed_at is not None:
            facts.append((label, format_dt(request.status_changed_at), False, False))
        else:
            facts.append((label, "Not recorded", True, False))
    return facts


class ReservationCard(QFrame):
    """One reservation, compact: item, reservation date, pickup details and status.
    No action buttons (cancelling lives in My Requests only)."""

    def __init__(self, request: BorrowRequest, now, parent=None):
        super().__init__(parent)
        self.request = request
        item = request.item
        self.is_late = is_past_pickup_deadline(request, now)
        self.setObjectName("resvCard")
        self.setProperty("closed", not request.is_active)
        self.setProperty("late", self.is_late)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(make_icon_badge(item), alignment=Qt.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = ElidedLabel(item.title)
        title.setObjectName("resvTitle")
        texts.addWidget(title)
        sub = ElidedLabel(f"{item.category} · {responsible_text(item)} · {request.request_id}")
        sub.setObjectName("resvSub")
        texts.addWidget(sub)
        top.addLayout(texts, 1)

        self.status_pill = QLabel(request.status.info.label)
        self.status_pill.setObjectName("resvStatus")
        self.status_pill.setProperty("status", request.status.value)
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        top.addWidget(self.status_pill, alignment=Qt.AlignTop)
        layout.addLayout(top)

        facts = AdaptiveGrid(min_item_width=150, spacing=16)
        facts.set_widgets([ReservationFact(label, value, muted, red)
                           for label, value, muted, red
                           in reservation_facts(request, now, self.is_late)])
        layout.addWidget(facts)

        if request.status_note:
            note = QLabel(request.status_note)
            note.setObjectName("resvNote")
            note.setWordWrap(True)
            layout.addWidget(note)


class MyReservationsScreen(QWidget):
    """Awaiting Pickup / Expired / Cancelled tabs of compact reservation cards.

    Signals:
      my_requests_requested - button in the empty state (opens My Requests)
    """

    my_requests_requested = Signal()

    def __init__(self, reservations=None, clock=now_local, parent=None, *,
                 stored_locally: bool = False):
        super().__init__(parent)
        self._stored_locally = stored_locally
        self.setObjectName("reservationsScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            CATALOG_STYLESHEET + MY_LIST_STYLESHEET + MY_REQUESTS_STYLESHEET
            + HEADER_QSS + MY_RESERVATIONS_V2_QSS
        )

        self._clock = clock               # lets tests use a fixed "now"
        self._awaiting = []
        self._history = []
        self._tab = TAB_AWAITING
        self._visible = []

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(5000)
        self._banner_timer.timeout.connect(lambda: self.banner.hide())

        self._build_ui()
        self.set_reservations(reservations if reservations is not None else [])

    # ---------- public API ----------
    @property
    def awaiting_requests(self) -> list:
        """Approved - Awaiting Pickup, earliest pickup first."""
        return list(self._awaiting)

    @property
    def history_requests(self) -> list:
        """Expired and cancelled-after-approval, most recent first."""
        return list(self._history)

    @property
    def expired_requests(self) -> list:
        return self._in_tab(TAB_EXPIRED)

    @property
    def cancelled_requests(self) -> list:
        return self._in_tab(TAB_CANCELLED)

    @property
    def visible_requests(self) -> list:
        """The reservations shown in the selected tab."""
        return list(self._visible)

    @property
    def current_tab(self) -> str:
        return self._tab

    @property
    def counts_text(self) -> str:
        return self.counts_label.text()

    def set_reservations(self, requests):
        """Give the screen this student's requests (all of them is fine).

        Anything that is not a reservation is ignored, so a Pending request can
        never appear here by mistake.
        """
        requests = list(requests)
        ids = [request.request_id for request in requests]
        if len(ids) != len(set(ids)):
            raise ValueError("Request IDs must be unique.")
        self._awaiting, self._history = split_reservations(requests)
        self._refresh()

    def set_tab(self, tab: str):
        """TAB_AWAITING, TAB_EXPIRED or TAB_CANCELLED."""
        if tab not in TAB_LABELS:
            raise ValueError(f"Unknown tab: {tab}")
        self._tab = tab
        self._tab_buttons[tab].setChecked(True)
        self._refresh()

    def refresh(self):
        """Redraw with the current time (the 'time to collect' text changes)."""
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
        self.tab_hint.setObjectName("resvTabHint")
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

        title = QLabel(accent_html("Reservations", "Reservations"))
        title.setObjectName("catalogTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Items approved for you and waiting to be collected, plus released "
            "reservations. Pending requests stay in My Requests."
        )
        subtitle.setObjectName("catalogSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.local_notice = QLabel(
            "Stored on this computer only. Not sent to school administrators.")
        self.local_notice.setObjectName("resvNotice")
        self.local_notice.setWordWrap(True)
        self.local_notice.setVisible(self._stored_locally)
        layout.addWidget(self.local_notice)

        self.counts_label = QLabel("")
        self.counts_label.setObjectName("resvCounts")
        self.counts_label.setTextFormat(Qt.RichText)
        layout.addWidget(self.counts_label)
        return header

    def _build_guide(self) -> QWidget:
        """A collapsed 'Reservation Guide' that opens to the reservation rule."""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.guide_toggle = QPushButton("▸  Reservation Guide")
        self.guide_toggle.setObjectName("resvGuideToggle")
        self.guide_toggle.setCheckable(True)
        self.guide_toggle.setCursor(Qt.PointingHandCursor)
        self.guide_toggle.toggled.connect(self._on_guide_toggled)
        layout.addWidget(self.guide_toggle, alignment=Qt.AlignLeft)

        self.guide_body = QFrame()
        self.guide_body.setObjectName("myListInfo")
        body = QVBoxLayout(self.guide_body)
        body.setContentsMargins(16, 12, 16, 12)
        text = QLabel(RESERVATION_RULE_TEXT)
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
        for tab in (TAB_AWAITING, TAB_EXPIRED, TAB_CANCELLED):
            button = QPushButton(TAB_LABELS[tab])
            button.setObjectName("resvTab")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, tab=tab: self.set_tab(tab))
            self._tab_group.addButton(button)
            self._tab_buttons[tab] = button
            row.addWidget(button)
        self._tab_buttons[TAB_AWAITING].setChecked(True)
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
        return [r for r in self._awaiting + self._history if _tab_of(r) == tab]

    @staticmethod
    def _clear(layout):
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh(self):
        now = self._clock()
        counts = {tab: len(self._in_tab(tab)) for tab in TAB_LABELS}
        late = sum(1 for r in self._awaiting if is_past_pickup_deadline(r, now))

        parts = [f"<b>{counts[TAB_AWAITING]}</b> awaiting pickup"]
        if late:
            parts.append(f'<b style="color:#FF8FA3;">{late}</b> past pickup deadline')
        parts.append(f"<b>{counts[TAB_EXPIRED]}</b> expired")
        parts.append(f"<b>{counts[TAB_CANCELLED]}</b> cancelled")
        self.counts_label.setText("  ·  ".join(parts))
        for tab, button in self._tab_buttons.items():
            button.setText(f"{TAB_LABELS[tab]}  {counts[tab]}")

        self._visible = self._in_tab(self._tab)
        self._clear(self.rows_layout)
        for request in self._visible:
            self.rows_layout.addWidget(ReservationCard(request, now))

        has_rows = bool(self._visible)
        self.rows_container.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)
        self.tab_hint.setVisible(has_rows)
        self.tab_hint.setText(TAB_HINTS[self._tab])
        if not has_rows:
            self._update_empty_state()

    def _update_empty_state(self):
        if not self._awaiting and not self._history:
            self.empty_title.setText("No reservations yet")
            self.empty_text.setText(
                "An item is reserved for you only after a lender or administrator approves "
                "your request. Requests that are still Pending are in My Requests.")
            self.empty_button.setVisible(True)
            return
        self.empty_button.setVisible(False)
        if self._tab == TAB_AWAITING:
            self.empty_title.setText("Nothing awaiting pickup")
            self.empty_text.setText("Approved reservations waiting to be collected will show up here.")
        elif self._tab == TAB_EXPIRED:
            self.empty_title.setText("No expired reservations")
            self.empty_text.setText("Reservations that were not collected in time will show up here.")
        else:
            self.empty_title.setText("No cancelled reservations")
            self.empty_text.setText("Reservations you cancelled after approval will show up here.")

    def _on_guide_toggled(self, expanded: bool):
        self.guide_body.setVisible(expanded)
        self.guide_toggle.setText(("▾" if expanded else "▸") + "  Reservation Guide")
