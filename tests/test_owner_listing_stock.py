"""Step 31E-6: owner listing stock persistence and per-copy availability."""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import connect
from app.owner_listing_service import OwnerListingError, OwnerListingService
from app.request_service import RequestError
from app.sample_data import build_empty_data
from test_student_owner_requests import OwnerRequestMixin

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


class OwnerListingStockTests(OwnerRequestMixin, unittest.TestCase):
    def stock_fields(self, quantity, **changes):
        fields = {
            "title": self.listing.title,
            "category": self.listing.category,
            "condition": self.listing.condition,
            "description": self.listing.description,
            "max_borrow_days": self.listing.max_borrow_days,
            "extra_rules": self.listing.extra_rules,
            "stock_quantity": quantity,
        }
        fields.update(changes)
        return fields

    def copy_rows(self):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(
                "SELECT state, request_id FROM owner_listing_copies "
                "WHERE listing_id = ? ORDER BY copy_id",
                (self.listing.listing_id,)).fetchall()
        finally:
            conn.close()

    def test_existing_listing_upgrade_defaults_to_one_and_keeps_saved_data(self):
        original_title = self.listing.title
        original_photo = self.photo_path.read_bytes()
        conn = sqlite3.connect(self.db)
        try:
            saved_photo = conn.execute(
                "SELECT file_path FROM listing_photos WHERE listing_key = ?",
                (self.listing.listing_id,)).fetchone()[0]
        finally:
            conn.close()
        conn = sqlite3.connect(self.db)
        try:
            conn.execute("DROP INDEX idx_owner_listing_copies_listing_state")
            conn.execute("DROP TABLE owner_listing_copies")
            conn.execute("ALTER TABLE owner_listings DROP COLUMN stock_quantity")
            conn.execute("DELETE FROM schema_migrations WHERE version = 18")
            conn.commit()
        finally:
            conn.close()

        migrated = connect(self.db)
        migrated.close()
        service = OwnerListingService(self.db, self.workspaces)
        listing = service.get(self.owner.id, self.listing.listing_id)

        self.assertEqual((listing.stock_quantity, listing.available_copies), (1, 1))
        self.assertEqual(listing.title, original_title)
        self.assertEqual(self.photo_path.read_bytes(), original_photo)
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute(
                "SELECT file_path FROM listing_photos WHERE listing_key = ?",
                (self.listing.listing_id,)).fetchone()[0], saved_photo)
            self.assertIn(18, [
                row[0] for row in conn.execute(
                    "SELECT version FROM schema_migrations")])
        finally:
            conn.close()
        self.assertEqual(len(self.copy_rows()), 1)

    def test_stock_updates_are_persisted_without_replacing_listing_or_photos(self):
        updated = self.owner_listings.update_published(
            self.owner.id, self.listing.listing_id,
            self.stock_fields(4, description="Updated description, same listing."),
        )
        updated = self.owner_listings.update_published(
            self.owner.id, self.listing.listing_id,
            {
                "title": updated.title,
                "category": updated.category,
                "condition": updated.condition,
                "description": updated.description,
                "max_borrow_days": updated.max_borrow_days,
                "extra_rules": updated.extra_rules,
            })
        reopened = OwnerListingService(self.db, self.workspaces).get(
            self.owner.id, self.listing.listing_id)

        self.assertEqual(updated.listing_id, self.listing.listing_id)
        self.assertEqual(updated.status, "Published")
        self.assertEqual(updated.stock_quantity, 4)
        self.assertEqual(updated.available_copies, 4)
        self.assertEqual(reopened.description, "Updated description, same listing.")
        self.assertEqual(reopened.stock_quantity, 4)
        conn = sqlite3.connect(self.db)
        try:
            photo = conn.execute(
                "SELECT file_path FROM listing_photos WHERE listing_key = ?",
                (self.listing.listing_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(photo)
        self.assertEqual(len(self.copy_rows()), 4)

    def test_invalid_quantities_are_rejected_without_changing_saved_stock(self):
        for quantity in (-1, True, "2", 10000):
            with self.subTest(quantity=quantity):
                with self.assertRaises(OwnerListingError):
                    self.owner_listings.update_published(
                        self.owner.id, self.listing.listing_id,
                        self.stock_fields(quantity))
                current = self.owner_listings.get(
                    self.owner.id, self.listing.listing_id)
                self.assertEqual((current.stock_quantity, current.available_copies), (1, 1))

    def test_pending_requests_do_not_reduce_available_copies(self):
        self.owner_listings.update_published(
            self.owner.id, self.listing.listing_id, self.stock_fields(3))
        self.requests.submit_requests(
            self.borrower.id, [self.draft()], "stock-pending-request")

        current = self.owner_listings.get(self.owner.id, self.listing.listing_id)
        self.assertEqual((current.stock_quantity, current.available_copies), (3, 3))

    def test_quantity_cannot_be_reduced_below_committed_copy_count(self):
        self.owner_listings.update_published(
            self.owner.id, self.listing.listing_id, self.stock_fields(3))
        request = self.requests.submit_requests(
            self.borrower.id, [self.draft()], "stock-reservation-request")[0]
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "UPDATE owner_listing_copies SET state = 'reserved', request_id = ? "
                "WHERE copy_id = (SELECT copy_id FROM owner_listing_copies "
                "WHERE listing_id = ? AND state = 'available' LIMIT 1)",
                (request.request_id, self.listing.listing_id))
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(
            self.owner_listings.get(self.owner.id, self.listing.listing_id).available_copies,
            2)
        updated = self.owner_listings.update_published(
            self.owner.id, self.listing.listing_id, self.stock_fields(1))
        self.assertEqual((updated.stock_quantity, updated.available_copies), (1, 0))
        with self.assertRaisesRegex(OwnerListingError, "cannot be less"):
            self.owner_listings.update_published(
                self.owner.id, self.listing.listing_id, self.stock_fields(0))
        unchanged = self.owner_listings.get(self.owner.id, self.listing.listing_id)
        self.assertEqual((unchanged.stock_quantity, unchanged.available_copies), (1, 0))

    def test_zero_stock_blocks_stale_catalog_request(self):
        self.owner_listings.update_published(
            self.owner.id, self.listing.listing_id, self.stock_fields(0))

        with self.assertRaisesRegex(RequestError, "out of stock"):
            self.requests.submit_requests(
                self.borrower.id, [self.draft()], "stock-out-of-stock-request")
        self.assertEqual(self.requests.list_requests(self.borrower.id), [])


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class StockCatalogUiTests(OwnerRequestMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_zero_stock_is_shown_in_catalog_and_disables_item_details_request(self):
        from app.dashboard_screen import StudentDashboard

        self.owner_listings.update_published(
            self.owner.id, self.listing.listing_id,
            {
                "title": self.listing.title,
                "category": self.listing.category,
                "condition": self.listing.condition,
                "description": self.listing.description,
                "max_borrow_days": self.listing.max_borrow_days,
                "extra_rules": self.listing.extra_rules,
                "stock_quantity": 0,
            })
        dashboard = StudentDashboard(
                build_empty_data(self.borrower.full_name),
                signed_in_email=self.borrower.email,
                student_id=self.borrower.id,
                request_service=self.requests)
        self.addCleanup(dashboard.deleteLater)
        dashboard._refresh_published_catalog()
        item = next(
            item for item in dashboard.catalog_page._items
            if item.listing_key == self.listing.listing_id)

        self.assertEqual((item.copies_total, item.copies_available), (0, 0))
        self.assertEqual(item.availability_text, "Out of Stock")
        self.assertFalse(item.request_enabled)
        self.assertIn("Out of Stock", item.request_disabled_reason)
        dashboard._open_item_details(item)
        self.assertFalse(dashboard.item_details_page.request_button.isEnabled())
        self.assertIn(
            "Out of Stock", dashboard.item_details_page.request_button.toolTip())
