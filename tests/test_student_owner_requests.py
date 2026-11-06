"""Step 32A: borrowing requests for published Student Owner listings."""
import os
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from PySide6.QtGui import QImage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth_service import AuthService  # noqa: E402
from app.catalog_screen import CatalogItem  # noqa: E402
from app.dashboard_screen import StudentDashboard  # noqa: E402
from app.my_list_screen import RequestDraft  # noqa: E402
from app.my_requests_screen import RequestStatus  # noqa: E402
from app.owner_listing_service import OwnerListingError, OwnerListingService  # noqa: E402
from app.photo_service import PhotoService  # noqa: E402
from app.request_service import RequestError, RequestService  # noqa: E402
from app.owner_workspace import OWNER_REQUESTS  # noqa: E402
from app.sample_data import build_empty_data  # noqa: E402
from app.student_owner_service import StudentOwnerService  # noqa: E402
from app.workspace_service import WorkspaceService  # noqa: E402

try:
    from PySide6.QtWidgets import (
        QApplication, QDialog, QLabel, QMessageBox, QInputDialog, QPushButton,
    )
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

PASSWORD = "correct horse"


class OwnerRequestMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "requests.db")
        self.photos_dir = Path(self.tmp.name) / "photos"
        self.auth = AuthService(self.db)
        self.borrower = self.auth.register(
            "Ana Reyes", "ana@csucc.edu.ph", PASSWORD, PASSWORD,
            student_id_number="BORROWER-32A")
        self.owner = self.auth.register(
            "Ben Cruz", "ben@csucc.edu.ph", PASSWORD, PASSWORD,
            student_id_number="OWNER-32A")
        self.owners = StudentOwnerService(self.db)
        self.workspaces = WorkspaceService(self.owners)
        self.owner_listings = OwnerListingService(self.db, self.workspaces)
        self.requests = RequestService(self.db)
        application = self.owners.submit_application(
            self.owner.id, "I have useful equipment to share with classmates.",
            "A calculator.", True)
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE student_owner_applications SET status = 'Approved' "
            "WHERE application_id = ?", (application.application_id,))
        conn.commit()
        conn.close()

        now = datetime.now().astimezone().replace(second=0, microsecond=0)
        self.pickup_at = (now + timedelta(days=7)).replace(hour=10, minute=0)
        self.schedule = {self.pickup_at.weekday(): [(540, 720)]}
        self.listing = self.owner_listings.create_draft(
            self.owner.id,
            {
                "title": "Shared Scientific Calculator",
                "category": "Mathematics",
                "condition": "Good",
                "description": "A working scientific calculator for class.",
                "max_borrow_days": 3,
                "extra_rules": "Return with the protective cover.",
            },
            self.schedule,
        )
        self.photos_dir.mkdir()
        self.photo_path = self.photos_dir / "cover.png"
        image = QImage(64, 64, QImage.Format.Format_RGB32)
        image.fill(0xFF6750A4)
        self.assertTrue(image.save(str(self.photo_path), "PNG"))
        PhotoService(self.db, self.photos_dir).add_photo(
            self.listing.listing_id, self.photo_path)
        self.owner_listings.publish(
            self.owner.id, self.listing.listing_id, photos_dir=self.photos_dir)
        self.item = CatalogItem(
            title=self.listing.title,
            creator="Ben Cruz",
            category="Mathematics",
            kind="Item",
            ownership="student",
            owner_note="Shared by Ben Cruz",
            copies_total=1,
            copies_available=1,
            record_id=self.listing.listing_id,
            description=self.listing.description,
            extra_rules=self.listing.extra_rules,
            max_borrow_days=self.listing.max_borrow_days,
            pickup_schedule=self.schedule,
            owner_student_id=self.owner.id,
        )

    def draft(self, item=None, pickup_at=None, days=2, max_days=3):
        return RequestDraft(
            item or self.item, pickup_at or self.pickup_at, days, max_days)

    def request_columns(self):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(
                "SELECT owner_listing_id, owner_student_id, item_photo_path, status "
                "FROM borrow_requests").fetchone()
        finally:
            conn.close()


class OwnerRequestServiceTests(OwnerRequestMixin, unittest.TestCase):
    def test_owner_listing_request_saves_stable_owner_schedule_and_status(self):
        saved = self.requests.submit_requests(
            self.borrower.id, [self.draft()], "owner-listing-request")
        self.assertEqual(len(saved), 1)
        request = self.requests.list_requests(self.borrower.id)[0]
        self.assertEqual(request.status, RequestStatus.PENDING_OWNER_APPROVAL)
        self.assertEqual(request.status.info.label, "Pending Owner Approval")
        self.assertTrue(request.request_id.startswith("REQ-"))
        self.assertEqual(request.owner_listing_id, self.listing.listing_id)
        self.assertEqual(request.owner_student_id, self.owner.id)
        self.assertEqual(request.preferred_pickup_at, self.pickup_at)
        self.assertEqual(request.requested_days, 2)
        self.assertEqual(request.max_days, 3)
        self.assertEqual(request.item_photo_path, str(self.photo_path))
        self.assertEqual(request.status_history[-1].status,
                         RequestStatus.PENDING_OWNER_APPROVAL)
        self.assertTrue(request.can_cancel)
        self.assertFalse(request.countdown_started)
        self.assertIsNone(request.due_at)
        self.assertEqual(
            self.request_columns(),
            (self.listing.listing_id, self.owner.id, str(self.photo_path),
             RequestStatus.PENDING_OWNER_APPROVAL.value))

    def test_duplicate_active_request_is_blocked_by_listing_id(self):
        self.requests.submit_requests(
            self.borrower.id, [self.draft()], "first-request")
        with self.assertRaisesRegex(RequestError, "already have an active request"):
            self.requests.submit_requests(
                self.borrower.id, [self.draft()], "second-request")
        self.assertEqual(len(self.requests.list_requests(self.borrower.id)), 1)

    def test_borrower_can_cancel_pending_owner_approval(self):
        request = self.requests.submit_requests(
            self.borrower.id, [self.draft()], "request-to-cancel")[0]
        cancelled = self.requests.cancel_request(self.borrower.id, request.request_id)
        self.assertEqual(cancelled.status, RequestStatus.CANCELLED)
        self.assertEqual(
            self.requests.get_request(self.borrower.id, request.request_id).status,
            RequestStatus.CANCELLED)

    def test_active_owner_request_blocks_listing_soft_deletion(self):
        self.requests.submit_requests(
            self.borrower.id, [self.draft()], "request-before-delete")
        with self.assertRaisesRegex(OwnerListingError, "active requests"):
            self.owner_listings.delete_listing(self.owner.id, self.listing.listing_id)
        self.assertEqual(
            self.owner_listings.get(self.owner.id, self.listing.listing_id).status,
            "Published")

    def test_own_listing_and_unavailable_or_paused_listings_are_rejected(self):
        with self.assertRaisesRegex(RequestError, "own listing"):
            self.requests.submit_requests(
                self.owner.id, [self.draft()], "owner-self-request")

        self.owner_listings.pause_listing(self.owner.id, self.listing.listing_id)
        with self.assertRaisesRegex(RequestError, "no longer accepting"):
            self.requests.submit_requests(
                self.borrower.id, [self.draft()], "paused-listing-request")
        self.owner_listings.resume_listing(
            self.owner.id, self.listing.listing_id, photos_dir=self.photos_dir)
        self.owner_listings.delete_listing(self.owner.id, self.listing.listing_id)
        with self.assertRaisesRegex(RequestError, "no longer accepting"):
            self.requests.submit_requests(
                self.borrower.id, [self.draft()], "deleted-listing-request")
        self.assertEqual(self.requests.list_requests(self.borrower.id), [])

    def test_owner_listing_identity_cannot_be_downgraded_to_a_sample_request(self):
        stale_item = replace(self.item, owner_student_id=None)
        with self.assertRaisesRegex(RequestError, "Refresh the Catalog"):
            self.requests.submit_requests(
                self.borrower.id, [self.draft(item=stale_item)],
                "missing-owner-reference")
        self.assertEqual(self.requests.list_requests(self.borrower.id), [])

    def test_schedule_and_maximum_duration_are_rechecked_before_saving(self):
        outside_window = self.pickup_at.replace(hour=13)
        with self.assertRaisesRegex(RequestError, "outside the owner's current availability"):
            self.requests.submit_requests(
                self.borrower.id, [self.draft(pickup_at=outside_window)],
                "outside-window-request")
        with self.assertRaisesRegex(RequestError, "at most 3 days"):
            self.requests.submit_requests(
                self.borrower.id, [self.draft(days=4)],
                "too-long-request")
        self.assertEqual(self.requests.list_requests(self.borrower.id), [])


class OwnerIncomingRequestServiceTests(OwnerRequestMixin, unittest.TestCase):
    def submit_for(self, borrower, key):
        return self.requests.submit_requests(
            borrower.id, [self.draft()], key)[0]

    def test_incoming_requests_are_owner_scoped_and_include_borrower_identity(self):
        request = self.submit_for(self.borrower, "incoming-scoped")

        incoming = self.requests.list_incoming_requests(self.owner.id)

        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0].request.request_id, request.request_id)
        self.assertEqual(incoming[0].borrower_name, "Ana Reyes")
        self.assertEqual(incoming[0].borrower_email, "ana@csucc.edu.ph")
        self.assertEqual(incoming[0].listing_status, "Published")
        with self.assertRaisesRegex(RequestError, "approved Student Owner"):
            self.requests.list_incoming_requests(self.borrower.id)
        with self.assertRaisesRegex(RequestError, "approved Student Owner"):
            self.requests.approve_owner_request(self.borrower.id, request.request_id)
        self.assertEqual(
            self.requests.list_requests(self.borrower.id)[0].status,
            RequestStatus.PENDING_OWNER_APPROVAL)

    def test_paused_listing_request_cannot_be_approved(self):
        submitted = self.submit_for(self.borrower, "incoming-paused")
        self.owner_listings.pause_listing(self.owner.id, self.listing.listing_id)

        incoming = self.requests.list_incoming_requests(self.owner.id)
        self.assertEqual(incoming[0].listing_status, "Paused")
        with self.assertRaisesRegex(RequestError, "no longer accepting"):
            self.requests.approve_owner_request(self.owner.id, submitted.request_id)
        self.assertEqual(
            self.requests.list_requests(self.borrower.id)[0].status,
            RequestStatus.PENDING_OWNER_APPROVAL)

    def test_approval_rechecks_the_current_pickup_schedule(self):
        submitted = self.submit_for(self.borrower, "incoming-stale-schedule")
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(
                "DELETE FROM listing_availability WHERE listing_id = ?",
                (self.listing.listing_id,))
            conn.commit()
        finally:
            conn.close()

        with self.assertRaisesRegex(RequestError, "pickup time is no longer available"):
            self.requests.approve_owner_request(self.owner.id, submitted.request_id)
        self.assertEqual(
            self.requests.list_requests(self.borrower.id)[0].status,
            RequestStatus.PENDING_OWNER_APPROVAL)

    def test_approval_reserves_one_copy_and_persists_without_starting_countdown(self):
        submitted = self.submit_for(self.borrower, "incoming-approve")

        approved = self.requests.approve_owner_request(
            self.owner.id, submitted.request_id)

        self.assertEqual(approved.status, RequestStatus.APPROVED)
        self.assertEqual(approved.scheduled_pickup_at, self.pickup_at)
        self.assertEqual(approved.pickup_deadline, self.pickup_at + timedelta(days=1))
        self.assertIsNotNone(approved.approved_at)
        self.assertIsNone(approved.picked_up_at)
        self.assertIsNone(approved.due_at)
        self.assertFalse(approved.countdown_started)
        self.assertEqual(approved.status_history[-1].status, RequestStatus.APPROVED)
        reloaded = RequestService(self.db).list_requests(self.borrower.id)[0]
        self.assertEqual(reloaded.status, RequestStatus.APPROVED)
        self.assertFalse(reloaded.countdown_started)
        conn = sqlite3.connect(self.db)
        try:
            copy = conn.execute(
                "SELECT state, request_id FROM owner_listing_copies "
                "WHERE listing_id = ?", (self.listing.listing_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(copy, ("reserved", submitted.request_id))
        with self.assertRaisesRegex(RequestError, "already been reviewed"):
            self.requests.approve_owner_request(self.owner.id, submitted.request_id)

    def test_rejection_keeps_request_and_does_not_reserve_stock(self):
        submitted = self.submit_for(self.borrower, "incoming-reject")

        rejected = self.requests.reject_owner_request(
            self.owner.id, submitted.request_id, "Pickup time does not work.")

        self.assertEqual(rejected.status, RequestStatus.REJECTED)
        self.assertEqual(rejected.status_note, "Pickup time does not work.")
        self.assertEqual(rejected.status_history[-1].note, "Pickup time does not work.")
        reloaded = RequestService(self.db).list_requests(self.borrower.id)[0]
        self.assertEqual(reloaded.status, RequestStatus.REJECTED)
        conn = sqlite3.connect(self.db)
        try:
            states = conn.execute(
                "SELECT state, request_id FROM owner_listing_copies "
                "WHERE listing_id = ?", (self.listing.listing_id,)).fetchall()
        finally:
            conn.close()
        self.assertEqual(states, [("available", None)])
        with self.assertRaisesRegex(RequestError, "not found"):
            self.requests.reject_owner_request(self.owner.id, submitted.request_id)

    def test_borrower_cancellation_releases_approved_owner_copy(self):
        submitted = self.submit_for(self.borrower, "incoming-cancel-approved")
        self.requests.approve_owner_request(self.owner.id, submitted.request_id)

        cancelled = self.requests.cancel_request(self.borrower.id, submitted.request_id)

        self.assertEqual(cancelled.status, RequestStatus.CANCELLED)
        conn = sqlite3.connect(self.db)
        try:
            copy = conn.execute(
                "SELECT state, request_id FROM owner_listing_copies "
                "WHERE listing_id = ?", (self.listing.listing_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(copy, ("available", None))

    def test_approval_cannot_overcommit_stock_across_borrowers(self):
        second_borrower = self.auth.register(
            "Mina Cruz", "mina@csucc.edu.ph", PASSWORD, PASSWORD,
            student_id_number="BORROWER-32B")
        first = self.submit_for(self.borrower, "incoming-stock-first")
        second = self.submit_for(second_borrower, "incoming-stock-second")

        self.requests.approve_owner_request(self.owner.id, first.request_id)

        with self.assertRaisesRegex(RequestError, "No copies are currently available"):
            self.requests.approve_owner_request(self.owner.id, second.request_id)
        self.assertEqual(
            self.requests.list_requests(second_borrower.id)[0].status,
            RequestStatus.PENDING_OWNER_APPROVAL)
        self.assertTrue(any(
            entry.request.request_id == second.request_id
            and entry.request.status is RequestStatus.PENDING_OWNER_APPROVAL
            for entry in self.requests.list_incoming_requests(self.owner.id)))


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class OwnerRequestUiTests(OwnerRequestMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def build_dashboard(self, student):
        dashboard = StudentDashboard(
            build_empty_data(student.full_name),
            signed_in_email=student.email,
            student_id=student.id,
            request_service=self.requests,
        )
        self.addCleanup(dashboard.deleteLater)
        return dashboard

    def test_actual_item_details_request_click_saves_and_shows_it_in_my_requests(self):
        dashboard = self.build_dashboard(self.borrower)
        dashboard.go_to("catalog")
        item = next(
            item for item in dashboard.catalog_page._items
            if item.listing_key == self.listing.listing_id)
        dashboard._open_item_details(item)
        self.assertTrue(dashboard.item_details_page.request_button.isEnabled())
        with mock.patch("app.dashboard_screen.QMessageBox.information"):
            def confirm_open_dialog(dialog):
                self.assertEqual(len(dialog.rows), 1)
                self.assertEqual(dialog.rows[0].max_days, 3)
                row = dialog.rows[0]
                # The dialog intentionally opens with "Choose a time"; model an
                # actual user selection before confirming the request.
                time_index = next(
                    index for index in range(row.time_combo.count())
                    if isinstance(row.time_combo.itemData(index), int)
                    and row.time_combo.itemData(index) >= 0
                )
                row.time_combo.setCurrentIndex(time_index)
                dialog.confirm_button.click()
                self.assertEqual(len(dialog.saved_requests), 1)
                self.assertEqual(len(dialog.drafts), 1)
                return QDialog.DialogCode.Accepted

            with mock.patch.object(
                    dashboard, "_show_saved_requests",
                    wraps=dashboard._show_saved_requests) as show_saved:
                with mock.patch(
                        "app.my_list_screen.RequestPreviewDialog.exec", confirm_open_dialog):
                    dashboard.item_details_page.request_button.click()
                self.assertTrue(show_saved.called)

        stored = self.requests.list_requests(self.borrower.id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].owner_listing_id, self.listing.listing_id)
        self.assertEqual(stored[0].status, RequestStatus.PENDING_OWNER_APPROVAL)
        self.assertIn("Pending Owner Approval",
                      dashboard.my_requests_page.banner.text())
        self.assertEqual(dashboard.my_requests_page.requests[0].request_id,
                         stored[0].request_id)
        photos = dashboard.my_requests_page.rows_container.findChildren(
            QLabel, "myReqPhoto")
        self.assertTrue(any(
            photo.accessibleName() == f"Photo of {stored[0].item.title}"
            for photo in photos))
        dashboard.my_requests_page.set_filter(RequestStatus.PENDING_OWNER_APPROVAL)
        self.assertEqual(
            [request.request_id for request in dashboard.my_requests_page.visible_requests],
            [stored[0].request_id])

    def test_owner_cannot_request_own_listing_from_item_details(self):
        dashboard = self.build_dashboard(self.owner)
        dashboard.go_to("catalog")
        item = next(
            item for item in dashboard.catalog_page._items
            if item.listing_key == self.listing.listing_id)
        dashboard._open_item_details(item)
        self.assertFalse(dashboard.item_details_page.request_button.isEnabled())
        self.assertIn("own listing", dashboard.item_details_page.request_button.toolTip())
        self.assertEqual(self.requests.list_requests(self.owner.id), [])

    def test_owner_workspace_shows_and_approves_incoming_request_from_ui(self):
        submitted = self.requests.submit_requests(
            self.borrower.id, [self.draft()], "incoming-ui-flow")[0]
        dashboard = self.build_dashboard(self.owner)
        dashboard.switch_workspace("student_owner")
        dashboard.owner_rail.buttons[OWNER_REQUESTS].click()

        self.assertIs(
            dashboard.content_stack.currentWidget(), dashboard.owner_requests_page)
        self.assertIn("Pending · 1",
                      dashboard.owner_requests_page.filter_buttons["pending"].text())
        review_button = next(
            button for button in dashboard.owner_requests_page.findChildren(QPushButton)
            if button.text() == "Review")
        review_button.click()
        self.assertFalse(dashboard.owner_requests_page.detail_view.isHidden())
        self.assertIn("Ana Reyes", dashboard.owner_requests_page.detail_facts.text())

        def confirm_approve(dialog):
            button = next(
                button for button in dialog.buttons()
                if button.text() == "Approve Request")
            button.click()
            return QDialog.DialogCode.Accepted

        with mock.patch.object(QMessageBox, "exec", confirm_approve):
            dashboard._on_approve_owner_request(submitted.request_id)

        self.assertEqual(
            self.requests.list_requests(self.borrower.id)[0].status,
            RequestStatus.APPROVED)
        self.assertIn("Pending · 0",
                      dashboard.owner_requests_page.filter_buttons["pending"].text())
        self.assertIn("Approved · 1",
                      dashboard.owner_requests_page.filter_buttons["approved"].text())

    def test_owner_rejection_ui_saves_optional_reason(self):
        submitted = self.requests.submit_requests(
            self.borrower.id, [self.draft()], "incoming-ui-reject")[0]
        dashboard = self.build_dashboard(self.owner)
        dashboard.switch_workspace("student_owner")
        dashboard.owner_rail.buttons[OWNER_REQUESTS].click()

        with mock.patch.object(
                QInputDialog, "getMultiLineText",
                return_value=("Pickup is unavailable that day.", True)):
            dashboard._on_reject_owner_request(submitted.request_id)

        rejected = self.requests.list_requests(self.borrower.id)[0]
        self.assertEqual(rejected.status, RequestStatus.REJECTED)
        self.assertEqual(rejected.status_note, "Pickup is unavailable that day.")
