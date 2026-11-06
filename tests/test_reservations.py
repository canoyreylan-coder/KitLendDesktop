"""Step 10 tests: Reservations (rules, read-only service filter, screen, dashboard, navigation).

Run from the project folder:   python -m unittest discover -s tests -v

The first two groups need no window. The last groups open widgets in Qt's invisible
"offscreen" mode and are skipped automatically if PySide6 is missing. Approved,
expired and cancelled-after-approval records are inserted straight into a TEMPORARY
database, because the app itself cannot create an approval yet (that needs a
lender/administrator, which is not built).
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.auth_service import AuthService  # noqa: E402
from app.my_list_screen import RequestDraft, get_max_borrow_days  # noqa: E402
from app.my_requests_screen import (  # noqa: E402
    RequestStatus,
    build_sample_requests,
    format_dt,
    request_facts,
)
from app.request_service import RequestError, RequestService  # noqa: E402
from app.reservation_rules import (  # noqa: E402
    is_awaiting_pickup,
    is_cancelled_after_approval,
    is_past_pickup_deadline,
    is_reservation,
    split_reservations,
)
from seed_helpers import (  # noqa: E402
    AVAILABLE,
    insert_request,
    make_borrowing,
    make_reservation,
    now_fixed,
    seed_samples,
)

PW = "correct horse"
RESERVATION_VALUES = {"approved", "expired", "cancelled"}


# ======================================================================
# 1. THE RULES (no window, no database)
# ======================================================================
class ReservationRuleTests(unittest.TestCase):
    def setUp(self):
        self.now = now_fixed()
        self.samples = build_sample_requests(self.now)

    def by_status(self, status):
        return [r for r in self.samples if r.status is status]

    def test_only_approved_expired_and_cancelled_after_approval_are_reservations(self):
        found = {r.status.value for r in self.samples if is_reservation(r)}
        self.assertEqual(found, RESERVATION_VALUES)
        self.assertEqual(sum(1 for r in self.samples if is_reservation(r)), 3)

    def test_pending_is_never_a_reservation(self):
        for request in self.by_status(RequestStatus.PENDING):
            self.assertFalse(is_reservation(request))

    def test_rejected_and_borrowing_statuses_are_never_reservations(self):
        for status in (RequestStatus.REJECTED, RequestStatus.BORROWED,
                       RequestStatus.RETURN_PENDING, RequestStatus.RETURNED):
            for request in self.by_status(status):
                self.assertFalse(is_reservation(request), status)

    def test_cancelled_after_approval_is_history_but_cancelled_before_is_not(self):
        after = make_reservation("REQ-CA", self.now, status=RequestStatus.CANCELLED, approved=True)
        before = make_reservation("REQ-CB", self.now, status=RequestStatus.CANCELLED, approved=False)
        self.assertTrue(is_cancelled_after_approval(after))
        self.assertTrue(is_reservation(after))
        self.assertFalse(is_cancelled_after_approval(before))
        self.assertFalse(is_reservation(before))

    def test_expired_is_history(self):
        expired = make_reservation("REQ-EX", self.now, status=RequestStatus.EXPIRED,
                                   pickup_in_days=-3)
        self.assertTrue(is_reservation(expired))
        self.assertFalse(is_awaiting_pickup(expired))

    def test_approved_has_no_due_date_and_no_borrowing_period(self):
        approved = make_reservation("REQ-AP", self.now)
        self.assertTrue(is_awaiting_pickup(approved))
        self.assertIsNone(approved.due_at)
        self.assertFalse(approved.countdown_started)
        facts = {label: value for label, value, _ in request_facts(approved, self.now)}
        self.assertEqual(facts["Borrowing period"], "Borrowing period not started")
        self.assertTrue(facts["Due date"].startswith("Not set"))

    def test_past_pickup_deadline_is_reported_without_changing_the_status(self):
        late = make_reservation("REQ-LATE", self.now, pickup_in_days=-2)
        on_time = make_reservation("REQ-OK", self.now, pickup_in_days=2)
        self.assertTrue(is_past_pickup_deadline(late, self.now))
        self.assertFalse(is_past_pickup_deadline(on_time, self.now))
        self.assertIs(late.status, RequestStatus.APPROVED)  # nothing expires it automatically

    def test_split_orders_awaiting_by_pickup_and_history_newest_first(self):
        later = make_reservation("REQ-L", self.now, pickup_in_days=4)
        sooner = make_reservation("REQ-S", self.now, pickup_in_days=1)
        old = make_reservation("REQ-O", self.now, status=RequestStatus.EXPIRED, pickup_in_days=-9)
        new = make_reservation("REQ-N", self.now, status=RequestStatus.EXPIRED, pickup_in_days=-2)
        awaiting, history = split_reservations([later, old, sooner, new])
        self.assertEqual([r.request_id for r in awaiting], ["REQ-S", "REQ-L"])
        self.assertEqual([r.request_id for r in history], ["REQ-N", "REQ-O"])

    def test_split_ignores_everything_that_is_not_a_reservation(self):
        awaiting, history = split_reservations(self.samples)
        self.assertEqual({r.status.value for r in awaiting + history}, RESERVATION_VALUES)
        self.assertEqual(len(awaiting + history), 3)


# ======================================================================
# 2. THE READ-ONLY SERVICE FILTER (temporary database, no window)
# ======================================================================
class LoadReservationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.service = RequestService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")

    def tearDown(self):
        self.tmp.cleanup()

    def query(self, sql):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def draft(self, item=None):
        item = item or AVAILABLE[0]
        when = (datetime.now().astimezone() + timedelta(hours=48)).replace(
            minute=0, second=0, microsecond=0)
        return RequestDraft(item=item, pickup_at=when, days=1, max_days=get_max_borrow_days(item))

    def test_new_student_has_no_reservations(self):
        result = self.service.load_reservations(self.ana.id)
        self.assertEqual((result.requests, result.skipped), ([], 0))

    def test_only_reservation_statuses_are_loaded(self):
        seed_samples(self.db, self.ana.id)
        self.assertEqual(len(self.service.load_requests(self.ana.id).requests), 8)
        loaded = self.service.load_reservations(self.ana.id).requests
        self.assertEqual({r.status.value for r in loaded}, RESERVATION_VALUES)
        self.assertEqual(len(loaded), 3)
        self.assertTrue(all(r.picked_up_at is None for r in loaded))

    def test_pending_requests_are_excluded(self):
        self.service.submit_requests(self.ana.id, [self.draft()], "k1")
        self.assertEqual(len(self.service.load_requests(self.ana.id).requests), 1)
        self.assertEqual(self.service.load_reservations(self.ana.id).requests, [])

    def test_borrowings_are_not_reservations(self):
        insert_request(self.db, self.ana.id,
                       make_borrowing("REQ-B1", now_fixed(), picked_days_ago=1, days=2), "kb")
        self.assertEqual(self.service.load_reservations(self.ana.id).requests, [])
        self.assertEqual(len(self.service.load_borrowings(self.ana.id).requests), 1)

    def test_students_never_see_each_others_reservations(self):
        now = now_fixed()
        insert_request(self.db, self.ana.id, make_reservation("REQ-ANA", now), "ka")
        insert_request(self.db, self.ben.id, make_reservation("REQ-BEN", now), "kb")
        ana_ids = {r.request_id for r in self.service.load_reservations(self.ana.id).requests}
        ben_ids = {r.request_id for r in self.service.load_reservations(self.ben.id).requests}
        self.assertEqual(ana_ids, {"REQ-ANA"})
        self.assertEqual(ben_ids, {"REQ-BEN"})

    def test_a_student_cannot_cancel_someone_elses_reservation(self):
        insert_request(self.db, self.ana.id, make_reservation("REQ-ANA", now_fixed()), "ka")
        with self.assertRaises(RequestError):
            self.service.cancel_request(self.ben.id, "REQ-ANA")
        self.assertEqual(len(self.service.load_reservations(self.ana.id).requests), 1)
        self.assertEqual(self.service.load_reservations(self.ana.id).requests[0].status,
                         RequestStatus.APPROVED)

    def test_cancelling_a_pending_request_never_becomes_reservation_history(self):
        saved = self.service.submit_requests(self.ana.id, [self.draft()], "k1")
        self.service.cancel_request(self.ana.id, saved[0].request_id)
        cancelled = self.service.load_requests(self.ana.id).requests[0]
        self.assertIs(cancelled.status, RequestStatus.CANCELLED)
        self.assertIsNone(cancelled.approved_at)  # it was never approved
        self.assertEqual(self.service.load_reservations(self.ana.id).requests, [])

    def test_cancelling_an_approved_reservation_moves_it_to_history_and_keeps_approval(self):
        original = make_reservation("REQ-AP", now_fixed(), pickup_in_days=2)
        insert_request(self.db, self.ana.id, original, "ka")
        self.assertEqual(len(self.service.load_reservations(self.ana.id).requests), 1)

        self.service.cancel_request(self.ana.id, "REQ-AP")  # the real, existing cancel path

        loaded = self.service.load_reservations(self.ana.id).requests
        self.assertEqual(len(loaded), 1)
        self.assertIs(loaded[0].status, RequestStatus.CANCELLED)
        self.assertEqual(loaded[0].approved_at, original.approved_at)   # approval kept
        self.assertTrue(is_cancelled_after_approval(loaded[0]))
        self.assertIsNone(loaded[0].due_at)                              # never borrowed
        self.assertIsNone(loaded[0].picked_up_at)
        history = self.query("SELECT status FROM borrow_request_history "
                             "WHERE request_id = 'REQ-AP' ORDER BY id")
        self.assertEqual(history[-1][0], "cancelled")

    def test_no_separate_reservations_table_and_no_duplicate_records(self):
        seed_samples(self.db, self.ana.id)
        tables_before = self.query("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        rows_before = self.query("SELECT COUNT(*) FROM borrow_requests")
        history_before = self.query("SELECT COUNT(*) FROM borrow_request_history")
        self.service.load_reservations(self.ana.id)
        self.service.load_reservations(self.ben.id)
        self.assertEqual(self.query("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"),
                         tables_before)
        self.assertFalse([t for (t,) in tables_before if "reserv" in t.lower()])
        self.assertEqual(self.query("SELECT COUNT(*) FROM borrow_requests"), rows_before)
        self.assertEqual(self.query("SELECT COUNT(*) FROM borrow_request_history"), history_before)

    def test_loading_reservations_leaves_accounts_untouched(self):
        seed_samples(self.db, self.ana.id)
        self.service.load_reservations(self.ana.id)
        self.assertEqual(self.auth.login("ana@csucc.edu.ph", PW).id, self.ana.id)


# ======================================================================
# 3 + 4. THE SCREEN, THE DASHBOARD AND NAVIGATION (need PySide6; run invisibly)
# ======================================================================
try:
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


def cards_in(layout):
    return [layout.itemAt(i).widget() for i in range(layout.count())]


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class MyReservationsScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.my_reservations_screen import MyReservationsScreen
        self.now = now_fixed()
        self.screen = MyReservationsScreen([], clock=lambda: self.now, stored_locally=True)

    def shown(self, tab):
        self.screen.set_tab(tab)
        return cards_in(self.screen.rows_layout)

    def all_cards(self):
        cards = self.shown("awaiting") + self.shown("expired") + self.shown("cancelled")
        self.screen.set_tab("awaiting")
        return cards

    def test_empty_screen_shows_the_empty_state(self):
        self.assertFalse(self.screen.empty_state.isHidden())
        self.assertTrue(self.screen.rows_container.isHidden())
        self.assertEqual(self.screen.empty_title.text(), "No reservations yet")
        self.assertFalse(self.screen.empty_button.isHidden())
        self.assertEqual([b.text() for b in self.screen._tab_buttons.values()],
                         ["Awaiting Pickup  0", "Expired  0", "Cancelled  0"])

    def test_empty_state_button_opens_my_requests(self):
        opened = []
        self.screen.my_requests_requested.connect(lambda: opened.append(True))
        self.screen.empty_button.click()
        self.assertEqual(opened, [True])

    def test_screen_given_every_status_shows_only_reservations(self):
        self.screen.set_reservations(build_sample_requests(self.now))
        shown = self.all_cards()
        self.assertEqual({c.request.status.value for c in shown}, RESERVATION_VALUES)
        self.assertEqual(len(shown), 3)
        for tab, status in (("awaiting", "approved"), ("expired", "expired"),
                            ("cancelled", "cancelled")):
            self.assertEqual({c.request.status.value for c in self.shown(tab)}, {status})
            self.assertEqual(self.screen.current_tab, tab)

    def test_pending_is_not_shown_even_if_passed_in(self):
        pending = [r for r in build_sample_requests(self.now) if r.status is RequestStatus.PENDING]
        self.screen.set_reservations(pending)
        self.assertEqual(self.all_cards(), [])
        self.assertFalse(self.screen.empty_state.isHidden())

    def test_cancelled_before_approval_is_not_shown(self):
        before = make_reservation("REQ-CB", self.now, status=RequestStatus.CANCELLED, approved=False)
        self.screen.set_reservations([before])
        self.assertEqual(self.all_cards(), [])
        self.assertFalse(self.screen.empty_state.isHidden())

    def test_cards_have_no_buttons_because_cancelling_lives_in_my_requests(self):
        self.screen.set_reservations(build_sample_requests(self.now))
        for card in self.all_cards():
            self.assertFalse(hasattr(card, "cancel_button"))
            self.assertEqual(card.findChildren(QPushButton), [])

    def test_cards_show_item_reservation_date_and_status(self):
        self.screen.set_reservations(build_sample_requests(self.now))
        card = self.shown("awaiting")[0]
        text = " ".join(label.text() for label in card.findChildren(QLabel))
        self.assertIn(card.request.item.title, text)
        self.assertIn("RESERVED", text)
        self.assertIn(format_dt(card.request.approved_at), text)
        self.assertEqual(card.status_pill.text(), card.request.status.info.label)
        self.assertNotIn("DUE", text.replace("DEADLINE", ""))  # no due date before pickup

    def test_past_deadline_is_highlighted_but_stays_approved(self):
        late = make_reservation("REQ-LATE", self.now, pickup_in_days=-2)
        self.screen.set_reservations(build_sample_requests(self.now) + [late])
        cards = self.shown("awaiting")
        flags = {c.request.request_id: c.is_late for c in cards}
        self.assertTrue(flags["REQ-LATE"])
        self.assertEqual(sum(flags.values()), 1)
        self.assertEqual(cards[0].request.request_id, "REQ-LATE")  # earliest pickup first
        self.assertEqual(cards[0].status_pill.text(), "Approved — Awaiting Pickup")
        self.assertTrue(cards[0].property("late"))
        self.assertIn("past pickup deadline", self.screen.counts_text)

    def test_counts_and_tab_labels(self):
        extra = [make_reservation("REQ-LATE", self.now, pickup_in_days=-2),
                 make_reservation("REQ-X", self.now, status=RequestStatus.EXPIRED, pickup_in_days=-6)]
        self.screen.set_reservations(build_sample_requests(self.now) + extra)
        self.assertEqual([b.text() for b in self.screen._tab_buttons.values()],
                         ["Awaiting Pickup  2", "Expired  2", "Cancelled  1"])
        self.assertEqual(len(self.screen.awaiting_requests), 2)
        self.assertEqual(len(self.screen.history_requests), 3)
        self.assertEqual(self.screen.awaiting_requests[0].request_id, "REQ-LATE")
        self.assertEqual(len(self.screen.expired_requests), 2)
        self.assertEqual(len(self.screen.cancelled_requests), 1)

    def test_history_only_has_clean_empty_states_for_awaiting(self):
        expired = make_reservation("REQ-X", self.now, status=RequestStatus.EXPIRED, pickup_in_days=-4)
        self.screen.set_reservations([expired])
        self.assertFalse(self.screen.empty_state.isHidden())
        self.assertEqual(self.screen.empty_title.text(), "Nothing awaiting pickup")
        self.assertTrue(self.screen.empty_button.isHidden())
        self.screen.set_tab("cancelled")
        self.assertEqual(self.screen.empty_title.text(), "No cancelled reservations")
        self.screen.set_tab("expired")
        self.assertTrue(self.screen.empty_state.isHidden())
        self.assertEqual(len(cards_in(self.screen.rows_layout)), 1)

    def test_unknown_tab_is_rejected(self):
        with self.assertRaises(ValueError):
            self.screen.set_tab("nope")

    def test_guide_is_collapsed_until_opened(self):
        self.assertTrue(self.screen.guide_body.isHidden())
        self.screen.guide_toggle.click()
        self.assertFalse(self.screen.guide_body.isHidden())

    def test_theme_is_limited_to_this_screen(self):
        import re
        from app.my_reservations_theme import MY_RESERVATIONS_V2_QSS
        groups = re.findall(r"^([^\n{}/][^{}]*)\{", MY_RESERVATIONS_V2_QSS, re.M)
        self.assertGreater(len(groups), 20)
        for group in groups:
            for selector in group.split(","):
                self.assertTrue(selector.strip().startswith("QWidget#reservationsScreen"),
                                selector.strip())

    def test_duplicate_ids_are_rejected(self):
        one = make_reservation("REQ-D", self.now)
        with self.assertRaises(ValueError):
            self.screen.set_reservations([one, one])

    def test_replacing_the_list_clears_old_cards(self):
        self.screen.set_reservations(build_sample_requests(self.now))
        self.screen.set_reservations([])
        self.assertEqual(self.screen.awaiting_requests, [])
        self.assertEqual(self.screen.history_requests, [])
        self.assertFalse(self.screen.empty_state.isHidden())


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardReservationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.service = RequestService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")
        self.build = lambda student: StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.service)

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_account_opens_an_empty_reservations_page(self):
        dash = self.build(self.ana)
        dash.go_to("reservations")
        self.assertIs(dash.content_stack.currentWidget(), dash.my_reservations_page)
        self.assertFalse(dash.my_reservations_page.empty_state.isHidden())

    def test_dashboard_shows_only_this_students_reservations(self):
        seed_samples(self.db, self.ana.id, prefix="A")
        seed_samples(self.db, self.ben.id, prefix="B")
        page = self.build(self.ana).my_reservations_page
        ids = {r.request_id for r in page.awaiting_requests + page.history_requests}
        self.assertEqual(len(ids), 3)
        self.assertTrue(all(i.startswith("AREQ-") for i in ids))

    def test_pending_request_stays_in_my_requests_only(self):
        dash = self.build(self.ana)
        item = AVAILABLE[0]
        when = (datetime.now().astimezone() + timedelta(hours=48)).replace(
            minute=0, second=0, microsecond=0)
        dash._submit_drafts([RequestDraft(item, when, 1, get_max_borrow_days(item))], "key-1")
        self.assertEqual(len(dash.my_requests_page.requests), 1)
        self.assertEqual(dash.my_reservations_page.awaiting_requests, [])
        self.assertEqual(dash.my_reservations_page.history_requests, [])
        self.assertEqual(dash.my_borrowings_page.current_requests, [])

    def test_cancelling_an_approved_reservation_through_the_dashboard_moves_it_to_history(self):
        insert_request(self.db, self.ana.id, make_reservation("REQ-AP", now_fixed()), "ka")
        dash = self.build(self.ana)
        self.assertEqual(len(dash.my_reservations_page.awaiting_requests), 1)
        request = dash.my_requests_page.requests[0]
        dash._cancel_request(request, now_fixed() + timedelta(seconds=5))  # saves to SQLite
        dash._reload_requests()
        self.assertEqual(dash.my_reservations_page.awaiting_requests, [])
        self.assertEqual([r.request_id for r in dash.my_reservations_page.history_requests],
                         ["REQ-AP"])

    def test_logout_clears_the_reservations_page(self):
        seed_samples(self.db, self.ana.id)
        dash = self.build(self.ana)
        self.assertTrue(dash.my_reservations_page.awaiting_requests)
        dash._emit_exit()
        self.assertEqual(dash.my_reservations_page.awaiting_requests, [])
        self.assertEqual(dash.my_reservations_page.history_requests, [])

    def test_empty_state_button_goes_to_my_requests(self):
        dash = self.build(self.ana)
        dash.go_to("reservations")
        dash.my_reservations_page.my_requests_requested.emit()
        self.assertIs(dash.content_stack.currentWidget(), dash.my_requests_page)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class NavigationRegressionTests(unittest.TestCase):
    """Everything from Steps 8C and 9 still works next to Reservations."""

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.service = RequestService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        seed_samples(self.db, self.ana.id)
        self.dash = StudentDashboard(build_empty_data("Ana Reyes"), signed_in_email=self.ana.email,
                                     student_id=self.ana.id, request_service=self.service)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_real_pages_open_in_the_same_stack(self):
        d = self.dash
        for key, page in (("dashboard", d.home_page), ("catalog", d.catalog_page),
                          ("my_list", d.my_list_page), ("my_requests", d.my_requests_page),
                          ("borrowings", d.my_borrowings_page),
                          ("reservations", d.my_reservations_page)):
            d.go_to(key)
            self.assertIs(d.content_stack.currentWidget(), page, key)
            self.assertTrue(d._nav_buttons[key].isChecked(), key)

    def test_settings_is_a_real_page_since_step_12(self):
        # Notifications became real in Step 11, Settings in Step 12 (tests/test_settings.py).
        self.dash.go_to("settings")
        self.assertIs(self.dash.content_stack.currentWidget(), self.dash.settings_page)

    def test_my_requests_still_shows_all_eight_requests(self):
        self.assertEqual(len(self.dash.my_requests_page.requests), 8)

    def test_my_borrowings_still_shows_only_confirmed_borrowings(self):
        page = self.dash.my_borrowings_page
        self.assertEqual({r.status.value for r in page.current_requests + page.history_requests},
                         {"borrowed", "return_pending", "returned"})

    def test_the_same_request_is_never_in_both_borrowings_and_reservations(self):
        borrowings = {r.request_id for r in self.dash.my_borrowings_page.current_requests
                      + self.dash.my_borrowings_page.history_requests}
        reservations = {r.request_id for r in self.dash.my_reservations_page.awaiting_requests
                        + self.dash.my_reservations_page.history_requests}
        self.assertFalse(borrowings & reservations)

    def test_my_list_still_has_its_calendar_code(self):
        # Step 10 must not touch My List. Its calendar classes are still importable.
        import app.my_list_screen as my_list
        for name in ("AvailabilityCalendar", "PickupCalendarPopup", "PickupSchedule",
                     "validate_pickup", "RequestPreviewDialog"):
            self.assertTrue(hasattr(my_list, name), name)


if __name__ == "__main__":
    unittest.main()
