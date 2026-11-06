"""Step 23b tests: My Requests tabs, compact counts, Active dropdown, Borrowing Guide,
Clear History / Clear Cancelled (hide only, saved, never deleted).

Groups 1 needs no window. Group 2 opens the real screen / dashboard (needs PySide6).
Run:  python -m unittest discover -s tests -p "test_my_requests_tabs.py" -v
"""
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import database  # noqa: E402
from app.my_requests_screen import RequestStatus, build_sample_requests  # noqa: E402
from app.request_service import RequestError, RequestService  # noqa: E402
from seed_helpers import insert_request, now_fixed  # noqa: E402
from test_notifications import TempDbCase  # noqa: E402

CLOSED = {RequestStatus.RETURNED, RequestStatus.REJECTED, RequestStatus.EXPIRED,
          RequestStatus.CANCELLED}


# ======================================================================
# 1. SAVING "CLEARED" (no window)
# ======================================================================
class ClearServiceTests(TempDbCase):
    def setUp(self):
        super().setUp()
        self.samples = build_sample_requests(now_fixed())
        for number, request in enumerate(self.samples):
            insert_request(self.db, self.ana.id, request, f"k{number}")
        self.by_status = {r.status: r for r in self.samples}

    def ids(self, *statuses):
        return [self.by_status[s].request_id for s in statuses]

    def test_nothing_is_hidden_at_first(self):
        self.assertEqual(self.requests.hidden_request_ids(self.ana.id), set())

    def test_hiding_saves_only_a_note_and_deletes_nothing(self):
        before = (self.count("borrow_requests"), self.count("borrow_request_history"))
        ids = self.ids(RequestStatus.RETURNED, RequestStatus.REJECTED, RequestStatus.EXPIRED)
        self.assertEqual(self.requests.hide_closed_requests(self.ana.id, ids), 3)
        self.assertEqual(self.requests.hidden_request_ids(self.ana.id), set(ids))
        self.assertEqual((self.count("borrow_requests"), self.count("borrow_request_history")), before)
        self.assertEqual(len(self.requests.list_requests(self.ana.id)), len(self.samples))

    def test_hidden_requests_stay_hidden_after_a_restart(self):
        ids = self.ids(RequestStatus.CANCELLED)
        self.requests.hide_closed_requests(self.ana.id, ids)
        self.assertEqual(RequestService(self.db).hidden_request_ids(self.ana.id), set(ids))

    def test_hiding_twice_is_harmless(self):
        ids = self.ids(RequestStatus.RETURNED)
        self.assertEqual(self.requests.hide_closed_requests(self.ana.id, ids), 1)
        self.assertEqual(self.requests.hide_closed_requests(self.ana.id, ids), 0)
        self.assertEqual(self.count("hidden_requests"), 1)

    def test_active_requests_can_never_be_hidden_and_nothing_is_half_done(self):
        mixed = self.ids(RequestStatus.RETURNED, RequestStatus.PENDING)
        with self.assertRaises(RequestError):
            self.requests.hide_closed_requests(self.ana.id, mixed)
        self.assertEqual(self.count("hidden_requests"), 0)
        for status in (RequestStatus.APPROVED, RequestStatus.BORROWED, RequestStatus.RETURN_PENDING):
            with self.assertRaises(RequestError):
                self.requests.hide_closed_requests(self.ana.id, self.ids(status))

    def test_other_students_and_unknown_ids_are_refused(self):
        closed_id = self.ids(RequestStatus.CANCELLED)
        with self.assertRaises(RequestError):
            self.requests.hide_closed_requests(self.ben.id, closed_id)  # Ana's request
        with self.assertRaises(RequestError):
            self.requests.hide_closed_requests(self.ana.id, ["REQ-NOPE"])
        self.assertEqual(self.requests.hidden_request_ids(self.ben.id), set())
        self.assertEqual(self.count("hidden_requests"), 0)

    def test_each_students_hidden_list_is_private(self):
        ben_request = [r for r in build_sample_requests(now_fixed())
                       if r.status is RequestStatus.CANCELLED][0]
        ben_request.request_id = "REQ-BEN-1"
        insert_request(self.db, self.ben.id, ben_request, "kb")
        self.requests.hide_closed_requests(self.ben.id, ["REQ-BEN-1"])
        self.assertEqual(self.requests.hidden_request_ids(self.ana.id), set())
        self.assertEqual(self.requests.hidden_request_ids(self.ben.id), {"REQ-BEN-1"})

    def test_empty_list_and_bad_time(self):
        self.assertEqual(self.requests.hide_closed_requests(self.ana.id, []), 0)
        with self.assertRaises(RequestError):
            from datetime import datetime
            self.requests.hide_closed_requests(
                self.ana.id, self.ids(RequestStatus.RETURNED), datetime(2026, 1, 1))  # no timezone

    def test_migration_11_is_recorded_once_and_adds_only_one_table(self):
        for _ in range(2):
            database.connect(self.db).close()
        versions = [r[0] for r in self.query("SELECT version FROM schema_migrations ORDER BY 1")]
        self.assertEqual(versions, [m[0] for m in database.MIGRATIONS])
        self.assertEqual(versions[-1], max(m[0] for m in database.MIGRATIONS))
        columns = [r[1] for r in self.query("PRAGMA table_info(hidden_requests)")]
        self.assertEqual(columns, ["student_id", "request_id", "hidden_at"])


# ======================================================================
# 2. THE SCREEN (needs a real PySide6)
# ======================================================================
try:
    import PySide6
    from PySide6.QtWidgets import QApplication, QComboBox, QFrame, QLabel, QPushButton
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class TabScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def make(self, **kwargs):
        from app.my_requests_screen import MyRequestsScreen
        screen = MyRequestsScreen(build_sample_requests(), **kwargs)
        screen.resize(1100, 800)
        screen.show()
        self.qt_app.processEvents()
        return screen

    def statuses(self, screen):
        return {r.status for r in screen.visible_requests}

    def test_three_tabs_with_the_right_requests_in_each(self):
        from app.my_requests_screen import TAB_ACTIVE, TAB_CANCELLED, TAB_HISTORY
        screen = self.make()
        self.assertEqual([b.text().split()[0] for b in screen._tab_buttons.values()],
                         ["Active", "History", "Cancelled"])
        self.assertEqual(screen.current_tab, TAB_ACTIVE)  # Active is the default
        self.assertEqual(self.statuses(screen), {
            RequestStatus.PENDING, RequestStatus.APPROVED,
            RequestStatus.BORROWED, RequestStatus.RETURN_PENDING})
        screen.set_tab(TAB_HISTORY)
        self.assertEqual(self.statuses(screen), {
            RequestStatus.RETURNED, RequestStatus.REJECTED, RequestStatus.EXPIRED})
        screen.set_tab(TAB_CANCELLED)
        self.assertEqual(self.statuses(screen), {RequestStatus.CANCELLED})

    def test_no_stat_cards_no_status_button_wall_and_one_notice(self):
        screen = self.make(stored_locally=True)
        self.assertEqual(screen.findChildren(QFrame, "myReqStat"), [])
        self.assertEqual(screen.findChildren(QPushButton, "myReqChip"), [])
        self.assertEqual(len(screen.findChildren(QPushButton, "myReqTab")), 3)
        notice = screen.findChild(QLabel, "myReqNotice")
        self.assertFalse(notice.isHidden())
        self.assertIn("this computer only", notice.text())
        self.assertIn("active", screen.counts_text)
        self.assertEqual(self.make(stored_locally=False).local_notice.isHidden(), True)

    def test_compact_counts_match_the_requests(self):
        screen = self.make()
        text = screen.counts_text
        self.assertIn("<b>4</b> active", text)
        self.assertIn("<b>1</b> awaiting approval", text)
        self.assertIn("<b>2</b> reserved or borrowed", text)
        self.assertIn("<b>4</b> closed", text)

    def test_dropdown_lives_in_active_only_and_filters_by_status(self):
        from app.my_requests_screen import FILTER_ALL, TAB_ACTIVE, TAB_HISTORY
        screen = self.make()
        combo = screen.status_filter
        self.assertIsInstance(combo, QComboBox)
        self.assertFalse(combo.isHidden())
        self.assertEqual(combo.count(), 6)  # All active + the five active statuses
        combo.setCurrentIndex(1)  # Pending
        self.assertEqual(self.statuses(screen), {RequestStatus.PENDING})
        self.assertEqual(screen.current_filter, RequestStatus.PENDING)
        screen.set_tab(TAB_HISTORY)
        self.assertTrue(combo.isHidden())
        self.assertEqual(screen.current_filter, FILTER_ALL)
        screen.set_tab(TAB_ACTIVE)
        self.assertEqual(len(screen.visible_requests), 4)

    def test_set_filter_keeps_working_for_the_dashboard_and_old_callers(self):
        from app.my_requests_screen import FILTER_ALL, TAB_ACTIVE, TAB_CANCELLED, TAB_HISTORY
        screen = self.make()
        screen.set_filter(RequestStatus.RETURNED)
        self.assertEqual(screen.current_tab, TAB_HISTORY)
        screen.set_filter(RequestStatus.CANCELLED)
        self.assertEqual(screen.current_tab, TAB_CANCELLED)
        screen.set_filter(RequestStatus.BORROWED)
        self.assertEqual((screen.current_tab, screen.current_filter),
                         (TAB_ACTIVE, RequestStatus.BORROWED))
        screen.set_filter(FILTER_ALL)
        self.assertEqual((screen.current_tab, screen.current_filter), (TAB_ACTIVE, FILTER_ALL))

    def test_borrowing_guide_is_collapsed_until_opened(self):
        screen = self.make()
        self.assertTrue(screen.guide_body.isHidden())
        screen.guide_toggle.click()
        self.assertFalse(screen.guide_body.isHidden())
        self.assertIn("Due date", screen.guide_body.findChild(QLabel, "myListInfoText").text())
        screen.guide_toggle.click()
        self.assertTrue(screen.guide_body.isHidden())

    def test_clear_buttons_exist_only_in_their_own_tab(self):
        from app.my_requests_screen import TAB_ACTIVE, TAB_CANCELLED, TAB_HISTORY
        screen = self.make()
        self.assertTrue(screen.clear_history_button.isHidden())
        self.assertTrue(screen.clear_cancelled_button.isHidden())
        screen.set_tab(TAB_HISTORY)
        self.assertFalse(screen.clear_history_button.isHidden())
        self.assertTrue(screen.clear_cancelled_button.isHidden())
        screen.set_tab(TAB_CANCELLED)
        self.assertTrue(screen.clear_history_button.isHidden())
        self.assertFalse(screen.clear_cancelled_button.isHidden())
        screen.set_tab(TAB_ACTIVE)
        self.assertTrue(screen.clear_history_button.isHidden())
        self.assertTrue(screen.clear_cancelled_button.isHidden())

    def test_clear_history_asks_first_and_only_clears_history(self):
        from app.my_requests_screen import TAB_CANCELLED, TAB_HISTORY
        saved, cleared = [], []
        screen = self.make(hide_handler=lambda ids, when: saved.append(ids))
        screen.requests_cleared.connect(cleared.append)
        screen.set_tab(TAB_HISTORY)
        asked = []
        screen._confirm_clear = lambda tab, count: (asked.append((tab, count)), False)[1]
        screen.clear_history_button.click()  # student says no
        self.assertEqual((asked, saved, len(screen.visible_requests)), ([(TAB_HISTORY, 3)], [], 3))
        screen._confirm_clear = lambda tab, count: True
        screen.clear_history_button.click()
        self.assertEqual(len(saved[0]), 3)
        self.assertEqual(screen.visible_requests, [])
        self.assertTrue(screen.clear_history_button.isHidden())  # nothing left to clear
        self.assertEqual(len(cleared), 1)
        self.assertEqual(len(screen.requests), 5)  # active (4) + cancelled (1) untouched
        screen.set_tab(TAB_CANCELLED)
        self.assertEqual(len(screen.visible_requests), 1)

    def test_clear_cancelled_only_clears_cancelled(self):
        from app.my_requests_screen import TAB_ACTIVE, TAB_CANCELLED, TAB_HISTORY
        saved = []
        screen = self.make(hide_handler=lambda ids, when: saved.append(ids))
        screen._confirm_clear = lambda tab, count: True
        screen.set_tab(TAB_CANCELLED)
        screen.clear_cancelled_button.click()
        self.assertEqual(len(saved[0]), 1)
        self.assertEqual(screen.visible_requests, [])
        screen.set_tab(TAB_HISTORY)
        self.assertEqual(len(screen.visible_requests), 3)
        screen.set_tab(TAB_ACTIVE)
        self.assertEqual(len(screen.visible_requests), 4)

    def test_a_failed_save_clears_nothing(self):
        from app.my_requests_screen import TAB_HISTORY

        def fail(ids, when):
            raise RequestError("Could not clear those requests. Nothing was changed.")

        screen = self.make(hide_handler=fail)
        screen._confirm_clear = lambda tab, count: True
        screen.set_tab(TAB_HISTORY)
        screen.clear_history_button.click()
        self.assertEqual(len(screen.visible_requests), 3)
        self.assertIn("Nothing was changed", screen.banner.text())

    def test_empty_states_are_readable_for_every_tab(self):
        from app.my_requests_screen import MyRequestsScreen, TAB_CANCELLED, TAB_HISTORY
        screen = MyRequestsScreen([])
        screen.show()
        self.assertEqual(screen.empty_title.text(), "No requests yet")
        self.assertFalse(screen.empty_button.isHidden())
        screen.set_requests(build_sample_requests())
        screen.set_requests([r for r in build_sample_requests() if r.status is RequestStatus.PENDING])
        screen.set_tab(TAB_HISTORY)
        self.assertEqual(screen.empty_title.text(), "No history")
        self.assertTrue(screen.empty_button.isHidden())
        screen.set_tab(TAB_CANCELLED)
        self.assertEqual(screen.empty_title.text(), "No cancelled requests")
        screen.set_tab("active")
        screen.status_filter.setCurrentIndex(
            screen.status_filter.findData(RequestStatus.APPROVED.value))
        self.assertIn("Approved", screen.empty_title.text())
        screen.empty_button.click()  # "Show all active"
        self.assertEqual(len(screen.visible_requests), 1)

    def test_cancelling_still_works_and_moves_the_request_to_the_cancelled_tab(self):
        from unittest import mock
        from PySide6.QtWidgets import QDialog
        from app.my_requests_screen import CancelRequestDialog, TAB_CANCELLED
        screen = self.make()
        pending = [r for r in screen.visible_requests if r.status is RequestStatus.PENDING][0]
        card = [c for c in screen.findChildren(QFrame, "myReqCard") if c.request is pending][0]
        with mock.patch.object(CancelRequestDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            card.cancel_button.click()
        self.assertIs(pending.status, RequestStatus.CANCELLED)
        self.assertNotIn(pending, screen.visible_requests)
        screen.set_tab(TAB_CANCELLED)
        self.assertIn(pending, screen.visible_requests)

    def test_cards_are_compact_and_the_window_can_be_narrow(self):
        screen = self.make()
        self.assertEqual(screen.findChildren(QFrame, "myReqFact"), [])  # no boxes in boxes
        self.assertEqual(len(screen.findChildren(QFrame, "myReqCard")), 4)
        for width in (500, 760, 1500):
            screen.resize(width, 700)
            self.qt_app.processEvents()


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardClearTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def build(self, student):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        return StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests, auth_service=self.auth)

    def test_cleared_requests_stay_hidden_after_restart_but_are_never_deleted(self):
        from app.my_requests_screen import TAB_CANCELLED
        samples = build_sample_requests(now_fixed())
        for number, request in enumerate(samples):
            insert_request(self.db, self.ana.id, request, f"k{number}")
        dash = self.build(self.ana)
        page = dash.my_requests_page
        self.assertEqual(len(page.requests), 8)
        page.set_tab(TAB_CANCELLED)
        page._confirm_clear = lambda tab, count: True
        page.clear_cancelled_button.click()
        self.assertEqual(len(page.requests), 7)
        self.assertEqual(self.count("hidden_requests"), 1)
        self.assertEqual(self.count("borrow_requests"), 8)  # nothing deleted
        again = self.build(self.ana)  # "restart"
        self.assertEqual(len(again.my_requests_page.requests), 7)
        self.assertTrue(all(r.status is not RequestStatus.CANCELLED
                            for r in again.my_requests_page.requests))
        # the Dashboard summary and other pages still know every request
        self.assertEqual(len(self.requests.list_requests(self.ana.id)), 8)
        other = self.build(self.ben)
        self.assertEqual(len(other.my_requests_page.requests), 0)


if __name__ == "__main__":
    unittest.main()
