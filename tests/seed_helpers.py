"""Shared helpers for the tests: build consistent requests and write them straight
into a TEMPORARY SQLite database (what a future lender/administrator action would
cause, since the app itself cannot create Approved/Borrowed records yet).
Not part of the app. Never point these at your real database.
"""
import dataclasses
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.catalog_screen import SAMPLE_ITEMS  # noqa: E402
from app.my_requests_screen import BorrowRequest, RequestStatus, build_sample_requests  # noqa: E402
from app.request_service import _to_text  # noqa: E402

AVAILABLE = [item for item in SAMPLE_ITEMS if item.is_available]


def now_fixed() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def make_borrowing(request_id, now, *, picked_days_ago, days, status=RequestStatus.BORROWED,
                   item=None):
    """A consistent Borrowed / Return Pending / Returned request."""
    pickup = now - timedelta(days=picked_days_ago)
    approved = pickup - timedelta(days=1)
    extra = {}
    if status is not RequestStatus.BORROWED:
        extra["status_changed_at"] = pickup + timedelta(hours=2)
    return BorrowRequest(
        request_id, item or AVAILABLE[0], 7, days, approved - timedelta(days=1), status,
        approved_at=approved, scheduled_pickup_at=pickup,
        pickup_deadline=pickup + timedelta(hours=8), picked_up_at=pickup,
        preferred_pickup_at=pickup, **extra)


def insert_request(db_path, student_id, request, key):
    """Write a request straight into SQLite (what a future lender/admin action would cause)."""
    item = request.item
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO borrow_requests (request_id, student_id, submission_key, batch_position, "
            "item_title, item_creator, item_category, item_kind, item_ownership, item_owner_note, "
            "item_copies_total, item_copies_available, item_collections, max_days, requested_days, "
            "status, submitted_at, preferred_pickup_at, approved_at, scheduled_pickup_at, "
            "pickup_deadline, picked_up_at, status_changed_at, status_note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (request.request_id, student_id, key, 0, item.title, item.creator, item.category,
             item.kind, item.ownership, item.owner_note, item.copies_total, item.copies_available,
             json.dumps(list(item.collections)), request.max_days, request.requested_days,
             request.status.value, _to_text(request.submitted_at),
             _to_text(request.preferred_pickup_at), _to_text(request.approved_at),
             _to_text(request.scheduled_pickup_at), _to_text(request.pickup_deadline),
             _to_text(request.picked_up_at), _to_text(request.status_changed_at),
             request.status_note))
        for change in request.status_history:
            conn.execute(
                "INSERT INTO borrow_request_history (request_id, status, changed_at, note) "
                "VALUES (?,?,?,?)",
                (request.request_id, change.status.value, _to_text(change.at), change.note))
        conn.commit()
    finally:
        conn.close()


def seed_samples(db_path, student_id, prefix=""):
    """All eight sample statuses for one student (IDs get a prefix to stay unique)."""
    for index, request in enumerate(build_sample_requests(now_fixed())):
        copy = dataclasses.replace(request, request_id=prefix + request.request_id)
        insert_request(db_path, student_id, copy, f"seed-{prefix}{index}")


def make_reservation(request_id, now, *, status=RequestStatus.APPROVED, pickup_in_days=1,
                     days=3, item=None, approved=True, note=""):
    """A consistent reservation-type request.

    status APPROVED  -> awaiting pickup (pickup_in_days < 0 means the deadline already passed)
    status EXPIRED   -> approved, never collected
    status CANCELLED -> cancelled AFTER approval (approved=True) or BEFORE it (approved=False)
    """
    scheduled = now + timedelta(days=pickup_in_days)
    approved_at = scheduled - timedelta(days=1)
    deadline = scheduled + timedelta(hours=8)
    submitted = approved_at - timedelta(days=1)
    kwargs = dict(preferred_pickup_at=scheduled)
    if approved:
        kwargs.update(approved_at=approved_at, scheduled_pickup_at=scheduled,
                      pickup_deadline=deadline)
    if status is RequestStatus.EXPIRED:
        kwargs["status_changed_at"] = deadline
    elif status is RequestStatus.CANCELLED:
        kwargs["status_changed_at"] = (approved_at if approved else submitted) + timedelta(hours=3)
        kwargs["status_note"] = note
    return BorrowRequest(request_id, item or AVAILABLE[0], 7, days, submitted, status, **kwargs)
