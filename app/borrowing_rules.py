"""Which requests count as real borrowings (Step 9). No GUI code in this file.

The rule, in one sentence:
    A request is a BORROWING only after the lender/administrator confirmed the
    physical handover (so it has an actual `picked_up_at`).

That means these are borrowings:
    Borrowed                      - the student has the item now
    Return Verification Pending   - the student reported the return, waiting for confirmation
    Returned                      - finished (kept as history)

These are NOT borrowings, however they look: Pending, Approved - Awaiting Pickup,
Rejected, Cancelled, Reservation Expired. The item never left the lender. They
stay in My Requests (and, later, Reservations).

Nothing here changes a request or computes a new due date. The due date is still
calculated by BorrowRequest.due_at = actual confirmed pickup + requested days.
"""
from datetime import datetime

from app.my_requests_screen import BorrowRequest, RequestStatus

CURRENT_STATUSES = (RequestStatus.BORROWED, RequestStatus.RETURN_PENDING)
HISTORY_STATUSES = (RequestStatus.RETURNED,)
BORROWING_STATUSES = CURRENT_STATUSES + HISTORY_STATUSES


def is_borrowing(request: BorrowRequest) -> bool:
    """True only for a request whose handover was confirmed."""
    return request.status in BORROWING_STATUSES and request.picked_up_at is not None


def is_current_borrowing(request: BorrowRequest) -> bool:
    """A borrowing the student still has (not yet verified as returned)."""
    return is_borrowing(request) and request.status in CURRENT_STATUSES


def is_overdue(request: BorrowRequest, now: datetime) -> bool:
    """Borrowed and past the due date. A reported return is not flagged overdue."""
    due = request.due_at
    return (request.status is RequestStatus.BORROWED and due is not None and due < now)


def split_borrowings(requests) -> tuple:
    """(current, history) - only real borrowings, each list in a useful order.

    current : soonest due date first, so the most urgent item is at the top
    history : most recently returned first
    """
    borrowings = [r for r in requests if is_borrowing(r)]
    current = sorted((r for r in borrowings if r.status in CURRENT_STATUSES),
                     key=lambda r: (r.due_at, r.request_id))
    history = sorted((r for r in borrowings if r.status in HISTORY_STATUSES),
                     key=lambda r: (r.status_changed_at or r.picked_up_at, r.request_id),
                     reverse=True)
    return current, history
