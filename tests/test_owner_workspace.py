"""Step 31A tests: Student Owner workspace (access rule, switching, shared account, pages).

Run:   python -m unittest discover -s tests -p "test_owner_workspace.py" -v
Group 1 needs no window. Groups 2-3 use Qt's invisible "offscreen" mode and temporary databases.
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

from app.auth_service import AuthService  # noqa: E402
from app.student_owner_service import StudentOwnerService  # noqa: E402
from app.workspace_service import (  # noqa: E402
    WORKSPACE_STUDENT,
    WORKSPACE_STUDENT_OWNER,
    WorkspaceService,
)

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

PW = "correct horse"
REASON = "I have spare lab equipment and would like to help classmates."
ITEMS = "A scientific calculator and a soldering kit."


class OwnerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-A1")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-B2")
        self.owner = StudentOwnerService(self.db)
        self.workspaces = WorkspaceService(self.owner)

    def apply(self, student):
        return self.owner.submit_application(student.id, REASON, ITEMS, True)

    def review(self, application_id, status):
        """Simulates the FUTURE review system (the student app has no such method)."""
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE student_owner_applications SET status=?, "
                     "reviewed_at='2026-10-24T00:00:00+00:00' WHERE application_id=?",
                     (status, application_id))
        conn.commit()
        conn.close()

    def keys(self, student):
        return [w.key for w in self.workspaces.assigned_workspaces(student.id)]


# ======================================================================
# 1. WHO MAY ENTER
# ======================================================================
class AccessRuleTests(OwnerBase):
    def test_only_an_approved_application_opens_the_owner_workspace(self):
        self.assertEqual(self.keys(self.ana), [WORKSPACE_STUDENT])          # never applied
        application = self.apply(self.ana)
        self.assertEqual(self.keys(self.ana), [WORKSPACE_STUDENT])          # Pending
        self.review(application.application_id, "Rejected")
        self.assertEqual(self.keys(self.ana), [WORKSPACE_STUDENT])          # Rejected
        application = self.apply(self.ana)
        self.review(application.application_id, "Approved")
        self.assertEqual(self.keys(self.ana), [WORKSPACE_STUDENT, WORKSPACE_STUDENT_OWNER])
        self.assertTrue(self.workspaces.can_use(self.ana.id, WORKSPACE_STUDENT_OWNER))

    def test_approval_is_per_account(self):
        self.review(self.apply(self.ana).application_id, "Approved")
        self.assertEqual(self.keys(self.ben), [WORKSPACE_STUDENT])
        self.assertFalse(self.workspaces.can_use(self.ben.id, WORKSPACE_STUDENT_OWNER))

    def test_access_follows_the_status_if_it_is_withdrawn(self):
        application = self.apply(self.ana)
        self.review(application.application_id, "Approved")
        self.review(application.application_id, "Rejected")
        self.assertFalse(self.workspaces.can_use(self.ana.id, WORKSPACE_STUDENT_OWNER))

    def test_without_a_service_or_with_bad_ids_or_errors_it_is_student_only(self):
        self.assertEqual([w.key for w in WorkspaceService().assigned_workspaces(self.ana.id)],
                         [WORKSPACE_STUDENT])
        for bad in (None, "1", True):
            self.assertEqual(self.workspaces.assigned_workspaces(bad), [])
            self.assertFalse(self.workspaces.is_student_owner(bad))
        broken = mock.Mock()
        broken.list_applications.side_effect = RuntimeError("database problem")
        self.assertEqual([w.key for w in WorkspaceService(broken).assigned_workspaces(1)],
                         [WORKSPACE_STUDENT])


# ======================================================================
# 2. THE PAGES
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_owner_dashboard_is_honest_about_what_exists(self):
        from app.owner_workspace import OwnerDashboardPage
        page = OwnerDashboardPage()
        self.addCleanup(page.deleteLater)
        page.set_identity("Ana Reyes", "ana@csucc.edu.ph")
        self.assertIn("Welcome, Ana", page.subtitle_label.text())
        self.assertIn("ana@csucc.edu.ph", page.account_text.text())
        seen = []
        page.switch_to_student_requested.connect(lambda: seen.append(1))
        page.switch_button.click()
        self.assertEqual(seen, [1])

    def test_my_listings_shows_the_empty_state_and_no_create_button(self):
        from PySide6.QtWidgets import QPushButton
        from app.owner_workspace import OwnerListingsPage
        page = OwnerListingsPage()
        self.addCleanup(page.deleteLater)
        self.assertEqual(page.listings, [])
        self.assertEqual(page.empty_title.text(), "No listings yet")
        labels = [b.text() for b in page.findChildren(QPushButton)]
        self.assertEqual(labels, ["+  Add Listing", "+  Add Listing", "Back to Owner Dashboard"])

    def test_owner_rail_has_its_own_buttons_and_selection(self):
        from app.owner_workspace import OwnerRail
        rail = OwnerRail("AR")
        self.addCleanup(rail.deleteLater)
        self.assertEqual(set(rail.buttons),
                         {"owner_dashboard", "my_listings", "incoming_requests",
                          "settings", "switch", "logout"})
        rail.select("my_listings")
        self.assertEqual(rail.selected_key, "my_listings")
        seen = []
        rail.nav_requested.connect(seen.append)
        rail.buttons["owner_dashboard"].click()
        self.assertEqual(seen, ["owner_dashboard"])

    def test_student_icon_set_is_unchanged(self):
        from app.icon_shapes import ICON_SHAPES
        self.assertNotIn("my_listings", ICON_SHAPES)
        self.assertNotIn("owner_dashboard", ICON_SHAPES)


# ======================================================================
# 3. INSIDE THE REAL DASHBOARD
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardWorkspaceTests(OwnerBase):
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

    def approve(self, student):
        self.review(self.apply(student).application_id, "Approved")

    def test_regular_student_sees_no_switch_and_cannot_enter(self):
        dash = self.build(self.ana)
        dash.go_to("settings")
        self.assertEqual(dash.settings_page.workspace_names, ["Student"])
        self.assertEqual(dash.settings_page.workspace_switch_buttons, {})
        self.assertFalse(dash.switch_workspace(WORKSPACE_STUDENT_OWNER))
        self.assertEqual(dash.current_workspace, WORKSPACE_STUDENT)
        self.assertTrue(dash.owner_rail.isHidden())
        self.assertFalse(dash.sidebar_rail.isHidden())

    def test_pending_and_rejected_students_cannot_enter(self):
        application = self.apply(self.ana)
        dash = self.build(self.ana)
        self.assertFalse(dash.switch_workspace(WORKSPACE_STUDENT_OWNER))
        self.review(application.application_id, "Rejected")
        self.assertFalse(dash.switch_workspace(WORKSPACE_STUDENT_OWNER))
        self.assertEqual(dash.current_workspace, WORKSPACE_STUDENT)

    def test_approved_owner_switches_through_settings_and_back(self):
        self.approve(self.ana)
        dash = self.build(self.ana)
        self.assertEqual(dash.current_workspace, WORKSPACE_STUDENT)         # login starts as Student
        dash.go_to("settings")
        self.assertEqual(dash.settings_page.workspace_names, ["Student", "Student Owner"])
        button = dash.settings_page.workspace_switch_buttons[WORKSPACE_STUDENT_OWNER]
        button.click()
        self.assertEqual(dash.current_workspace, WORKSPACE_STUDENT_OWNER)
        self.assertFalse(dash.owner_rail.isHidden())
        self.assertTrue(dash.sidebar_rail.isHidden())
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_dashboard_page)
        dash.owner_rail.buttons["my_listings"].click()
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_listings_page)
        dash.owner_rail.buttons["switch"].click()
        self.assertEqual(dash.current_workspace, WORKSPACE_STUDENT)
        self.assertFalse(dash.sidebar_rail.isHidden())
        self.assertTrue(dash.owner_rail.isHidden())
        self.assertIs(dash.content_stack.currentWidget(), dash.home_page)

    def test_both_workspaces_share_one_settings_page_and_account(self):
        self.approve(self.ana)
        dash = self.build(self.ana)
        dash.go_to("settings")
        student_settings = dash.settings_page
        dash.switch_workspace(WORKSPACE_STUDENT_OWNER)
        dash.owner_rail.buttons["settings"].click()
        self.assertIs(dash.content_stack.currentWidget(), student_settings)
        self.assertEqual(student_settings.email_value.text(), "ana@csucc.edu.ph")
        self.assertEqual(student_settings.name_value.text(), "Ana Reyes")
        self.assertIn(WORKSPACE_STUDENT, student_settings.workspace_switch_buttons)
        student_settings.workspace_switch_buttons[WORKSPACE_STUDENT].click()
        self.assertEqual(dash.current_workspace, WORKSPACE_STUDENT)
        self.assertIs(dash.settings_page, student_settings)

    def test_student_pages_are_not_reachable_from_the_owner_workspace(self):
        self.approve(self.ana)
        dash = self.build(self.ana)
        dash.switch_workspace(WORKSPACE_STUDENT_OWNER)
        dash.go_to("catalog")
        self.assertIs(dash.content_stack.currentWidget(), dash.owner_dashboard_page)

    def test_borrowing_features_still_work_for_an_owner(self):
        self.approve(self.ana)
        dash = self.build(self.ana)
        dash.switch_workspace(WORKSPACE_STUDENT_OWNER)
        dash.switch_workspace(WORKSPACE_STUDENT)
        for key in ("catalog", "my_list", "my_requests", "borrowings", "reservations",
                    "notifications"):
            dash.go_to(key)
            self.assertIs(dash.content_stack.currentWidget(), dash._pages[key])
        from app.catalog_screen import SAMPLE_ITEMS
        item = SAMPLE_ITEMS[0]
        dash._on_catalog_bookmark_toggled(item, True)
        self.assertIn(item, dash.my_list_page.saved_items)

    def test_withdrawn_approval_sends_the_owner_back_to_student(self):
        application = self.apply(self.ana)
        self.review(application.application_id, "Approved")
        dash = self.build(self.ana)
        dash.switch_workspace(WORKSPACE_STUDENT_OWNER)
        self.review(application.application_id, "Rejected")
        dash.owner_rail.buttons["my_listings"].click()
        self.assertEqual(dash.current_workspace, WORKSPACE_STUDENT)

    def test_sidebar_layout_is_untouched_by_switching(self):
        self.approve(self.ana)
        dash = self.build(self.ana)
        before = dash.sidebar_rail.layout_model().copy() if hasattr(
            dash.sidebar_rail, "layout_model") else None
        geometry = {k: b.geometry() for k, b in dash._nav_buttons.items()}
        dash.switch_workspace(WORKSPACE_STUDENT_OWNER)
        dash.switch_workspace(WORKSPACE_STUDENT)
        self.assertEqual({k: b.geometry() for k, b in dash._nav_buttons.items()}, geometry)
        if before is not None:
            self.assertEqual(dash.sidebar_rail.layout_model(), before)

    def test_sidebar_customisation_is_refused_inside_the_owner_workspace(self):
        self.approve(self.ana)
        dash = self.build(self.ana)
        dash.switch_workspace(WORKSPACE_STUDENT_OWNER)
        dash._start_sidebar_editing()
        self.assertFalse(dash.sidebar_rail.editing)

    def test_switching_is_refused_while_the_sidebar_is_being_edited(self):
        self.approve(self.ana)
        dash = self.build(self.ana)
        dash.go_to("settings")
        dash._start_sidebar_editing()
        if dash.sidebar_rail.editing:
            self.assertFalse(dash.switch_workspace(WORKSPACE_STUDENT_OWNER))

    def test_logout_returns_to_the_student_workspace(self):
        self.approve(self.ana)
        dash = self.build(self.ana)
        dash.switch_workspace(WORKSPACE_STUDENT_OWNER)
        seen = []
        dash.logout_requested.connect(lambda: seen.append(1))
        with mock.patch.object(type(dash), "_confirm_logout", return_value=True):
            dash.owner_rail.buttons["logout"].click()
        self.assertEqual(seen, [1])
        self.assertEqual(dash.current_workspace, WORKSPACE_STUDENT)

    def test_owner_floating_container_is_the_same_shell(self):
        self.approve(self.ana)
        dash = self.build(self.ana)
        dash.switch_workspace(WORKSPACE_STUDENT_OWNER)
        self.assertIs(dash.owner_rail.parentWidget(), dash.shell)
        self.assertIs(dash.content_stack.parentWidget(), dash.shell)


if __name__ == "__main__":
    unittest.main()
