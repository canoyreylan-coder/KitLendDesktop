"""Step 31D tests: the shared listing-category registry and category choice in Add/Edit Listing.

Groups 1-3 need no window (real SQLite files in temporary folders). Group 4 uses Qt's invisible
"offscreen" mode and is skipped when PySide6 is missing.
Run:  python -m unittest discover -s tests -p "test_listing_categories.py" -v
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import database  # noqa: E402
from app.auth_service import AuthService  # noqa: E402
from app.listing_category_service import (  # noqa: E402
    CategoryError, CategoryExistsError, CategoryService, OwnerCategoryAccess,
    STATUS_EMPTY, STATUS_EXISTS, STATUS_OK, STATUS_SIMILAR, STATUS_TOO_LONG, STATUS_TOO_SHORT,
    SimilarCategoryError, clean_name, name_key, similarity)
from app.owner_listing_service import OwnerListingError, OwnerListingService  # noqa: E402
from app.student_owner_service import StudentOwnerService  # noqa: E402
from app.workspace_service import WorkspaceService  # noqa: E402

try:
    import PySide6
    from PySide6.QtWidgets import QApplication
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False

PW = "correct horse"
BUILTIN = ["Electronics", "Engineering", "Mathematics", "Programming", "Science", "Study Gear"]


def good(**changes):
    fields = {"title": "Casio fx-991EX Calculator", "category": "Mathematics",
              "condition": "Good", "description": "Scientific calculator with a cover.",
              "max_borrow_days": 2, "extra_rules": ""}
    fields.update(changes)
    return fields


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-A1")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-B2")
        self.cai = self.auth.register("Cai Dela", "cai@csucc.edu.ph", PW, PW, student_id_number="ID-C3")
        self.owner_service = StudentOwnerService(self.db)
        self.workspaces = WorkspaceService(self.owner_service)
        self.approve(self.ana)
        self.approve(self.ben)   # Cai stays an ordinary student
        self.categories = CategoryService(self.db, self.workspaces)
        self.listings = OwnerListingService(self.db, self.workspaces)

    def approve(self, student):
        application = self.owner_service.submit_application(
            student.id, "I have spare lab equipment and would like to help classmates.",
            "A scientific calculator and a soldering kit.", True)
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE student_owner_applications SET status='Approved' WHERE application_id=?",
                     (application.application_id,))
        conn.commit()
        conn.close()

    def query(self, sql, params=()):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def names(self, parent_id=None):
        found = (self.categories.general_categories() if parent_id is None
                 else self.categories.subcategories(parent_id))
        return [c.name for c in found]


# ======================================================================
# 1. NAMES: duplicates and similar names
# ======================================================================
class NameRuleTests(unittest.TestCase):
    def test_spaces_and_capitals_are_ignored_for_duplicates(self):
        self.assertEqual(clean_name("  study    Gear \t"), "study Gear")
        self.assertEqual(name_key("  study    GEAR "), name_key("Study Gear"))
        self.assertNotEqual(name_key("Study Gear"), name_key("StudyGear"))

    def test_similar_names_score_high_and_different_ones_low(self):
        for a, b in (("Book", "Books"), ("Math", "Mathematics"), ("StudyGear", "Study Gear"),
                     ("Programing", "Programming"), ("Study-Gear", "study gear"),
                     ("Electronic", "Electronics")):
            self.assertGreaterEqual(similarity(a, b), 0.8, (a, b))
        for a, b in (("Fantasy", "Electronics"), ("Cats", "Cars"), ("Games", "Gadgets"),
                     ("Chemistry", "Mathematics")):
            self.assertLess(similarity(a, b), 0.8, (a, b))


class RegistryTests(Base):
    def test_the_six_existing_categories_are_there_and_marked_builtin(self):
        self.assertEqual(self.names(), BUILTIN)
        self.assertTrue(all(c.is_builtin for c in self.categories.general_categories()))

    def test_a_new_general_category_is_stored_once_for_everyone(self):
        books = self.categories.create(self.ana.id, "  Books ")
        self.assertEqual((books.name, books.parent_id), ("Books", None))
        self.assertIn("Books", self.names())
        # ONE shared table: the row is not tied to a listing or an owner's own list
        rows = self.query("SELECT name, created_by FROM listing_categories WHERE name='Books'")
        self.assertEqual(rows, [("Books", self.ana.id)])

    def test_another_owner_sees_it_immediately_through_a_separate_service_object(self):
        self.categories.create(self.ana.id, "Books")
        ben_view = OwnerListingService(self.db, self.workspaces)   # Ben's own objects
        self.assertIn("Books", ben_view.categories)
        self.assertIn("Books", CategoryService(self.db, self.workspaces).general_categories()[0].name
                      or "Books")
        ben_access = OwnerCategoryAccess(CategoryService(self.db, self.workspaces), self.ben.id)
        self.assertIn("Books", ben_access.top_names())

    def test_subcategories_belong_to_one_general_category(self):
        books = self.categories.create(self.ana.id, "Books")
        games = self.categories.create(self.ana.id, "Games")
        fantasy = self.categories.create(self.ana.id, "Fantasy", books.category_id)
        self.assertEqual(self.names(books.category_id), ["Fantasy"])
        self.assertEqual(self.names(games.category_id), [])
        again = self.categories.create(self.ben.id, "Fantasy", games.category_id)  # same name, other parent
        self.assertNotEqual(again.category_id, fantasy.category_id)

    def test_only_two_levels_are_allowed(self):
        books = self.categories.create(self.ana.id, "Books")
        fantasy = self.categories.create(self.ana.id, "Fantasy", books.category_id)
        with self.assertRaises(CategoryError):
            self.categories.create(self.ana.id, "Epic", fantasy.category_id)
        with self.assertRaises(CategoryError):
            self.categories.create(self.ana.id, "Epic", 99999)

    def test_duplicates_are_refused_whatever_the_capitals_or_spaces(self):
        for attempt in ("mathematics", "  MATHEMATICS ", "Study   gear", "study gear"):
            with self.assertRaises(CategoryExistsError, msg=attempt) as caught:
                self.categories.create(self.ana.id, attempt)
            self.assertIn(caught.exception.category.name, ("Mathematics", "Study Gear"))
        books = self.categories.create(self.ana.id, "Books")
        self.categories.create(self.ana.id, "Fantasy", books.category_id)
        with self.assertRaises(CategoryExistsError):
            self.categories.create(self.ben.id, " fantasy ", books.category_id)
        self.assertEqual(self.names().count("Mathematics"), 1)

    def test_the_database_itself_refuses_a_duplicate(self):
        books = self.categories.create(self.ana.id, "Books").category_id
        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO listing_categories (name, name_key, created_at) "
                             "VALUES ('mathematics', 'mathematics', 'x')")
            conn.rollback()
            conn.execute("INSERT INTO listing_categories (parent_id, name, name_key, created_at) "
                         "VALUES (?, 'Fantasy', 'fantasy', 'x')", (books,))
            conn.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO listing_categories (parent_id, name, name_key, created_at) "
                             "VALUES (?, 'FANTASY', 'fantasy', 'x')", (books,))
            conn.rollback()
        finally:
            conn.close()

    def test_a_create_that_loses_a_race_returns_the_existing_category(self):
        from app.listing_category_service import CategoryCheck
        self.categories.create(self.ben.id, "Books")
        # Pretend nothing existed when Ana looked (Ben had not finished yet): the check inside
        # the database write lock must still catch it, and nothing is created twice.
        with mock.patch.object(CategoryService, "check_name",
                               return_value=CategoryCheck(STATUS_OK, "books")):
            with self.assertRaises(CategoryExistsError) as caught:
                self.categories.create(self.ana.id, "books")
        self.assertEqual(caught.exception.category.name, "Books")
        self.assertEqual(self.names().count("Books"), 1)

    def test_similar_names_need_confirmation_and_suggest_the_existing_ones(self):
        self.categories.create(self.ana.id, "Books")
        with self.assertRaises(SimilarCategoryError) as caught:
            self.categories.create(self.ben.id, "Book")
        self.assertEqual([c.name for c in caught.exception.similar], ["Books"])
        self.assertNotIn("Book", self.names())            # nothing was created
        created = self.categories.create(self.ben.id, "Book", confirm_similar=True)
        self.assertEqual(created.name, "Book")
        self.assertIn("Book", self.names())

    def test_check_name_reports_what_would_happen(self):
        books = self.categories.create(self.ana.id, "Books")
        check = self.categories.check_name
        self.assertEqual(check("").status, STATUS_EMPTY)
        self.assertEqual(check("A").status, STATUS_TOO_SHORT)
        self.assertEqual(check("x" * 41).status, STATUS_TOO_LONG)
        self.assertEqual(check("!!!").status, "invalid")
        self.assertEqual(check(" BOOKS ").status, STATUS_EXISTS)
        self.assertEqual(check("BOOKS").existing.category_id, books.category_id)
        self.assertEqual(check("Book").status, STATUS_SIMILAR)
        self.assertEqual(check("Mathematic").status, STATUS_SIMILAR)
        self.assertEqual(check("Origami").status, STATUS_OK)
        self.assertEqual(check("Origami").name, "Origami")

    def test_similar_names_are_only_compared_at_the_same_level(self):
        books = self.categories.create(self.ana.id, "Books")
        self.assertEqual(self.categories.check_name("Book", books.category_id).status, STATUS_OK)

    def test_only_approved_student_owners_can_create(self):
        for student in (self.cai, None):
            with self.assertRaises(CategoryError):
                self.categories.create(student.id if student else None, "Books")
        with self.assertRaises(CategoryError):
            CategoryService(self.db, None).create(self.ana.id, "Books")
        self.assertNotIn("Books", self.names())
        # ... but anyone can READ the shared list
        self.assertEqual(len(CategoryService(self.db).general_categories()), 6)

    def test_bad_names_are_refused_with_a_friendly_message(self):
        for bad in ("", "  ", "A", "x" * 41, "!!!"):
            with self.assertRaises(CategoryError, msg=repr(bad)):
                self.categories.create(self.ana.id, bad)
        self.assertEqual(self.names(), BUILTIN)


# ======================================================================
# 2. LISTINGS USE THE REGISTRY
# ======================================================================
class ListingIntegrationTests(Base):
    def test_listing_categories_come_from_the_shared_registry(self):
        self.assertEqual(list(self.listings.categories), BUILTIN)
        self.categories.create(self.ben.id, "Books")
        self.assertIn("Books", self.listings.categories)

    def test_a_listing_can_use_a_category_and_a_subcategory(self):
        books = self.categories.create(self.ana.id, "Books")
        self.categories.create(self.ana.id, "Fantasy", books.category_id)
        saved = self.listings.create_draft(
            self.ana.id, good(title="The Hobbit", category="Books", subcategory="Fantasy"))
        self.assertEqual((saved.category, saved.subcategory), ("Books", "Fantasy"))
        self.assertEqual(saved.category_path, "Books › Fantasy")
        reopened = self.listings.get(self.ana.id, saved.listing_id)
        self.assertEqual(reopened.category_path, "Books › Fantasy")
        self.assertEqual(self.listings.list_drafts(self.ana.id)[0].subcategory, "Fantasy")
        # the listing row keeps the general category NAME, exactly as before
        self.assertEqual(self.query("SELECT category FROM owner_listings"), [("Books",)])

    def test_subcategory_is_optional_and_can_be_changed_or_removed(self):
        books = self.categories.create(self.ana.id, "Books")
        self.categories.create(self.ana.id, "Fantasy", books.category_id)
        self.categories.create(self.ana.id, "Poetry", books.category_id)
        saved = self.listings.create_draft(self.ana.id, good(category="Mathematics"))
        self.assertEqual(saved.subcategory, "")
        saved = self.listings.update_draft(
            self.ana.id, saved.listing_id, good(category="Books", subcategory="poetry"))
        self.assertEqual(saved.category_path, "Books › Poetry")
        saved = self.listings.update_draft(
            self.ana.id, saved.listing_id, good(category="Books", subcategory="Fantasy"))
        self.assertEqual(saved.subcategory, "Fantasy")
        saved = self.listings.update_draft(self.ana.id, saved.listing_id, good(category="Books"))
        self.assertEqual(saved.category_path, "Books")
        self.assertEqual(self.query("SELECT COUNT(*) FROM listing_category_links"), [(1,)])

    def test_a_subcategory_from_another_category_or_an_unknown_one_is_refused(self):
        books = self.categories.create(self.ana.id, "Books")
        self.categories.create(self.ana.id, "Fantasy", books.category_id)
        for bad in (dict(category="Mathematics", subcategory="Fantasy"),
                    dict(category="Books", subcategory="Nonexistent"),
                    dict(category="Nonexistent"), dict(category="")):
            with self.assertRaises(OwnerListingError, msg=str(bad)):
                self.listings.create_draft(self.ana.id, good(**bad))
        self.assertEqual(self.query("SELECT COUNT(*) FROM owner_listings"), [(0,)])

    def test_category_names_match_ignoring_case_and_spaces_but_are_stored_canonically(self):
        saved = self.listings.create_draft(self.ana.id, good(category="  study   GEAR "))
        self.assertEqual(saved.category, "Study Gear")

    def test_a_failed_save_leaves_no_half_saved_category_link(self):
        books = self.categories.create(self.ana.id, "Books")
        self.categories.create(self.ana.id, "Fantasy", books.category_id)
        self.listings.create_draft(self.ana.id, good(title="The Hobbit", category="Books"))
        with self.assertRaises(OwnerListingError):  # same owner, same name
            self.listings.create_draft(self.ana.id, good(title="the hobbit", category="Books",
                                                         subcategory="Fantasy"))
        self.assertEqual(self.query("SELECT COUNT(*) FROM listing_category_links"), [(1,)])

    def test_owners_listings_stay_private_but_the_category_list_is_shared(self):
        self.listings.create_draft(self.ana.id, good())
        self.assertEqual(self.listings.list_drafts(self.ben.id), [])
        self.assertEqual(list(OwnerListingService(self.db, self.workspaces).categories), BUILTIN)

    def test_the_old_fixed_list_mode_still_works(self):
        legacy = OwnerListingService(self.db, self.workspaces, ("Mathematics", "Programming"))
        self.assertIsNone(legacy.category_service)
        self.assertEqual(legacy.categories, ("Mathematics", "Programming"))
        saved = legacy.create_draft(self.ana.id, good(title="Legacy item"))
        self.assertEqual((saved.category, saved.subcategory), ("Mathematics", ""))
        with self.assertRaises(OwnerListingError):
            legacy.create_draft(self.ana.id, good(title="Other", category="Science"))


class AccessAdapterTests(Base):
    def test_the_form_adapter_speaks_plain_names(self):
        access = OwnerCategoryAccess(self.categories, self.ana.id)
        self.assertEqual(access.top_names(), BUILTIN)
        self.assertEqual(access.create("Books"), "Books")
        self.assertEqual(access.create("Fantasy", "Books"), "Fantasy")
        self.assertEqual(access.sub_names("Books"), ["Fantasy"])
        self.assertEqual(access.sub_names("Nothing"), [])
        check = access.check("books")
        self.assertEqual((check.status, check.existing), (STATUS_EXISTS, "Books"))
        self.assertEqual(access.check("Book").similar, ("Books",))
        with self.assertRaises(SimilarCategoryError):
            access.create("Book")
        with self.assertRaises(CategoryError):
            access.create("Epic", "Nonexistent")


# ======================================================================
# 3. THE MIGRATION (existing and new installations)
# ======================================================================
class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "old.db")

    def make_old_database(self):
        """A database exactly as Step 31C left it (migrations up to 14), with data in it."""
        old = [m for m in database.MIGRATIONS if m[0] <= 14]
        with mock.patch.object(database, "MIGRATIONS", old):
            auth = AuthService(self.db)
            ana = auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-A1")
        conn = sqlite3.connect(self.db)
        for number, (title, category) in enumerate(
                [("Calculator", "Mathematics"), ("Laptop stand", "Study Gear"),
                 ("Oddly categorised", "  Robotics Kits ")], start=1):
            conn.execute(
                "INSERT INTO owner_listings (listing_id, owner_student_id, title, category, "
                "description, condition, max_borrow_days, extra_rules, status, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, 'A fine item, well kept.', 'Good', 2, '', "
                "'Draft', 't', 't')", (f"LD-0000000{number}", ana.id, title, category))
        conn.commit()
        conn.close()
        return ana

    def test_an_existing_installation_keeps_every_account_listing_and_category(self):
        ana = self.make_old_database()
        before = sqlite3.connect(self.db).execute(
            "SELECT listing_id, title, category FROM owner_listings ORDER BY 1").fetchall()
        self.assertNotIn("listing_categories", [
            r[0] for r in sqlite3.connect(self.db).execute("SELECT name FROM sqlite_master")])

        service = CategoryService(self.db)        # opening the database runs migration 15
        names = [c.name for c in service.general_categories()]
        self.assertEqual(names, sorted(BUILTIN + ["Robotics Kits"], key=str.casefold))

        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute(
            "SELECT listing_id, title, category FROM owner_listings ORDER BY 1").fetchall(), before)
        self.assertEqual(conn.execute("SELECT full_name FROM students").fetchall(), [("Ana Reyes",)])
        links = conn.execute(
            "SELECT l.title, c.name FROM listing_category_links k "
            "JOIN owner_listings l ON l.listing_id = k.listing_id "
            "JOIN listing_categories c ON c.category_id = k.category_id ORDER BY 1").fetchall()
        self.assertEqual(links, [("Calculator", "Mathematics"), ("Laptop stand", "Study Gear"),
                                 ("Oddly categorised", "Robotics Kits")])
        self.assertEqual(conn.execute(
            "SELECT is_builtin FROM listing_categories WHERE name='Robotics Kits'").fetchone(), (0,))
        conn.close()
        self.assertTrue(ana.id)

    def test_a_safety_copy_is_made_before_the_migration(self):
        self.make_old_database()
        CategoryService(self.db).general_categories()
        backup = Path(f"{self.db}.before-v15.bak")
        self.assertTrue(backup.exists())
        copy = sqlite3.connect(str(backup))
        try:
            tables = [r[0] for r in copy.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            self.assertNotIn("listing_categories", tables)       # it is the PRE-migration state
            self.assertEqual(copy.execute("SELECT COUNT(*) FROM owner_listings").fetchone(), (3,))
        finally:
            copy.close()

    def test_migrating_twice_changes_nothing(self):
        self.make_old_database()
        first = [c.name for c in CategoryService(self.db).general_categories()]
        again = [c.name for c in CategoryService(self.db).general_categories()]
        self.assertEqual(first, again)
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM listing_category_links").fetchone(), (3,))
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=15").fetchone(), (1,))
        conn.close()

    def test_a_brand_new_installation_gets_the_six_categories_and_no_listings(self):
        service = CategoryService(self.db)
        self.assertEqual([c.name for c in service.general_categories()], BUILTIN)
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM listing_category_links").fetchone(), (0,))
        self.assertEqual([r[0] for r in conn.execute("SELECT version FROM schema_migrations")][-1], 15)
        conn.close()
        self.assertFalse(Path(f"{self.db}.before-v15.bak").exists())  # nothing to back up


# ======================================================================
# 4. ADD / EDIT LISTING FORM AND THE NEW-CATEGORY DIALOG (needs PySide6)
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class FormTests(Base):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        from app.owner_workspace import OwnerListingFormPage
        from app.owner_listing_service import CONDITIONS
        self.access = OwnerCategoryAccess(self.categories, self.ana.id)
        self.form = OwnerListingFormPage(self.listings.categories, CONDITIONS,
                                         category_source=self.access)
        self.form.start_new()

    def pick(self, combo, text):
        index = combo.findText(text)
        self.assertGreaterEqual(index, 0, text)
        combo.setCurrentIndex(index)

    def test_category_and_subcategory_choices_come_from_the_registry(self):
        form = self.form
        self.assertEqual([form.category_combo.itemText(i) for i in range(1, form.category_combo.count())],
                         BUILTIN)
        self.assertFalse(form.subcategory_combo.isEnabled())
        self.categories.create(self.ana.id, "Books")
        self.categories.create(self.ana.id, "Fantasy", self.categories.find("Books").category_id)
        form.refresh_categories()
        self.pick(form.category_combo, "Books")
        self.assertTrue(form.subcategory_combo.isEnabled())
        self.assertEqual([form.subcategory_combo.itemText(i) for i in range(form.subcategory_combo.count())],
                         ["No subcategory", "Fantasy"])
        self.pick(form.subcategory_combo, "Fantasy")
        self.assertEqual(form.fields()["category"], "Books")
        self.assertEqual(form.fields()["subcategory"], "Fantasy")
        self.pick(form.category_combo, "Science")   # changing the category clears the subcategory
        self.assertEqual(form.fields()["subcategory"], "")

    def test_a_category_created_by_another_owner_appears_without_reopening_the_form(self):
        self.assertEqual(self.form.category_combo.findText("Origami"), -1)
        OwnerCategoryAccess(CategoryService(self.db, self.workspaces), self.ben.id).create("Origami")
        self.form.category_combo.showPopup()          # opening the list re-reads the registry
        self.form.category_combo.hidePopup()
        self.assertGreaterEqual(self.form.category_combo.findText("Origami"), 0)

    def test_refreshing_keeps_the_current_choice(self):
        self.pick(self.form.category_combo, "Science")
        self.categories.create(self.ben.id, "Origami")
        self.form.refresh_categories()
        self.assertEqual(self.form.category_combo.currentText(), "Science")

    def test_editing_a_saved_draft_shows_its_category_and_subcategory(self):
        books = self.categories.create(self.ana.id, "Books")
        self.categories.create(self.ana.id, "Fantasy", books.category_id)
        saved = self.listings.create_draft(
            self.ana.id, good(title="The Hobbit", category="Books", subcategory="Fantasy"))
        self.form.load(saved)
        self.assertEqual(self.form.category_combo.currentText(), "Books")
        self.assertEqual(self.form.subcategory_combo.currentText(), "Fantasy")
        self.assertEqual(self.form.title_label.text(), "Edit Draft")

    def test_the_new_category_dialog_creates_and_selects_a_category(self):
        from app.owner_category_dialog import NewCategoryDialog
        dialog = NewCategoryDialog(self.access, None)
        dialog.name_input.setText("  Origami  ")
        self.assertTrue(dialog.create_button.isEnabled())
        dialog.create_button.click()
        self.assertEqual(dialog.result_name, "Origami")
        self.assertIn("Origami", self.names())

    def test_the_dialog_blocks_duplicates_and_offers_the_existing_category(self):
        from app.owner_category_dialog import NewCategoryDialog
        dialog = NewCategoryDialog(self.access, None)
        dialog.name_input.setText("  mathematics ")
        self.assertFalse(dialog.create_button.isEnabled())
        self.assertTrue(dialog.use_button.isEnabled())
        self.assertEqual(dialog.suggestion_names(), ["Mathematics"])
        dialog.use_button.click()
        self.assertEqual(dialog.result_name, "Mathematics")
        self.assertEqual(self.names().count("Mathematics"), 1)

    def test_the_dialog_warns_about_similar_names_before_allowing_creation(self):
        from app.owner_category_dialog import NewCategoryDialog
        self.categories.create(self.ana.id, "Books")
        dialog = NewCategoryDialog(self.access, None)
        dialog.name_input.setText("Book")
        self.assertEqual(dialog.suggestion_names(), ["Books"])
        self.assertIn("similar", dialog.hint_label.text().lower())
        self.assertEqual(dialog.create_button.text(), "Create anyway")
        dialog.suggestion_list.setCurrentRow(0)
        dialog.use_button.click()                     # choosing the suggestion creates nothing
        self.assertEqual(dialog.result_name, "Books")
        self.assertNotIn("Book", self.names())
        other = NewCategoryDialog(self.access, None)
        other.name_input.setText("Book")
        other.create_button.click()                   # explicit "Create anyway"
        self.assertEqual(other.result_name, "Book")
        self.assertIn("Book", self.names())

    def test_the_dialog_creates_a_subcategory_under_the_chosen_category(self):
        from app.owner_category_dialog import NewCategoryDialog
        self.categories.create(self.ana.id, "Books")
        dialog = NewCategoryDialog(self.access, "Books")
        dialog.name_input.setText("Fantasy")
        dialog.create_button.click()
        self.assertEqual(self.access.sub_names("Books"), ["Fantasy"])

    def test_form_buttons_open_the_dialog_and_select_the_result(self):
        self.form._run_dialog = lambda dialog: (
            setattr(dialog, "result_name", None) or dialog.name_input.setText("Origami")
            or dialog.create_button.click() or True)
        self.form.new_category_button.click()
        self.assertEqual(self.form.category_combo.currentText(), "Origami")
        self.assertTrue(self.form.new_subcategory_button.isEnabled())
        self.form._run_dialog = lambda dialog: (
            dialog.name_input.setText("Paper folding") or dialog.create_button.click() or True)
        self.form.new_subcategory_button.click()
        self.assertEqual(self.form.subcategory_combo.currentText(), "Paper folding")

    def test_new_subcategory_needs_a_category_first(self):
        self.assertFalse(self.form.new_subcategory_button.isEnabled())

    def test_without_a_category_source_the_form_works_as_before(self):
        from app.owner_workspace import OwnerListingFormPage
        plain = OwnerListingFormPage(["Mathematics"], ("Good",))
        self.assertTrue(plain.subcategory_combo.isHidden())
        self.assertTrue(plain.new_category_button.isHidden())
        self.assertEqual(plain.fields()["subcategory"], "")


if __name__ == "__main__":
    unittest.main()
