"""Owner listing drafts, stored per Student Owner in the local SQLite file (Step 31B).

No Qt in this file. Rules:
  * Only an APPROVED Student Owner (checked through WorkspaceService on EVERY call) can
    create, read or edit listings. Anyone else gets OwnerListingError.
  * Every query is limited to the signed-in owner's own rows, so one owner can never read
    or change another owner's draft.
  * Drafts and published listings are stored here. Publishing only changes the status; it
    does not add listings to the student Catalog or start borrowing approvals.
  * Step 31C: each listing also has an availability schedule (pickup weekdays and time
    ranges, table listing_availability). It is saved in the same transaction as the draft,
    or on its own with save_availability(), and is always limited to the owner's own rows.
    Photos are handled by app/owner_listing_photos.py.
  * Step 31D: categories come from the SHARED registry (app/listing_category_service.py):
    a listing has one general category and an optional subcategory. `owner_listings.category`
    still holds the general category's name, so existing listings and screens are unchanged;
    the link table (listing_category_links) adds the subcategory. Passing an explicit
    `categories` list to the constructor keeps the old fixed-list behaviour (used by tests).
"""
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.database import DatabaseError, connect, default_db_path
from app.listing_category_service import CategoryError, CategoryService
from app.owner_availability import AvailabilityError, AvailabilitySchedule
from app.photo_service import PhotoService
from app.workspace_service import WORKSPACE_STUDENT_OWNER

STATUS_DRAFT = "Draft"
STATUS_PUBLISHED = "Published"
STATUS_PAUSED = "Paused"
STATUS_DELETED = "Deleted"
ACTIVE_LISTING_REQUEST_STATUSES = (
    "pending", "pending_owner_approval", "approved", "borrowed", "return_pending")
CONDITIONS = ("New", "Like new", "Good", "Fair", "Worn")
MIN_TITLE, MAX_TITLE = 3, 80
MIN_DESCRIPTION, MAX_DESCRIPTION = 10, 1000
MAX_EXTRA_RULES = 500
MIN_DAYS, MAX_DAYS = 1, 30
MAX_STOCK_QUANTITY = 9999
NOT_ALLOWED = "Only approved Student Owners can manage listings."


class OwnerListingError(Exception):
    """A listing problem; str(error) is safe to show to the student."""

    is_user_facing = True


@dataclass(frozen=True)
class OwnerListing:
    listing_id: str
    owner_student_id: int
    title: str
    category: str
    description: str
    condition: str
    max_borrow_days: int
    extra_rules: str
    status: str
    created_at: str
    updated_at: str
    subcategory: str = ""   # Step 31D: optional, "" when none
    stock_quantity: int = 1
    available_copies: int = 1

    @property
    def category_path(self) -> str:
        """"Books › Fantasy" (or just the general category)."""
        return f"{self.category} › {self.subcategory}" if self.subcategory else self.category

    @property
    def is_draft(self) -> bool:
        return self.status == STATUS_DRAFT


@dataclass(frozen=True)
class PublishedCatalogListing:
    listing: OwnerListing
    owner_name: str
    availability: AvailabilitySchedule


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _clean_block(text) -> str:
    lines = [" ".join(line.split()) for line in str(text or "").strip().splitlines()]
    return "\n".join(lines).strip()


def validate_fields(fields: dict, categories) -> dict:
    """Return the cleaned fields or raise OwnerListingError with a friendly message."""
    title = _clean(fields.get("title"))
    if not title:
        raise OwnerListingError("Please enter the item name.")
    if len(title) < MIN_TITLE:
        raise OwnerListingError(f"The item name needs at least {MIN_TITLE} characters.")
    if len(title) > MAX_TITLE:
        raise OwnerListingError(f"Please keep the item name under {MAX_TITLE} characters.")
    category = str(fields.get("category") or "").strip()
    if category not in categories:
        raise OwnerListingError("Please choose a category.")
    condition = str(fields.get("condition") or "").strip()
    if condition not in CONDITIONS:
        raise OwnerListingError("Please choose the item's condition.")
    description = _clean_block(fields.get("description"))
    if not description:
        raise OwnerListingError("Please describe the item.")
    if len(description) < MIN_DESCRIPTION:
        raise OwnerListingError(
            f"Please describe the item a little more (at least {MIN_DESCRIPTION} characters).")
    if len(description) > MAX_DESCRIPTION:
        raise OwnerListingError(f"Please keep the description under {MAX_DESCRIPTION} characters.")
    days = fields.get("max_borrow_days")
    if not isinstance(days, int) or isinstance(days, bool) or not MIN_DAYS <= days <= MAX_DAYS:
        raise OwnerListingError(
            f"The longest loan must be between {MIN_DAYS} and {MAX_DAYS} days.")
    extra = _clean_block(fields.get("extra_rules"))
    if len(extra) > MAX_EXTRA_RULES:
        raise OwnerListingError(f"Please keep the extra rules under {MAX_EXTRA_RULES} characters.")
    stock_quantity = fields.get("stock_quantity", 1)
    if (not isinstance(stock_quantity, int) or isinstance(stock_quantity, bool)
            or not 0 <= stock_quantity <= MAX_STOCK_QUANTITY):
        raise OwnerListingError(
            f"Stock quantity must be a whole number from 0 to {MAX_STOCK_QUANTITY}.")
    return {"title": title, "category": category, "condition": condition,
            "description": description, "max_borrow_days": days, "extra_rules": extra,
            "stock_quantity": stock_quantity}


# A listing together with its optional subcategory name (the link table may have no row).
_LISTING_SELECT = (
    "SELECT l.*, sc.name AS subcategory_name, "
    "(SELECT COUNT(*) FROM owner_listing_copies c WHERE c.listing_id = l.listing_id "
    "AND c.state = 'available') AS available_copies FROM owner_listings l "
    "LEFT JOIN listing_category_links k ON k.listing_id = l.listing_id "
    "LEFT JOIN listing_categories sc ON sc.category_id = k.subcategory_id ")


def _row(row) -> OwnerListing:
    keys = row.keys()
    status = row["status"]
    if "deleted_at" in keys and row["deleted_at"]:
        status = STATUS_DELETED
    elif ("paused_at" in keys and row["paused_at"]
          and status == STATUS_PUBLISHED):
        status = STATUS_PAUSED
    return OwnerListing(
        row["listing_id"], row["owner_student_id"], row["title"], row["category"],
        row["description"], row["condition"], row["max_borrow_days"], row["extra_rules"],
        status, row["created_at"], row["updated_at"],
        (row["subcategory_name"] or "") if "subcategory_name" in keys else "",
        row["stock_quantity"] if "stock_quantity" in keys else 1,
        row["available_copies"] if "available_copies" in keys
        else row["stock_quantity"] if "stock_quantity" in keys else 1)


def _add_stock_copies(conn, listing_id: str, owner_student_id: int, quantity: int, now: str):
    conn.executemany(
        "INSERT INTO owner_listing_copies "
        "(copy_id, listing_id, owner_student_id, state, request_id, created_at, updated_at) "
        "VALUES (?, ?, ?, 'available', NULL, ?, ?)",
        [("OC-" + secrets.token_hex(16).upper(), listing_id, owner_student_id, now, now)
         for _ in range(quantity)])


def _sync_stock_copies(conn, listing_id: str, owner_student_id: int,
                       current_quantity: int, new_quantity: int, now: str):
    """Resize only uncommitted physical copies, preserving every allocated copy row."""
    counts = conn.execute(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN state IN ('reserved', 'loaned') THEN 1 ELSE 0 END) AS committed "
        "FROM owner_listing_copies WHERE listing_id = ?", (listing_id,)).fetchone()
    total = counts["total"]
    committed = counts["committed"] or 0
    if total != current_quantity:
        raise OwnerListingError(
            "The saved stock records are inconsistent. Your changes were not saved.")
    if new_quantity < committed:
        raise OwnerListingError(
            f"Stock quantity cannot be less than the {committed} copies committed "
            "to active loans or reservations.")
    difference = new_quantity - current_quantity
    if difference > 0:
        _add_stock_copies(conn, listing_id, owner_student_id, difference, now)
    elif difference < 0:
        removed = conn.execute(
            "DELETE FROM owner_listing_copies WHERE copy_id IN ("
            "SELECT copy_id FROM owner_listing_copies WHERE listing_id = ? "
            "AND state = 'available' ORDER BY created_at DESC, copy_id DESC LIMIT ?)",
            (listing_id, -difference)).rowcount
        if removed != -difference:
            raise OwnerListingError(
                "Stock quantity cannot be reduced below copies committed to active "
                "loans or reservations.")


def _write_category_link(conn, listing_id: str, category_id: int, subcategory_id):
    conn.execute(
        "INSERT INTO listing_category_links (listing_id, category_id, subcategory_id) "
        "VALUES (?, ?, ?) ON CONFLICT (listing_id) DO UPDATE SET "
        "category_id = excluded.category_id, subcategory_id = excluded.subcategory_id",
        (listing_id, category_id, subcategory_id))


def _schedule(availability) -> AvailabilitySchedule:
    try:
        return AvailabilitySchedule.from_dict(availability)
    except AvailabilityError as exc:
        raise OwnerListingError(str(exc)) from None


def _write_slots(conn, listing_id: str, schedule: AvailabilitySchedule):
    """Replace this listing's saved windows with `schedule` (inside the caller's transaction)."""
    conn.execute("DELETE FROM listing_availability WHERE listing_id = ?", (listing_id,))
    for weekday, windows in schedule.days:
        for start, end in windows:
            conn.execute(
                "INSERT INTO listing_availability (listing_id, weekday, start_minute, "
                "end_minute) VALUES (?, ?, ?, ?)", (listing_id, weekday, start, end))


def _schedules_from_rows(rows) -> dict:
    grouped = {}
    for row in rows:
        grouped.setdefault(row["listing_id"], {}).setdefault(row["weekday"], []).append(
            (row["start_minute"], row["end_minute"]))
    return {listing_id: AvailabilitySchedule.from_dict(days)
            for listing_id, days in grouped.items()}


class OwnerListingService:
    def __init__(self, db_path=None, workspace_service=None, categories=None):
        self._db_path = db_path if db_path is not None else default_db_path()
        self._workspaces = workspace_service
        if categories is None:
            self._registry = CategoryService(self._db_path, workspace_service)
        else:
            self._registry = None  # an explicit list: the old fixed-category behaviour
        self._categories = tuple(categories) if categories is not None else None

    @property
    def category_service(self):
        """The shared category registry (None when a fixed category list was given)."""
        return self._registry

    @property
    def categories(self) -> tuple:
        """The general category names a listing can use right now (fresh from the registry)."""
        if self._registry is None:
            return self._categories
        try:
            return tuple(c.name for c in self._registry.general_categories())
        except CategoryError:
            return ()

    def _prepare(self, fields: dict):
        """Validate the form fields -> (clean data, category id, subcategory id or None)."""
        if self._registry is None:
            return validate_fields(fields, self._categories), None, None
        fields = dict(fields)
        try:
            category, sub = self._registry.resolve(fields.get("category"),
                                                   fields.get("subcategory"))
        except CategoryError as exc:
            if str(fields.get("category") or "").strip():
                # The category text was given but is unknown, or the subcategory is wrong.
                raise OwnerListingError(str(exc)) from None
            category, sub = None, None
        # Titles etc. are checked first, in the same order as before ("Please choose a category.")
        names = [category.name] if category is not None else []
        fields["category"] = category.name if category is not None else ""
        data = validate_fields(fields, names)
        return data, category.category_id, (sub.category_id if sub is not None else None)

    # ---------- access ----------
    def _require_owner(self, student_id):
        if (not isinstance(student_id, int) or isinstance(student_id, bool)
                or self._workspaces is None
                or not self._workspaces.can_use(student_id, WORKSPACE_STUDENT_OWNER)):
            raise OwnerListingError(NOT_ALLOWED)

    def can_manage(self, student_id) -> bool:
        try:
            self._require_owner(student_id)
        except OwnerListingError:
            return False
        return True

    def _open(self):
        try:
            return connect(self._db_path)
        except DatabaseError:
            raise OwnerListingError(
                "Could not open the local database. Nothing was changed.") from None

    # ---------- reading ----------
    def list_drafts(self, student_id: int) -> list:
        """This owner's drafts, most recently edited first."""
        self._require_owner(student_id)
        conn = self._open()
        try:
            rows = conn.execute(
                _LISTING_SELECT + "WHERE l.owner_student_id = ? AND l.status = ? "
                "AND l.deleted_at IS NULL "
                "ORDER BY l.updated_at DESC, l.rowid DESC", (student_id, STATUS_DRAFT)).fetchall()
        except sqlite3.Error:
            raise OwnerListingError("Could not load your listings.") from None
        finally:
            conn.close()
        return [_row(r) for r in rows]

    def list_listings(self, student_id: int) -> list:
        """This owner's listings, including drafts and published listings."""
        self._require_owner(student_id)
        conn = self._open()
        try:
            rows = conn.execute(
                _LISTING_SELECT + "WHERE l.owner_student_id = ? "
                "AND l.status IN (?, ?) AND l.deleted_at IS NULL "
                "ORDER BY l.updated_at DESC, l.rowid DESC",
                (student_id, STATUS_DRAFT, STATUS_PUBLISHED)).fetchall()
        except sqlite3.Error:
            raise OwnerListingError("Could not load your listings.") from None
        finally:
            conn.close()
        return [_row(r) for r in rows]

    def list_published_catalog(self) -> list[PublishedCatalogListing]:
        """Published listings and their saved owner/schedule, for the student Catalog."""
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT l.*, sc.name AS subcategory_name, s.full_name AS owner_name, "
                "(SELECT COUNT(*) FROM owner_listing_copies c "
                "WHERE c.listing_id = l.listing_id AND c.state = 'available') "
                "AS available_copies "
                "FROM owner_listings l "
                "JOIN students s ON s.id = l.owner_student_id "
                "LEFT JOIN listing_category_links k ON k.listing_id = l.listing_id "
                "LEFT JOIN listing_categories sc ON sc.category_id = k.subcategory_id "
                "WHERE l.status = ? AND l.paused_at IS NULL AND l.deleted_at IS NULL "
                "ORDER BY l.updated_at DESC, l.rowid DESC",
                (STATUS_PUBLISHED,)).fetchall()
            listing_ids = [row["listing_id"] for row in rows]
            schedules = {}
            if listing_ids:
                placeholders = ",".join("?" for _ in listing_ids)
                availability_rows = conn.execute(
                    "SELECT listing_id, weekday, start_minute, end_minute "
                    f"FROM listing_availability WHERE listing_id IN ({placeholders}) "
                    "ORDER BY listing_id, weekday, start_minute",
                    listing_ids).fetchall()
                schedules = _schedules_from_rows(availability_rows)
        except sqlite3.Error:
            raise OwnerListingError("Could not load published listings.") from None
        finally:
            conn.close()
        return [
            PublishedCatalogListing(
                _row(row), row["owner_name"],
                schedules.get(row["listing_id"], AvailabilitySchedule.empty()))
            for row in rows
        ]

    def get(self, student_id: int, listing_id: str) -> OwnerListing:
        self._require_owner(student_id)
        conn = self._open()
        try:
            row = conn.execute(
                _LISTING_SELECT + "WHERE l.listing_id = ? AND l.owner_student_id = ? "
                "AND l.deleted_at IS NULL",
                (listing_id, student_id)).fetchone()
        except sqlite3.Error:
            raise OwnerListingError("Could not load this listing.") from None
        finally:
            conn.close()
        if row is None:
            raise OwnerListingError("That listing was not found.")
        return _row(row)

    # ---------- writing ----------
    def create_draft(self, student_id: int, fields: dict, availability=None) -> OwnerListing:
        """Save a new draft. `availability` ({weekday: [(start, end), ...]}) is optional and is
        saved together with it: either both are saved or neither."""
        self._require_owner(student_id)
        data, category_id, subcategory_id = self._prepare(fields)
        schedule = _schedule(availability)
        conn = self._open()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
            for _ in range(5):
                listing_id = "LD-" + secrets.token_hex(4).upper()
                try:
                    conn.execute(
                        "INSERT INTO owner_listings (listing_id, owner_student_id, title, "
                        "category, description, condition, max_borrow_days, extra_rules, status, "
                        "created_at, updated_at, stock_quantity) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (listing_id, student_id, data["title"], data["category"],
                         data["description"], data["condition"], data["max_borrow_days"],
                         data["extra_rules"], STATUS_DRAFT, now, now,
                         data["stock_quantity"]))
                    break
                except sqlite3.IntegrityError as exc:
                    if "listing_id" in str(exc):
                        continue
                    raise
            else:
                raise sqlite3.OperationalError("could not create a unique listing ID")
            _add_stock_copies(
                conn, listing_id, student_id, data["stock_quantity"], now)
            _write_slots(conn, listing_id, schedule)
            if category_id is not None:
                _write_category_link(conn, listing_id, category_id, subcategory_id)
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            raise OwnerListingError("You already have a listing with this name.") from None
        except sqlite3.Error:
            conn.rollback()
            raise OwnerListingError("Something went wrong, so your draft was not saved.") from None
        finally:
            conn.close()
        return self.get(student_id, listing_id)

    def publish(self, student_id: int, listing_id: str,
                photos_dir: str | Path | None = None) -> OwnerListing:
        """Publish a complete draft belonging to this approved owner."""
        self._require_owner(student_id)
        conn = self._open()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                _LISTING_SELECT + "WHERE l.listing_id = ? AND l.owner_student_id = ?",
                (listing_id, student_id)).fetchone()
            if row is None:
                raise OwnerListingError("That listing was not found.")
            if row["status"] != STATUS_DRAFT:
                raise OwnerListingError("Only draft listings can be published.")
            self._validate_publish_requirements(conn, row, listing_id, photos_dir)

            cursor = conn.execute(
                "UPDATE owner_listings SET status = ?, updated_at = ? "
                "WHERE listing_id = ? AND owner_student_id = ? AND status = ?",
                (STATUS_PUBLISHED, now, listing_id, student_id, STATUS_DRAFT))
            if cursor.rowcount != 1:
                raise OwnerListingError("That draft is no longer available to publish.")
            conn.commit()
        except OwnerListingError:
            conn.rollback()
            raise
        except sqlite3.Error:
            conn.rollback()
            raise OwnerListingError("Something went wrong, so the listing was not published.") from None
        finally:
            conn.close()
        return self.get(student_id, listing_id)

    def _validate_publish_requirements(self, conn, row, listing_id, photos_dir=None):
        missing = []
        fields = {
            "title": row["title"],
            "category": row["category"],
            "subcategory": row["subcategory_name"] or "",
            "condition": row["condition"],
            "description": row["description"],
            "max_borrow_days": row["max_borrow_days"],
            "extra_rules": row["extra_rules"],
        }
        try:
            self._prepare(fields)
        except OwnerListingError as exc:
            missing.append(str(exc))

        slots = conn.execute(
            "SELECT 1 FROM listing_availability WHERE listing_id = ? LIMIT 1",
            (listing_id,)).fetchone()
        if slots is None:
            missing.append("Set at least one pickup day and time.")

        photo_rows = conn.execute(
            "SELECT file_path FROM listing_photos WHERE listing_key = ?",
            (listing_id,)).fetchall()
        photo_service = PhotoService(
            self._db_path, photos_dir or Path(self._db_path).parent / "photos")
        usable_photos = sum(
            PhotoService.is_usable(photo_service.resolve(photo["file_path"]))
            for photo in photo_rows)
        if usable_photos < 1:
            missing.append("Add at least one usable listing photo.")
        if missing:
            raise OwnerListingError("Cannot publish yet: " + " ".join(missing))

    def pause_listing(self, student_id: int, listing_id: str) -> OwnerListing:
        """Hide this owner's published listing from the Catalog without changing its data."""
        self._require_owner(student_id)
        conn = self._open()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "UPDATE owner_listings SET paused_at = ?, updated_at = ? "
                "WHERE listing_id = ? AND owner_student_id = ? AND status = ? "
                "AND paused_at IS NULL AND deleted_at IS NULL",
                (now, now, listing_id, student_id, STATUS_PUBLISHED))
            if cursor.rowcount != 1:
                conn.rollback()
                raise OwnerListingError("Only your published listings can be paused.")
            conn.commit()
        except OwnerListingError:
            conn.rollback()
            raise
        except sqlite3.Error:
            conn.rollback()
            raise OwnerListingError("Something went wrong, so the listing was not paused.") from None
        finally:
            conn.close()
        return self.get(student_id, listing_id)

    def resume_listing(self, student_id: int, listing_id: str,
                       photos_dir: str | Path | None = None) -> OwnerListing:
        """Validate and republish this owner's paused listing."""
        self._require_owner(student_id)
        conn = self._open()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                _LISTING_SELECT + "WHERE l.listing_id = ? AND l.owner_student_id = ? "
                "AND l.status = ? AND l.paused_at IS NOT NULL AND l.deleted_at IS NULL",
                (listing_id, student_id, STATUS_PUBLISHED)).fetchone()
            if row is None:
                raise OwnerListingError("That paused listing was not found.")
            self._validate_publish_requirements(conn, row, listing_id, photos_dir)
            cursor = conn.execute(
                "UPDATE owner_listings SET paused_at = NULL, updated_at = ? "
                "WHERE listing_id = ? AND owner_student_id = ? AND status = ? "
                "AND paused_at IS NOT NULL AND deleted_at IS NULL",
                (now, listing_id, student_id, STATUS_PUBLISHED))
            if cursor.rowcount != 1:
                raise OwnerListingError("That paused listing is no longer available.")
            conn.commit()
        except OwnerListingError:
            conn.rollback()
            raise
        except sqlite3.Error:
            conn.rollback()
            raise OwnerListingError("Something went wrong, so the listing was not resumed.") from None
        finally:
            conn.close()
        return self.get(student_id, listing_id)

    def delete_listing(self, student_id: int, listing_id: str):
        """Soft-delete this owner's listing, retaining photos and history for references."""
        self._require_owner(student_id)
        conn = self._open()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT l.title, s.full_name FROM owner_listings l "
                "JOIN students s ON s.id = l.owner_student_id "
                "WHERE l.listing_id = ? AND l.owner_student_id = ? AND l.deleted_at IS NULL",
                (listing_id, student_id)).fetchone()
            if row is None:
                raise OwnerListingError("That listing was not found.")
            placeholders = ",".join("?" for _ in ACTIVE_LISTING_REQUEST_STATUSES)
            # New requests use the stable listing ID; older snapshot-only records use
            # a conservative owner match because their original listing cannot be known.
            active = conn.execute(
                "SELECT request_id FROM borrow_requests "
                f"WHERE status IN ({placeholders}) AND (owner_listing_id = ? OR "
                "(owner_listing_id IS NULL AND item_ownership = 'student' "
                "AND (item_creator = ? OR item_owner_note = ?))) LIMIT 1",
                (*ACTIVE_LISTING_REQUEST_STATUSES, listing_id, row["full_name"],
                 f"Shared by {row['full_name']}")).fetchone()
            if active is not None:
                raise OwnerListingError(
                    "This listing cannot be deleted while active requests, reservations, "
                    "or loans may refer to it.")
            cursor = conn.execute(
                "UPDATE owner_listings SET deleted_at = ?, updated_at = ? "
                "WHERE listing_id = ? AND owner_student_id = ? AND deleted_at IS NULL",
                (now, now, listing_id, student_id))
            if cursor.rowcount != 1:
                raise OwnerListingError("That listing is no longer available.")
            conn.commit()
        except OwnerListingError:
            conn.rollback()
            raise
        except sqlite3.Error:
            conn.rollback()
            raise OwnerListingError("Something went wrong, so the listing was not deleted.") from None
        finally:
            conn.close()

    def update_draft(self, student_id: int, listing_id: str, fields: dict,
                     availability=None) -> OwnerListing:
        """Edit one of THIS owner's drafts. Other owners' listings and non-drafts are refused.

        `availability=None` leaves the saved schedule untouched; a dict (even an empty one)
        replaces it, in the same transaction as the other changes."""
        return self._update_listing(
            student_id, listing_id, fields, availability, STATUS_DRAFT, "draft")

    def update_published(self, student_id: int, listing_id: str, fields: dict,
                         availability=None) -> OwnerListing:
        """Edit one of THIS owner's published listings without changing its status or ID.

        `availability=None` leaves the saved schedule untouched; a dict (even an empty one)
        replaces it, in the same transaction as the other changes."""
        return self._update_listing(
            student_id, listing_id, fields, availability, STATUS_PUBLISHED, "published listing")

    def _update_listing(self, student_id: int, listing_id: str, fields: dict,
                        availability, required_status: str, listing_kind: str) -> OwnerListing:
        self._require_owner(student_id)
        data, category_id, subcategory_id = self._prepare(fields)
        schedule = None if availability is None else _schedule(availability)
        conn = self._open()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT stock_quantity FROM owner_listings "
                "WHERE listing_id = ? AND owner_student_id = ? AND status = ? "
                "AND deleted_at IS NULL",
                (listing_id, student_id, required_status)).fetchone()
            if existing is None:
                raise OwnerListingError(f"That {listing_kind} was not found.")
            if "stock_quantity" not in fields:
                data["stock_quantity"] = existing["stock_quantity"]
            cursor = conn.execute(
                "UPDATE owner_listings SET title = ?, category = ?, description = ?, "
                "condition = ?, max_borrow_days = ?, extra_rules = ?, stock_quantity = ?, "
                "updated_at = ? "
                "WHERE listing_id = ? AND owner_student_id = ? AND status = ? "
                "AND deleted_at IS NULL",
                (data["title"], data["category"], data["description"], data["condition"],
                 data["max_borrow_days"], data["extra_rules"], data["stock_quantity"],
                 now, listing_id, student_id, required_status))
            if cursor.rowcount != 1:
                conn.rollback()
                raise OwnerListingError(f"That {listing_kind} was not found.")
            _sync_stock_copies(
                conn, listing_id, student_id, existing["stock_quantity"],
                data["stock_quantity"], now)
            if schedule is not None:
                _write_slots(conn, listing_id, schedule)
            if category_id is not None:
                _write_category_link(conn, listing_id, category_id, subcategory_id)
            conn.commit()
        except OwnerListingError:
            conn.rollback()
            raise
        except sqlite3.IntegrityError:
            conn.rollback()
            raise OwnerListingError("You already have a listing with this name.") from None
        except sqlite3.Error:
            conn.rollback()
            raise OwnerListingError("Something went wrong, so your changes were not saved.") from None
        finally:
            conn.close()
        return self.get(student_id, listing_id)

    # ---------- Step 31C: availability ----------
    def get_availability(self, student_id: int, listing_id: str) -> AvailabilitySchedule:
        """The saved pickup schedule of one of THIS owner's listings (empty if none set)."""
        self.get(student_id, listing_id)   # owner + ownership check
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT listing_id, weekday, start_minute, end_minute FROM listing_availability "
                "WHERE listing_id = ? ORDER BY weekday, start_minute", (listing_id,)).fetchall()
        except sqlite3.Error:
            raise OwnerListingError("Could not load the availability schedule.") from None
        finally:
            conn.close()
        return _schedules_from_rows(rows).get(listing_id, AvailabilitySchedule.empty())

    def availability_for_all(self, student_id: int) -> dict:
        """{listing_id: AvailabilitySchedule} for every listing of THIS owner (for My Listings)."""
        self._require_owner(student_id)
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT a.listing_id, a.weekday, a.start_minute, a.end_minute "
                "FROM listing_availability a JOIN owner_listings l ON l.listing_id = a.listing_id "
                "WHERE l.owner_student_id = ? ORDER BY a.listing_id, a.weekday, a.start_minute",
                (student_id,)).fetchall()
        except sqlite3.Error:
            raise OwnerListingError("Could not load the availability schedules.") from None
        finally:
            conn.close()
        return _schedules_from_rows(rows)

    def save_availability(self, student_id: int, listing_id: str,
                          availability) -> AvailabilitySchedule:
        """Replace the pickup schedule of one of THIS owner's listings, at any time.
        An empty schedule clears it. Returns the saved schedule."""
        self._require_owner(student_id)
        schedule = _schedule(availability)
        conn = self._open()
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                "UPDATE owner_listings SET updated_at = ? "
                "WHERE listing_id = ? AND owner_student_id = ?", (now, listing_id, student_id))
            if cursor.rowcount != 1:
                conn.rollback()
                raise OwnerListingError("That listing was not found.")
            _write_slots(conn, listing_id, schedule)
            conn.commit()
        except OwnerListingError:
            raise
        except sqlite3.Error:
            conn.rollback()
            raise OwnerListingError(
                "Something went wrong, so the schedule was not saved.") from None
        finally:
            conn.close()
        return schedule
