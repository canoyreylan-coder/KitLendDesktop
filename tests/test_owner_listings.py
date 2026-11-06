"""Step 31B tests: My Listings, Add Listing and draft editing.

Run:   python -m unittest discover -s tests -p "test_owner_listings.py" -v
Groups 1-2 need no window. Group 3 uses Qt's invisible "offscreen" mode. Temporary databases only.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.auth_service import AuthService  # noqa: E402
from app.owner_listing_service import (  # noqa: E402
    CONDITIONS,
    MAX_DESCRIPTION,
    MAX_TITLE,
    NOT_ALLOWED,
    OwnerListingError,
    OwnerListingService,
)
from app.photo_service import PhotoService  # noqa: E402
from app.student_owner_service import StudentOwnerService  # noqa: E402
from app.workspace_service import WorkspaceService  # noqa: E402

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

PW = "correct horse"
CATEGORIES = ("Mathematics", "Programming", "Electronics")


def good(**changes):
    fields = {"title": "Casio fx-991EX Calculator", "category": "Mathematics",
              "condition": "Good", "description": "Scientific calculator with a cover.",
              "max_borrow_days": 2, "extra_rules": "Return with the cover."}
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
        self.listings = OwnerListingService(self.db, self.workspaces, CATEGORIES)

    def approve(self, student):
        application = self.owner_service.submit_application(
            student.id, "I have spare lab equipment and would like to help classmates.",
            "A scientific calculator and a soldering kit.", True)
        self.set_status(application.application_id, "Approved")
        return application

    def set_status(self, application_id, status):
        """Simulates the FUTURE review system."""
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE student_owner_applications SET status=? WHERE application_id=?",
                     (status, application_id))
        conn.commit()
        conn.close()

    def rows(self, sql="SELECT * FROM owner_listings", params=()):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _publishable_draft(self):
        draft = self.listings.create_draft(
            self.ana.id, good(), {0: [(540, 720)]})
        photo_path = Path(self.tmp.name) / "publishable.png"
        photo_path.write_bytes(b"test image")
        PhotoService(self.db, Path(self.tmp.name) / "photos").add_photo(
            draft.listing_id, photo_path)
        return draft


# ======================================================================
# 1. ACCESS: only approved Student Owners
# ======================================================================
class AccessTests(Base):
    def test_students_without_approval_cannot_do_anything(self):
        pending = self.owner_service.submit_application(
            self.ben.id, "I have spare lab equipment and would like to help classmates.",
            "A scientific calculator and a soldering kit.", True)
        for student in (self.ana, self.ben):            # never applied / Pending
            self.assertFalse(self.listings.can_manage(student.id))
            with self.assertRaises(OwnerListingError) as ctx:
                self.listings.create_draft(student.id, good())
            self.assertEqual(str(ctx.exception), NOT_ALLOWED)
            with self.assertRaises(OwnerListingError):
                self.listings.list_drafts(student.id)
        self.set_status(pending.application_id, "Rejected")
        with self.assertRaises(OwnerListingError):
            self.listings.create_draft(self.ben.id, good())
        self.assertEqual(self.rows(), [])

    def test_bad_ids_and_missing_workspace_service_are_refused(self):
        self.approve(self.ana)
        for bad in (None, "1", True):
            with self.assertRaises(OwnerListingError):
                self.listings.list_drafts(bad)
        with self.assertRaises(OwnerListingError):
            OwnerListingService(self.db, None, CATEGORIES).list_drafts(self.ana.id)

    def test_withdrawn_approval_stops_access_at_once(self):
        application = self.approve(self.ana)
        draft = self.listings.create_draft(self.ana.id, good())
        self.set_status(application.application_id, "Rejected")
        with self.assertRaises(OwnerListingError):
            self.listings.list_drafts(self.ana.id)
        with self.assertRaises(OwnerListingError):
            self.listings.update_draft(self.ana.id, draft.listing_id, good(title="Changed"))
        self.assertEqual(len(self.rows()), 1)           # the draft is kept, just not reachable

    def test_an_owner_cannot_see_or_edit_another_owners_draft(self):
        self.approve(self.ana)
        self.approve(self.ben)
        draft = self.listings.create_draft(self.ana.id, good())
        self.assertEqual(self.listings.list_drafts(self.ben.id), [])
        with self.assertRaises(OwnerListingError):
            self.listings.get(self.ben.id, draft.listing_id)
        with self.assertRaises(OwnerListingError):
            self.listings.update_draft(self.ben.id, draft.listing_id, good(title="Stolen"))
        self.assertEqual(self.listings.get(self.ana.id, draft.listing_id).title, good()["title"])


# ======================================================================
# 2. SAVING, REOPENING, EDITING
# ======================================================================
class DraftTests(Base):
    def setUp(self):
        super().setUp()
        self.approve(self.ana)
        self.approve(self.ben)

    def test_a_draft_is_saved_linked_to_the_owner_account(self):
        draft = self.listings.create_draft(self.ana.id, good())
        self.assertTrue(draft.listing_id.startswith("LD-"))
        self.assertEqual((draft.owner_student_id, draft.status), (self.ana.id, "Draft"))
        row = self.rows()[0]
        self.assertEqual(row["owner_student_id"], self.ana.id)
        self.assertEqual((row["title"], row["category"], row["condition"], row["max_borrow_days"]),
                         ("Casio fx-991EX Calculator", "Mathematics", "Good", 2))
        self.assertEqual(row["extra_rules"], "Return with the cover.")

    def test_drafts_survive_reopening_and_list_newest_edit_first(self):
        first = self.listings.create_draft(self.ana.id, good(title="First item"))
        self.listings.create_draft(self.ana.id, good(title="Second item"))
        self.listings.update_draft(self.ana.id, first.listing_id, good(title="First item", max_borrow_days=5))
        again = OwnerListingService(self.db, self.workspaces, CATEGORIES)
        titles = [d.title for d in again.list_drafts(self.ana.id)]
        self.assertEqual(titles, ["First item", "Second item"])   # edited one moves to the top

    def test_editing_changes_the_same_draft(self):
        draft = self.listings.create_draft(self.ana.id, good())
        updated = self.listings.update_draft(
            self.ana.id, draft.listing_id,
            good(title="Casio fx-991EX", condition="Fair", max_borrow_days=7, extra_rules=""))
        self.assertEqual(updated.listing_id, draft.listing_id)
        self.assertEqual((updated.title, updated.condition, updated.max_borrow_days,
                          updated.extra_rules), ("Casio fx-991EX", "Fair", 7, ""))
        self.assertEqual(updated.created_at, draft.created_at)
        self.assertGreater(updated.updated_at, draft.updated_at)
        self.assertEqual(len(self.rows()), 1)

    def test_editing_published_listing_preserves_identity_status_and_updates_schedule(self):
        original = self.listings.create_draft(
            self.ana.id, good(), {0: [(540, 720)]})
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE owner_listings SET status = 'Published' WHERE listing_id = ?",
            (original.listing_id,))
        conn.commit()
        conn.close()

        updated = self.listings.update_published(
            self.ana.id, original.listing_id,
            good(title="Updated Calculator", category="Electronics", condition="Fair",
                 description="Updated description with the same saved listing.",
                 max_borrow_days=6),
            {2: [(600, 840)]})

        self.assertEqual(updated.listing_id, original.listing_id)
        self.assertEqual(updated.owner_student_id, self.ana.id)
        self.assertEqual(updated.status, "Published")
        self.assertEqual(updated.title, "Updated Calculator")
        self.assertEqual(updated.category, "Electronics")
        self.assertEqual(updated.condition, "Fair")
        self.assertEqual(updated.max_borrow_days, 6)
        self.assertEqual(
            self.listings.get_availability(self.ana.id, original.listing_id).as_dict(),
            {2: [(600, 840)]})
        self.assertEqual(len(self.rows()), 1)

    def test_only_owner_can_edit_published_listing(self):
        listing = self.listings.create_draft(self.ana.id, good())
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE owner_listings SET status = 'Published' WHERE listing_id = ?",
            (listing.listing_id,))
        conn.commit()
        conn.close()

        with self.assertRaises(OwnerListingError):
            self.listings.update_published(
                self.ben.id, listing.listing_id, good(title="Unauthorized edit"))
        self.assertEqual(
            self.listings.get(self.ana.id, listing.listing_id).title, listing.title)

    def test_pause_resume_persists_and_preserves_listing_assets(self):
        listing = self._publishable_draft()
        self.listings.publish(
            self.ana.id, listing.listing_id, photos_dir=Path(self.tmp.name) / "photos")
        photos_before = self.rows(
            "SELECT photo_id, listing_key, file_path, is_primary FROM listing_photos "
            "WHERE listing_key = ?", (listing.listing_id,))
        paused = self.listings.pause_listing(self.ana.id, listing.listing_id)
        self.assertEqual(paused.status, "Paused")
        self.assertEqual(len(self.listings.list_published_catalog()), 0)
        self.assertEqual(
            self.rows("SELECT photo_id, listing_key, file_path, is_primary FROM listing_photos "
                      "WHERE listing_key = ?", (listing.listing_id,)),
            photos_before)

        reopened = OwnerListingService(self.db, self.workspaces, CATEGORIES)
        self.assertEqual(reopened.get(self.ana.id, listing.listing_id).status, "Paused")
        resumed = reopened.resume_listing(
            self.ana.id, listing.listing_id, photos_dir=Path(self.tmp.name) / "photos")
        self.assertEqual(resumed.status, "Published")
        self.assertEqual(len(reopened.list_published_catalog()), 1)
        self.assertEqual(reopened.get_availability(
            self.ana.id, listing.listing_id).as_dict(), {0: [(540, 720)]})
        self.assertEqual(
            self.rows("SELECT photo_id, listing_key, file_path, is_primary FROM listing_photos "
                      "WHERE listing_key = ?", (listing.listing_id,)),
            photos_before)

    def test_resume_rejects_incomplete_paused_listing(self):
        listing = self.listings.create_draft(self.ana.id, good())
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE owner_listings SET status = 'Published', paused_at = 'paused' "
            "WHERE listing_id = ?", (listing.listing_id,))
        conn.commit()
        conn.close()

        with self.assertRaises(OwnerListingError) as ctx:
            self.listings.resume_listing(self.ana.id, listing.listing_id)
        self.assertIn("pickup day", str(ctx.exception))
        self.assertEqual(self.listings.get(self.ana.id, listing.listing_id).status, "Paused")

    def test_delete_soft_hides_listing_and_preserves_photos_and_other_listing(self):
        first = self._publishable_draft()
        second = self.listings.create_draft(
            self.ben.id, good(title="Ben's separate listing"))
        photos_before = self.rows(
            "SELECT photo_id, listing_key, file_path FROM listing_photos "
            "WHERE listing_key = ?", (first.listing_id,))
        self.listings.delete_listing(self.ana.id, first.listing_id)

        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        deleted_row = conn.execute(
            "SELECT listing_id, deleted_at FROM owner_listings WHERE listing_id = ?",
            (first.listing_id,)).fetchone()
        conn.close()
        self.assertEqual(deleted_row["listing_id"], first.listing_id)
        self.assertTrue(deleted_row["deleted_at"])
        self.assertEqual(self.listings.list_listings(self.ana.id), [])
        with self.assertRaises(OwnerListingError):
            self.listings.get(self.ana.id, first.listing_id)
        self.assertEqual(
            self.rows("SELECT photo_id, listing_key, file_path FROM listing_photos "
                      "WHERE listing_key = ?", (first.listing_id,)),
            photos_before)
        self.assertEqual(self.listings.get(self.ben.id, second.listing_id), second)

    def test_delete_is_blocked_by_active_owner_request_even_after_listing_rename(self):
        listing = self.listings.create_draft(self.ana.id, good())
        request_id = "REQ-ACTIVE-TEST"
        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO borrow_requests (request_id, student_id, submission_key, "
            "batch_position, item_title, item_creator, item_category, item_kind, "
            "item_ownership, item_owner_note, item_copies_total, item_copies_available, "
            "item_collections, max_days, requested_days, status, submitted_at, "
            "preferred_pickup_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (request_id, self.ben.id, "submission-test", 0, "Old listing title", "Ana Reyes",
             listing.category, "Item", "student", "Shared by Ana Reyes", 1, 1, "[]",
             2, 1, "approved", "2026-01-01T10:00:00+00:00",
             "2026-01-02T10:00:00+00:00"))
        conn.commit()
        conn.close()

        with self.assertRaises(OwnerListingError) as ctx:
            self.listings.delete_listing(self.ana.id, listing.listing_id)
        self.assertIn("active requests, reservations, or loans", str(ctx.exception))
        self.assertEqual(self.listings.get(self.ana.id, listing.listing_id), listing)

    def test_validation_messages_and_nothing_saved_on_error(self):
        bad = [good(title=""), good(title="ab"), good(title="x" * (MAX_TITLE + 1)),
               good(category=""), good(category="Cooking"), good(condition=""),
               good(condition="Broken"), good(description=""), good(description="short"),
               good(description="x" * (MAX_DESCRIPTION + 1)), good(max_borrow_days=0),
               good(max_borrow_days=31), good(max_borrow_days=None), good(max_borrow_days=True)]
        for fields in bad:
            with self.assertRaises(OwnerListingError, msg=fields):
                self.listings.create_draft(self.ana.id, fields)
        self.assertEqual(self.rows(), [])
        self.assertIn("Good", CONDITIONS)

    def test_optional_rules_and_whitespace_cleanup(self):
        draft = self.listings.create_draft(
            self.ana.id, good(title="  Digital   Multimeter ", extra_rules="   "))
        self.assertEqual((draft.title, draft.extra_rules), ("Digital Multimeter", ""))

    def test_same_name_is_refused_per_owner_but_allowed_for_others(self):
        self.listings.create_draft(self.ana.id, good(title="Multimeter"))
        with self.assertRaises(OwnerListingError) as ctx:
            self.listings.create_draft(self.ana.id, good(title="multimeter"))
        self.assertIn("already have", str(ctx.exception))
        other = self.listings.create_draft(self.ben.id, good(title="Multimeter"))
        with self.assertRaises(OwnerListingError):
            self.listings.create_draft(self.ben.id, good(title="MULTIMETER"))
        self.assertEqual(other.owner_student_id, self.ben.id)
        second = self.listings.create_draft(self.ana.id, good(title="Soldering kit"))
        with self.assertRaises(OwnerListingError):          # renaming onto an existing name
            self.listings.update_draft(self.ana.id, second.listing_id, good(title="Multimeter"))
        self.assertEqual(self.listings.get(self.ana.id, second.listing_id).title, "Soldering kit")

    def test_published_or_unknown_listings_cannot_be_edited_as_drafts(self):
        draft = self.listings.create_draft(self.ana.id, good())
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE owner_listings SET status='Published'")
        conn.commit()
        conn.close()
        with self.assertRaises(OwnerListingError):
            self.listings.update_draft(self.ana.id, draft.listing_id, good(title="Changed"))
        with self.assertRaises(OwnerListingError):
            self.listings.update_draft(self.ana.id, "LD-NOPE", good())
        self.assertEqual(self.listings.list_drafts(self.ana.id), [])

    def test_incomplete_draft_remains_private_and_reports_requirements(self):
        draft = self.listings.create_draft(self.ana.id, good())
        with self.assertRaises(OwnerListingError) as ctx:
            self.listings.publish(self.ana.id, draft.listing_id)
        self.assertIn("pickup day", str(ctx.exception))
        self.assertIn("usable listing photo", str(ctx.exception))
        self.assertEqual(self.listings.get(self.ana.id, draft.listing_id).status, "Draft")
        self.assertEqual(self.rows()[0]["status"], "Draft")

    def test_required_listing_fields_are_validated_before_publish(self):
        draft = self.listings.create_draft(self.ana.id, good())
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE owner_listings SET description = 'Too short' WHERE listing_id = ?",
                     (draft.listing_id,))
        conn.commit()
        conn.close()

        with self.assertRaises(OwnerListingError) as ctx:
            self.listings.publish(self.ana.id, draft.listing_id)
        self.assertIn("describe the item a little more", str(ctx.exception))
        self.assertEqual(self.listings.get(self.ana.id, draft.listing_id).status, "Draft")

    def test_only_the_listing_owner_can_publish(self):
        draft = self._publishable_draft()
        with self.assertRaises(OwnerListingError) as ctx:
            self.listings.publish(self.ben.id, draft.listing_id)
        self.assertIn("not found", str(ctx.exception))
        self.assertEqual(self.listings.get(self.ana.id, draft.listing_id).status, "Draft")

    def test_publish_persists_status_without_changing_listing_assets(self):
        draft = self._publishable_draft()
        photo_before = [tuple(row) for row in self.rows(
            "SELECT listing_key, file_path, position, is_primary FROM listing_photos")]
        availability_before = [tuple(row) for row in self.rows(
            "SELECT listing_id, weekday, start_minute, end_minute FROM listing_availability")]

        published = self.listings.publish(self.ana.id, draft.listing_id)
        reopened = OwnerListingService(self.db, self.workspaces, CATEGORIES)
        self.assertEqual(published.status, "Published")
        self.assertEqual(reopened.get(self.ana.id, draft.listing_id).status, "Published")
        self.assertEqual(reopened.list_drafts(self.ana.id), [])
        self.assertEqual(
            [(item.listing_id, item.status) for item in reopened.list_listings(self.ana.id)],
            [(draft.listing_id, "Published")])
        self.assertEqual(reopened.get(self.ana.id, draft.listing_id).extra_rules,
                         "Return with the cover.")
        self.assertEqual([tuple(row) for row in self.rows(
            "SELECT listing_key, file_path, position, is_primary FROM listing_photos")],
            photo_before)
        self.assertEqual([tuple(row) for row in self.rows(
            "SELECT listing_id, weekday, start_minute, end_minute FROM listing_availability")],
            availability_before)

    def test_other_tables_are_untouched(self):
        before = self.rows("SELECT * FROM students ORDER BY id")
        self.listings.create_draft(self.ana.id, good())
        self.assertEqual(self.rows("SELECT * FROM students ORDER BY id"), before)


# ======================================================================
# 3. THE PAGES AND THE DASHBOARD (Qt, offscreen)
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class UiTests(Base):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def build(self, student):
        from app.dashboard_screen import StudentDashboard
        from app.request_service import RequestService
        from app.sample_data import build_empty_data
        dash = StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=RequestService(self.db))
        self.addCleanup(dash.deleteLater)
        return dash

    def owner_dash(self, student=None):
        student = student or self.ana
        self.approve(student)
        dash = self.build(student)
        self.assertTrue(dash.switch_workspace("student_owner"))
        return dash

    def fill(self, page, **changes):
        data = good(**changes)
        page.title_input.setText(data["title"])
        page.category_combo.setCurrentText(data["category"]) if data["category"] else None
        page.condition_combo.setCurrentText(data["condition"]) if data["condition"] else None
        page.description_input.setPlainText(data["description"])
        page.days_input.setValue(data["max_borrow_days"])
        page.rules_input.setPlainText(data["extra_rules"])

    def test_empty_my_listings_has_add_listing_buttons(self):
        dash = self.owner_dash()
        dash.owner_rail.buttons["my_listings"].click()
        page = dash.owner_listings_page
        self.assertIs(dash.content_stack.currentWidget(), page)
        self.assertFalse(page.empty_state.isHidden())
        self.assertEqual(page.empty_title.text(), "No listings yet")
        page.empty_add_button.click()
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_form_page)
        self.assertEqual(dash.owner_form_page.title_label.text(), "Add Listing")
        self.assertEqual(dash.owner_rail.selected_key, "my_listings")

    def test_add_save_show_reopen_and_edit_a_draft(self):
        dash = self.owner_dash()
        listings, form = dash.owner_listings_page, dash.owner_form_page
        listings.add_button.click() if not listings.add_button.isHidden() else listings.empty_add_button.click()
        self.fill(form)
        form.save_button.click()
        self.assertIs(dash.content_stack.currentWidget(), listings)
        self.assertEqual([l.title for l in listings.listings], ["Casio fx-991EX Calculator"])
        self.assertTrue(listings.empty_state.isHidden())
        self.assertIn("saved", listings.banner.text())
        self.assertEqual(len(self.rows()), 1)
        card = listings.cards[0]
        card.edit_button.click()                                   # reopen
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertTrue(form.is_editing)
        self.assertEqual(form.title_label.text(), "Edit Draft")
        self.assertEqual(form.title_input.text(), "Casio fx-991EX Calculator")
        self.assertEqual(form.category_combo.currentText(), "Mathematics")
        self.assertEqual(form.condition_combo.currentText(), "Good")
        self.assertEqual(form.days_input.value(), 2)
        self.assertEqual(form.rules_input.toPlainText(), "Return with the cover.")
        form.title_input.setText("Casio Calculator")
        form.condition_combo.setCurrentText("Fair")
        form.save_button.click()
        self.assertEqual(len(self.rows()), 1)                       # edited, not duplicated
        self.assertEqual(listings.listings[0].title, "Casio Calculator")
        self.assertEqual(listings.listings[0].condition, "Fair")

    def test_stock_quantity_is_saved_and_tracked_as_an_unsaved_form_change(self):
        dash = self.owner_dash()
        listings, form = dash.owner_listings_page, dash.owner_form_page
        listings.empty_add_button.click()
        self.fill(form)
        self.assertEqual(form.stock_input.value(), 1)
        form.stock_input.setValue(3)
        self.assertTrue(form.has_unsaved_changes)
        form.save_button.click()

        listing = self.listings.list_listings(self.ana.id)[0]
        self.assertEqual((listing.stock_quantity, listing.available_copies), (3, 3))
        self.assertIn("Total copies: 3 · Available copies: 3",
                      listings.cards[0].stock_label.text())
        listing_id = listing.listing_id

        listings.cards[0].edit_button.click()
        self.assertEqual(form.stock_input.value(), 3)
        self.assertFalse(form.has_unsaved_changes)
        form.stock_input.setValue(2)
        self.assertTrue(form.has_unsaved_changes)
        form.save_button.click()
        updated = self.listings.get(self.ana.id, listing_id)
        self.assertEqual((updated.listing_id, updated.status), (listing_id, "Draft"))
        self.assertEqual((updated.stock_quantity, updated.available_copies), (2, 2))

        listings.cards[0].edit_button.click()
        form.stock_input.setValue(0)
        form.save_button.click()
        self.assertIn("Out of Stock", listings.cards[0].stock_label.text())
        listings.cards[0].preview_button.click()
        preview = dash._owner_preview_page
        self.assertEqual(preview.total_copies_label.text(), "Total copies · 0")
        self.assertEqual(
            preview.available_copies_label.text(),
            "Available copies · 0 (Out of Stock)")

    def test_listing_preview_shows_saved_details_and_photos_without_changing_draft(self):
        from PySide6.QtGui import QColor, QPixmap
        from PySide6.QtWidgets import QPushButton, QWidget
        from app.photo_service import PhotoService

        self.approve(self.ana)
        listing = self.listings.create_draft(
            self.ana.id, good(), {0: [(9 * 60, 17 * 60)]})
        photo_paths = []
        for index, color in enumerate((QColor("#7175F5"), QColor("#F4A8C4"))):
            path = os.path.join(self.tmp.name, f"preview-{index}.png")
            pixmap = QPixmap(120, 80)
            pixmap.fill(color)
            self.assertTrue(pixmap.save(path))
            photo_paths.append(path)
            PhotoService(self.db, self.tmp.name).add_photo(listing.listing_id, path)

        before = tuple(self.rows("SELECT listing_id, title, updated_at, status FROM owner_listings")[0])
        dash = self.build(self.ana)
        self.assertTrue(dash.switch_workspace("student_owner"))
        listings = dash.owner_listings_page
        dash.owner_rail.buttons["my_listings"].click()
        self.assertEqual([item.listing_id for item in listings.listings], [listing.listing_id])
        card = listings.cards[0]
        card.preview_button.click()

        preview = dash._owner_preview_page
        self.assertIsInstance(preview, QWidget)
        self.assertIs(dash.content_stack.currentWidget(), preview)
        self.assertFalse(dash.owner_rail.isHidden())
        self.assertIn("Back to My Listings", preview.back_button.text())
        self.assertIn("Mathematics", preview.category_label.text())
        self.assertIn("Good", preview.condition_label.text())
        self.assertEqual(preview.total_copies_label.text(), "Total copies · 1")
        self.assertEqual(preview.available_copies_label.text(), "Available copies · 1")
        self.assertIn("Mon", preview.availability_label.text())
        self.assertEqual(preview.description_label.text(), listing.description)
        self.assertEqual(len(preview.photo_buttons), 2)
        preview.photo_buttons[1].click()
        self.assertEqual(preview._selected_photo, 1)
        dash.show()
        dash.resize(1200, 700)
        self.app.processEvents()
        from app.dashboard_widgets import ReflowGrid
        grids = preview.findChildren(ReflowGrid)
        self.assertEqual(grids, [preview.main_grid])
        self.assertEqual(preview.main_grid._columns, 2)
        info_layout = preview.information_widget.layout()
        self.assertEqual(
            [info_layout.itemAt(index).widget()
             for index in range(info_layout.count())],
            list(preview.information_sections))
        self.assertEqual(
            [preview.main_grid.layout().getItemPosition(index)[:2]
             for index in range(2)],
            [(0, 0), (0, 1)])
        dash.resize(480, 500)
        self.app.processEvents()
        self.assertEqual(preview.main_grid._columns, 1)
        self.assertEqual(
            [preview.main_grid.layout().getItemPosition(index)[:2]
             for index in range(2)],
            [(0, 0), (1, 0)])
        preview.description_label.setText("Short description.")
        self.app.processEvents()
        short_description_height = preview.description_label.height()
        preview.description_label.setText("A detailed description. " * 80)
        self.app.processEvents()
        self.assertGreater(preview.description_label.height(), short_description_height)
        preview.photo_label.click()
        self.app.processEvents()
        self.assertFalse(preview.image_viewer.isHidden())
        scale_before_zoom = preview._image_scale
        zoom_in = next(button for button in preview.image_viewer.findChildren(QPushButton)
            if button.text() == "Zoom In")
        zoom_in.click()
        self.assertGreater(preview._image_scale, scale_before_zoom)
        fit = next(button for button in preview.image_viewer.findChildren(QPushButton)
            if button.text() == "Reset / Fit")
        fit.click()
        preview.viewer_close_button.click()
        self.assertTrue(preview.image_viewer.isHidden())
        self.assertEqual(tuple(self.rows(
            "SELECT listing_id, title, updated_at, status FROM owner_listings")[0]), before)

        preview.back_button.click()
        self.assertIs(dash.content_stack.currentWidget(), listings)
        self.assertEqual([item.listing_id for item in listings.listings], [listing.listing_id])
        self.assertIs(listings.cards[0], card)
        self.assertEqual(dash.owner_rail.selected_key, "my_listings")
        after = tuple(self.rows("SELECT listing_id, title, updated_at, status FROM owner_listings")[0])
        self.assertEqual(after, before)

    def test_errors_keep_the_form_open_with_the_text(self):
        dash = self.owner_dash()
        form = dash.owner_form_page
        dash.owner_listings_page.empty_add_button.click()
        self.fill(form, title="Calculator", condition="")
        form.condition_combo.setCurrentIndex(0)
        form.save_button.click()
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertFalse(form.message.isHidden())
        self.assertEqual(form.title_input.text(), "Calculator")
        self.assertEqual(self.rows(), [])

    def test_drafts_come_back_after_restart_and_stay_private(self):
        dash = self.owner_dash()
        dash.owner_listings_page.empty_add_button.click()
        self.fill(dash.owner_form_page)
        dash.owner_form_page.save_button.click()
        again = self.build(self.ana)                                  # "restart"
        again.switch_workspace("student_owner")
        again.owner_rail.buttons["my_listings"].click()
        self.assertEqual(len(again.owner_listings_page.listings), 1)
        self.assertEqual(again.owner_dashboard_page.listings_tile.value_label.text(), "1")
        other = self.owner_dash(self.ben)
        other.owner_rail.buttons["my_listings"].click()
        self.assertEqual(other.owner_listings_page.listings, [])

    def test_publish_button_requires_confirmation_and_rejected_draft_stays_draft(self):
        dash = self.owner_dash()
        draft = self.listings.create_draft(self.ana.id, good())
        dash.owner_rail.buttons["my_listings"].click()
        card = dash.owner_listings_page.cards[0]

        dash._confirm_listing_publish = lambda _title: False
        card.publish_button.click()
        self.assertEqual(self.listings.get(self.ana.id, draft.listing_id).status, "Draft")
        self.assertEqual(len(dash.owner_listings_page.listings), 1)

        dash._confirm_listing_publish = lambda _title: True
        card.publish_button.click()
        self.assertEqual(self.listings.get(self.ana.id, draft.listing_id).status, "Draft")
        self.assertIn("pickup day", dash.owner_listings_page.banner.text())
        self.assertIn("usable listing photo", dash.owner_listings_page.banner.text())

    def test_publish_button_updates_status_and_remains_visible_after_restart(self):
        dash = self.owner_dash()
        draft = self.listings.create_draft(self.ana.id, good(), {0: [(540, 720)]})
        photo_path = Path(self.tmp.name) / "ui-publish.png"
        photo_path.write_bytes(b"test image")
        PhotoService(self.db, Path(self.tmp.name) / "photos").add_photo(
            draft.listing_id, photo_path)
        dash.owner_rail.buttons["my_listings"].click()
        dash._confirm_listing_publish = lambda _title: True

        dash.owner_listings_page.cards[0].publish_button.click()
        self.assertEqual(self.listings.get(self.ana.id, draft.listing_id).status, "Published")
        self.assertIn("now appears in the Catalog", dash.owner_listings_page.banner.text())
        self.assertFalse(dash.owner_listings_page.cards[0].edit_button.isHidden())
        self.assertTrue(dash.owner_listings_page.cards[0].publish_button.isHidden())

        again = self.build(self.ana)
        self.assertTrue(again.switch_workspace("student_owner"))
        again.owner_rail.buttons["my_listings"].click()
        self.assertEqual(
            [(item.listing_id, item.status) for item in again.owner_listings_page.listings],
            [(draft.listing_id, "Published")])
        self.assertEqual(again.owner_listings_page.cards[0].status_label.text(), "Published")

    def test_listing_action_menu_pauses_resumes_and_soft_deletes_catalog_item(self):
        dash = self.owner_dash()
        listing = self._publishable_draft()
        other = self.listings.create_draft(
            self.ana.id, good(title="Other publishable listing"), {1: [(600, 780)]})
        PhotoService(self.db, Path(self.tmp.name) / "photos").add_photo(
            other.listing_id, Path(self.tmp.name) / "publishable.png")
        self.listings.publish(
            self.ana.id, listing.listing_id, photos_dir=Path(self.tmp.name) / "photos")
        self.listings.publish(
            self.ana.id, other.listing_id, photos_dir=Path(self.tmp.name) / "photos")
        dash._refresh_published_catalog()
        dash._reload_owner_listings()

        card = next(card for card in dash.owner_listings_page.cards
                    if card.listing_id == listing.listing_id)
        self.assertEqual(card.status_label.text(), "Published")
        self.assertTrue(hasattr(card, "pause_action"))
        self.assertIn(listing.listing_id, {
            item.listing_key for item in dash.catalog_page._items
            if item.ownership == "student" and item.record_id})

        dash._confirm_listing_pause = lambda _title: False
        card.pause_action.trigger()
        self.assertEqual(self.listings.get(self.ana.id, listing.listing_id).status, "Published")
        dash._confirm_listing_pause = lambda _title: True
        card.pause_action.trigger()
        paused_card = next(card for card in dash.owner_listings_page.cards
                           if card.listing_id == listing.listing_id)
        self.assertEqual(paused_card.status_label.text(), "Paused")
        self.assertTrue(hasattr(paused_card, "resume_action"))
        owner_ids = {
            item.listing_key for item in dash.catalog_page._items
            if item.ownership == "student" and item.record_id}
        self.assertNotIn(listing.listing_id, owner_ids)
        self.assertIn(other.listing_id, owner_ids)

        paused_card.resume_action.trigger()
        self.assertEqual(self.listings.get(self.ana.id, listing.listing_id).status, "Published")
        owner_ids = {
            item.listing_key for item in dash.catalog_page._items
            if item.ownership == "student" and item.record_id}
        self.assertIn(listing.listing_id, owner_ids)

        resumed_card = next(card for card in dash.owner_listings_page.cards
                            if card.listing_id == listing.listing_id)
        dash._confirm_listing_delete = lambda _title: False
        resumed_card.delete_action.trigger()
        self.assertEqual(self.listings.get(self.ana.id, listing.listing_id).status, "Published")
        dash._confirm_listing_delete = lambda _title: True
        resumed_card.delete_action.trigger()
        self.assertNotIn(listing.listing_id, {
            item.listing_id for item in dash.owner_listings_page.listings})
        self.assertIn(other.listing_id, {
            item.listing_id for item in dash.owner_listings_page.listings})
        self.assertNotIn(listing.listing_id, {
            item.listing_key for item in dash.catalog_page._items
            if item.ownership == "student" and item.record_id})
        self.assertIn(other.listing_id, {
            item.listing_key for item in dash.catalog_page._items
            if item.ownership == "student" and item.record_id})
        self.assertTrue(self.rows(
            "SELECT photo_id FROM listing_photos WHERE listing_key = ?",
            (listing.listing_id,)))

    def test_published_listing_edit_confirms_saves_without_replacing_id_or_photos(self):
        from PySide6.QtGui import QColor, QPixmap
        from app.owner_listing_photos import OwnerListingPhotoService
        from app.photo_service import PhotoService

        dash = self.owner_dash()
        photos_dir = Path(self.tmp.name) / "photos"
        original_photo = Path(self.tmp.name) / "original.png"
        staged_photo = Path(self.tmp.name) / "staged.png"
        for path, color in ((original_photo, QColor("#7175F5")),
                            (staged_photo, QColor("#F4A8C4"))):
            image = QPixmap(100, 80)
            image.fill(color)
            self.assertTrue(image.save(str(path)))

        listing = self.listings.create_draft(
            self.ana.id, good(), {0: [(540, 720)]})
        photo_service = PhotoService(self.db, photos_dir)
        original = photo_service.add_photo(listing.listing_id, original_photo)
        self.listings.publish(self.ana.id, listing.listing_id, photos_dir=photos_dir)
        dash._owner_photo_service = OwnerListingPhotoService(
            self.db, self.listings, photos_dir=photos_dir)
        dash._refresh_published_catalog()
        dash._reload_owner_listings()

        card = next(
            card for card in dash.owner_listings_page.cards
            if card.listing_id == listing.listing_id)
        self.assertFalse(card.edit_button.isHidden())
        card.edit_button.click()
        form = dash.owner_form_page
        self.assertTrue(form.is_published)
        self.assertEqual(form.title_label.text(), "Edit Published Listing")
        form.title_input.setText("Revised Calculator")
        form.description_input.setPlainText("Revised description for the catalog listing.")
        form.category_combo.setCurrentText("Electronics")
        form.condition_combo.setCurrentText("Fair")
        form.days_input.setValue(8)
        form.stock_input.setValue(4)
        form.photos.add_requested.emit([str(staged_photo)])

        before_cancel = tuple(self.rows(
            "SELECT listing_id, title, status, stock_quantity, updated_at "
            "FROM owner_listings"))
        confirm_calls = []
        dash._confirm_published_listing_save = (
            lambda title: confirm_calls.append(title) or False)
        form.save_button.click()
        self.assertEqual(confirm_calls, ["Revised Calculator"])
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertEqual(tuple(self.rows(
            "SELECT listing_id, title, status, stock_quantity, updated_at "
            "FROM owner_listings")),
            before_cancel)
        self.assertEqual(len(photo_service.photos_for(listing.listing_id)), 1)
        self.assertTrue(form.has_unsaved_changes)

        dash._confirm_published_listing_save = lambda _title: True
        form.save_button.click()
        saved = self.listings.get(self.ana.id, listing.listing_id)
        self.assertEqual(saved.listing_id, listing.listing_id)
        self.assertEqual(saved.status, "Published")
        self.assertEqual(saved.title, "Revised Calculator")
        self.assertEqual(saved.description, "Revised description for the catalog listing.")
        self.assertEqual(saved.category, "Electronics")
        self.assertEqual(saved.condition, "Fair")
        self.assertEqual(saved.max_borrow_days, 8)
        self.assertEqual((saved.stock_quantity, saved.available_copies), (4, 4))
        saved_photos = photo_service.photos_for(listing.listing_id)
        self.assertEqual(len(saved_photos), 2)
        self.assertIn(original.photo_id, {photo.photo_id for photo in saved_photos})
        catalog_item = next(
            item for item in dash.catalog_page._items
            if item.listing_key == listing.listing_id)
        self.assertEqual(catalog_item.title, saved.title)
        self.assertEqual(catalog_item.description, saved.description)
        self.assertEqual(catalog_item.condition, saved.condition)
        self.assertEqual(catalog_item.max_borrow_days, saved.max_borrow_days)
        self.assertEqual((catalog_item.copies_total, catalog_item.copies_available), (4, 4))

    def test_published_edit_save_and_discard_navigation_are_guarded(self):
        dash = self.owner_dash()
        listing = self.listings.create_draft(self.ana.id, good())
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE owner_listings SET status = 'Published' WHERE listing_id = ?",
            (listing.listing_id,))
        conn.commit()
        conn.close()
        dash._reload_owner_listings()

        card = next(
            card for card in dash.owner_listings_page.cards
            if card.listing_id == listing.listing_id)
        card.edit_button.click()
        form = dash.owner_form_page
        form.title_input.setText("Saved published title")
        dash._choose_listing_leave_action = lambda: "save"
        confirmations = []
        dash._confirm_published_listing_save = (
            lambda title: confirmations.append(title) or False)

        dash.owner_rail.buttons["settings"].click()
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertEqual(self.listings.get(self.ana.id, listing.listing_id).title,
                         listing.title)
        self.assertEqual(confirmations, ["Saved published title"])
        self.assertIsNone(getattr(dash, "_pending_form_leave", None))

        dash._confirm_published_listing_save = lambda _title: True
        dash.owner_rail.buttons["settings"].click()
        saved = self.listings.get(self.ana.id, listing.listing_id)
        self.assertIs(dash.content_stack.currentWidget(), dash._pages["settings"])
        self.assertEqual(saved.title, "Saved published title")
        self.assertEqual(saved.status, "Published")

        dash.owner_rail.buttons["my_listings"].click()
        next(card for card in dash.owner_listings_page.cards
             if card.listing_id == listing.listing_id).edit_button.click()
        form.description_input.setPlainText("This edit will be discarded.")
        dash._choose_listing_leave_action = lambda: "discard"
        dash.owner_rail.buttons["owner_dashboard"].click()
        after_discard = self.listings.get(self.ana.id, listing.listing_id)
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_dashboard_page)
        self.assertEqual(after_discard.title, saved.title)
        self.assertEqual(after_discard.description, saved.description)
        self.assertEqual(after_discard.status, "Published")

    def test_published_listing_appears_in_catalog_and_opens_with_saved_data(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage
        from PySide6.QtTest import QTest
        from app.item_details_screen import item_facts
        from app.preference_service import VIEW_LIST

        dash = self.owner_dash()
        published = self.listings.create_draft(
            self.ana.id,
            good(title="Owner Published Soldering Kit", category="Mathematics"),
            {0: [(540, 720)]})
        draft = self.listings.create_draft(
            self.ana.id, good(title="Private Draft Multimeter"), {1: [(600, 720)]})
        source = Path(self.tmp.name) / "catalog-photo.png"
        image = QImage(96, 72, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.blue)
        self.assertTrue(image.save(str(source)))
        PhotoService(self.db, Path(self.tmp.name) / "photos").add_photo(
            published.listing_id, source)
        dash._reload_owner_listings()
        dash._confirm_listing_publish = lambda _title: True
        publish_card = next(
            card for card in dash.owner_listings_page.cards
            if card.listing_id == published.listing_id)
        publish_card.publish_button.click()

        self.assertIn(
            published.listing_id,
            {item.listing_key for item in dash.catalog_page._items})
        self.assertTrue(dash.switch_workspace("student"))
        dash.go_to("catalog")
        catalog = dash.catalog_page
        owner_item = next(
            item for item in catalog._items if item.listing_key == published.listing_id)
        self.assertEqual(owner_item.creator, "Ana Reyes")
        self.assertEqual(owner_item.category_label, "Mathematics")
        self.assertEqual(owner_item.condition, "Good")
        self.assertEqual(owner_item.pickup_schedule, {0: [(540, 720)]})
        self.assertFalse(owner_item.request_enabled)
        self.assertNotIn(draft.listing_id, {item.listing_key for item in catalog._items})

        catalog.filter_panel.combo("category").setCurrentText("Mathematics")
        catalog.filter_panel.combo("ownership").setCurrentText("Student-Owned")
        catalog.filter_panel.combo("availability").setCurrentText("Available")
        catalog.search_input.setText("Owner Published Soldering Kit")
        self.assertEqual(catalog.visible_items, [owner_item])
        catalog.set_bookmarked_items([owner_item])
        self.assertEqual(catalog.bookmarked_items[0].listing_key, published.listing_id)
        self.assertFalse(catalog._cards[catalog._items.index(owner_item)].request_button.isEnabled())

        catalog.set_view_mode(VIEW_LIST)
        self.assertEqual(catalog.visible_rows[0].item.listing_key, published.listing_id)
        dash.show()
        self.app.processEvents()
        QTest.mouseClick(catalog.visible_rows[0], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        details = dash.item_details_page
        self.assertIs(dash.content_stack.currentWidget(), details)
        self.assertEqual(details.item.listing_key, published.listing_id)
        self.assertEqual(details.photo_paths, self._expected_catalog_photo_paths(published.listing_id))
        self.assertFalse(details.request_button.isEnabled())
        facts = item_facts(owner_item)
        self.assertIn(("Condition", "Good"), facts["About this item"])
        self.assertIn(("Owner", "Ana Reyes"), facts["Owner and pickup"])
        self.assertIn("Mon", facts["Owner and pickup"][-1][1])
        self.assertEqual(facts["Description"][0][1], good()["description"])

        details.save_button.click()
        self.assertEqual(
            self.rows("SELECT listing_key FROM saved_items WHERE student_id = ?",
                      (self.ana.id,))[0]["listing_key"],
            published.listing_id)
        self.assertIn(owner_item, dash.my_list_page.saved_items)

    def _expected_catalog_photo_paths(self, listing_id):
        return [photo.path for photo in PhotoService(
            self.db, Path(self.tmp.name) / "photos").photos_for(listing_id)]

    def test_cancel_returns_to_my_listings_without_saving(self):
        dash = self.owner_dash()
        dash.owner_listings_page.empty_add_button.click()
        self.fill(dash.owner_form_page)
        dash._choose_listing_leave_action = lambda: "discard"
        dash.owner_form_page.cancel_button.click()
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_listings_page)
        self.assertEqual(self.rows(), [])

    def test_unsaved_back_can_keep_editing_or_discard_new_listing(self):
        dash = self.owner_dash()
        form = dash.owner_form_page
        dash.owner_listings_page.empty_add_button.click()
        self.fill(form)
        self.assertTrue(form.has_unsaved_changes)

        dash._choose_listing_leave_action = lambda: "keep"
        form.back_button.click()
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertEqual(form.title_input.text(), good()["title"])

        dash._choose_listing_leave_action = lambda: "discard"
        form.back_button.click()
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_listings_page)
        self.assertEqual(self.rows(), [])

    def test_actual_owner_sidebar_click_keeps_or_discards_dirty_add_form(self):
        dash = self.owner_dash()
        form = dash.owner_form_page
        dash.owner_listings_page.empty_add_button.click()
        self.fill(form, title="Unsaved calculator")
        form.availability_editor.weekdays_button.click()
        actions = []
        dash._choose_listing_leave_action = lambda: actions.append("prompt") or "keep"

        dash.owner_rail.buttons["owner_dashboard"].click()
        self.assertEqual(actions, ["prompt"])
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertEqual(form.title_input.text(), "Unsaved calculator")
        self.assertEqual(form.category_combo.currentText(), "Mathematics")
        self.assertEqual(sorted(form.availability()), [0, 1, 2, 3, 4])
        self.assertEqual(dash.owner_rail.selected_key, "my_listings")
        self.assertEqual(self.rows(), [])

        dash._choose_listing_leave_action = lambda: "discard"
        dash.owner_rail.buttons["owner_dashboard"].click()
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_dashboard_page)
        self.assertEqual(self.rows(), [])

    def test_actual_owner_sidebar_click_preserves_then_discards_edit_and_staged_photo(self):
        from PySide6.QtGui import QColor, QPixmap
        from app.owner_listing_photos import OwnerListingPhotoService

        self.approve(self.ana)
        original_schedule = {0: [(9 * 60, 17 * 60)]}
        listing = self.listings.create_draft(self.ana.id, good(), original_schedule)
        saved_path = os.path.join(self.tmp.name, "existing.png")
        staged_path = os.path.join(self.tmp.name, "staged-sidebar.png")
        for path, color in ((saved_path, QColor("#7175F5")),
                            (staged_path, QColor("#F4A8C4"))):
            pixmap = QPixmap(100, 80)
            pixmap.fill(color)
            self.assertTrue(pixmap.save(path))
        photos = OwnerListingPhotoService(
            self.db, self.listings, photos_dir=os.path.join(self.tmp.name, "photos"))
        photos.add_photo(self.ana.id, listing.listing_id, saved_path)
        dash = self.build(self.ana)
        dash._owner_photo_service = photos
        self.assertTrue(dash.switch_workspace("student_owner"))
        dash.owner_listings_page.cards[0].edit_button.click()
        form = dash.owner_form_page
        form.title_input.setText("Changed but not saved")
        form.category_combo.setCurrentText("Programming")
        form.availability_editor.weekdays_button.click()
        form.photos.add_requested.emit([staged_path])
        self.assertTrue(form.has_unsaved_changes)

        decisions = []
        dash._choose_listing_leave_action = lambda: decisions.append("asked") or "keep"
        dash.owner_rail.buttons["settings"].click()
        self.assertEqual(decisions, ["asked"])
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertEqual(form.title_input.text(), "Changed but not saved")
        self.assertEqual(form.category_combo.currentText(), "Programming")
        self.assertEqual(sorted(form.availability()), [0, 1, 2, 3, 4])
        self.assertEqual(form.photos.count, 2)
        self.assertEqual(dash.owner_rail.selected_key, "my_listings")

        dash._choose_listing_leave_action = lambda: "discard"
        dash.owner_rail.buttons["owner_dashboard"].click()
        saved = self.listings.get(self.ana.id, listing.listing_id)
        self.assertEqual(saved.title, listing.title)
        self.assertEqual(saved.category, listing.category)
        self.assertEqual(self.listings.get_availability(
            self.ana.id, listing.listing_id).as_dict(), original_schedule)
        self.assertEqual(len(photos.photos(self.ana.id, listing.listing_id)), 1)
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_dashboard_page)

    def test_actual_owner_sidebar_save_draft_and_leave_persists_before_navigation(self):
        dash = self.owner_dash()
        dash.owner_listings_page.empty_add_button.click()
        form = dash.owner_form_page
        self.fill(form, title="Saved from sidebar")
        dash._choose_listing_leave_action = lambda: "save"

        dash.owner_rail.buttons["owner_dashboard"].click()

        self.assertIs(dash.content_stack.currentWidget(), dash.owner_dashboard_page)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["title"], "Saved from sidebar")
        self.assertEqual(self.rows()[0]["status"], "Draft")

    def test_save_draft_and_leave_only_navigates_after_success(self):
        dash = self.owner_dash()
        form = dash.owner_form_page
        dash.owner_listings_page.empty_add_button.click()
        self.fill(form)
        dash._choose_listing_leave_action = lambda: "save"
        form.back_button.click()
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_listings_page)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["status"], "Draft")

        listing = self.listings.list_drafts(self.ana.id)[0]
        dash.owner_listings_page.cards[0].edit_button.click()
        form.title_input.setText("")
        before = self.listings.get(self.ana.id, listing.listing_id).title
        dash._choose_listing_leave_action = lambda: "save"
        form.back_button.click()
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertEqual(self.listings.get(self.ana.id, listing.listing_id).title, before)
        self.assertEqual(form.title_input.text(), "")
        self.assertIsNone(getattr(dash, "_pending_form_leave", None))

    def test_discard_staged_photo_does_not_change_saved_photos(self):
        from PySide6.QtGui import QColor, QPixmap
        from app.owner_listing_photos import OwnerListingPhotoService

        self.approve(self.ana)
        listing = self.listings.create_draft(self.ana.id, good())
        saved_path = os.path.join(self.tmp.name, "saved.png")
        added_path = os.path.join(self.tmp.name, "staged.png")
        for path, color in ((saved_path, QColor("#7175F5")),
                            (added_path, QColor("#F4A8C4"))):
            pixmap = QPixmap(100, 80)
            pixmap.fill(color)
            self.assertTrue(pixmap.save(path))
        photos = OwnerListingPhotoService(self.db, self.listings, photos_dir=self.tmp.name)
        photos.add_photo(self.ana.id, listing.listing_id, saved_path)
        dash = self.build(self.ana)
        dash._owner_photo_service = photos
        self.assertTrue(dash.switch_workspace("student_owner"))
        dash.owner_listings_page.cards[0].edit_button.click()
        form = dash.owner_form_page
        self.assertFalse(form.has_unsaved_changes)
        form.photos.add_requested.emit([added_path])
        self.assertTrue(form.has_unsaved_changes)
        self.assertEqual(form.photos.count, 2)

        dash._choose_listing_leave_action = lambda: "discard"
        form.back_button.click()
        self.assertEqual(len(photos.photos(self.ana.id, listing.listing_id)), 1)
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_listings_page)

    def test_window_close_is_blocked_until_dirty_form_leave_is_confirmed(self):
        from PySide6.QtGui import QCloseEvent
        from app.main_window import MainWindow
        from app.request_service import RequestService

        self.approve(self.ana)
        window = MainWindow(auth_service=self.auth, request_service=RequestService(self.db))
        self.addCleanup(window.deleteLater)
        window.show_dashboard(self.ana)
        dash = window.dashboard
        self.assertTrue(dash.switch_workspace("student_owner"))
        dash.owner_listings_page.empty_add_button.click()
        dash.owner_form_page.title_input.setText("Unsaved listing")
        dash._choose_listing_leave_action = lambda: "keep"
        event = QCloseEvent()
        window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_form_page)

    def test_workspace_switch_waits_for_dirty_form_decision(self):
        dash = self.owner_dash()
        dash.owner_listings_page.empty_add_button.click()
        form = dash.owner_form_page
        form.title_input.setText("Unsaved listing")

        dash._choose_listing_leave_action = lambda: "keep"
        self.assertFalse(dash.switch_workspace("student"))
        self.assertEqual(dash.current_workspace, "student_owner")
        self.assertIs(dash.content_stack.currentWidget(), form)

        dash._choose_listing_leave_action = lambda: "discard"
        self.assertFalse(dash.switch_workspace("student"))
        self.assertEqual(dash.current_workspace, "student")
        self.assertEqual(self.rows(), [])

    def test_actual_workspace_switch_control_is_guarded(self):
        dash = self.owner_dash()
        dash.owner_listings_page.empty_add_button.click()
        form = dash.owner_form_page
        form.title_input.setText("Keep me until confirmed")
        dash._choose_listing_leave_action = lambda: "keep"

        dash.owner_rail.buttons["switch"].click()
        self.assertEqual(dash.current_workspace, "student_owner")
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertEqual(form.title_input.text(), "Keep me until confirmed")

        dash._choose_listing_leave_action = lambda: "discard"
        dash.owner_rail.buttons["switch"].click()
        self.assertEqual(dash.current_workspace, "student")
        self.assertEqual(self.rows(), [])

    def test_actual_logout_control_is_guarded_before_logout_confirmation(self):
        dash = self.owner_dash()
        dash.owner_listings_page.empty_add_button.click()
        form = dash.owner_form_page
        form.title_input.setText("Keep me until confirmed")
        dash._choose_listing_leave_action = lambda: "keep"
        logout_signals = []
        dash.logout_requested.connect(lambda: logout_signals.append(True))
        dash.owner_rail.buttons["logout"].click()
        self.assertEqual(logout_signals, [])
        self.assertIs(dash.content_stack.currentWidget(), form)

        dash._choose_listing_leave_action = lambda: "discard"
        dash._confirm_logout = lambda: True
        dash.owner_rail.buttons["logout"].click()
        self.assertEqual(logout_signals, [True])
        self.assertEqual(self.rows(), [])

    def test_regular_students_cannot_reach_listing_management(self):
        dash = self.build(self.cai)
        self.assertFalse(dash.switch_workspace("student_owner"))
        dash._on_add_listing()
        dash._on_listing_save(good(), None)
        self.assertEqual(self.rows(), [])
        self.assertEqual(dash.current_workspace, "student")

    def test_withdrawn_approval_blocks_saving_without_losing_form_changes(self):
        application = self.approve(self.ana)
        dash = self.build(self.ana)
        dash.switch_workspace("student_owner")
        dash.owner_listings_page.empty_add_button.click()
        self.set_status(application.application_id, "Rejected")
        self.fill(dash.owner_form_page)
        dash.owner_form_page.save_button.click()
        self.assertEqual(dash.current_workspace, "student_owner")
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_form_page)
        self.assertEqual(dash.owner_form_page.title_input.text(), good()["title"])
        self.assertFalse(dash.owner_form_page.message.isHidden())
        self.assertEqual(self.rows(), [])

    def test_workspace_switching_and_student_features_still_work(self):
        dash = self.owner_dash()
        dash.owner_rail.buttons["switch"].click()
        self.assertEqual(dash.current_workspace, "student")
        dash.go_to("catalog")
        self.assertIs(dash.content_stack.currentWidget(), dash.catalog_page)
        dash.go_to("settings")
        dash.settings_page.workspace_switch_buttons["student_owner"].click()
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_dashboard_page)


if __name__ == "__main__":
    unittest.main()
