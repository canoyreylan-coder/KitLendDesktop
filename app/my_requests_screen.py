"""KitLend My Requests screen, request models, and sample data.

What this file contains, from top to bottom:
  1. REQUEST DATA     - statuses, the due-date rule, the BorrowRequest dataclass
  2. SAMPLE DATA      - one realistic request for every status
  3. TEXT HELPERS     - date formatting and the "facts" shown on each card
  4. SMALL WIDGETS    - fact block, summary tile, request card
  5. CANCEL DIALOG    - different wording for Pending and Approved - Awaiting Pickup
  6. MY REQUESTS      - the whole screen that puts everything together
  7. STYLES (QSS)     - only the NEW styles; Catalog and My List styles are reused

Borrowing rule (the most important rule in this file):
    Due date/time = ACTUAL CONFIRMED PICKUP date/time + requested duration
One borrowing day = 24 consecutive hours. The student chooses a preferred pickup
time and a duration, but neither approval nor the scheduled pickup time starts the
countdown. Only the physical handover, confirmed by the lender or administrator,
does. A request that was never picked up never gets a due date.

Sample requests are in memory. Real persisted requests are supplied by
RequestService through the Dashboard; this screen itself does not write to SQLite.
The student never confirms a pickup here. Owner/admin approval and handover are
separate future actions (see BorrowRequest.confirm_pickup).
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
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
from app.header_style import HEADER_QSS, accent_html
from app.my_requests_theme import CLEAR_DIALOG_QSS, MY_REQUESTS_V2_QSS
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
    PENDING_OWNER_APPROVAL = "pending_owner_approval"
    APPROVED = "approved"          # student-facing name: "Approved — Awaiting Pickup"
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
        "Waiting for the lender or administrator to review it and confirm that "
        "your preferred pickup works. No borrowing period has started.",
        "", True),
    RequestStatus.PENDING_OWNER_APPROVAL: StatusInfo(
        "Pending Owner Approval",
        "Waiting for the Student Owner to review your request. No borrowing period "
        "has started.",
        "", True),
    RequestStatus.APPROVED: StatusInfo(
        "Approved — Awaiting Pickup",
        "Approved and reserved for you. Collect the item at the confirmed pickup "
        "time, before the pickup deadline. Your borrowing period starts only when "
        "the lender or administrator confirms the handover.",
        "", True),
    RequestStatus.REJECTED: StatusInfo(
        "Rejected",
        "The lender or administrator declined this request. No borrowing "
        "period was started.",
        "Rejected", False),
    RequestStatus.BORROWED: StatusInfo(
        "Borrowed",
        "The lender or administrator confirmed the handover. Your borrowing "
        "period counts from that confirmed pickup time.",
        "", True),
    RequestStatus.RETURN_PENDING: StatusInfo(
        "Return Verification Pending",
        "You reported this item as returned. Waiting for the lender or "
        "administrator to confirm they received it. Your original pickup and "
        "due dates are kept.",
        "Return reported", True),
    RequestStatus.RETURNED: StatusInfo(
        "Returned",
        "The lender or administrator verified the return. All done, thank you!",
        "Return verified", False),
    RequestStatus.CANCELLED: StatusInfo(
        "Cancelled",
        "You cancelled this request before the item was picked up. No borrowing "
        "period was started.",
        "Cancelled", False),
    RequestStatus.EXPIRED: StatusInfo(
        "Reservation Expired",
        "The reservation was not collected within the pickup window, so it was "
        "released. No borrowing period was started.",
        "Expired", False),
}

# Statuses that can only exist AFTER an approval happened
_NEEDS_APPROVAL = {
    RequestStatus.APPROVED, RequestStatus.BORROWED, RequestStatus.RETURN_PENDING,
    RequestStatus.RETURNED, RequestStatus.EXPIRED,
}
# Statuses that mean "never approved"
_NEVER_APPROVED = {
    RequestStatus.PENDING, RequestStatus.PENDING_OWNER_APPROVAL, RequestStatus.REJECTED,
}
# Statuses that can only exist AFTER the item was physically handed over
_NEEDS_PICKUP = {
    RequestStatus.BORROWED, RequestStatus.RETURN_PENDING, RequestStatus.RETURNED,
}

# The rule shown at the top of the screen (kept as a constant so it can be tested)
BORROWING_RULE_TEXT = (
    "How borrowing time works: you choose a preferred pickup time and how many "
    "days you want the item (up to the maximum set by the lender or administrator). "
    "Approval does not start the countdown. Your borrowing period starts only when "
    "the lender or administrator confirms the handover. Due date = confirmed pickup "
    "time + the days you chose (1 day = 24 hours)."
)


def now_local() -> datetime:
    """Current time as a timezone-aware datetime (all timestamps use this kind)."""
    return datetime.now().astimezone()


def compute_due_at(actual_pickup_at: datetime | None, requested_days: int) -> datetime | None:
    """THE due-date rule, on its own so it can be tested without any window.

        Due date/time = actual confirmed pickup date/time + requested days

    One borrowing day = 24 consecutive hours. Returns None when nothing has been
    picked up yet. Approval time, preferred pickup and scheduled pickup are NOT
    inputs: only the confirmed handover starts the borrowing countdown.
    """
    if actual_pickup_at is None:
        return None
    if actual_pickup_at.tzinfo is None:
        raise ValueError("The actual pickup time must be timezone-aware.")
    if requested_days < 1:
        raise ValueError("The borrowing duration must be at least 1 day.")
    # Add the days on the real timeline (UTC) so each day is exactly 24 hours, even
    # across a daylight-saving change, then show the result in the pickup's own timezone.
    due_utc = actual_pickup_at.astimezone(timezone.utc) + timedelta(days=requested_days)
    return due_utc.astimezone(actual_pickup_at.tzinfo)


@dataclass(frozen=True)
class StatusChange:
    """One entry in a request's history: it moved to `status` at time `at`."""

    status: RequestStatus
    at: datetime
    note: str = ""


@dataclass
class BorrowRequest:
    """ONE requested item. Several items requested together are several of these,
    each with its own ID and status, so they never affect each other.

    `max_days` lives here (not on CatalogItem) for this preview.

    The moments are kept apart on purpose (they can all be different):
      preferred_pickup_at  - what the student asked for when submitting
      scheduled_pickup_at  - the pickup time the lender/admin confirmed
      pickup_deadline      - last moment the reserved item can still be collected
      picked_up_at         - the ACTUAL confirmed handover (starts the countdown)
    """

    request_id: str
    item: CatalogItem
    max_days: int
    requested_days: int
    submitted_at: datetime
    status: RequestStatus
    approved_at: datetime | None = None
    pickup_deadline: datetime | None = None   # SAMPLE deadline in this preview
    picked_up_at: datetime | None = None      # actual confirmed handover
    status_changed_at: datetime | None = None  # rejected / cancelled / expired / return events
    status_note: str = ""
    # Added in Step 7B. They come last so older BorrowRequest(...) calls still work.
    preferred_pickup_at: datetime | None = None
    scheduled_pickup_at: datetime | None = None
    status_history: list = field(default_factory=list)  # list of StatusChange
    owner_listing_id: str | None = None
    owner_student_id: int | None = None
    item_photo_path: str | None = None

    def __post_init__(self):
        rid = self.request_id
        label = self.status.info.label
        if not 1 <= self.requested_days <= self.max_days:
            raise ValueError(
                f"{rid}: requested days ({self.requested_days}) must be "
                f"between 1 and the maximum ({self.max_days})."
            )
        for name in ("submitted_at", "preferred_pickup_at", "approved_at",
                     "scheduled_pickup_at", "pickup_deadline", "picked_up_at",
                     "status_changed_at"):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{rid}: {name} must be timezone-aware.")

        # --- which statuses may / must have an approval ---
        if self.status in _NEEDS_APPROVAL and self.approved_at is None:
            raise ValueError(f"{rid}: {label} needs an approval time.")
        if self.status in _NEVER_APPROVED and self.approved_at is not None:
            raise ValueError(f"{rid}: {label} cannot have an approval time.")

        # --- the actual handover is what makes a request "Borrowed" ---
        if self.status in _NEEDS_PICKUP and self.picked_up_at is None:
            raise ValueError(f"{rid}: {label} needs the actual confirmed pickup time.")
        if self.status not in _NEEDS_PICKUP and self.picked_up_at is not None:
            raise ValueError(f"{rid}: {label} cannot have an actual pickup time.")

        # --- the pickup arrangement only exists after approval ---
        if self.status in _NEVER_APPROVED and (
                self.scheduled_pickup_at is not None or self.pickup_deadline is not None):
            raise ValueError(f"{rid}: {label} cannot have a pickup arrangement.")
        if self.status in (RequestStatus.APPROVED, RequestStatus.EXPIRED) \
                and self.pickup_deadline is None:
            raise ValueError(f"{rid}: {label} needs a pickup deadline.")
        if self.status is RequestStatus.APPROVED and self.scheduled_pickup_at is None:
            raise ValueError(f"{rid}: {label} needs the confirmed pickup time.")

        # --- moments must be in a sensible order ---
        self._check_order("submitted_at", "preferred_pickup_at")
        self._check_order("submitted_at", "approved_at")
        self._check_order("submitted_at", "status_changed_at")
        self._check_order("approved_at", "scheduled_pickup_at")
        self._check_order("scheduled_pickup_at", "pickup_deadline")
        self._check_order("approved_at", "picked_up_at")
        self._check_order("picked_up_at", "pickup_deadline")  # collected within the window

        # --- history ---
        if not self.status_history:
            self.status_history = self._build_history()
        else:
            if self.status_history[-1].status is not self.status:
                raise ValueError(f"{rid}: the last history entry must match the status.")
            if any(change.at.tzinfo is None for change in self.status_history):
                raise ValueError(f"{rid}: history times must be timezone-aware.")

    def _check_order(self, earlier_name: str, later_name: str):
        earlier = getattr(self, earlier_name)
        later = getattr(self, later_name)
        if earlier is not None and later is not None and later < earlier:
            raise ValueError(f"{self.request_id}: {later_name} cannot be before {earlier_name}.")

    def _build_history(self) -> list:
        """Rebuild the history from the timestamps we already have."""
        initial_status = (RequestStatus.PENDING_OWNER_APPROVAL
                          if self.owner_listing_id else RequestStatus.PENDING)
        history = [StatusChange(initial_status, self.submitted_at, "Request submitted")]
        if self.approved_at is not None:
            history.append(StatusChange(RequestStatus.APPROVED, self.approved_at, "Request approved"))
        if self.picked_up_at is not None:
            history.append(StatusChange(RequestStatus.BORROWED, self.picked_up_at, "Handover confirmed"))
        if self.status in (RequestStatus.REJECTED, RequestStatus.CANCELLED, RequestStatus.EXPIRED,
                           RequestStatus.RETURN_PENDING, RequestStatus.RETURNED) \
                and self.status_changed_at is not None:
            history.append(StatusChange(self.status, self.status_changed_at, self.status_note))
        return sorted(history, key=lambda change: change.at)

    @property
    def due_at(self) -> datetime | None:
        """Actual confirmed pickup + requested days (1 day = 24 hours).

        None until the handover is confirmed. It is calculated, never stored, so
        it can never drift away from the pickup time, and it is kept after the
        item is returned as a historical record.
        """
        return compute_due_at(self.picked_up_at, self.requested_days)

    @property
    def countdown_started(self) -> bool:
        """True only after the physical handover was confirmed."""
        return self.picked_up_at is not None

    @property
    def is_active(self) -> bool:
        return self.status.info.is_active

    @property
    def can_cancel(self) -> bool:
        """Only Pending or Approved — Awaiting Pickup requests that were not collected."""
        return (self.status in (RequestStatus.PENDING,
                                RequestStatus.PENDING_OWNER_APPROVAL,
                                RequestStatus.APPROVED)
                and self.picked_up_at is None)

    def cancel(self, when: datetime):
        """Cancel THIS request only. Approval, pickup arrangement and deadline stay
        on record (history is preserved). There is never an actual pickup or a
        due date, because the item was never handed over."""
        if not self.can_cancel:
            raise ValueError(f"{self.request_id} cannot be cancelled ({self.status.info.label}).")
        if when.tzinfo is None:
            raise ValueError(f"{self.request_id}: the cancellation time must be timezone-aware.")
        if not self.status_note:
            self.status_note = (
                "Cancelled by you before pickup. The reservation was released."
                if self.status is RequestStatus.APPROVED
                else "Cancelled by you before it was approved."
            )
        self.status = RequestStatus.CANCELLED
        self.status_changed_at = when
        self.status_history.append(StatusChange(RequestStatus.CANCELLED, when, self.status_note))

    def confirm_pickup(self, when: datetime):
        """FUTURE lender/administrator action. NOTHING on this screen calls it.

        Records the actual handover and starts the borrowing period. A pickup that
        is later than scheduled is fine as long as the reservation is still open;
        the due date then counts from `when`, not from the scheduled time. An
        expired reservation cannot be picked up without a new valid arrangement.
        """
        if self.status is RequestStatus.EXPIRED:
            raise ValueError(f"{self.request_id}: the reservation expired; a new valid pickup "
                             "arrangement is needed.")
        if self.status is not RequestStatus.APPROVED:
            raise ValueError(f"{self.request_id}: only an approved reservation can be picked up "
                             f"({self.status.info.label}).")
        if when.tzinfo is None:
            raise ValueError(f"{self.request_id}: the pickup time must be timezone-aware.")
        if when < self.approved_at:
            raise ValueError(f"{self.request_id}: pickup cannot be before the approval.")
        if self.pickup_deadline is not None and when > self.pickup_deadline:
            raise ValueError(f"{self.request_id}: the pickup deadline has passed; a new valid "
                             "pickup arrangement is needed.")
        self.picked_up_at = when
        self.status = RequestStatus.BORROWED
        self.status_history.append(StatusChange(RequestStatus.BORROWED, when, "Handover confirmed"))


# ======================================================================
# 2. SAMPLE DATA (timestamps are relative to "now", so they stay consistent)
# ======================================================================
def sample_pickup_deadline(scheduled_pickup_at: datetime, item: CatalogItem) -> datetime:
    """SAMPLE ONLY. No school calendar, holidays or school-day logic exists yet.

    School items: 5:00 PM on the scheduled pickup day (stand-in for "end of the
    school day"). Student items: 24 hours after the scheduled pickup, standing in
    for whatever the lender decides.
    """
    if item.ownership == "school":
        deadline = scheduled_pickup_at.replace(hour=17, minute=0, second=0, microsecond=0)
        if deadline <= scheduled_pickup_at:
            deadline += timedelta(days=1)
        return deadline
    return scheduled_pickup_at + timedelta(days=1)


def build_sample_requests(now: datetime | None = None) -> list:
    """One request per status, with realistic, internally consistent timestamps.

    Every past event is on an earlier day than `now`, so nothing is ever dated in
    the future by accident. Pickup times are tidy clock times (e.g. 3:00 PM).
    """
    now = now or now_local()
    by_title = {item.title: item for item in SAMPLE_ITEMS}

    def day(offset: int, hour: int, minute: int = 0) -> datetime:
        """The day `offset` days from today, at hour:minute."""
        return (now + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)

    def arrangement(title: str, approved: datetime, scheduled: datetime) -> dict:
        """Approval + confirmed pickup time + pickup deadline, kept consistent."""
        return dict(
            approved_at=approved,
            scheduled_pickup_at=scheduled,
            pickup_deadline=sample_pickup_deadline(scheduled, by_title[title]),
        )

    def make(number, title, max_days, days, status, submitted, **times):
        return BorrowRequest(f"REQ-{number}", by_title[title], max_days, days, submitted, status, **times)

    # 1. Pending: preferred pickup shown, no approval, no due date.
    pending = make(1001, "Introduction to Algorithms (CLRS)", 5, 4, RequestStatus.PENDING,
                   day(-1, 16, 20), preferred_pickup_at=day(2, 15, 0))

    # 2. Approved — Awaiting Pickup: reserved, NOT picked up, no due date yet.
    title = "Arduino Uno Starter Kit"
    approved = make(1002, title, 5, 4, RequestStatus.APPROVED, day(-2, 10, 15),
                    preferred_pickup_at=day(1, 15, 0),
                    **arrangement(title, day(-1, 9, 40), day(1, 15, 0)))

    # 3. Borrowed: collected 10 minutes after the scheduled time. The due date
    #    counts from the ACTUAL handover (2:10 PM), not from approval or 2:00 PM.
    title = "Digital Multimeter"
    borrowed = make(1003, title, 5, 5, RequestStatus.BORROWED, day(-6, 10, 30),
                    preferred_pickup_at=day(-4, 14, 0),
                    picked_up_at=day(-4, 14, 10),
                    **arrangement(title, day(-5, 9, 15), day(-4, 14, 0)))

    # 4. Return Verification Pending: original pickup and due dates are kept.
    title = "Grokking Algorithms"
    return_pending = make(1004, title, 7, 5, RequestStatus.RETURN_PENDING, day(-9, 13, 0),
                          preferred_pickup_at=day(-7, 15, 0),
                          picked_up_at=day(-7, 15, 0),
                          status_changed_at=day(-2, 11, 30),
                          **arrangement(title, day(-8, 10, 0), day(-7, 15, 0)))

    # 5. Returned: pickup, due date and return verification are all on record.
    title = "Discrete Mathematics and Its Applications"
    returned = make(1005, title, 7, 7, RequestStatus.RETURNED, day(-22, 9, 0),
                    preferred_pickup_at=day(-20, 14, 0),
                    picked_up_at=day(-20, 14, 5),
                    status_changed_at=day(-14, 10, 30),
                    **arrangement(title, day(-21, 10, 0), day(-20, 14, 0)))

    rejected = make(1006, "Raspberry Pi 4 Model B Kit", 3, 3, RequestStatus.REJECTED,
                    day(-2, 14, 0), preferred_pickup_at=day(-1, 10, 0),
                    status_changed_at=day(-2, 17, 30),
                    status_note="Declined by the administrator: kits are reserved for a class lab this week.")

    # 6. Cancelled reservation: it WAS approved, then cancelled before pickup.
    #    The approval stays on record; there is no actual pickup and no due date.
    title = "Clean Code"
    cancelled = make(1007, title, 7, 3, RequestStatus.CANCELLED, day(-5, 9, 30),
                     preferred_pickup_at=day(-3, 14, 0),
                     status_changed_at=day(-3, 8, 45),
                     status_note="Cancelled by you before pickup. The reservation was released.",
                     **arrangement(title, day(-4, 11, 0), day(-3, 14, 0)))

    # 7. Expired reservation: approved, never collected, released at the deadline.
    title = "Soldering Iron Kit (60W)"
    expired_times = arrangement(title, day(-6, 9, 30), day(-5, 15, 0))
    expired = make(1008, title, 3, 2, RequestStatus.EXPIRED, day(-7, 10, 0),
                   preferred_pickup_at=day(-5, 15, 0),
                   status_changed_at=expired_times["pickup_deadline"],
                   status_note="Not collected within the pickup window.",
                   **expired_times)

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


def request_item_badge(request: BorrowRequest):
    """Show a saved listing photo when present; otherwise retain the normal item badge."""
    path = request.item_photo_path
    if path:
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            photo = QLabel()
            photo.setObjectName("myReqPhoto")
            photo.setFixedSize(52, 52)
            photo.setAlignment(Qt.AlignCenter)
            photo.setStyleSheet(
                "QLabel#myReqPhoto { background-color: #252A45; border-radius: 10px; }")
            photo.setPixmap(pixmap.scaled(
                48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            photo.setAccessibleName(f"Photo of {request.item.title}")
            return photo
    return make_icon_badge(request.item)


def request_facts(request: BorrowRequest, now: datetime) -> list:
    """The details shown on a card, as (label, value, is_muted) tuples.

    Kept as a plain function so the pickup and due-date rules are easy to read
    and test. The key idea: there is NO due date until the handover is confirmed.
    """
    status = request.status
    setter = "lender" if request.item.ownership == "student" else "administrator"
    facts = [
        ("Submitted", format_dt(request.submitted_at), False),
        ("Borrowing duration",
         f"{days_text(request.requested_days)} requested · max {days_text(request.max_days)} "
         f"(set by the {setter})", False),
    ]

    # --- what the student asked for ---
    if request.preferred_pickup_at is not None:
        value = format_dt(request.preferred_pickup_at)
        if status in (RequestStatus.PENDING, RequestStatus.PENDING_OWNER_APPROVAL):
            value += " · subject to approval"
        facts.append(("Preferred pickup", value, False))
    else:
        facts.append(("Preferred pickup", "Not provided", True))

    # --- approval ---
    if request.approved_at is not None:
        facts.append(("Approved", format_dt(request.approved_at), False))
    elif status in (RequestStatus.PENDING, RequestStatus.PENDING_OWNER_APPROVAL):
        facts.append(("Approved", "Not approved yet", True))
    else:
        facts.append(("Approved", "Never approved", True))

    # --- the arrangement the lender/administrator confirmed (kept as history too) ---
    suffix = ""
    if status is RequestStatus.CANCELLED:
        suffix = " · released"
    elif status is RequestStatus.EXPIRED:
        suffix = " · missed"
    if request.scheduled_pickup_at is not None:
        facts.append(("Confirmed pickup", format_dt(request.scheduled_pickup_at) + suffix, False))
    if request.pickup_deadline is not None and status in (
            RequestStatus.APPROVED, RequestStatus.CANCELLED, RequestStatus.EXPIRED):
        facts.append(("Pickup deadline (sample)", format_dt(request.pickup_deadline) + suffix, False))

    # --- the ACTUAL handover ---
    if request.picked_up_at is not None:
        facts.append(("Picked up (confirmed)", format_dt(request.picked_up_at), False))
    elif status in (RequestStatus.PENDING, RequestStatus.PENDING_OWNER_APPROVAL,
                    RequestStatus.APPROVED):
        facts.append(("Picked up", "Not picked up yet", True))
    else:
        facts.append(("Picked up", "Not picked up", True))

    # --- borrowing period and due date (due date = actual pickup + duration, or nothing) ---
    due = request.due_at
    if status is RequestStatus.APPROVED:
        facts.append(("Borrowing period", "Borrowing period not started", False))
    if due is not None:
        facts.append(("Due date", format_dt(due), False))
    elif status in (RequestStatus.PENDING, RequestStatus.PENDING_OWNER_APPROVAL,
                    RequestStatus.APPROVED):
        facts.append(("Due date", "Not set. It starts when pickup is confirmed.", True))
    elif status is RequestStatus.REJECTED:
        facts.append(("Due date", "None. This request was rejected.", True))
    else:  # cancelled or expired reservation
        facts.append(("Due date", "None. The item was never picked up.", True))

    # --- time left: borrowing time only while borrowed, pickup time while reserved ---
    if due is not None and status is RequestStatus.BORROWED:
        if due >= now:
            facts.append(("Time remaining", f"{format_span(due - now)} left", False))
        else:
            facts.append(("Time remaining", f"Past the due date by {format_span(now - due)}", False))
    elif status is RequestStatus.APPROVED and request.pickup_deadline is not None:
        if request.pickup_deadline >= now:
            facts.append(("Time to collect",
                          f"Pickup window closes in {format_span(request.pickup_deadline - now)}", False))
        else:
            facts.append(("Time to collect",
                          f"Pickup deadline passed. Please contact the {setter}.", False))

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
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)

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
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(2)

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
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # --- top row: icon, title/category, status pill ---
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(request_item_badge(request), alignment=Qt.AlignTop)

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


class MiniFact(QWidget):
    """A compact 'LABEL / value' pair for the My Requests cards (no box around it)."""

    def __init__(self, label: str, value: str, muted: bool = False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label_widget = QLabel(label.upper())
        label_widget.setObjectName("myReqMiniLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("myReqMiniValue")
        value_widget.setProperty("muted", muted)
        value_widget.setWordWrap(True)
        layout.addWidget(label_widget)
        layout.addWidget(value_widget)


class CompactRequestCard(QFrame):
    """One request on the My Requests page: tidy, roomy and easy to scan.

    Same facts, status pill and Cancel Request button as RequestCard, but laid out
    compactly with no boxes inside the card. RequestCard itself is left untouched because
    My Borrowings and My Reservations still use it.
    """

    cancel_clicked = Signal(object)  # sends the BorrowRequest

    def __init__(self, request: BorrowRequest, now: datetime, parent=None):
        super().__init__(parent)
        self.request = request
        item = request.item
        self.setObjectName("myReqCard")
        self.setProperty("closed", not request.is_active)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)

        # --- top row: icon, title / category, status pill ---
        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(request_item_badge(request), alignment=Qt.AlignTop)
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

        # --- owner row: ownership tag, who is responsible, request ID ---
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

        # --- what the status means (one quiet paragraph) ---
        description = QLabel(request.status.info.description)
        description.setObjectName("myReqDescription")
        description.setWordWrap(True)
        layout.addWidget(description)
        if request.status_note:
            note = QLabel(request.status_note)
            note.setObjectName("myReqNote")
            note.setWordWrap(True)
            layout.addWidget(note)

        # --- details under a hairline, re-flowing into 1-4 columns ---
        rule = QFrame()
        rule.setObjectName("myReqRule")
        rule.setFixedHeight(1)
        layout.addWidget(rule)
        facts = AdaptiveGrid(min_item_width=190, spacing=14)
        facts.set_widgets([MiniFact(label, value, muted)
                           for label, value, muted in request_facts(request, now)])
        layout.addWidget(facts)

        # --- actions: only requests with something to say or do get a row ---
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
                self.cancel_button.setObjectName("myListRemoveButton")
                self.cancel_button.setCursor(Qt.PointingHandCursor)
                self.cancel_button.clicked.connect(lambda: self.cancel_clicked.emit(self.request))
                actions.addWidget(self.cancel_button)
            layout.addLayout(actions)


class ClearEntriesDialog(QDialog):
    """Asks before hiding finished requests. exec() is Accepted only if confirmed."""

    def __init__(self, title: str, count: int, parent=None, *, stored_locally: bool = False):
        super().__init__(parent)
        self.setObjectName("myReqClearDialog")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(CLEAR_DIALOG_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        heading = QLabel(f"{title}?")
        heading.setObjectName("clearTitle")
        layout.addWidget(heading)
        what = "request" if count == 1 else "requests"
        text = QLabel(
            f"This hides {count} {what} from this page. Nothing is deleted: "
            "the records stay in your account history."
            + (" They remain saved on this computer." if stored_locally else "")
        )
        text.setObjectName("clearText")
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addSpacing(6)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        keep = QPushButton("Keep Them")
        keep.setObjectName("clearKeep")
        keep.setCursor(Qt.PointingHandCursor)
        keep.setDefault(True)   # Enter keeps everything (the safe choice)
        keep.clicked.connect(self.reject)
        buttons.addWidget(keep)
        self.confirm_button = QPushButton(title)
        self.confirm_button.setObjectName("clearConfirm")
        self.confirm_button.setAutoDefault(False)
        self.confirm_button.setCursor(Qt.PointingHandCursor)
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)


# ======================================================================
# 5. CANCEL DIALOG
# ======================================================================
class CancelRequestDialog(QDialog):
    """Asks before cancelling. Pending and Approved / Reserved get different wording.

    exec() returns Accepted only if the student confirmed.
    """

    def __init__(self, request: BorrowRequest, parent=None, *, stored_locally: bool = False):
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

        tag = QLabel(
            "Saved on this computer only · Not sent to school administrators"
            if stored_locally else "Preview only · Nothing is saved"
        )
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
            approved_text = format_dt(request.approved_at) if request.approved_at else "earlier"
            pickup_text = (f" Your pickup is arranged for {format_dt(request.scheduled_pickup_at)}."
                           if request.scheduled_pickup_at else "")
            text = (
                f"This item is already reserved for you (approved {approved_text}).{pickup_text} "
                "Cancelling releases the existing reservation so another borrower can "
                "request it. No borrowing period has started. This cannot be undone. "
                "Your other requests are not affected."
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

# The three main tabs. Which statuses live where:
TAB_ACTIVE = "active"
TAB_HISTORY = "history"
TAB_CANCELLED = "cancelled"
TAB_LABELS = {TAB_ACTIVE: "Active", TAB_HISTORY: "History", TAB_CANCELLED: "Cancelled"}
TAB_STATUSES = {
    TAB_ACTIVE: (RequestStatus.PENDING, RequestStatus.PENDING_OWNER_APPROVAL,
                 RequestStatus.APPROVED,
                 RequestStatus.BORROWED, RequestStatus.RETURN_PENDING),
    TAB_HISTORY: (RequestStatus.RETURNED, RequestStatus.REJECTED, RequestStatus.EXPIRED),
    TAB_CANCELLED: (RequestStatus.CANCELLED,),
}
CLEAR_TITLES = {TAB_HISTORY: "Clear History", TAB_CANCELLED: "Clear Cancelled"}


def tab_for_status(status: RequestStatus) -> str:
    for tab, statuses in TAB_STATUSES.items():
        if status in statuses:
            return tab
    return TAB_ACTIVE


class MyRequestsScreen(QWidget):
    """Every request the student made: Active / History / Cancelled tabs, safe cancelling.

    Signals (nothing else needs to be connected):
      request_cancelled(request)  - one request was cancelled (after the handler,
                                    if there is one, saved the change)
      requests_cleared(requests)  - finished requests were hidden with Clear History /
                                    Clear Cancelled (after the handler saved it)
      browse_catalog_requested    - button in the empty state

    Options (both default to the old preview behaviour):
      stored_locally  - show that requests live on this computer only and are
                        not sent to school administrators.
      cancel_handler  - function (request, when) that SAVES the cancellation. If
                        it raises, nothing changes and the problem is shown.
      hide_handler    - function (request_ids, when) that SAVES "these were cleared".
                        If it raises, nothing changes and the problem is shown. Clearing
                        only hides entries here; it never deletes a request.
    """

    request_cancelled = Signal(object)
    requests_cleared = Signal(object)
    browse_catalog_requested = Signal()

    def __init__(self, requests=None, clock=now_local, parent=None, *,
                 stored_locally: bool = False, cancel_handler=None, hide_handler=None):
        super().__init__(parent)
        self._stored_locally = stored_locally
        self.cancel_handler = cancel_handler
        self.hide_handler = hide_handler
        self.setObjectName("myRequestsScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(CATALOG_STYLESHEET + MY_LIST_STYLESHEET + MY_REQUESTS_STYLESHEET + HEADER_QSS
                           + MY_REQUESTS_V2_QSS)  # Step 23: soft-dark look, this screen only

        self._clock = clock               # lets tests use a fixed "now"
        self._requests = []
        self._tab = TAB_ACTIVE
        self._filter = FILTER_ALL         # inside Active: FILTER_ALL or a RequestStatus
        self._visible = []
        self._dialog_open = False         # stops a second dialog from opening
        self._empty_action = "browse"     # "browse", "show_all" or "" (no button)

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
        """FILTER_ALL, or the status picked in the Active dropdown."""
        return self._filter

    @property
    def current_tab(self) -> str:
        return self._tab

    @property
    def counts_text(self) -> str:
        return self.counts_label.text()

    def set_requests(self, requests):
        """Replace all requests. Request IDs must be unique."""
        requests = list(requests)
        ids = [request.request_id for request in requests]
        if len(ids) != len(set(ids)):
            raise ValueError("Request IDs must be unique.")
        self._requests = requests
        self._refresh()

    def set_tab(self, tab: str):
        """TAB_ACTIVE, TAB_HISTORY or TAB_CANCELLED."""
        if tab not in TAB_LABELS:
            raise ValueError(f"Unknown tab: {tab}")
        self._tab = tab
        if tab != TAB_ACTIVE:
            self._filter = FILTER_ALL
        self._tab_buttons[tab].setChecked(True)
        self._refresh()

    def set_filter(self, status_filter):
        """FILTER_ALL (all active requests) or a RequestStatus (opens the tab it lives in)."""
        if status_filter is FILTER_ALL or status_filter == FILTER_ALL:
            self._tab, self._filter = TAB_ACTIVE, FILTER_ALL
        else:
            self._tab = tab_for_status(status_filter)
            self._filter = status_filter if self._tab == TAB_ACTIVE else FILTER_ALL
        self._tab_buttons[self._tab].setChecked(True)
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
        layout.setSpacing(14)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_guide())

        self.banner = QLabel("")
        self.banner.setObjectName("myListBanner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        layout.addWidget(self.banner)

        layout.addLayout(self._build_tabs())
        layout.addLayout(self._build_toolbar())

        self.rows_container = QWidget()
        self.rows_container.setObjectName("catalogContent")
        self._rows_layout = QVBoxLayout(self.rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(14)
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

        title = QLabel(accent_html("My Requests", "Requests"))
        title.setObjectName("catalogTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Follow every borrowing request. Each item has its own ID and is "
            "approved on its own."
        )
        subtitle.setObjectName("catalogSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ONE subtle notice instead of a big box (only when requests are really stored here)
        self.local_notice = QLabel(
            "Stored on this computer only. Not sent to school administrators or lenders "
            "yet, so nobody will review these requests for now."
        )
        self.local_notice.setObjectName("myReqNotice")
        self.local_notice.setWordWrap(True)
        self.local_notice.setVisible(self._stored_locally)
        layout.addWidget(self.local_notice)

        # compact counts instead of four big tiles
        self.counts_label = QLabel("")
        self.counts_label.setObjectName("myReqCounts")
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
        self.guide_toggle.setObjectName("myReqGuideToggle")
        self.guide_toggle.setCheckable(True)
        self.guide_toggle.setCursor(Qt.PointingHandCursor)
        self.guide_toggle.toggled.connect(self._on_guide_toggled)
        layout.addWidget(self.guide_toggle, alignment=Qt.AlignLeft)

        self.guide_body = QFrame()
        self.guide_body.setObjectName("myListInfo")
        body_layout = QVBoxLayout(self.guide_body)
        body_layout.setContentsMargins(16, 12, 16, 12)
        text = QLabel(BORROWING_RULE_TEXT)
        text.setObjectName("myListInfoText")
        text.setWordWrap(True)
        body_layout.addWidget(text)
        self.guide_body.hide()
        layout.addWidget(self.guide_body)
        return holder

    def _build_tabs(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_buttons = {}
        for tab in (TAB_ACTIVE, TAB_HISTORY, TAB_CANCELLED):
            button = QPushButton(TAB_LABELS[tab])
            button.setObjectName("myReqTab")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, tab=tab: self._on_tab_clicked(tab))
            self._tab_group.addButton(button)
            self._tab_buttons[tab] = button
            row.addWidget(button)
        self._tab_buttons[TAB_ACTIVE].setChecked(True)
        row.addStretch()
        return row

    def _build_toolbar(self) -> QHBoxLayout:
        """Result count on the left; the Active dropdown or a Clear button on the right."""
        row = QHBoxLayout()
        row.setSpacing(10)
        self.result_label = QLabel("")
        self.result_label.setObjectName("catalogResultLabel")
        row.addWidget(self.result_label, 1)

        # Detailed status filtering lives here, inside the Active tab only.
        self.status_filter = QComboBox()
        self.status_filter.setObjectName("myReqFilter")
        self.status_filter.setCursor(Qt.PointingHandCursor)
        self.status_filter.setMinimumWidth(230)
        self.status_filter.addItem("All active", FILTER_ALL)  # item data: plain text keys
        for status in TAB_STATUSES[TAB_ACTIVE]:
            self.status_filter.addItem(status.info.label, status.value)
        self.status_filter.currentIndexChanged.connect(self._on_status_filter_changed)
        row.addWidget(self.status_filter)

        self.clear_history_button = self._make_clear_button(TAB_HISTORY)
        self.clear_cancelled_button = self._make_clear_button(TAB_CANCELLED)
        row.addWidget(self.clear_history_button)
        row.addWidget(self.clear_cancelled_button)
        return row

    def _make_clear_button(self, tab: str) -> QPushButton:
        button = QPushButton(CLEAR_TITLES[tab])
        button.setObjectName("myReqClearButton")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, tab=tab: self._on_clear_clicked(tab))
        return button

    def _build_empty_state(self) -> QFrame:
        box = QFrame()
        box.setObjectName("catalogEmpty")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 40, 30, 40)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignHCenter)

        icon = QLabel("📭")  # Kit appears on the Dashboard only
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

        self.empty_button = QPushButton("")
        self.empty_button.setObjectName("catalogPrimaryButton")
        self.empty_button.setCursor(Qt.PointingHandCursor)
        self.empty_button.clicked.connect(self._on_empty_button_clicked)
        layout.addWidget(self.empty_button, alignment=Qt.AlignHCenter)
        return box

    # ---------- refreshing what is shown ----------
    def _requests_in_tab(self, tab: str) -> list:
        statuses = TAB_STATUSES[tab]
        return [r for r in self._requests if r.status in statuses]

    def _refresh(self):
        now = self._clock()
        requests = self._requests
        counts = {tab: len(self._requests_in_tab(tab)) for tab in TAB_LABELS}

        # compact counts line + tab labels
        pending = sum(1 for r in requests if r.status in (
            RequestStatus.PENDING, RequestStatus.PENDING_OWNER_APPROVAL))
        holding = sum(1 for r in requests
                      if r.status in (RequestStatus.APPROVED, RequestStatus.BORROWED))
        closed = counts[TAB_HISTORY] + counts[TAB_CANCELLED]
        self.counts_label.setText(
            f"<b>{counts[TAB_ACTIVE]}</b> active  ·  <b>{pending}</b> awaiting approval  ·  "
            f"<b>{holding}</b> reserved or borrowed  ·  <b>{closed}</b> closed")
        for tab, button in self._tab_buttons.items():
            button.setText(f"{TAB_LABELS[tab]}  {counts[tab]}")

        # Active dropdown: counts in the labels, selection kept
        self.status_filter.blockSignals(True)
        for index in range(self.status_filter.count()):
            key = self._combo_key(index)
            count = (counts[TAB_ACTIVE] if key == FILTER_ALL
                     else sum(1 for r in requests if r.status is key))
            label = "All active" if key == FILTER_ALL else key.info.label
            self.status_filter.setItemText(index, f"{label} ({count})")
        selected = next((i for i in range(self.status_filter.count())
                         if self._combo_key(i) == self._filter), 0)
        self.status_filter.setCurrentIndex(selected)
        self.status_filter.blockSignals(False)

        # which requests are shown (newest first)
        shown = self._requests_in_tab(self._tab)
        if self._tab == TAB_ACTIVE and self._filter != FILTER_ALL:
            shown = [r for r in shown if r.status is self._filter]
        self._visible = sorted(shown, key=lambda r: r.submitted_at, reverse=True)

        # the right-hand controls belong to one tab each
        self.status_filter.setVisible(self._tab == TAB_ACTIVE)
        self.clear_history_button.setVisible(self._tab == TAB_HISTORY and bool(self._visible))
        self.clear_cancelled_button.setVisible(self._tab == TAB_CANCELLED and bool(self._visible))

        while self._rows_layout.count():
            widget = self._rows_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for request in self._visible:
            card = CompactRequestCard(request, now)
            card.cancel_clicked.connect(self._on_cancel_clicked)
            self._rows_layout.addWidget(card)

        has_rows = bool(self._visible)
        self.rows_container.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)
        if has_rows:
            word = "request" if len(self._visible) == 1 else "requests"
            self.result_label.setText(f"Showing {len(self._visible)} {word}")
        else:
            self.result_label.setText("No requests to show")
            self._update_empty_state()

    def _update_empty_state(self):
        if not self._requests:
            self._empty_action = "browse"
            self.empty_title.setText("No requests yet")
            self.empty_text.setText(
                "When you request an item from Browse Catalog or My List, it will "
                "show up here so you can follow its progress."
            )
            self.empty_button.setText("Browse Catalog")
        elif self._tab == TAB_ACTIVE and self._filter != FILTER_ALL:
            self._empty_action = "show_all"
            self.empty_title.setText(f"No “{self._filter.info.label}” requests")
            self.empty_text.setText("Nothing matches this status right now. Try another filter.")
            self.empty_button.setText("Show all active")
        elif self._tab == TAB_ACTIVE:
            self._empty_action = "browse"
            self.empty_title.setText("No active requests")
            self.empty_text.setText("Requests that are still in progress will show up here.")
            self.empty_button.setText("Browse Catalog")
        elif self._tab == TAB_HISTORY:
            self._empty_action = ""
            self.empty_title.setText("No history")
            self.empty_text.setText("Returned, rejected and expired requests will show up here.")
        else:
            self._empty_action = ""
            self.empty_title.setText("No cancelled requests")
            self.empty_text.setText("Requests you cancel will show up here.")
        self.empty_button.setVisible(bool(self._empty_action))

    # ---------- reacting to clicks ----------
    def _on_guide_toggled(self, expanded: bool):
        self.guide_body.setVisible(expanded)
        self.guide_toggle.setText(("▾" if expanded else "▸") + "  Borrowing Guide")

    def _on_tab_clicked(self, tab: str):
        self._tab = tab
        if tab != TAB_ACTIVE:
            self._filter = FILTER_ALL
        self._refresh()

    def _combo_key(self, index: int):
        """FILTER_ALL or the RequestStatus stored at this dropdown position."""
        value = self.status_filter.itemData(index)
        return FILTER_ALL if value == FILTER_ALL else RequestStatus(value)

    def _on_status_filter_changed(self, index: int):
        self._filter = self._combo_key(index)
        self._refresh()

    def _on_empty_button_clicked(self):
        if self._empty_action == "browse":
            self.browse_catalog_requested.emit()
        elif self._empty_action == "show_all":
            self.set_filter(FILTER_ALL)

    def _confirm_clear(self, tab: str, count: int) -> bool:
        """Ask first. (A separate method so tests can answer for the student.)"""
        self._dialog_open = True
        try:
            return ClearEntriesDialog(
                CLEAR_TITLES[tab], count, self, stored_locally=self._stored_locally
            ).exec() == QDialog.DialogCode.Accepted
        finally:
            self._dialog_open = False

    def _on_clear_clicked(self, tab: str):
        """Clear History / Clear Cancelled: hide the finished requests of THAT tab only."""
        if self._dialog_open or tab != self._tab:
            return
        entries = self._requests_in_tab(tab)
        if not entries or not self._confirm_clear(tab, len(entries)):
            return
        when = self._clock()
        if self.hide_handler is not None:
            # Save FIRST. If saving fails, nothing changes and no success is shown.
            try:
                self.hide_handler([r.request_id for r in entries], when)
            except Exception as exc:
                self.show_message(
                    str(exc) if getattr(exc, "is_user_facing", False)
                    else "Something went wrong, so nothing was cleared."
                )
                self._refresh()
                return
        hidden_ids = {r.request_id for r in entries}
        self._requests = [r for r in self._requests if r.request_id not in hidden_ids]
        self._refresh()
        self.requests_cleared.emit(entries)
        count = len(entries)
        message = (f"Done! {count} {'request was' if count == 1 else 'requests were'} cleared "
                   f"from {TAB_LABELS[tab]}. They are only hidden here; your records are kept.")
        self.show_message(message + ("" if self.hide_handler else " Preview only."))

    def _on_cancel_clicked(self, request: BorrowRequest):
        if self._dialog_open:
            return
        if not request.can_cancel:  # the request changed since the card was drawn
            self.show_message(f"{request.request_id} can no longer be cancelled.")
            self._refresh()
            return

        self._dialog_open = True
        try:
            confirmed = CancelRequestDialog(
                request, self, stored_locally=self._stored_locally
            ).exec() == QDialog.DialogCode.Accepted
        finally:
            self._dialog_open = False
        if not confirmed or not request.can_cancel:
            return

        was_reserved = request.status is RequestStatus.APPROVED
        when = self._clock()
        if self.cancel_handler is not None:
            # Save FIRST. If saving fails, nothing changes and no success is shown.
            try:
                self.cancel_handler(request, when)
            except Exception as exc:
                self.show_message(
                    str(exc) if getattr(exc, "is_user_facing", False)
                    else "Something went wrong, so the request was not cancelled."
                )
                self._refresh()
                return
        request.cancel(when)  # only THIS request changes
        self._refresh()
        self.request_cancelled.emit(request)
        message = f"Done! {request.request_id} ({request.item.title}) was cancelled."
        if was_reserved:
            message += " The reservation was released for other borrowers."
        ending = "Saved on this computer only." if self._stored_locally else "Preview only."
        self.show_message(message + f" Your other requests were not changed. {ending}")


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
QLabel#myReqStatus[status="pending_owner_approval"] {{
    background-color: #FFE3B3; color: {NAVY};
}}
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
