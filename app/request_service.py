"""Local borrowing-request storage (Step 8C). No GUI code in this file.

Requests are saved in the same local SQLite file as the student accounts.
They are not sent to a backend. School-owned items start as Pending; published
Student Owner listings start as Pending Owner Approval. Student Owners can approve
or reject their own listing requests here; pickup confirmation remains a later step.

Safety rules this service enforces:
  * Every read and write is tied to ONE student id, taken from the logged-in
    session. A student can never read or cancel another student's request.
  * A batch is saved in ONE transaction: all items are saved, or none are.
  * A "submission key" makes a retry safe: sending the same batch twice (for
    example after a failure) can never create duplicate records.
  * A student cannot have two active requests for the same item.
  * The borrowing rule is untouched: nothing here stores or computes a due
    date. Due date = ACTUAL confirmed pickup + requested days, and that only
    exists after a future lender/administrator confirms the handover.

  * Step 11: every successful submit/cancel also stores its notification in the SAME
    transaction (see app/notification_service.py), so a request change and its
    notification are saved together or not at all. Nothing else creates notifications.

A future central backend can replace this class without touching the screens.
"""
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.borrowing_rules import is_borrowing
from app.catalog_screen import CatalogItem
from app.database import DatabaseError, connect, default_db_path
from app.my_list_screen import validate_days, validate_pickup
from app.my_requests_screen import BorrowRequest, RequestStatus, StatusChange
from app.notification_service import record_request_cancelled, record_request_submitted
from app.photo_service import PhotoService
from app.reservation_rules import is_reservation

ACTIVE_STATUS_VALUES = tuple(status.value for status in RequestStatus if status.info.is_active)
CANCELLABLE_STATUS_VALUES = (
    RequestStatus.PENDING.value, RequestStatus.PENDING_OWNER_APPROVAL.value,
    RequestStatus.APPROVED.value,
)
# Finished requests: the only ones "Clear History" / "Clear Cancelled" may hide.
CLEARABLE_STATUS_VALUES = (
    RequestStatus.RETURNED.value, RequestStatus.REJECTED.value,
    RequestStatus.EXPIRED.value, RequestStatus.CANCELLED.value,
)
SUBMITTED_NOTE = "Request submitted"
REQUEST_ID_PREFIX = "REQ-"


class RequestError(Exception):
    """A problem with a request; str(error) is safe to show to the student."""

    is_user_facing = True


@dataclass(frozen=True)
class LoadResult:
    requests: list   # BorrowRequest objects (this student's only)
    skipped: int     # saved records that could not be read (normally 0)


@dataclass(frozen=True)
class IncomingRequest:
    request: BorrowRequest
    borrower_name: str
    borrower_email: str
    listing_status: str


# ---------- small conversion helpers ----------
def _to_text(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat(timespec="seconds")


def _from_text(text) -> datetime | None:
    if not text:
        return None
    return datetime.fromisoformat(text).astimezone()  # timezone-aware, local zone


def _default_clock() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def _item_key(item: CatalogItem) -> tuple:
    if item.ownership == "student" and item.owner_student_id is not None:
        return (item.ownership, item.listing_key)
    return (item.title, item.creator, item.kind)


def _row_to_request(row: sqlite3.Row, history_rows) -> BorrowRequest:
    item = CatalogItem(
        title=row["item_title"],
        creator=row["item_creator"],
        category=row["item_category"],
        kind=row["item_kind"],
        ownership=row["item_ownership"],
        owner_note=row["item_owner_note"],
        copies_total=row["item_copies_total"],
        copies_available=row["item_copies_available"],
        collections=tuple(json.loads(row["item_collections"] or "[]")),
        record_id=row["owner_listing_id"],
        owner_student_id=row["owner_student_id"],
    )
    history = [
        StatusChange(RequestStatus(h["status"]), _from_text(h["changed_at"]), h["note"])
        for h in history_rows
    ]
    return BorrowRequest(
        request_id=row["request_id"],
        item=item,
        max_days=row["max_days"],
        requested_days=row["requested_days"],
        submitted_at=_from_text(row["submitted_at"]),
        status=RequestStatus(row["status"]),
        approved_at=_from_text(row["approved_at"]),
        pickup_deadline=_from_text(row["pickup_deadline"]),
        picked_up_at=_from_text(row["picked_up_at"]),
        status_changed_at=_from_text(row["status_changed_at"]),
        status_note=row["status_note"] or "",
        preferred_pickup_at=_from_text(row["preferred_pickup_at"]),
        scheduled_pickup_at=_from_text(row["scheduled_pickup_at"]),
        status_history=history,
        owner_listing_id=row["owner_listing_id"],
        owner_student_id=row["owner_student_id"],
        item_photo_path=row["item_photo_path"],
    )


class RequestService:
    def __init__(self, db_path=None, clock=_default_clock):
        self._db_path = db_path if db_path is not None else default_db_path()
        self._clock = clock  # tests can pass a fixed clock
        self._photos = PhotoService(
            self._db_path, Path(self._db_path).parent / "photos")

    @property
    def db_path(self):
        """Where the local database lives (other services share the same file)."""
        return self._db_path

    def _connect(self):
        return connect(self._db_path)

    @staticmethod
    def _require_approved_owner(conn, owner_id: int):
        if (not isinstance(owner_id, int) or isinstance(owner_id, bool)
                or conn.execute(
                    "SELECT 1 FROM student_owner_applications "
                    "WHERE student_id = ? AND status = 'Approved' LIMIT 1",
                    (owner_id,),
                ).fetchone() is None):
            raise RequestError("Only an approved Student Owner can review these requests.")

    def list_incoming_requests(self, owner_id: int) -> list[IncomingRequest]:
        """Load requests attached to this approved owner's stable listing IDs."""
        try:
            conn = self._connect()
        except DatabaseError:
            raise RequestError("Could not open the local database.") from None
        try:
            self._require_approved_owner(conn, owner_id)
            rows = conn.execute(
                "SELECT r.*, s.full_name AS borrower_name, s.email AS borrower_email, "
                "CASE WHEN l.deleted_at IS NOT NULL THEN 'Deleted' "
                "WHEN l.paused_at IS NOT NULL THEN 'Paused' "
                "ELSE l.status END AS listing_status "
                "FROM borrow_requests r "
                "JOIN owner_listings l ON l.listing_id = r.owner_listing_id "
                "JOIN students s ON s.id = r.student_id "
                "WHERE r.owner_student_id = ? AND l.owner_student_id = ? "
                "ORDER BY CASE r.status WHEN ? THEN 0 WHEN ? THEN 1 "
                "WHEN ? THEN 2 ELSE 3 END, r.submitted_at DESC, r.request_id",
                (owner_id, owner_id, RequestStatus.PENDING_OWNER_APPROVAL.value,
                 RequestStatus.APPROVED.value, RequestStatus.REJECTED.value),
            ).fetchall()
            histories = {}
            if rows:
                request_ids = [row["request_id"] for row in rows]
                marks = ",".join("?" for _ in request_ids)
                for history in conn.execute(
                    "SELECT * FROM borrow_request_history "
                    f"WHERE request_id IN ({marks}) ORDER BY changed_at, id",
                    request_ids,
                ):
                    histories.setdefault(history["request_id"], []).append(history)
            return [
                IncomingRequest(
                    _row_to_request(row, histories.get(row["request_id"], [])),
                    row["borrower_name"],
                    row["borrower_email"],
                    row["listing_status"],
                )
                for row in rows
            ]
        except RequestError:
            raise
        except (sqlite3.Error, DatabaseError, ValueError, TypeError):
            raise RequestError("Could not load incoming borrowing requests.") from None
        finally:
            conn.close()

    def approve_owner_request(self, owner_id: int, request_id: str) -> BorrowRequest:
        """Approve one pending request and reserve one copy in the same transaction."""
        now = self._clock().replace(microsecond=0)
        if now.tzinfo is None:
            raise RequestError("The approval time is invalid. Please try again.")
        try:
            conn = self._connect()
        except DatabaseError:
            raise RequestError("Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._require_approved_owner(conn, owner_id)
            row = conn.execute(
                "SELECT r.*, l.status AS listing_status, l.deleted_at, l.paused_at, "
                "l.max_borrow_days "
                "FROM borrow_requests r "
                "JOIN owner_listings l ON l.listing_id = r.owner_listing_id "
                "WHERE r.request_id = ? AND r.owner_student_id = ? "
                "AND l.owner_student_id = ?",
                (request_id, owner_id, owner_id),
            ).fetchone()
            if row is None:
                raise RequestError("That request was not found in your listings.")
            if row["status"] != RequestStatus.PENDING_OWNER_APPROVAL.value:
                raise RequestError("That request has already been reviewed.")
            if (row["listing_status"] != "Published" or row["deleted_at"] is not None
                    or row["paused_at"] is not None):
                raise RequestError("This listing is no longer accepting requests.")
            pickup = _from_text(row["preferred_pickup_at"])
            if pickup is None:
                raise RequestError("The requested pickup time is missing.")
            if pickup <= now:
                raise RequestError(
                    "The requested pickup time has passed. The borrower will need to submit "
                    "a new request.")
            if row["requested_days"] > row["max_borrow_days"]:
                raise RequestError(
                    "The listing's borrowing limit changed. The borrower will need to submit "
                    "a new request.")
            pickup_local = pickup.astimezone(now.tzinfo)
            pickup_minute = pickup_local.hour * 60 + pickup_local.minute
            windows = conn.execute(
                "SELECT start_minute, end_minute FROM listing_availability "
                "WHERE listing_id = (SELECT owner_listing_id FROM borrow_requests "
                "WHERE request_id = ?) AND weekday = ?",
                (request_id, pickup_local.weekday()),
            ).fetchall()
            if not any(
                slot["start_minute"] <= pickup_minute
                and pickup_minute + 30 <= slot["end_minute"]
                and (pickup_minute - slot["start_minute"]) % 30 == 0
                for slot in windows
            ):
                raise RequestError(
                    "The requested pickup time is no longer available. The borrower will "
                    "need to submit a new request.")
            timestamp = _to_text(now)
            copy = conn.execute(
                "SELECT copy_id FROM owner_listing_copies "
                "WHERE listing_id = (SELECT owner_listing_id FROM borrow_requests "
                "WHERE request_id = ?) AND owner_student_id = ? AND state = 'available' "
                "ORDER BY created_at, copy_id LIMIT 1",
                (request_id, owner_id),
            ).fetchone()
            if copy is None:
                raise RequestError("No copies are currently available to approve this request.")
            reserved = conn.execute(
                "UPDATE owner_listing_copies SET state = 'reserved', request_id = ?, "
                "updated_at = ? WHERE copy_id = ? AND owner_student_id = ? "
                "AND state = 'available' AND request_id IS NULL",
                (request_id, timestamp, copy["copy_id"], owner_id),
            )
            if reserved.rowcount != 1:
                raise RequestError("A copy is no longer available. Refresh and try again.")

            deadline = _to_text(pickup + timedelta(days=1))
            note = "Approved by Student Owner; awaiting pickup."
            changed = conn.execute(
                "UPDATE borrow_requests SET status = ?, approved_at = ?, "
                "scheduled_pickup_at = ?, pickup_deadline = ?, status_note = ? "
                "WHERE request_id = ? AND owner_student_id = ? AND status = ? "
                "AND picked_up_at IS NULL",
                (RequestStatus.APPROVED.value, timestamp, _to_text(pickup), deadline, note,
                 request_id, owner_id, RequestStatus.PENDING_OWNER_APPROVAL.value),
            )
            if changed.rowcount != 1:
                raise RequestError("That request has already been reviewed.")
            conn.execute(
                "INSERT INTO borrow_request_history (request_id, status, changed_at, note) "
                "VALUES (?, ?, ?, ?)",
                (request_id, RequestStatus.APPROVED.value, timestamp, note),
            )
            history = conn.execute(
                "SELECT * FROM borrow_request_history WHERE request_id = ? "
                "ORDER BY changed_at, id", (request_id,),
            ).fetchall()
            updated = conn.execute(
                "SELECT * FROM borrow_requests WHERE request_id = ?", (request_id,),
            ).fetchone()
            result = _row_to_request(updated, history)
            conn.commit()
            return result
        except RequestError:
            conn.rollback()
            raise
        except (sqlite3.Error, DatabaseError, ValueError, TypeError):
            conn.rollback()
            raise RequestError("Could not approve the request. Nothing was changed.") from None
        finally:
            conn.close()

    def reject_owner_request(
        self, owner_id: int, request_id: str, reason: str = ""
    ) -> BorrowRequest:
        """Reject one pending request without changing the listing's copy inventory."""
        now = self._clock().replace(microsecond=0)
        if now.tzinfo is None:
            raise RequestError("The rejection time is invalid. Please try again.")
        reason = (reason or "").strip()
        if len(reason) > 500:
            raise RequestError("The optional rejection reason must be 500 characters or fewer.")
        note = reason or "Rejected by Student Owner."
        try:
            conn = self._connect()
        except DatabaseError:
            raise RequestError("Could not open the local database. Nothing was changed.") from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._require_approved_owner(conn, owner_id)
            row = conn.execute(
                "SELECT r.request_id FROM borrow_requests r "
                "JOIN owner_listings l ON l.listing_id = r.owner_listing_id "
                "WHERE r.request_id = ? AND r.owner_student_id = ? "
                "AND l.owner_student_id = ? AND r.status = ? AND r.picked_up_at IS NULL",
                (request_id, owner_id, owner_id, RequestStatus.PENDING_OWNER_APPROVAL.value),
            ).fetchone()
            if row is None:
                raise RequestError("That pending request was not found in your listings.")
            timestamp = _to_text(now)
            changed = conn.execute(
                "UPDATE borrow_requests SET status = ?, status_changed_at = ?, status_note = ? "
                "WHERE request_id = ? AND owner_student_id = ? AND status = ? "
                "AND picked_up_at IS NULL",
                (RequestStatus.REJECTED.value, timestamp, note, request_id, owner_id,
                 RequestStatus.PENDING_OWNER_APPROVAL.value),
            )
            if changed.rowcount != 1:
                raise RequestError("That request has already been reviewed.")
            conn.execute(
                "INSERT INTO borrow_request_history (request_id, status, changed_at, note) "
                "VALUES (?, ?, ?, ?)",
                (request_id, RequestStatus.REJECTED.value, timestamp, note),
            )
            history = conn.execute(
                "SELECT * FROM borrow_request_history WHERE request_id = ? "
                "ORDER BY changed_at, id", (request_id,),
            ).fetchall()
            updated = conn.execute(
                "SELECT * FROM borrow_requests WHERE request_id = ?", (request_id,),
            ).fetchone()
            result = _row_to_request(updated, history)
            conn.commit()
            return result
        except RequestError:
            conn.rollback()
            raise
        except (sqlite3.Error, DatabaseError, ValueError, TypeError):
            conn.rollback()
            raise RequestError("Could not reject the request. Nothing was changed.") from None
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Submitting
    # ------------------------------------------------------------------
    def submit_requests(self, student_id: int, drafts, submission_key: str) -> list:
        """Save one Pending request per draft. Returns the saved BorrowRequests.

        All-or-nothing. Calling it again with the SAME submission_key returns the
        already-saved requests instead of creating new ones.
        """
        drafts = list(drafts or [])
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise RequestError("Please log in again before requesting items.")
        if not drafts:
            raise RequestError("There is nothing to request.")
        if not submission_key or not isinstance(submission_key, str):
            raise RequestError("This request could not be identified. Please try again.")

        now = self._clock()
        keys = [_item_key(draft.item) for draft in drafts]
        if len(keys) != len(set(keys)):
            raise RequestError("The same item appears twice in this request.")
        for draft in drafts:
            self._check_draft(draft, now)

        # Build the objects first: if they are valid here, they can always be loaded later.
        prepared = []
        for draft in drafts:
            try:
                prepared.append(BorrowRequest(
                    request_id="",  # real ID is generated while saving
                    item=draft.item,
                    max_days=draft.max_days,
                    requested_days=draft.days,
                    submitted_at=now,
                    status=(RequestStatus.PENDING_OWNER_APPROVAL
                            if draft.item.owner_student_id is not None
                            else RequestStatus.PENDING),
                    preferred_pickup_at=_to_text_roundtrip(draft.pickup_at),
                    owner_listing_id=(draft.item.listing_key
                                      if draft.item.owner_student_id is not None else None),
                    owner_student_id=draft.item.owner_student_id,
                    status_history=[StatusChange(
                        RequestStatus.PENDING_OWNER_APPROVAL
                        if draft.item.owner_student_id is not None
                        else RequestStatus.PENDING, now, SUBMITTED_NOTE)],
                ))
            except ValueError as exc:
                raise RequestError(f"“{draft.item.title}”: {exc}") from exc

        try:
            conn = self._connect()
        except DatabaseError:
            raise RequestError(
                "Could not open the local database. Nothing was saved. Please try again."
            ) from None
        try:
            conn.execute("BEGIN IMMEDIATE")  # one writer at a time: no duplicate races
            if conn.execute("SELECT 1 FROM students WHERE id = ?", (student_id,)).fetchone() is None:
                raise RequestError("Your account could not be found. Please log in again.")

            existing = self._load_by_submission_key(conn, student_id, submission_key)
            if existing:                      # same batch sent again -> no new records
                conn.rollback()
                return existing

            listing_contexts = [
                self._validate_owner_listing_request(conn, student_id, draft, now)
                for draft in drafts
            ]
            self._reject_active_duplicates(conn, student_id, drafts)

            saved = []
            for position, (draft, request, context) in enumerate(
                    zip(drafts, prepared, listing_contexts)):
                if context is not None:
                    request.owner_listing_id = context["listing_id"]
                    request.owner_student_id = context["owner_student_id"]
                    request.item_photo_path = context["photo_path"]
                request.request_id = self._insert_request(
                    conn, student_id, submission_key, position, draft, request, context)
                conn.execute(
                    "INSERT INTO borrow_request_history (request_id, status, changed_at, note) "
                    "VALUES (?, ?, ?, ?)",
                    (request.request_id, request.status.value, _to_text(now), SUBMITTED_NOTE),
                )
                # Same transaction: the notification exists only if the request does.
                record_request_submitted(
                    conn, student_id, request.request_id, draft.item.title, now)
                saved.append(request)
            conn.commit()
            return saved
        except RequestError:
            conn.rollback()
            raise
        except (sqlite3.Error, DatabaseError, ValueError):
            conn.rollback()
            raise RequestError(
                "Could not save your request because of a database problem. "
                "Nothing was saved."
            ) from None
        finally:
            conn.close()

    @staticmethod
    def _check_draft(draft, now: datetime):
        title = draft.item.title
        if not draft.item.is_available:
            raise RequestError(f"“{title}” is not available right now, so it can't be requested.")
        if not isinstance(draft.max_days, int) or draft.max_days < 1:
            raise RequestError(f"“{title}” has no valid borrowing limit.")
        problem = validate_days(draft.days, draft.max_days)
        if problem:
            raise RequestError(f"“{title}”: {problem}")
        problem = validate_pickup(draft.pickup_at, now)
        if problem:
            raise RequestError(f"“{title}”: {problem}")

    @staticmethod
    def _reject_active_duplicates(conn, student_id: int, drafts):
        marks = ",".join("?" for _ in ACTIVE_STATUS_VALUES)
        for draft in drafts:
            if draft.item.ownership == "student" and draft.item.owner_student_id is not None:
                row = conn.execute(
                    f"SELECT request_id FROM borrow_requests WHERE student_id = ? "
                    f"AND owner_listing_id = ? AND status IN ({marks}) LIMIT 1",
                    (student_id, draft.item.listing_key, *ACTIVE_STATUS_VALUES)).fetchone()
            else:
                row = conn.execute(
                    f"SELECT request_id FROM borrow_requests WHERE student_id = ? "
                    f"AND item_title = ? AND item_creator = ? AND item_kind = ? "
                    f"AND status IN ({marks}) LIMIT 1",
                    (student_id, draft.item.title, draft.item.creator, draft.item.kind,
                     *ACTIVE_STATUS_VALUES)).fetchone()
            if row is not None:
                raise RequestError(
                    f"You already have an active request for “{draft.item.title}” "
                    f"({row['request_id']}). Check My Requests."
                )

    def _validate_owner_listing_request(self, conn, student_id, draft, now):
        """Revalidate a Student Owner listing and its live schedule inside the save transaction."""
        item = draft.item
        if item.ownership != "student":
            return None
        if item.owner_student_id is None:
            if item.record_id is not None and conn.execute(
                    "SELECT 1 FROM owner_listings WHERE listing_id = ?",
                    (item.record_id,)).fetchone() is not None:
                raise RequestError("Refresh the Catalog before requesting this listing.")
            return None
        listing_id = item.listing_key
        row = conn.execute(
            "SELECT l.listing_id, l.owner_student_id, l.title, l.category, "
            "l.max_borrow_days, l.status, l.paused_at, l.deleted_at, l.stock_quantity, "
            "s.full_name, (SELECT COUNT(*) FROM owner_listing_copies c "
            "WHERE c.listing_id = l.listing_id AND c.state = 'available') "
            "AS available_copies "
            "FROM owner_listings l JOIN students s ON s.id = l.owner_student_id "
            "WHERE l.listing_id = ?", (listing_id,)).fetchone()
        if (row is None or row["status"] != "Published" or row["paused_at"] is not None
                or row["deleted_at"] is not None):
            raise RequestError("This listing is no longer accepting borrowing requests.")
        if row["owner_student_id"] == student_id:
            raise RequestError("You cannot request to borrow your own listing.")
        if row["owner_student_id"] != item.owner_student_id:
            raise RequestError("The listing owner changed. Refresh the Catalog and try again.")
        if row["stock_quantity"] == 0:
            raise RequestError("This listing is out of stock and cannot accept new requests.")
        if row["available_copies"] == 0:
            raise RequestError("All copies are currently committed and cannot be requested.")
        if (row["title"] != item.title or row["category"] != item.category
                or row["max_borrow_days"] != draft.max_days
                or row["full_name"] != item.creator):
            raise RequestError("This listing has changed. Refresh the Catalog and try again.")
        pickup_local = draft.pickup_at.astimezone(now.tzinfo)
        day = pickup_local.date()
        today = now.astimezone(now.tzinfo).date()
        if day < today or day > today + timedelta(days=60):
            raise RequestError("Choose a pickup date within the next 60 days.")
        minute = pickup_local.hour * 60 + pickup_local.minute
        windows = conn.execute(
            "SELECT start_minute, end_minute FROM listing_availability "
            "WHERE listing_id = ? AND weekday = ? ORDER BY start_minute",
            (listing_id, day.weekday())).fetchall()
        if not any(start <= minute and minute + 30 <= end
                   and (minute - start) % 30 == 0
                   for start, end in ((slot["start_minute"], slot["end_minute"])
                                      for slot in windows)):
            raise RequestError(
                "That pickup time is outside the owner's current availability. "
                "Choose an available slot.")
        photo = conn.execute(
            "SELECT file_path FROM listing_photos WHERE listing_key = ? "
            "ORDER BY is_primary DESC, position, photo_id LIMIT 1",
            (listing_id,)).fetchone()
        photo_path = self._photos.resolve(photo["file_path"]) if photo else None
        return {
            "listing_id": listing_id,
            "owner_student_id": row["owner_student_id"],
            "photo_path": photo_path,
        }

    @staticmethod
    def _insert_request(conn, student_id, submission_key, position, draft, request,
                        listing_context=None) -> str:
        item = draft.item
        status = request.status
        for _attempt in range(8):  # a clash on a random ID is very unlikely; just retry
            request_id = REQUEST_ID_PREFIX + secrets.token_hex(4).upper()
            try:
                conn.execute(
                    "INSERT INTO borrow_requests (request_id, student_id, submission_key, "
                    "batch_position, item_title, item_creator, item_category, item_kind, "
                    "item_ownership, item_owner_note, item_copies_total, item_copies_available, "
                    "item_collections, max_days, requested_days, status, submitted_at, "
                    "preferred_pickup_at, owner_listing_id, owner_student_id, item_photo_path) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (request_id, student_id, submission_key, position, item.title, item.creator,
                     item.category, item.kind, item.ownership, item.owner_note,
                     item.copies_total, item.copies_available, json.dumps(list(item.collections)),
                     draft.max_days, draft.days, status.value,
                     _to_text(request.submitted_at), _to_text(request.preferred_pickup_at),
                     listing_context["listing_id"] if listing_context else None,
                     listing_context["owner_student_id"] if listing_context else None,
                     listing_context["photo_path"] if listing_context else None),
                )
                return request_id
            except sqlite3.IntegrityError as exc:
                if "request_id" not in str(exc):
                    raise
        raise sqlite3.Error("could not create a unique request ID")

    # ------------------------------------------------------------------
    # Loading (always for ONE student)
    # ------------------------------------------------------------------
    def load_requests(self, student_id: int) -> LoadResult:
        """Every request that belongs to this student (and nobody else's)."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM borrow_requests WHERE student_id = ? "
                    "ORDER BY submitted_at, request_id", (student_id,)).fetchall()
                history = self._history_for_student(conn, student_id)
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            raise RequestError("Could not load your saved requests. Please try again.") from None

        loaded, skipped = [], 0
        for row in rows:
            try:
                loaded.append(_row_to_request(row, history.get(row["request_id"], [])))
            except (ValueError, KeyError, TypeError):
                skipped += 1  # one damaged record must not hide all the others
        return LoadResult(loaded, skipped)

    def list_requests(self, student_id: int) -> list:
        return self.load_requests(student_id).requests

    def load_borrowings(self, student_id: int) -> LoadResult:
        """This student's real borrowings only (read-only, nothing is changed).

        Borrowed, Return Verification Pending and Returned requests that have a
        confirmed pickup. Pending, Approved, Rejected, Cancelled and Expired
        requests are never included. Nothing in the app can create a Borrowed
        record yet (that needs a lender/administrator), so this is empty for now.
        """
        result = self.load_requests(student_id)
        return LoadResult([r for r in result.requests if is_borrowing(r)], result.skipped)

    def load_reservations(self, student_id: int) -> LoadResult:
        """This student's real reservations only (read-only, nothing is changed).

        Approved - Awaiting Pickup, plus the history that can be identified reliably:
        Expired reservations and requests cancelled AFTER approval. Pending requests
        and requests cancelled before approval are never included. They are the same
        records My Requests shows; nothing is copied or stored separately. Nothing in
        the app can create an approval yet (that needs a lender/administrator), so
        this is empty for now.
        """
        result = self.load_requests(student_id)
        return LoadResult([r for r in result.requests if is_reservation(r)], result.skipped)

    def get_request(self, student_id: int, request_id: str) -> BorrowRequest | None:
        """One request, but only if it belongs to this student."""
        try:
            conn = self._connect()
            try:
                return self._load_one(conn, student_id, request_id)
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError, ValueError, KeyError, TypeError):
            raise RequestError("Could not read that request. Please try again.") from None

    @staticmethod
    def _history_for_student(conn, student_id: int) -> dict:
        grouped = {}
        for h in conn.execute(
                "SELECT h.* FROM borrow_request_history h "
                "JOIN borrow_requests r ON r.request_id = h.request_id "
                "WHERE r.student_id = ? ORDER BY h.id", (student_id,)):
            grouped.setdefault(h["request_id"], []).append(h)
        return grouped

    @staticmethod
    def _load_one(conn, student_id: int, request_id: str) -> BorrowRequest | None:
        row = conn.execute(
            "SELECT * FROM borrow_requests WHERE request_id = ? AND student_id = ?",
            (request_id, student_id)).fetchone()
        if row is None:
            return None
        history = conn.execute(
            "SELECT * FROM borrow_request_history WHERE request_id = ? ORDER BY id",
            (request_id,)).fetchall()
        return _row_to_request(row, history)

    def _load_by_submission_key(self, conn, student_id: int, submission_key: str) -> list:
        rows = conn.execute(
            "SELECT request_id FROM borrow_requests WHERE student_id = ? AND submission_key = ? "
            "ORDER BY batch_position", (student_id, submission_key)).fetchall()
        found = [self._load_one(conn, student_id, row["request_id"]) for row in rows]
        return [request for request in found if request is not None]

    # ------------------------------------------------------------------
    # Clearing finished requests from My Requests (hide only, never delete)
    # ------------------------------------------------------------------
    def hidden_request_ids(self, student_id: int) -> set:
        """IDs of this student's requests they cleared from My Requests."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT request_id FROM hidden_requests WHERE student_id = ?",
                    (student_id,)).fetchall()
            finally:
                conn.close()
        except (sqlite3.Error, DatabaseError):
            raise RequestError("Could not load your cleared requests. Please try again.") from None
        return {row["request_id"] for row in rows}

    def hide_closed_requests(self, student_id: int, request_ids, when: datetime | None = None) -> int:
        """Hide finished requests on My Requests. Returns how many were newly hidden.

        Nothing in borrow_requests or its history is changed or deleted; only a row in
        hidden_requests is added. Only this student's Returned, Rejected, Expired or Cancelled
        requests qualify. If ANY id is someone else's, unknown or still active, nothing at all
        is hidden.
        """
        ids = list(dict.fromkeys(request_ids))
        if not ids:
            return 0
        when = (when or self._clock()).replace(microsecond=0)
        if when.tzinfo is None:
            raise RequestError("The time is invalid. Please try again.")
        try:
            conn = self._connect()
        except DatabaseError:
            raise RequestError(
                "Could not open the local database. Nothing was changed. Please try again."
            ) from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            newly_hidden = 0
            for request_id in ids:
                row = conn.execute(
                    "SELECT status FROM borrow_requests WHERE request_id = ? AND student_id = ?",
                    (request_id, student_id)).fetchone()
                if row is None or row["status"] not in CLEARABLE_STATUS_VALUES:
                    raise RequestError(
                        "Only finished requests can be cleared. Nothing was changed.")
                newly_hidden += conn.execute(
                    "INSERT OR IGNORE INTO hidden_requests (student_id, request_id, hidden_at) "
                    "VALUES (?, ?, ?)", (student_id, request_id, _to_text(when))).rowcount
            conn.commit()
            return newly_hidden
        except RequestError:
            conn.rollback()
            raise
        except (sqlite3.Error, DatabaseError):
            conn.rollback()
            raise RequestError(
                "Could not clear those requests because of a database problem. "
                "Nothing was changed.") from None
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Cancelling
    # ------------------------------------------------------------------
    def cancel_request(self, student_id: int, request_id: str, when: datetime | None = None):
        """Cancel ONE of this student's requests and keep its history. Returns it.

        Only a request that is still Pending (or approved but not yet collected)
        can be cancelled. Anyone else's request looks exactly like a missing one.
        """
        when = (when or self._clock()).replace(microsecond=0)
        if when.tzinfo is None:
            raise RequestError("The cancellation time is invalid. Please try again.")
        not_found = RequestError("That request was not found in your account.")

        try:
            conn = self._connect()
        except DatabaseError:
            raise RequestError(
                "Could not open the local database. Nothing was changed. Please try again."
            ) from None
        try:
            conn.execute("BEGIN IMMEDIATE")
            request = self._load_one(conn, student_id, request_id)
            if request is None:
                raise not_found
            if not request.can_cancel:
                raise RequestError(
                    f"{request_id} can no longer be cancelled ({request.status.info.label})."
                )
            # Never record a time earlier than the request's own history.
            latest = max([request.submitted_at] + [c.at for c in request.status_history])
            was_approved = request.status is RequestStatus.APPROVED
            request.cancel(max(when, latest))  # builds the same note/history as the screen

            changed = conn.execute(
                "UPDATE borrow_requests SET status = ?, status_changed_at = ?, status_note = ? "
                "WHERE request_id = ? AND student_id = ? AND picked_up_at IS NULL "
                f"AND status IN ({','.join('?' for _ in CANCELLABLE_STATUS_VALUES)})",
                (RequestStatus.CANCELLED.value, _to_text(request.status_changed_at),
                 request.status_note, request_id, student_id, *CANCELLABLE_STATUS_VALUES),
            ).rowcount
            if changed != 1:
                raise RequestError(f"{request_id} can no longer be cancelled.")
            if was_approved and request.owner_listing_id:
                released = conn.execute(
                    "UPDATE owner_listing_copies SET state = 'available', request_id = NULL, "
                    "updated_at = ? WHERE request_id = ? AND listing_id = ? "
                    "AND owner_student_id = ? AND state = 'reserved'",
                    (_to_text(request.status_changed_at), request_id,
                     request.owner_listing_id, request.owner_student_id),
                )
                if released.rowcount != 1:
                    raise RequestError(
                        "The reserved copy could not be released, so the request was not "
                        "cancelled. Please try again.")
            conn.execute(
                "INSERT INTO borrow_request_history (request_id, status, changed_at, note) "
                "VALUES (?, ?, ?, ?)",
                (request_id, RequestStatus.CANCELLED.value,
                 _to_text(request.status_changed_at), request.status_note),
            )
            # Same transaction: only reached when the cancellation really happened.
            record_request_cancelled(
                conn, student_id, request_id, request.item.title, request.status_changed_at)
            conn.commit()
            return request
        except RequestError:
            conn.rollback()
            raise
        except (sqlite3.Error, DatabaseError, ValueError, KeyError, TypeError):
            conn.rollback()
            raise RequestError(
                "Could not cancel the request because of a database problem. "
                "Nothing was changed."
            ) from None
        finally:
            conn.close()


def _to_text_roundtrip(moment: datetime) -> datetime:
    """Drop sub-second noise so the object equals what is stored."""
    return moment.replace(microsecond=0)
