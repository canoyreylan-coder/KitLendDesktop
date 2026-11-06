"""What the redesigned Dashboard home page shows, as plain data (Stage 2A). No GUI code.

Two sources, never mixed:
  * view_from_requests(requests) - a signed-in student's REAL saved requests. Borrowings
    and reservations are picked with the same rules the My Borrowings / Reservations pages
    use (app/borrowing_rules.py and app/reservation_rules.py), so the Dashboard can never
    disagree with them. Nothing is invented: no records means empty lists.
  * view_from_demo(data) - the clearly-labelled sample data of the demo dashboard.

The page (app/dashboard_home.py) only draws a HomeView; it does no filtering itself.
"""
from dataclasses import dataclass
from datetime import datetime

from app.borrowing_rules import is_overdue, split_borrowings
from app.my_requests_screen import RequestStatus, now_local
from app.reservation_rules import split_reservations
from app.sample_data import (
    DemoData,
    describe_days_ago,
    describe_days_left,
    due_tone,
    format_short_date,
    format_weekday_date,
    plural,
)

DUE_SOON_DAYS = 3

# sample_data.due_tone() speaks the old palette; the Dashboard uses these tone names.
_DUE_TONES = {"alert": "rose", "pink": "amber", "purple": "lavender", "mint": "mint"}


@dataclass(frozen=True)
class RowView:
    title: str
    meta: str = ""
    pill_text: str = ""
    pill_tone: str = "muted"
    progress: int | None = None
    dot_tone: str = ""   # a small colored dot before the text ("" = none)
    unread: bool = False


@dataclass(frozen=True)
class HomeView:
    borrowings: tuple = ()      # every current borrowing, soonest due first
    reservations: tuple = ()    # every reservation waiting for pickup
    pending: tuple = ()         # every Pending request, newest first
    activity: tuple = ()        # newest first (already limited)
    due_soon_count: int = 0
    ready_count: int = 0

    @property
    def summary(self) -> str:
        b, p, r = len(self.borrowings), len(self.pending), len(self.reservations)
        if not (b or p or r):
            return ("Nothing is borrowed or waiting right now. "
                    "Browse the catalog to find something for class.")
        parts = [plural(b, "active borrowing")]
        if self.due_soon_count:
            parts[0] += f" ({self.due_soon_count} due within {DUE_SOON_DAYS} days)"
        parts.append(plural(p, "pending request"))
        parts.append(plural(r, "reservation"))
        return "You have " + ", ".join(parts[:-1]) + " and " + parts[-1] + "."


EMPTY_VIEW = HomeView()


def _local(moment: datetime) -> datetime:
    return moment.astimezone()


def _days_between(later: datetime, now: datetime) -> int:
    return (_local(later).date() - _local(now).date()).days


def _progress(start: datetime, end: datetime, now: datetime) -> int:
    total = max((end - start).total_seconds(), 1)
    return max(0, min(100, round((now - start).total_seconds() / total * 100)))


# ---------- real data ----------
def _borrowing_row(request, now: datetime) -> RowView:
    due = request.due_at
    meta = (f"{request.item.kind} · Borrowed {format_short_date(_local(request.picked_up_at).date())}"
            f" · Due {format_weekday_date(_local(due).date())}")
    if request.status is RequestStatus.RETURN_PENDING:
        return RowView(request.item.title, meta, "Return reported", "lavender")
    days_left = _days_between(due, now)
    if is_overdue(request, now):
        text = "Overdue" if days_left >= 0 else describe_days_left(days_left)
        tone = "rose"
    else:
        text, tone = describe_days_left(days_left), _DUE_TONES[due_tone(days_left)]
    return RowView(request.item.title, meta, text, tone,
                   progress=_progress(request.picked_up_at, due, now))


def _reservation_row(request) -> RowView:
    if request.scheduled_pickup_at is not None:
        meta = f"Pickup {format_weekday_date(_local(request.scheduled_pickup_at).date())}"
    elif request.pickup_deadline is not None:
        meta = f"Pick up by {format_short_date(_local(request.pickup_deadline).date())}"
    else:
        meta = "Waiting for a pickup time"
    return RowView(request.item.title, f"{request.item.kind} · {meta}",
                   "Awaiting pickup", "mint")


def _pending_row(request) -> RowView:
    meta = (f"{request.item.kind} · Requested "
            f"{format_short_date(_local(request.submitted_at).date())}"
            f" · {plural(request.requested_days, 'day')}")
    return RowView(request.item.title, meta, request.status.info.label, "lavender")


_ACTIVITY = {
    RequestStatus.PENDING: ("Requested {}", "lavender"),
    RequestStatus.PENDING_OWNER_APPROVAL: ("Awaiting owner approval: {}", "lavender"),
    RequestStatus.APPROVED: ("Approved: {}", "mint"),
    RequestStatus.REJECTED: ("Rejected: {}", "rose"),
    RequestStatus.BORROWED: ("Borrowed {}", "lavender"),
    RequestStatus.RETURN_PENDING: ("Reported return of {}", "pink"),
    RequestStatus.RETURNED: ("Returned {}", "mint"),
    RequestStatus.CANCELLED: ("Cancelled request for {}", "muted"),
    RequestStatus.EXPIRED: ("Reservation expired: {}", "amber"),
}


def _activity(requests, now: datetime, limit: int = 5) -> tuple:
    events = []
    for request in requests:
        changes = [(c.status, c.at) for c in request.status_history]
        pending_statuses = (RequestStatus.PENDING, RequestStatus.PENDING_OWNER_APPROVAL)
        if not any(status in pending_statuses for status, _ in changes):
            initial_status = request.status if request.status in pending_statuses else (
                RequestStatus.PENDING)
            changes.append((initial_status, request.submitted_at))
        for status, at in changes:
            events.append((at, request.request_id, status, request.item.title))
    events.sort(key=lambda e: (e[0], e[1]), reverse=True)
    rows = []
    for at, _, status, title in events[:limit]:
        text, tone = _ACTIVITY[status]
        rows.append(RowView(text.format(title),
                            describe_days_ago(max(_days_between(now, at), 0)),
                            dot_tone=tone))
    return tuple(rows)


def view_from_requests(requests, now: datetime | None = None) -> HomeView:
    """The Dashboard for ONE student's real requests (all statuses may be passed in)."""
    requests = list(requests)
    now = now or now_local()
    current, _ = split_borrowings(requests)
    awaiting, _ = split_reservations(requests)
    pending_statuses = (RequestStatus.PENDING, RequestStatus.PENDING_OWNER_APPROVAL)
    pending = sorted((r for r in requests if r.status in pending_statuses),
                     key=lambda r: (r.submitted_at, r.request_id), reverse=True)
    due_soon = sum(1 for r in current
                   if r.status is RequestStatus.BORROWED
                   and _days_between(r.due_at, now) <= DUE_SOON_DAYS)
    return HomeView(
        borrowings=tuple(_borrowing_row(r, now) for r in current),
        reservations=tuple(_reservation_row(r) for r in awaiting),
        pending=tuple(_pending_row(r) for r in pending),
        activity=_activity(requests, now),
        due_soon_count=due_soon,
        ready_count=len(awaiting),
    )


# ---------- demo (sample) data ----------
_DEMO_ACTIVITY_TONES = {"borrowed": "lavender", "returned": "mint",
                        "reserved": "pink", "renewed": "muted"}


def view_from_demo(data: DemoData) -> HomeView:
    borrowings = tuple(
        RowView(item.title,
                f"{item.category} · Borrowed {format_short_date(item.borrowed_on)}"
                f" · Due {format_weekday_date(item.due_on)}",
                describe_days_left(item.days_left),
                _DUE_TONES[due_tone(item.days_left)],
                progress=item.loan_progress)
        for item in data.borrowings_by_due_date())
    reservations = tuple(
        RowView(r.title, f"{r.category} · {r.detail}", r.status,
                "mint" if r.is_ready else "lavender")
        for r in data.reservations)
    activity = tuple(
        RowView(e.text, describe_days_ago(e.days_ago),
                dot_tone=_DEMO_ACTIVITY_TONES.get(e.kind, "muted"))
        for e in data.activity[:5])
    return HomeView(borrowings=borrowings, reservations=reservations, pending=(),
                    activity=activity, due_soon_count=len(data.due_soon()),
                    ready_count=data.ready_reservation_count)
