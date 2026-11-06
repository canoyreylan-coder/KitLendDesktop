"""The shared listing-category registry (Step 31D). No Qt in this file.

ONE table (`listing_categories`) in the shared database holds every category, so a category an
owner creates is available to every owner using the same database the moment it is saved.
Nothing is cached: every read asks the database.

Two levels only: a general category (Books) and optional subcategories (Fantasy under Books).

Names
  * Duplicates are detected ignoring capitalization and extra spaces ("study  GEAR" is "Study
    Gear"). A duplicate is never created; the existing category is offered instead.
  * SIMILAR names ("Book" vs "Books", "Math" vs "Mathematics", "StudyGear") are not blocked,
    but creation needs an explicit OK (confirm_similar=True) after the owner has been shown
    the existing categories.
  * The database itself also refuses duplicates (unique indexes), e.g. when two owners create
    the same category at the same moment: the second one simply gets the existing category.

Only an APPROVED Student Owner can create categories (WorkspaceService is asked on every call).
Categories cannot be renamed or deleted in this step.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.database import DatabaseError, connect, default_db_path
from app.workspace_service import WORKSPACE_STUDENT_OWNER

MIN_NAME, MAX_NAME = 2, 40
SIMILAR_THRESHOLD = 0.8
MAX_SIMILAR = 5
NOT_ALLOWED = "Only approved Student Owners can create categories."

STATUS_EMPTY = "empty"
STATUS_TOO_SHORT = "too_short"
STATUS_TOO_LONG = "too_long"
STATUS_INVALID = "invalid"
STATUS_EXISTS = "exists"
STATUS_SIMILAR = "similar"
STATUS_OK = "ok"


class CategoryError(Exception):
    """A category problem; str(error) is safe to show to the student."""

    is_user_facing = True


class CategoryExistsError(CategoryError):
    """That name is already taken (ignoring case and spaces). `.category` is the existing one."""

    def __init__(self, category):
        super().__init__(f"“{category.name}” already exists. Please use it instead.")
        self.category = category


class SimilarCategoryError(CategoryError):
    """Similar names exist; creating needs confirm_similar=True. `.similar` lists them."""

    def __init__(self, similar):
        names = ", ".join(c.name for c in similar)
        super().__init__(f"Similar categories already exist: {names}. "
                         "Please use one of them, or confirm to create a new one.")
        self.similar = tuple(similar)


@dataclass(frozen=True)
class Category:
    category_id: int
    parent_id: int | None
    name: str
    is_builtin: bool = False

    @property
    def is_general(self) -> bool:
        return self.parent_id is None


@dataclass(frozen=True)
class CategoryCheck:
    """What typing `name` would do: status is one of the STATUS_* values."""
    status: str
    name: str = ""
    existing: Category | None = None
    similar: tuple = ()


def clean_name(raw) -> str:
    """Tidy spaces: trims the ends and turns any run of spaces/tabs into one space."""
    return " ".join(str(raw or "").split())


def name_key(raw) -> str:
    """Case- and space-insensitive identity of a name (what 'duplicate' means)."""
    return clean_name(raw).casefold()


def _canonical(raw) -> str:
    return "".join(ch for ch in clean_name(raw).casefold() if ch.isalnum())


def similarity(a, b) -> float:
    """0..1 - how alike two names look (ignores case, spaces and punctuation)."""
    ca, cb = _canonical(a), _canonical(b)
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    if min(len(ca), len(cb)) >= 4 and (ca in cb or cb in ca):
        return 0.9  # "Math" inside "Mathematics"
    return SequenceMatcher(None, ca, cb).ratio()


def _category(row) -> Category:
    return Category(row["category_id"], row["parent_id"], row["name"], bool(row["is_builtin"]))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CategoryService:
    def __init__(self, db_path=None, workspace_service=None):
        self._db_path = db_path if db_path is not None else default_db_path()
        self._workspaces = workspace_service

    def _open(self):
        try:
            return connect(self._db_path)
        except DatabaseError:
            raise CategoryError("Could not open the local database. Nothing was changed.") from None

    # ---------- reading (open to everyone; always fresh from the database) ----------
    def _select(self, where: str, params=()) -> list:
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT category_id, parent_id, name, is_builtin FROM listing_categories "
                f"WHERE {where} ORDER BY name_key, category_id", params).fetchall()
        except sqlite3.Error:
            raise CategoryError("Could not load the categories.") from None
        finally:
            conn.close()
        return [_category(r) for r in rows]

    def general_categories(self) -> list:
        return self._select("parent_id IS NULL")

    def subcategories(self, parent_id: int) -> list:
        return self._select("parent_id = ?", (parent_id,))

    def get(self, category_id: int):
        found = self._select("category_id = ?", (category_id,))
        return found[0] if found else None

    def find(self, name: str, parent_id=None):
        """The category with this name (ignoring case/spaces) at that level, or None."""
        key = name_key(name)
        if not key:
            return None
        if parent_id is None:
            found = self._select("parent_id IS NULL AND name_key = ?", (key,))
        else:
            found = self._select("parent_id = ? AND name_key = ?", (parent_id, key))
        return found[0] if found else None

    def similar_to(self, name: str, parent_id=None) -> list:
        """Existing categories at the same level that look like `name` (best match first).
        An exact duplicate is not 'similar'; it is reported by find()."""
        key = name_key(name)
        siblings = (self.general_categories() if parent_id is None
                    else self.subcategories(parent_id))
        scored = [(similarity(name, c.name), c) for c in siblings if name_key(c.name) != key]
        scored = [(score, c) for score, c in scored if score >= SIMILAR_THRESHOLD]
        scored.sort(key=lambda pair: (-pair[0], pair[1].name.casefold()))
        return [c for _score, c in scored[:MAX_SIMILAR]]

    def check_name(self, raw, parent_id=None) -> CategoryCheck:
        """What would happen if this name were entered now (used for live feedback)."""
        name = clean_name(raw)
        if not name:
            return CategoryCheck(STATUS_EMPTY)
        if len(name) < MIN_NAME:
            return CategoryCheck(STATUS_TOO_SHORT, name)
        if len(name) > MAX_NAME:
            return CategoryCheck(STATUS_TOO_LONG, name)
        if not any(ch.isalnum() for ch in name):
            return CategoryCheck(STATUS_INVALID, name)
        existing = self.find(name, parent_id)
        if existing is not None:
            return CategoryCheck(STATUS_EXISTS, name, existing=existing)
        similar = self.similar_to(name, parent_id)
        if similar:
            return CategoryCheck(STATUS_SIMILAR, name, similar=tuple(similar))
        return CategoryCheck(STATUS_OK, name)

    # ---------- creating (approved Student Owners only) ----------
    def _require_owner(self, student_id):
        if (not isinstance(student_id, int) or isinstance(student_id, bool)
                or self._workspaces is None
                or not self._workspaces.can_use(student_id, WORKSPACE_STUDENT_OWNER)):
            raise CategoryError(NOT_ALLOWED)

    def create(self, student_id: int, raw_name, parent_id=None, confirm_similar=False) -> Category:
        """Add a general category (parent_id None) or a subcategory of a general one.

        Raises CategoryExistsError for a duplicate and SimilarCategoryError when similar names
        exist and `confirm_similar` is False. Anything else wrong raises CategoryError."""
        self._require_owner(student_id)
        if parent_id is not None:
            parent = self.get(parent_id)
            if parent is None or not parent.is_general:
                raise CategoryError("Please choose a general category first.")
        check = self.check_name(raw_name, parent_id)
        messages = {
            STATUS_EMPTY: "Please enter a category name.",
            STATUS_TOO_SHORT: f"The name needs at least {MIN_NAME} characters.",
            STATUS_TOO_LONG: f"Please keep the name under {MAX_NAME + 1} characters.",
            STATUS_INVALID: "The name needs at least one letter or number.",
        }
        if check.status in messages:
            raise CategoryError(messages[check.status])
        if check.status == STATUS_EXISTS:
            raise CategoryExistsError(check.existing)
        if check.status == STATUS_SIMILAR and not confirm_similar:
            raise SimilarCategoryError(check.similar)

        name = check.name
        conn = self._open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Look again inside the write lock: another owner may have just created it.
            clash = conn.execute(
                "SELECT category_id, parent_id, name, is_builtin FROM listing_categories "
                "WHERE name_key = ? AND "
                + ("parent_id IS NULL" if parent_id is None else "parent_id = ?"),
                (name_key(name),) if parent_id is None else (name_key(name), parent_id)).fetchone()
            if clash is not None:
                conn.rollback()
                raise CategoryExistsError(_category(clash))
            cursor = conn.execute(
                "INSERT INTO listing_categories (parent_id, name, name_key, is_builtin, "
                "created_by, created_at) VALUES (?, ?, ?, 0, ?, ?)",
                (parent_id, name, name_key(name), student_id, _now()))
            category = Category(cursor.lastrowid, parent_id, name, False)
            conn.commit()
        except CategoryExistsError:
            raise
        except sqlite3.IntegrityError:
            conn.rollback()
            existing = self.find(name, parent_id)
            if existing is not None:
                raise CategoryExistsError(existing) from None
            raise CategoryError("Something went wrong, so the category was not created.") from None
        except sqlite3.Error:
            conn.rollback()
            raise CategoryError("Something went wrong, so the category was not created.") from None
        finally:
            conn.close()
        return category

    # ---------- used by the listing service ----------
    def resolve(self, category_name, subcategory_name=None):
        """(general category, subcategory or None) for names chosen in the form, or CategoryError.
        Names match ignoring case and extra spaces."""
        category = self.find(category_name)
        if category is None:
            raise CategoryError("Please choose a category.")
        if not clean_name(subcategory_name):
            return category, None
        sub = self.find(subcategory_name, category.category_id)
        if sub is None:
            raise CategoryError("Please choose a subcategory from the list.")
        return category, sub


class OwnerCategoryAccess:
    """What the Add/Edit Listing form needs, bound to ONE signed-in owner (plain names in,
    plain names out, so the form never touches the database or the service directly)."""

    def __init__(self, service: CategoryService, student_id: int):
        self._service = service
        self._student_id = student_id

    def _parent_id(self, parent_name):
        if not parent_name:
            return None
        parent = self._service.find(parent_name)
        if parent is None:
            raise CategoryError("Please choose a general category first.")
        return parent.category_id

    def top_names(self) -> list:
        return [c.name for c in self._service.general_categories()]

    def sub_names(self, category_name) -> list:
        parent = self._service.find(category_name) if category_name else None
        return [c.name for c in self._service.subcategories(parent.category_id)] if parent else []

    def check(self, name, parent_name=None) -> CategoryCheck:
        """A CategoryCheck whose `existing` is a name and `similar` is a tuple of names."""
        result = self._service.check_name(name, self._parent_id(parent_name))
        return CategoryCheck(
            result.status, result.name,
            result.existing.name if result.existing else None,
            tuple(c.name for c in result.similar))

    def create(self, name, parent_name=None, confirm_similar=False) -> str:
        """Create it and return its name. Raises CategoryExistsError / SimilarCategoryError /
        CategoryError (all with messages that are safe to show)."""
        return self._service.create(
            self._student_id, name, self._parent_id(parent_name), confirm_similar).name
