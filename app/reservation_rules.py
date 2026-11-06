"""Which requests count as reservations (Step 10). No GUI code in this file.

A RESERVATION is an item that was approved for the student but NOT yet handed over.
Approval is not borrowing: no pickup, no due date, no borrowing period.

Shown as "Awaiting pickup":
    Approved - Awaiting Pickup (and never picked up)

Shown as reservation HISTORY (only when it can be reliably identified):
    Reservation Expired                  - an expired request always had an approval
    Cancelled AFTER approval             - status Cancelled and `approved_at` is set

How "cancelled after approval" is recognised (no guessing):
    cancel_request() only changes status, status_changed_at and status_note. It never
    clears `approved_at`. So a Cancelled request WITH an approval time was cancelled
    after approval, and one WITHOUT it was cancelled while still Pending. The second
    kind is never a reservation and stays in My Requests only.

Never reservations: Pending (stays in My Requests), Rejected (never reserved),
Borrowed / Return Pending / Returned (those belong to My Borrowings).

Today nothing in the app can create an approval (that needs a lender/administrator),
so real accounts have no reservations yet. When approvals, pickup confirmation, the
FIFO waitlist or pickup-expiration scheduling arrive they will write the same request
records, and this single file is the only place that decides what counts.
"""
from datetime import datetime

from app.my_requests_screen import BorrowRequest, RequestStatus


def is_awaiting_pickup(request: BorrowRequest) -> bool:
    """Approved and reserved, but not collected. No due date exists yet."""
    return request.status is RequestStatus.APPROVED and request.picked_up_at is None


def is_cancelled_after_approval(request: BorrowRequest) -> bool:
    return (request.status is RequestStatus.CANCELLED
            and request.approved_at is not None
            and request.picked_up_at is None)


def is_expired_reservation(request: BorrowRequest) -> bool:
    return (request.status is RequestStatus.EXPIRED
            and request.approved_at is not None
            and request.picked_up_at is None)


def is_reservation_history(request: BorrowRequest) -> bool:
    return is_expired_reservation(request) or is_cancelled_after_approval(request)


def is_reservation(request: BorrowRequest) -> bool:
    return is_awaiting_pickup(request) or is_reservation_history(request)


def is_past_pickup_deadline(request: BorrowRequest, now: datetime) -> bool:
    """Still Approved, but the pickup window already closed.

    Nothing expires reservations automatically yet (no scheduler), so such a
    request keeps the Approved status until a later step handles it. This only
    reports the fact; it never changes the request.
    """
    return (is_awaiting_pickup(request) and request.pickup_deadline is not None
            and request.pickup_deadline < now)


def split_reservations(requests) -> tuple:
    """(awaiting, history) - only real reservations, each list in a useful order.

    awaiting : earliest confirmed pickup first (most urgent at the top)
    history  : most recent change first
    """
    awaiting = sorted((r for r in requests if is_awaiting_pickup(r)),
                      key=lambda r: (r.scheduled_pickup_at or r.approved_at, r.request_id))
    history = sorted((r for r in requests if is_reservation_history(r)),
                     key=lambda r: (r.status_changed_at or r.approved_at, r.request_id),
                     reverse=True)
    return awaiting, history
