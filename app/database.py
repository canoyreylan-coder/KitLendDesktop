"""Local SQLite storage (TEMPORARY development storage).

KitLend will eventually use a central backend so many computers can share data.
Until then, accounts live in a per-user SQLite file stored OUTSIDE the project
folder, in the operating system's application-data directory.
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_FOLDER_NAME = "KitLend"
DB_FILE_NAME = "kitlend_local.db"


class DatabaseError(Exception):
    """Raised when the local database cannot be opened or used."""


def get_app_data_dir() -> Path:
    """Return a persistent, user-writable folder (created if missing)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    path = Path(base) / APP_FOLDER_NAME
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DatabaseError(f"Cannot create application data folder: {exc}") from exc
    return path


def default_db_path() -> Path:
    return get_app_data_dir() / DB_FILE_NAME


SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    iterations    INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);
"""


# ----------------------------------------------------------------------
# Additive migrations (Step 8C, extended in Steps 11, 12, 13 and 14F)
# ----------------------------------------------------------------------
# Rules that keep existing accounts safe:
#   * A migration may add defaulted/nullable columns and CREATE new tables/indexes.
#   * Existing records are never dropped, renamed or replaced - `students` is never touched.
#   * Each migration runs in ONE transaction and is recorded in
#     `schema_migrations`, so it is applied once and a failure changes nothing.
#   * Before the first new migration touches a database that already holds
#     accounts, a one-time safety copy is saved next to it (*.before-vN.bak).
def _add_student_id_number(conn: sqlite3.Connection):
    """Step 29D: give every student an optional Student ID Number, unique when present.

    Safe to repeat: the column is added only if it is missing and the index only if it does not
    exist. Existing rows keep NULL ("not added yet"); no account, password or other data changes.
    Uniqueness ignores upper/lower case and never assumes any ID format.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(students)")}
    if "student_id_number" not in columns:
        conn.execute("ALTER TABLE students ADD COLUMN student_id_number TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_students_student_id_number "
        "ON students (student_id_number COLLATE NOCASE) WHERE student_id_number IS NOT NULL")


MIGRATIONS = [
    # (version, name, [statements])
    (1, "baseline: students table", []),  # created by SCHEMA above; only recorded
    (2, "borrow requests and their status history", [
        """
        CREATE TABLE IF NOT EXISTS borrow_requests (
            request_id             TEXT PRIMARY KEY,
            student_id             INTEGER NOT NULL REFERENCES students(id),
            submission_key         TEXT NOT NULL,
            batch_position         INTEGER NOT NULL,
            item_title             TEXT NOT NULL,
            item_creator           TEXT NOT NULL,
            item_category          TEXT NOT NULL,
            item_kind              TEXT NOT NULL,
            item_ownership         TEXT NOT NULL,
            item_owner_note        TEXT NOT NULL,
            item_copies_total      INTEGER NOT NULL,
            item_copies_available  INTEGER NOT NULL,
            item_collections       TEXT NOT NULL DEFAULT '[]',
            max_days               INTEGER NOT NULL,
            requested_days         INTEGER NOT NULL CHECK (requested_days >= 1),
            status                 TEXT NOT NULL,
            submitted_at           TEXT NOT NULL,
            preferred_pickup_at    TEXT NOT NULL,
            approved_at            TEXT,
            scheduled_pickup_at    TEXT,
            pickup_deadline        TEXT,
            picked_up_at           TEXT,
            status_changed_at      TEXT,
            status_note            TEXT NOT NULL DEFAULT '',
            UNIQUE (student_id, submission_key, batch_position)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_borrow_requests_student "
        "ON borrow_requests (student_id, submitted_at)",
        """
        CREATE TABLE IF NOT EXISTS borrow_request_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id  TEXT NOT NULL REFERENCES borrow_requests(request_id),
            status      TEXT NOT NULL,
            changed_at  TEXT NOT NULL,
            note        TEXT NOT NULL DEFAULT ''
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_borrow_request_history_request "
        "ON borrow_request_history (request_id, id)",
    ]),
    (3, "notifications (Step 11)", [
        # One row per event that happened to ONE student. Additive only: no existing
        # table is touched and nothing is generated for older requests.
        #   event_type  - machine-readable kind (e.g. 'request_submitted'); future
        #                 notification preferences and email reminders key off this.
        #   request_id  - the request the event is about (plain text, no foreign key,
        #                 so later notification kinds are not forced to have one).
        #   dedupe_key  - one stable key per real event; UNIQUE per student so the same
        #                 event can never be stored twice.
        #   read_at     - NULL while unread, the time it was read afterwards.
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL REFERENCES students(id),
            event_type  TEXT NOT NULL,
            title       TEXT NOT NULL,
            message     TEXT NOT NULL,
            request_id  TEXT,
            dedupe_key  TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            read_at     TEXT,
            UNIQUE (student_id, dedupe_key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_notifications_student "
        "ON notifications (student_id, created_at, id)",
    ]),
    (4, "notification preferences (Step 12)", [
        # One row per (student, event type) the student has EXPLICITLY chosen.
        # No row means "never chosen", which counts as ON (the Step 11 behaviour), so
        # existing accounts keep getting notifications until they switch one off and
        # no row has to be written for them by the migration.
        #   enabled - 1 = notify me, 0 = do not create this kind of notification
        """
        CREATE TABLE IF NOT EXISTS notification_preferences (
            student_id  INTEGER NOT NULL REFERENCES students(id),
            event_type  TEXT NOT NULL,
            enabled     INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (student_id, event_type)
        )
        """,
    ]),
    (5, "student owner applications (Step 13)", [
        # One row per application. Rows are never updated or deleted by the student
        # app, so earlier applications and rejection reasons are kept for good.
        #   status      - Pending / Approved / Rejected. A new application always starts
        #                 as Pending; the student app has no way to change it later.
        #   review_note - the reviewer's reason (used for Rejected). Written only by the
        #                 future authorized review system, never by the student.
        # The partial unique index lets a student hold at most ONE Pending-or-Approved
        # application, so duplicates are impossible even if the app code had a bug.
        """
        CREATE TABLE IF NOT EXISTS student_owner_applications (
            application_id  TEXT PRIMARY KEY,
            student_id      INTEGER NOT NULL REFERENCES students(id),
            reason          TEXT NOT NULL,
            items_to_lend   TEXT NOT NULL,
            rules_agreed    INTEGER NOT NULL CHECK (rules_agreed = 1),
            rules_version   TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'Pending'
                            CHECK (status IN ('Pending', 'Approved', 'Rejected')),
            submitted_at    TEXT NOT NULL,
            reviewed_at     TEXT,
            review_note     TEXT NOT NULL DEFAULT ''
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_student_owner_applications_student "
        "ON student_owner_applications (student_id, submitted_at)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_student_owner_one_open_application "
        "ON student_owner_applications (student_id) "
        "WHERE status IN ('Pending', 'Approved')",
    ]),
    (6, "sidebar layout per student (Step 14F)", [
        # One row per student, and only for students who customised their sidebar. No row
        # means "use the default look", so the migration writes nothing for existing accounts.
        #   layout_json - sizes/positions of the sidebar icons (see app/sidebar_layout.py)
        """
        CREATE TABLE IF NOT EXISTS sidebar_layouts (
            student_id  INTEGER PRIMARY KEY REFERENCES students(id),
            layout_json TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
        """,
    ]),
    (7, "student preferences (Step 17)", [
        # Small per-student settings such as the Catalog's Grid/List view. One row per
        # (student, key) and only after the student changes something, so existing accounts
        # get no rows and keep the defaults. Authentication and borrowing tables are untouched.
        #   pref_key   - e.g. "catalog_view"
        #   pref_value - e.g. "grid" or "list" (the service validates it)
        """
        CREATE TABLE IF NOT EXISTS student_preferences (
            student_id  INTEGER NOT NULL REFERENCES students(id),
            pref_key    TEXT NOT NULL,
            pref_value  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            PRIMARY KEY (student_id, pref_key)
        )
        """,
    ]),
    (8, "listing reports (Step 19)", [
        # One row per report a student sends about a Catalog listing. Reports only ever
        # ADD information: nothing here hides, removes or changes a listing. The UNIQUE
        # pair makes a second report of the same listing by the same account impossible,
        # even if the app code had a bug. `status` is for a future review system.
        #   listing_key - stable text key of the listing (see CatalogItem.listing_key)
        #   listing_title / listing_owner - snapshot so a report stays readable later
        """
        CREATE TABLE IF NOT EXISTS listing_reports (
            report_id      TEXT PRIMARY KEY,
            student_id     INTEGER NOT NULL REFERENCES students(id),
            listing_key    TEXT NOT NULL,
            listing_title  TEXT NOT NULL,
            listing_owner  TEXT NOT NULL,
            reason         TEXT NOT NULL,
            description    TEXT NOT NULL DEFAULT '',
            status         TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open', 'Reviewed', 'Dismissed')),
            created_at     TEXT NOT NULL,
            UNIQUE (student_id, listing_key)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_listing_reports_listing "
        "ON listing_reports (listing_key)",
    ]),
    (9, "listing photo references (Step 21)", [
        # Up to 5 photo FILE REFERENCES per listing (the picture files stay on disk, never in
        # the database). Nothing is inserted by the migration: no listing has photos until a
        # future Student Owner upload feature adds them.
        #   file_path  - absolute path, or relative to the app's photos folder
        #   position   - 0..4, the display order in the gallery
        #   is_primary - at most ONE per listing (partial unique index below)
        """
        CREATE TABLE IF NOT EXISTS listing_photos (
            photo_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_key  TEXT NOT NULL,
            file_path    TEXT NOT NULL,
            position     INTEGER NOT NULL CHECK (position BETWEEN 0 AND 4),
            is_primary   INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
            added_at     TEXT NOT NULL,
            UNIQUE (listing_key, position),
            UNIQUE (listing_key, file_path)
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_listing_photos_one_primary "
        "ON listing_photos (listing_key) WHERE is_primary = 1",
    ]),
    (10, "saved My List items per student", [
        # The items a student bookmarked (the Catalog star / My List). One row per student and
        # listing, so an item can never be saved twice. Nothing is inserted by the migration.
        #   listing_key - CatalogItem.listing_key (same text identity used by reports/photos)
        """
        CREATE TABLE IF NOT EXISTS saved_items (
            student_id  INTEGER NOT NULL REFERENCES students(id),
            listing_key TEXT NOT NULL,
            saved_at    TEXT NOT NULL,
            PRIMARY KEY (student_id, listing_key)
        )
        """,
    ]),
    (11, "requests cleared from My Requests (hidden, never deleted)", [
        # "Clear History" / "Clear Cancelled" only HIDE a finished request on the My Requests
        # page. The request itself (and its history) stays in borrow_requests untouched, and
        # the other screens still see it. One row per student and request.
        """
        CREATE TABLE IF NOT EXISTS hidden_requests (
            student_id  INTEGER NOT NULL REFERENCES students(id),
            request_id  TEXT NOT NULL REFERENCES borrow_requests(request_id),
            hidden_at   TEXT NOT NULL,
            PRIMARY KEY (student_id, request_id)
        )
        """,
    ]),
    (12, "student id number (Step 29D)", [_add_student_id_number]),
    (13, "owner listing drafts (Step 31B)", [
        # One row per listing a Student Owner created. Step 31B only ever writes 'Draft'; the
        # other statuses are reserved for the later publishing step. Additive only.
        #   owner_student_id - the account that owns the listing (every query filters on it)
        #   max_borrow_days  - the borrowing rule: longest loan the owner allows
        #   extra_rules      - optional free-text rules from the owner
        # The unique index stops the same owner from keeping two listings with one name.
        """
        CREATE TABLE IF NOT EXISTS owner_listings (
            listing_id        TEXT PRIMARY KEY,
            owner_student_id  INTEGER NOT NULL REFERENCES students(id),
            title             TEXT NOT NULL,
            category          TEXT NOT NULL,
            description       TEXT NOT NULL,
            condition         TEXT NOT NULL,
            max_borrow_days   INTEGER NOT NULL CHECK (max_borrow_days >= 1),
            extra_rules       TEXT NOT NULL DEFAULT '',
            status            TEXT NOT NULL DEFAULT 'Draft'
                              CHECK (status IN ('Draft', 'Published', 'Archived')),
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_owner_listings_owner "
        "ON owner_listings (owner_student_id, updated_at)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_owner_listings_unique_title "
        "ON owner_listings (owner_student_id, lower(title))",
    ]),
    (14, "listing availability schedules (Step 31C)", [
        # When a listing's item can be collected: one row per weekday + pickup time range.
        # Additive only; nothing is inserted by the migration. The longest loan stays where
        # it already is (owner_listings.max_borrow_days). Future borrower pickup-date/time
        # validation will read these rows (see app/owner_availability.py).
        #   weekday      - 0 = Monday ... 6 = Sunday
        #   start_minute - minutes after midnight the pickup window opens (0..1439)
        #   end_minute   - minutes after midnight it closes (1..1440, after start_minute)
        # A listing may have several windows on one day; the pair below keeps them distinct.
        """
        CREATE TABLE IF NOT EXISTS listing_availability (
            slot_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id   TEXT NOT NULL REFERENCES owner_listings(listing_id),
            weekday      INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
            start_minute INTEGER NOT NULL CHECK (start_minute BETWEEN 0 AND 1439),
            end_minute   INTEGER NOT NULL CHECK (end_minute BETWEEN 1 AND 1440),
            CHECK (end_minute > start_minute),
            UNIQUE (listing_id, weekday, start_minute)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_listing_availability_listing "
        "ON listing_availability (listing_id, weekday, start_minute)",
    ]),
    (15, "shared listing categories (Step 31D)", [
        # ONE registry for the whole database, shared by every Student Owner (never per owner).
        #   parent_id  - NULL = a general category (Books); otherwise the general category this
        #                subcategory belongs to (Fantasy under Books). Only two levels.
        #   name       - how it is shown (spaces tidied, the first spelling that was entered)
        #   name_key   - lower-cased name with single spaces: "Study  GEAR" and "study gear" have
        #                the same key. The two unique indexes below make the DATABASE refuse a
        #                duplicate, even if two owners create it at the same moment.
        #   is_builtin - 1 for the categories KitLend started with
        """
        CREATE TABLE IF NOT EXISTS listing_categories (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id   INTEGER REFERENCES listing_categories(category_id),
            name        TEXT NOT NULL,
            name_key    TEXT NOT NULL CHECK (length(name_key) >= 1),
            is_builtin  INTEGER NOT NULL DEFAULT 0 CHECK (is_builtin IN (0, 1)),
            created_by  INTEGER REFERENCES students(id),
            created_at  TEXT NOT NULL,
            CHECK (parent_id IS NULL OR parent_id <> category_id)
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_general_unique "
        "ON listing_categories (name_key) WHERE parent_id IS NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_sub_unique "
        "ON listing_categories (parent_id, name_key) WHERE parent_id IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_categories_parent ON listing_categories (parent_id, name_key)",
        # Which category (and optional subcategory) a listing uses. owner_listings.category keeps
        # the general category's NAME exactly as before, so every existing listing and screen
        # keeps working; this table only adds the link and the subcategory.
        """
        CREATE TABLE IF NOT EXISTS listing_category_links (
            listing_id     TEXT PRIMARY KEY REFERENCES owner_listings(listing_id),
            category_id    INTEGER NOT NULL REFERENCES listing_categories(category_id),
            subcategory_id INTEGER REFERENCES listing_categories(category_id)
        )
        """,
        # The six categories KitLend already used (same names, so existing listings still match).
        "INSERT OR IGNORE INTO listing_categories (name, name_key, is_builtin, created_at) "
        "SELECT name, lower(name), 1, strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now') FROM ("
        "SELECT 'Mathematics' AS name UNION ALL SELECT 'Programming' UNION ALL "
        "SELECT 'Electronics' UNION ALL SELECT 'Engineering' UNION ALL SELECT 'Science' "
        "UNION ALL SELECT 'Study Gear')",
        # Any other category text an existing listing already carries is kept as a category too,
        # so no saved listing loses its category.
        "INSERT OR IGNORE INTO listing_categories (name, name_key, is_builtin, created_at) "
        "SELECT MIN(trim(category)), lower(trim(category)), 0, "
        "strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now') FROM owner_listings "
        "WHERE trim(category) <> '' GROUP BY lower(trim(category))",
        "INSERT OR IGNORE INTO listing_category_links (listing_id, category_id) "
        "SELECT l.listing_id, c.category_id FROM owner_listings l JOIN listing_categories c "
        "ON c.parent_id IS NULL AND c.name_key = lower(trim(l.category))",
    ]),
    (16, "owner listing pause and soft deletion (Step 31E-5)", [
        lambda conn: _add_owner_listing_lifecycle_columns(conn),
        "CREATE INDEX IF NOT EXISTS idx_owner_listings_lifecycle "
        "ON owner_listings (status, paused_at, deleted_at)",
    ]),
    (17, "student owner borrowing request references (Step 32A)", [
        lambda conn: _add_owner_request_columns(conn),
        "CREATE INDEX IF NOT EXISTS idx_borrow_requests_owner_listing "
        "ON borrow_requests (owner_listing_id, student_id, status)",
    ]),
    (18, "student owner listing stock quantity (Step 31E-6)", [
        lambda conn: _add_owner_listing_stock(conn),
        "CREATE INDEX IF NOT EXISTS idx_owner_listing_copies_listing_state "
        "ON owner_listing_copies (listing_id, state)",
    ]),
]


def _add_owner_listing_lifecycle_columns(conn: sqlite3.Connection):
    """Add reversible lifecycle markers without rewriting listing rows or their references."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(owner_listings)")}
    if "paused_at" not in columns:
        conn.execute("ALTER TABLE owner_listings ADD COLUMN paused_at TEXT")
    if "deleted_at" not in columns:
        conn.execute("ALTER TABLE owner_listings ADD COLUMN deleted_at TEXT")


def _add_owner_request_columns(conn: sqlite3.Connection):
    """Add stable owner/listing and photo references without rewriting old requests."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(borrow_requests)")}
    additions = (
        ("owner_listing_id", "TEXT REFERENCES owner_listings(listing_id)"),
        ("owner_student_id", "INTEGER REFERENCES students(id)"),
        ("item_photo_path", "TEXT"),
    )
    for name, definition in additions:
        if name not in columns:
            conn.execute(f"ALTER TABLE borrow_requests ADD COLUMN {name} {definition}")


def _add_owner_listing_stock(conn: sqlite3.Connection):
    """Add stock quantity and stable per-copy rows; existing listings start with one copy."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(owner_listings)")}
    if "stock_quantity" not in columns:
        conn.execute(
            "ALTER TABLE owner_listings ADD COLUMN stock_quantity "
            "INTEGER NOT NULL DEFAULT 1 CHECK (stock_quantity >= 0)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS owner_listing_copies (
            copy_id          TEXT PRIMARY KEY,
            listing_id       TEXT NOT NULL REFERENCES owner_listings(listing_id),
            owner_student_id INTEGER NOT NULL REFERENCES students(id),
            state            TEXT NOT NULL DEFAULT 'available'
                             CHECK (state IN ('available', 'reserved', 'loaned')),
            request_id       TEXT UNIQUE REFERENCES borrow_requests(request_id),
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            CHECK (
                (state = 'available' AND request_id IS NULL)
                OR (state IN ('reserved', 'loaned') AND request_id IS NOT NULL)
            )
        )
    """)
    conn.execute(
        "INSERT INTO owner_listing_copies "
        "(copy_id, listing_id, owner_student_id, state, request_id, created_at, updated_at) "
        "SELECT 'OC-' || lower(hex(randomblob(16))), l.listing_id, l.owner_student_id, "
        "'available', NULL, l.created_at, l.updated_at FROM owner_listings l "
        "WHERE NOT EXISTS (SELECT 1 FROM owner_listing_copies c "
        "WHERE c.listing_id = l.listing_id)")


_MIGRATION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


def _safety_copy(conn: sqlite3.Connection, db_path, version: int):
    """One-time backup of a database that already holds accounts (best effort)."""
    try:
        if str(db_path) == ":memory:":
            return
        has_accounts = conn.execute("SELECT 1 FROM students LIMIT 1").fetchone()
        if has_accounts is None:
            return
        backup_path = Path(f"{db_path}.before-v{version}.bak")
        if backup_path.exists():
            return
        target = sqlite3.connect(str(backup_path))
        try:
            conn.backup(target)
        finally:
            target.close()
    except (sqlite3.Error, OSError):
        pass  # the migration is purely additive, so a missing copy is not fatal


def _apply_migrations(conn: sqlite3.Connection, db_path):
    conn.execute(_MIGRATION_TABLE)
    conn.commit()
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for version, name, statements in MIGRATIONS:
        if version in applied:
            continue
        if statements:
            _safety_copy(conn, db_path, version)
        try:
            conn.execute("BEGIN IMMEDIATE")
            for statement in statements:
                if callable(statement):  # a step that needs a little Python logic
                    statement(conn)
                else:
                    conn.execute(statement)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) "
                "VALUES (?, ?, ?)",
                (version, name, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise


def connect(db_path) -> sqlite3.Connection:
    """Open a connection, make sure the schema exists, and apply pending migrations."""
    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        conn.commit()
        _apply_migrations(conn, db_path)
        return conn
    except (sqlite3.Error, OSError) as exc:
        if conn is not None:
            conn.close()
        raise DatabaseError(f"Cannot open the local database: {exc}") from exc
