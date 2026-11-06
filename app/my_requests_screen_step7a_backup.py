"""KitLend My Requests screen (UI only - sample data, no database, nothing is sent).

What this file contains, from top to bottom:
  1. REQUEST DATA     - statuses, the BorrowRequest dataclass and its duration rules
  2. SAMPLE DATA      - one realistic request for every status
  3. TEXT HELPERS     - date formatting and the "facts" shown on each card
  4. SMALL WIDGETS    - fact block, summary tile, request card
  5. CANCEL DIALOG    - different wording for Pending and Approved / Reserved
  6. MY REQUESTS      - the whole screen that puts everything together
  7. STYLES (QSS)     - only the NEW styles; Catalog and My List styles are reused

Borrowing-duration rule (the most important rule in this file):
    Due date/time = approval date/time + requested duration
One borrowing day = 24 consecutive hours. The countdown starts at the real
APPROVAL time, never at the submission time or the pickup time. A request that
was never approved never gets a due date.

Everything is simulated in memory. No requests are created, no inventory
changes, no emails, no database, no login, and no dashboard connection.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Reuse what the Catalog and My List already provide.
from app.catalog_screen import (
    CATALOG_STYLESHEET,
    CATEGORY_BY_NAME,
    CURIOUS_MASCOT_PATH,
    HAPPY_MASCOT_PATH,
    MUTED_TEXT,
    SAMPLE_ITEMS,
    SOFT_LAVENDER,
    AdaptiveGrid,
    CatalogItem,
    TagPill,
)
from app.dashboard_widgets import ElidedLabel
from app.my_list_screen import MY_LIST_STYLESHEET, lender_name, make_icon_badge
from app.theme import CREAM, MINT, NAVY, PERIWINKLE, PINK


# ======================================================================
# 1. REQUEST DATA
# ======================================================================
class RequestStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    BORROWED = "borrowed"
    RETURN_PENDING = "return_pending"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    @property
    def info(self) -> "StatusInfo":
        return STATUS_INFO[self]


@dataclass(frozen=True)
class StatusInfo:
    label: str            # the ONE label used everywhere in the UI
    description: str      # plain-language explanation shown on the card
    changed_label: str    # name of the "status_changed_at" moment ("" = not shown)
    is_active: bool       # still in progress? (False = closed)


STATUS_INFO = {
    RequestStatus.PENDING: StatusInfo(
        "Pending",
        "Waiting for the lender or administrator to review it. Your borrowing "
        "period starts once the request is approved.",
        "", True),
    RequestStatus.APPROVED: StatusInfo(
        "Approved / Reserved",
        "Approved and reserved for you. Your borrowing period has already "
        "started, so collect the item before the pickup deadline.",
        "", True),
    RequestStatus.REJECTED: StatusInfo(
        "Rejected",
        "The lender or administrator declined this request. No borrowing "
        "period was started.",
        "Rejected", False),
    RequestStatus.BORROWED: StatusInfo(
        "Borrowed",
        "You have collected this item. The borrowing period still counts from "
        "the approval time, not from pickup.",
        "", True),
    RequestStatus.RETURN_PENDING: StatusInfo(
        "Return Verification Pending",
        "You reported this item as returned. Waiting for the lender or "
        "administrator to confirm they received it.",
        "Return reported", True),
    RequestStatus.RETURNED: StatusInfo(
        "Returned",
        "The lender or administrator verified the return. All done, thank you!",
        "Return verified", False),
    RequestStatus.CANCELLED: StatusInfo(
        "Cancelled",
        "You cancelled this request.",
        "Cancelled", False),
    RequestStatus.EXPIRED: StatusInfo(
        "Reservation Expired",
        "The reservation was not collected before its pickup deadline, so it "
        "was released.",
        "Expired", False),
}

# Statuses that can only exist AFTER an approval happened
_NEEDS_APPROVAL = {
    RequestStatus.APPROVED, RequestStatus.BORROWED, RequestStatus.RETURN_PENDING,
    RequestStatus.RETURNED, RequestStatus.EXPIRED,
}
# Statuses that mean "never approved"
_NEVER_APPROVED = {RequestStatus.PENDING, RequestStatus.REJECTED}


def now_local() -> datetime:
    """Current time as a timezone-aware datetime (all timestamps use this kind)."""
    return datetime.now().astimezone()


@dataclass
class BorrowRequest:
    """ONE requested item. Several items requested together are several of these,
    each with its own ID and status, so they never affect each other.

    `max_days` lives here (not on CatalogItem) for this preview.
    """

    request_id: str
    item: CatalogItem
    max_days: int
    requested_days: int
    submitted_at: datetime
    status: RequestStatus
    approved_at: datetime | None = None
    pickup_deadline: datetime | None = None   # SAMPLE deadline in this preview
    picked_up_at: datetime | None = None
    status_changed_at: datetime | None = None  # rejected / cancelled / expired / return events
    status_note: str = ""

    def __post_init__(self):
        if not 1 <= self.requested_days <= self.max_days:
            raise ValueError(
                f"{self.request_id}: requested days ({self.requested_days}) must be "
                f"between 1 and the maximum ({self.max_days})."
            )
        for name in ("submitted_at", "approved_at", "pickup_deadline",
                     "picked_up_at", "status_changed_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{self.request_id}: {name} must be timezone-aware.")
        if self.status in _NEEDS_APPROVAL and self.approved_at is None:
            raise ValueError(f"{self.request_id}: {self.status.info.label} needs an approval time.")
        if self.status in _NEVER_APPROVED and self.approved_at is not None:
            raise ValueError(f"{self.request_id}: {self.status.info.label} cannot have an approval time.")

    @property
    def due_at(self) -> datetime | None:
        """Approval time + requested days (1 day = 24 hours). None if never approved.

        It is calculated, never stored, so it can never drift away from the
        approval time. It is kept after cancellation/expiry as a historical record.
        """
        if self.approved_at is None:
            return None
        return self.approved_at + timedelta(days=self.requested_days)

    @property
    def is_active(self) -> bool:
        return self.status.info.is_active

    @property
    def can_cancel(self) -> bool:
        """Only Pending or Approved / Reserved requests that were not collected."""
        return (self.status in (RequestStatus.PENDING, RequestStatus.APPROVED)
                and self.picked_up_at is None)

    def cancel(self, when: datetime):
        """Cancel THIS request only. Approval, pickup deadline and due date stay
        on record (history is preserved)."""
        if not self.can_cancel:
            raise ValueError(f"{self.request_id} cannot be cancelled ({self.status.info.label}).")
        self.status = RequestStatus.CANCELLED
        self.status_changed_at = when


# ======================================================================
# 2. SAMPLE DATA (timestamps are relative to "now", so they stay consistent)
# ======================================================================
def sample_pickup_deadline(approved_at: datetime, item: CatalogItem) -> datetime:
    """SAMPLE ONLY. No school calendar, holidays or school-day logic exists yet.

    School items: 5:00 PM on the calendar day after approval (stand-in for
    "end of the next school day"). Student items: 2 days, standing in for
    whatever the lender decides.
    """
    if item.ownership == "school":
        return (approved_at + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
    return approved_at + timedelta(days=2)


def build_sample_requests(now: datetime | None = None) -> list:
    """One request per status, with internally consistent timestamps."""
    now = now or now_local()
    by_title = {item.title: item for item in SAMPLE_ITEMS}

    def hours_ago(hours: float) -> datetime:
        return now - timedelta(hours=hours)

    def make(number, title, max_days, days, status, submitted, **times):
        item = by_title[title]
        approved = times.get("approved_at")
        if approved is not None and "pickup_deadline" not in times:
            times["pickup_deadline"] = sample_pickup_deadline(approved, item)
        return BorrowRequest(f"REQ-{number}", item, max_days, days, submitted, status, **times)

    pending = make(1001, "Introduction to Algorithms (CLRS)", 5, 4, RequestStatus.PENDING,
                   hours_ago(3))

    approved_at = hours_ago(6)
    approved = make(1002, "Arduino Uno Starter Kit", 7, 3, RequestStatus.APPROVED,
                    hours_ago(30), approved_at=approved_at)

    borrowed_approved = hours_ago(92)
    borrowed = make(1003, "Digital Multimeter", 5, 5, RequestStatus.BORROWED,
                    hours_ago(96), approved_at=borrowed_approved,
                    picked_up_at=hours_ago(74))

    return_approved = hours_ago(124)
    return_pending = make(1004, "Grokking Algorithms", 7, 5, RequestStatus.RETURN_PENDING,
                          hours_ago(129), approved_at=return_approved,
                          picked_up_at=hours_ago(121), status_changed_at=hours_ago(9))

    returned_approved = hours_ago(14 * 24 + 20)
    returned = make(1005, "Discrete Mathematics and Its Applications", 7, 7, RequestStatus.RETURNED,
                    hours_ago(15 * 24), approved_at=returned_approved,
                    picked_up_at=hours_ago(14 * 24 + 18), status_changed_at=hours_ago(8 * 24))

    rejected = make(1006, "Raspberry Pi 4 Model B Kit", 3, 3, RequestStatus.REJECTED,
                    hours_ago(48), status_changed_at=hours_ago(44),
                    status_note="Declined by the administrator: kits are reserved for a class lab this week.")

    cancelled = make(1007, "Clean Code", 7, 3, RequestStatus.CANCELLED,
                     hours_ago(5 * 24), status_changed_at=hours_ago(5 * 24 - 2),
                     status_note="Cancelled by you before it was approved.")

    expired_approved = hours_ago(5 * 24 + 20)
    expired_item = by_title["Soldering Iron Kit (60W)"]
    expired_deadline = sample_pickup_deadline(expired_approved, expired_item)
    expired = make(1008, "Soldering Iron Kit (60W)", 3, 2, RequestStatus.EXPIRED,
                   hours_ago(6 * 24), approved_at=expired_approved,
                   pickup_deadline=expired_deadline, status_changed_at=expired_deadline,
                   status_note="Not collected before the pickup deadline.")

    return [pending, approved, borrowed, return_pending, returned, rejected, cancelled, expired]


# ======================================================================
# 3. TEXT HELPERS (plain Python - easy to read and to test)
# ======================================================================
def format_dt(moment: datetime) -> str:
    """'Oct 22, 2026, 2:00 PM' in the computer's local time."""
    local = moment.astimezone()
    hour = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    return f"{local:%b} {local.day}, {local.year}, {hour}:{local:%M} {suffix}"


def format_span(span: timedelta) -> str:
    """'2 days 4 h', '5 h 20 min', 'less than 1 min'."""
    minutes = max(0, int(span.total_seconds() // 60))
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} h")
    if mins and not days:
        parts.append(f"{mins} min")
    return " ".join(parts) or "less than 1 min"


def days_text(days: int) -> str:
    return f"{days} day{'s' if days != 1 else ''}"


def responsible_text(item: CatalogItem) -> str:
    if item.ownership == "student":
        return f"Lender · {lender_name(item)}"
    return f"Administrator · {item.owner_note}"


def request_facts(request: BorrowRequest, now: datetime) -> list:
    """The details shown on a card, as (label, value, is_muted) tuples.

    Kept as a plain function so the duration rules are easy to read and test.
    """
    status = request.status
    setter = "lender" if request.item.ownership == "student" else "administrator"
    facts = [
        ("Submitted", format_dt(request.submitted_at), False),
        ("Borrowing duration",
         f"{days_text(request.requested_days)} requested · max {days_text(request.max_days)} "
         f"(set by the {setter})", False),
    ]

    # --- approval ---
    if request.approved_at is not None:
        facts.append(("Approved", format_dt(request.approved_at), False))
    elif status is RequestStatus.PENDING:
        facts.append(("Approved", "Not approved yet", True))
    else:
        facts.append(("Approved", "Never approved", True))

    # --- pickup ---
    if status in (RequestStatus.BORROWED, RequestStatus.RETURN_PENDING, RequestStatus.RETURNED) \
            and request.picked_up_at is not None:
        facts.append(("Picked up", format_dt(request.picked_up_at), False))
    elif request.approved_at is not None and request.pickup_deadline is not None:
        value = format_dt(request.pickup_deadline)
        if status is RequestStatus.EXPIRED:
            value += " · missed"
        elif status is RequestStatus.CANCELLED:
            value += " · released"
        facts.append(("Pickup deadline (sample)", value, False))

    # --- due date (always approval + duration, or nothing) ---
    due = request.due_at
    if due is not None:
        if status in (RequestStatus.CANCELLED, RequestStatus.EXPIRED):
            facts.append(("Due date (recorded)", f"{format_dt(due)} · no longer applies", False))
        else:
            facts.append(("Due date", format_dt(due), False))
    elif status is RequestStatus.PENDING:
        facts.append(("Due date", "Due date pending approval.", True))
    else:
        facts.append(("Due date", "None, this request was never approved.", True))

    # --- remaining time (only while a countdown is really running) ---
    if due is not None and status in (RequestStatus.APPROVED, RequestStatus.BORROWED):
        if due >= now:
            facts.append(("Time remaining", f"{format_span(due - now)} left", False))
        else:
            facts.append(("Time remaining", f"Past the due date by {format_span(now - due)}", False))

    # --- status change moment ---
    changed_label = status.info.changed_label
    if changed_label and request.status_changed_at is not None:
        facts.append((changed_label, format_dt(request.status_changed_at), False))
    return facts


# ======================================================================
# 4. SMALL WIDGETS
# ======================================================================
class FactBlock(QFrame):
    """A small 'LABEL / value' box inside a request card."""

    def __init__(self, label: str, value: str, muted: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("myReqFact")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        label_widget = QLabel(label.upper())
        label_widget.setObjectName("myReqFactLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("myReqFactValue")
        value_widget.setProperty("muted", muted)
        value_widget.setWordWrap(True)
        layout.addWidget(label_widget)
        layout.addWidget(value_widget)


class SummaryTile(QFrame):
    """Big number with a label, used for the summary counts."""

    def __init__(self, label: str, hint: str, parent=None):
        super().__init__(parent)
        self.setObjectName("myReqStat")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(0)

        label_widget = QLabel(label)
        label_widget.setObjectName("myReqStatLabel")
        self.value_label = QLabel("0")
        self.value_label.setObjectName("myReqStatValue")
        hint_widget = QLabel(hint)
        hint_widget.setObjectName("myReqStatHint")
        hint_widget.setWordWrap(True)
        layout.addWidget(label_widget)
        layout.addWidget(self.value_label)
        layout.addWidget(hint_widget)

    def set_value(self, value: int):
        self.value_label.setText(str(value))


class RequestCard(QFrame):
    """One request: item, owner, status, details and (if allowed) Cancel Request."""

    cancel_clicked = Signal(object)  # sends the BorrowRequest

    def __init__(self, request: BorrowRequest, now: datetime, parent=None):
        super().__init__(parent)
        self.request = request
        item = request.item
        self.setObjectName("myReqCard")
        self.setProperty("closed", not request.is_active)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # --- top row: icon, title/category, status pill ---
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(make_icon_badge(item), alignment=Qt.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(3)
        title = ElidedLabel(item.title)
        title.setObjectName("catalogItemTitle")
        texts.addWidget(title)
        category = CATEGORY_BY_NAME.get(item.category)
        icon = f"{category.icon} " if category else ""
        category_line = ElidedLabel(f"{icon}{item.category} · {item.kind}")
        category_line.setObjectName("catalogItemCreator")
        texts.addWidget(category_line)
        top.addLayout(texts, 1)

        self.status_pill = QLabel(request.status.info.label)
        self.status_pill.setObjectName("myReqStatus")
        self.status_pill.setProperty("status", request.status.value)
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        top.addWidget(self.status_pill, alignment=Qt.AlignTop)
        layout.addLayout(top)

        # --- owner row: ownership label, who is responsible, request ID ---
        owner_row = QHBoxLayout()
        owner_row.setSpacing(8)
        owner_row.addWidget(TagPill(item.ownership_label, item.ownership))
        responsible = ElidedLabel(responsible_text(item))
        responsible.setObjectName("catalogItemNote")
        owner_row.addWidget(responsible, 1)
        request_id = QLabel(request.request_id)
        request_id.setObjectName("myReqId")
        owner_row.addWidget(request_id)
        layout.addLayout(owner_row)

        # --- what the status means ---
        description = QLabel(request.status.info.description)
        description.setObjectName("myReqDescription")
        description.setWordWrap(True)
        layout.addWidget(description)
        if request.status_note:
            note = QLabel(request.status_note)
            note.setObjectName("myReqNote")
            note.setWordWrap(True)
            layout.addWidget(note)

        # --- details (re-flow into 1-3 columns) ---
        facts = AdaptiveGrid(min_item_width=210, spacing=8)
        facts.set_widgets([FactBlock(label, value, muted)
                           for label, value, muted in request_facts(request, now)])
        layout.addWidget(facts)

        # --- actions ---
        # Only requests with something to say or do get an action row.
        needs_return_note = request.status in (RequestStatus.BORROWED, RequestStatus.RETURN_PENDING)
        if needs_return_note or request.can_cancel:
            actions = QHBoxLayout()
            actions.setSpacing(10)
            if needs_return_note:
                hint = QLabel("Cancellation unavailable. Please follow the return process.")
                hint.setObjectName("myReqActionNote")
                hint.setWordWrap(True)
                actions.addWidget(hint, 1)
            else:
                actions.addStretch()
            if request.can_cancel:
                self.cancel_button = QPushButton("Cancel Request")
                self.cancel_button.setObjectName("myListRemoveButton")  # same soft-red style as Remove
                self.cancel_button.setCursor(Qt.PointingHandCursor)
                self.cancel_button.clicked.connect(lambda: self.cancel_clicked.emit(self.request))
                actions.addWidget(self.cancel_button)
            layout.addLayout(actions)


# ======================================================================
# 5. CANCEL DIALOG
# ======================================================================
class CancelRequestDialog(QDialog):
    """Asks before cancelling. Pending and Approved / Reserved get different wording.

    exec() returns Accepted only if the student confirmed.
    """

    def __init__(self, request: BorrowRequest, parent=None):
        super().__init__(parent)
        self.setObjectName("myReqDialog")
        self.setWindowTitle("Cancel request")
        self.setModal(True)
        self.resize(540, 440)
        self.setMinimumSize(440, 380)
        self.setStyleSheet(CATALOG_STYLESHEET + MY_LIST_STYLESHEET + MY_REQUESTS_STYLESHEET)

        reserved = request.status is RequestStatus.APPROVED
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        tag = QLabel("Preview only · Nothing is saved")
        tag.setObjectName("catalogTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout.addWidget(tag, alignment=Qt.AlignLeft)

        title = QLabel("Cancel this reservation?" if reserved else "Cancel this request?")
        title.setObjectName("myListDialogTitle")
        layout.addWidget(title)

        summary = QLabel(
            f"<b>{request.item.title}</b><br>"
            f"{request.request_id} · {request.status.info.label}"
        )
        summary.setObjectName("myReqDialogSummary")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        box = QFrame()
        box.setObjectName("myReqWarning" if reserved else "myListInfo")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(14, 10, 14, 10)
        if reserved:
            text = (
                f"This item is already reserved for you (approved "
                f"{format_dt(request.approved_at)}). Cancelling releases the "
                "reservation so another borrower can request it. This cannot be "
                "undone. Your other requests are not affected."
            )
        else:
            text = (
                "This request has not been approved yet, so cancelling simply "
                "withdraws it. No borrowing period has started. Your other "
                "requests are not affected."
            )
        message = QLabel(text)
        message.setObjectName("myReqWarningText" if reserved else "myListInfoText")
        message.setWordWrap(True)
        box_layout.addWidget(message)
        layout.addWidget(box)

        self.acknowledge = None
        if reserved:
            # Explicit confirmation: the red button stays off until this is ticked.
            self.acknowledge = QPushButton("☐  I understand this releases the reservation")
            self.acknowledge.setObjectName("myReqAck")
            self.acknowledge.setCheckable(True)
            self.acknowledge.setCursor(Qt.PointingHandCursor)
            self.acknowledge.toggled.connect(self._on_acknowledged)
            layout.addWidget(self.acknowledge)

        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        keep = QPushButton("Keep Reservation" if reserved else "Keep Request")
        keep.setObjectName("myListBackButton")
        keep.setCursor(Qt.PointingHandCursor)
        keep.setDefault(True)   # pressing Enter keeps the request (the safe choice)
        keep.clicked.connect(self.reject)
        buttons.addWidget(keep)

        self.confirm_button = QPushButton("Yes, Cancel Request")
        self.confirm_button.setObjectName("myReqDangerButton")
        self.confirm_button.setAutoDefault(False)
        self.confirm_button.setCursor(Qt.PointingHandCursor)
        self.confirm_button.setEnabled(not reserved)
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

    def _on_acknowledged(self, checked: bool):
        self.acknowledge.setText(
            ("☑" if checked else "☐") + "  I understand this releases the reservation"
        )
        self.confirm_button.setEnabled(checked)


# ======================================================================
# 6. MY REQUESTS SCREEN
# ======================================================================
FILTER_ALL = "all"


class MyRequestsScreen(QWidget):
    """Every request the student made, with status filters and safe cancelling.

    Signals (nothing is connected to them yet):
      request_cancelled(request)  - one request was cancelled (in memory only)
      browse_catalog_requested    - button in the empty state
    """

    request_cancelled = Signal(object)
    browse_catalog_requested = Signal()

    def __init__(self, requests=None, clock=now_local, parent=None):
        super().__init__(parent)
        self.setObjectName("myRequestsScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(CATALOG_STYLESHEET + MY_LIST_STYLESHEET + MY_REQUESTS_STYLESHEET)

        self._clock = clock               # lets tests use a fixed "now"
        self._requests = []
        self._filter = FILTER_ALL         # FILTER_ALL or a RequestStatus
        self._visible = []
        self._dialog_open = False         # stops a second dialog from opening
        self._empty_action_is_browse = True

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(5000)
        self._banner_timer.timeout.connect(lambda: self.banner.hide())

        self._build_ui()
        self.set_requests(requests if requests is not None else [])

    # ---------- public API ----------
    @property
    def requests(self) -> list:
        return list(self._requests)

    @property
    def visible_requests(self) -> list:
        """The requests currently shown (handy for testing)."""
        return list(self._visible)

    @property
    def current_filter(self):
        return self._filter

    def set_requests(self, requests):
        """Replace all requests. Request IDs must be unique."""
        requests = list(requests)
        ids = [request.request_id for request in requests]
        if len(ids) != len(set(ids)):
            raise ValueError("Request IDs must be unique.")
        self._requests = requests
        self._refresh()

    def set_filter(self, status_filter):
        """FILTER_ALL or a RequestStatus."""
        self._filter = status_filter
        self._filter_buttons[status_filter].setChecked(True)
        self._refresh()

    def show_message(self, text: str):
        self.banner.setText(text)
        self.banner.show()
        self._banner_timer.start()

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
        layout.addWidget(self._build_duration_info())

        self.banner = QLabel("")
        self.banner.setObjectName("myListBanner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        layout.addWidget(self.banner)

        layout.addWidget(self._build_summary())
        layout.addWidget(self._build_filters())

        self.result_label = QLabel("")
        self.result_label.setObjectName("catalogResultLabel")
        layout.addWidget(self.result_label)

        self.rows_container = QWidget()
        self.rows_container.setObjectName("catalogContent")
        self._rows_layout = QVBoxLayout(self.rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(12)
        layout.addWidget(self.rows_container)

        self.empty_state = self._build_empty_state()
        layout.addWidget(self.empty_state)
        layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("catalogHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(26, 18, 26, 18)
        layout.setSpacing(12)

        texts = QVBoxLayout()
        texts.setSpacing(8)
        tag = QLabel("Preview · Sample data only")
        tag.setObjectName("catalogTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        texts.addWidget(tag, alignment=Qt.AlignLeft)

        title = QLabel("My Requests")
        title.setObjectName("catalogTitle")
        texts.addWidget(title)

        subtitle = QLabel(
            "Follow every borrowing request. Each item has its own ID and is "
            "approved on its own."
        )
        subtitle.setObjectName("catalogSubtitle")
        subtitle.setWordWrap(True)
        texts.addWidget(subtitle)
        texts.addStretch()
        layout.addLayout(texts, 1)

        pixmap = QPixmap(str(HAPPY_MASCOT_PATH))
        if not pixmap.isNull():
            mascot = QLabel()
            mascot.setPixmap(pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(mascot, 0, Qt.AlignTop | Qt.AlignRight)
        return header

    def _build_duration_info(self) -> QFrame:
        box = QFrame()
        box.setObjectName("myListInfo")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 10)
        text = QLabel(
            "How borrowing time works: your borrowing period begins when a request "
            "is approved, not when you submit it or pick the item up. Due date = "
            "approval time + the days you chose (1 day = 24 hours)."
        )
        text.setObjectName("myListInfoText")
        text.setWordWrap(True)
        layout.addWidget(text)
        return box

    def _build_summary(self) -> QWidget:
        self._tiles = {
            "active": SummaryTile("Active requests", "Still in progress"),
            "pending": SummaryTile("Awaiting approval", "Pending requests"),
            "holding": SummaryTile("Reserved or borrowed", "Approved or collected"),
            "closed": SummaryTile("Completed", "Returned, rejected, cancelled or expired"),
        }
        grid = AdaptiveGrid(min_item_width=170, spacing=12)
        grid.set_widgets(list(self._tiles.values()))
        return grid

    def _build_filters(self) -> QWidget:
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_buttons = {}
        options = [(FILTER_ALL, "All")] + [(status, status.info.label) for status in RequestStatus]
        self._filter_labels = dict(options)
        for key, _label in options:
            button = QPushButton("")
            button.setObjectName("myReqChip")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, key=key: self._on_filter_clicked(key))
            self._filter_group.addButton(button)
            self._filter_buttons[key] = button
        self._filter_buttons[FILTER_ALL].setChecked(True)

        grid = AdaptiveGrid(min_item_width=200, spacing=8)
        grid.set_widgets(list(self._filter_buttons.values()))
        return grid

    def _build_empty_state(self) -> QFrame:
        box = QFrame()
        box.setObjectName("catalogEmpty")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignHCenter)

        pixmap = QPixmap(str(CURIOUS_MASCOT_PATH))
        icon = QLabel()
        icon.setObjectName("catalogEmptyIcon")
        icon.setAlignment(Qt.AlignCenter)
        if not pixmap.isNull():
            icon.setPixmap(pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon.setText("📭")  # a missing image file must never crash the app
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

        self.empty_button = QPushButton("")
        self.empty_button.setObjectName("catalogPrimaryButton")
        self.empty_button.setCursor(Qt.PointingHandCursor)
        self.empty_button.clicked.connect(self._on_empty_button_clicked)
        layout.addWidget(self.empty_button, alignment=Qt.AlignHCenter)
        return box

    # ---------- refreshing what is shown ----------
    def _refresh(self):
        now = self._clock()
        requests = self._requests

        # summary counts
        self._tiles["active"].set_value(sum(1 for r in requests if r.is_active))
        self._tiles["pending"].set_value(sum(1 for r in requests if r.status is RequestStatus.PENDING))
        self._tiles["holding"].set_value(sum(
            1 for r in requests if r.status in (RequestStatus.APPROVED, RequestStatus.BORROWED)))
        self._tiles["closed"].set_value(sum(1 for r in requests if not r.is_active))

        # filter chip labels with counts
        for key, button in self._filter_buttons.items():
            count = len(requests) if key == FILTER_ALL else sum(1 for r in requests if r.status is key)
            button.setText(f"{self._filter_labels[key]} ({count})")

        # which requests are shown (newest first)
        shown = [r for r in requests if self._filter == FILTER_ALL or r.status is self._filter]
        self._visible = sorted(shown, key=lambda r: r.submitted_at, reverse=True)

        while self._rows_layout.count():
            widget = self._rows_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for request in self._visible:
            card = RequestCard(request, now)
            card.cancel_clicked.connect(self._on_cancel_clicked)
            self._rows_layout.addWidget(card)

        has_rows = bool(self._visible)
        self.rows_container.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)
        if has_rows:
            self.result_label.setText(f"Showing {len(self._visible)} of {len(requests)} requests")
        else:
            self.result_label.setText("No requests to show")
            self._update_empty_state()

    def _update_empty_state(self):
        if not self._requests:
            self._empty_action_is_browse = True
            self.empty_title.setText("No requests yet")
            self.empty_text.setText(
                "When you request an item from Browse Catalog or My List, it will "
                "show up here so you can follow its progress."
            )
            self.empty_button.setText("Browse Catalog")
        else:
            self._empty_action_is_browse = False
            label = self._filter_labels[self._filter]
            self.empty_title.setText(f"No “{label}” requests")
            self.empty_text.setText("Nothing matches this status right now. Try another filter.")
            self.empty_button.setText("Show all requests")

    # ---------- reacting to clicks ----------
    def _on_filter_clicked(self, key):
        self._filter = key
        self._refresh()

    def _on_empty_button_clicked(self):
        if self._empty_action_is_browse:
            self.browse_catalog_requested.emit()
        else:
            self.set_filter(FILTER_ALL)

    def _on_cancel_clicked(self, request: BorrowRequest):
        if self._dialog_open:
            return
        if not request.can_cancel:  # the request changed since the card was drawn
            self.show_message(f"{request.request_id} can no longer be cancelled.")
            self._refresh()
            return

        self._dialog_open = True
        try:
            confirmed = CancelRequestDialog(request, self).exec() == QDialog.DialogCode.Accepted
        finally:
            self._dialog_open = False
        if not confirmed or not request.can_cancel:
            return

        was_reserved = request.status is RequestStatus.APPROVED
        request.cancel(self._clock())  # only THIS request changes
        self._refresh()
        self.request_cancelled.emit(request)
        message = f"Done! {request.request_id} ({request.item.title}) was cancelled."
        if was_reserved:
            message += " The reservation was released for other borrowers."
        self.show_message(message + " Your other requests were not changed. Preview only.")


# ======================================================================
# 7. STYLES (QSS) - only what is NEW here
# ======================================================================
MY_REQUESTS_STYLESHEET = f"""
QWidget#myRequestsScreen {{
    background-color: {NAVY};
}}

QDialog#myReqDialog {{
    background-color: {NAVY};
}}

/* ---------- Summary tiles ---------- */
QFrame#myReqStat {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 18px;
}}

QLabel#myReqStatLabel {{
    color: {NAVY};
    font-size: 13px;
    font-weight: bold;
}}

QLabel#myReqStatValue {{
    color: {NAVY};
    font-size: 30px;
    font-weight: bold;
}}

QLabel#myReqStatHint {{
    color: {MUTED_TEXT};
    font-size: 11px;
}}

/* ---------- Status filter chips ---------- */
QPushButton#myReqChip {{
    background-color: {SOFT_LAVENDER};
    color: {NAVY};
    border: 2px solid #DDDFFA;
    border-radius: 14px;
    padding: 8px 10px;
    font-size: 12px;
    font-weight: bold;
}}

QPushButton#myReqChip:hover {{
    background-color: #E3E4FA;
}}

QPushButton#myReqChip:checked {{
    background-color: {PERIWINKLE};
    color: white;
    border-color: {NAVY};
}}

/* ---------- Request cards ---------- */
QFrame#myReqCard {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 22px;
}}

QFrame#myReqCard[closed="true"] {{
    background-color: #F1F0FA;
    border: 3px dashed #B5B7D6;
}}

QLabel#myReqId {{
    color: {MUTED_TEXT};
    font-size: 11px;
    font-weight: bold;
}}

QLabel#myReqDescription {{
    color: {NAVY};
    font-size: 12px;
}}

QLabel#myReqNote {{
    color: {MUTED_TEXT};
    font-size: 12px;
    font-style: italic;
}}

QLabel#myReqActionNote {{
    color: {MUTED_TEXT};
    font-size: 12px;
}}

QFrame#myReqFact {{
    background-color: {SOFT_LAVENDER};
    border: 2px solid #DDDFFA;
    border-radius: 12px;
}}

QLabel#myReqFactLabel {{
    color: {PERIWINKLE};
    font-size: 10px;
    font-weight: bold;
}}

QLabel#myReqFactValue {{
    color: {NAVY};
    font-size: 13px;
    font-weight: bold;
}}

QLabel#myReqFactValue[muted="true"] {{
    color: {MUTED_TEXT};
    font-weight: normal;
    font-style: italic;
}}

/* ---------- Status pills (one look per status) ---------- */
QLabel#myReqStatus {{
    border: 2px solid {NAVY};
    border-radius: 12px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: bold;
}}

QLabel#myReqStatus[status="pending"] {{ background-color: #FFE3B3; color: {NAVY}; }}
QLabel#myReqStatus[status="approved"] {{ background-color: {MINT}; color: {NAVY}; }}
QLabel#myReqStatus[status="borrowed"] {{ background-color: {PERIWINKLE}; color: white; }}
QLabel#myReqStatus[status="return_pending"] {{ background-color: {PINK}; color: {NAVY}; }}
QLabel#myReqStatus[status="returned"] {{ background-color: #8FE3C8; color: {NAVY}; }}
QLabel#myReqStatus[status="rejected"] {{
    background-color: #FFD9E6;
    color: #C2386B;
    border-color: #C2386B;
}}
QLabel#myReqStatus[status="cancelled"] {{
    background-color: #E3E4FA;
    color: {MUTED_TEXT};
    border: 2px dashed #8D90BD;
}}
QLabel#myReqStatus[status="expired"] {{
    background-color: #FFE9D6;
    color: #A55A1E;
    border: 2px dashed #A55A1E;
}}

/* ---------- Cancel dialog ---------- */
QLabel#myReqDialogSummary {{
    color: {CREAM};
    font-size: 14px;
}}

QFrame#myReqWarning {{
    background-color: rgba(244, 168, 196, 40);
    border: 2px solid {PINK};
    border-radius: 16px;
}}

QLabel#myReqWarningText {{
    color: {PINK};
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#myReqAck {{
    background: transparent;
    color: {CREAM};
    border: 2px solid {PINK};
    border-radius: 12px;
    padding: 8px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#myReqAck:hover {{
    background-color: rgba(244, 168, 196, 40);
}}

QPushButton#myReqAck:checked {{
    background-color: {PINK};
    color: {NAVY};
}}

QPushButton#myReqDangerButton {{
    background-color: {PINK};
    color: {NAVY};
    border: 3px solid {NAVY};
    border-radius: 16px;
    padding: 10px 22px;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#myReqDangerButton:hover {{
    background-color: #F7BDD3;
}}

QPushButton#myReqDangerButton:disabled {{
    background-color: #5A5C8F;
    color: #B5B7D6;
    border: 3px dashed #8D90BD;
}}
"""
