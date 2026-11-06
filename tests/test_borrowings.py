"""Step 9 tests: My Borrowings (rules, read-only service filter, screen, dashboard wiring).

Run from the project folder:   python -m unittest discover -s tests -v

The first two groups need no window. The last two groups open widgets in Qt's
invisible "offscreen" mode, and are skipped automatically if PySide6 is missing.
Borrowed records are inserted straight into a TEMPORARY database, because the
app itself cannot create one (that needs a lender/administrator, not built yet).
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
from app.borrowing_rules import is_borrowing, is_overdue, split_borrowings  # noqa: E402
from app.my_list_screen import RequestDraft, get_max_borrow_days  # noqa: E402
from app.my_requests_screen import (  # noqa: E402
    RequestStatus,
    build_sample_requests,
    compute_due_at,
    format_dt,
)
from app.request_service import RequestService  # noqa: E402
from seed_helpers import (  # noqa: E402
    AVAILABLE,
    insert_request,
    make_borrowing,
    now_fixed,
    seed_samples,
)

PW = "correct horse"
BORROWING_VALUES = {"borrowed", "return_pending", "returned"}


# ======================================================================
# 1. THE RULES (no window, no database)
# ======================================================================
class BorrowingRuleTests(unittest.TestCase):
    def setUp(self):
        self.now = now_fixed()
        self.samples = build_sample_requests(self.now)

    def test_only_confirmed_handover_statuses_are_borrowings(self):
        flags = {r.status.value: is_borrowing(r) for r in self.samples}
        self.assertEqual({k for k, v in flags.items() if v}, BORROWING_VALUES)

    def test_pending_and_approved_are_never_borrowings(self):
        for request in self.samples:
            if request.status in (RequestStatus.PENDING, RequestStatus.APPROVED):
                self.assertFalse(is_borrowing(request), request.status)
                self.assertIsNone(request.due_at)  # no due date before pickup

    def test_rejected_cancelled_expired_are_never_borrowings(self):
        for request in self.samples:
            if request.status in (RequestStatus.REJECTED, RequestStatus.CANCELLED,
                                  RequestStatus.EXPIRED):
                self.assertFalse(is_borrowing(request), request.status)

    def test_split_sorts_current_by_due_date_and_history_newest_first(self):
        later = make_borrowing("REQ-A", self.now, picked_days_ago=1, days=5)   # due in 4 days
        sooner = make_borrowing("REQ-B", self.now, picked_days_ago=3, days=4)  # due in 1 day
        old_return = make_borrowing("REQ-C", self.now, picked_days_ago=20, days=3,
                                    status=RequestStatus.RETURNED)
        new_return = make_borrowing("REQ-D", self.now, picked_days_ago=6, days=3,
                                    status=RequestStatus.RETURNED)
        current, history = split_borrowings([later, old_return, sooner, new_return])
        self.assertEqual([r.request_id for r in current], ["REQ-B", "REQ-A"])
        self.assertEqual([r.request_id for r in history], ["REQ-D", "REQ-C"])

    def test_split_ignores_requests_that_are_not_borrowings(self):
        current, history = split_borrowings(self.samples)
        shown = {r.status.value for r in current + history}
        self.assertEqual(shown, BORROWING_VALUES)
        self.assertEqual(len(current + history), 3)

    def test_overdue_only_when_borrowed_and_past_due(self):
        overdue = make_borrowing("REQ-O", self.now, picked_days_ago=10, days=2)
        on_time = make_borrowing("REQ-T", self.now, picked_days_ago=1, days=2)
        reported = make_borrowing("REQ-R", self.now, picked_days_ago=10, days=2,
                                  status=RequestStatus.RETURN_PENDING)
        self.assertTrue(is_overdue(overdue, self.now))
        self.assertFalse(is_overdue(on_time, self.now))
        self.assertFalse(is_overdue(reported, self.now))  # already reported as returned

    def test_due_date_counts_from_confirmed_pickup_not_approval(self):
        request = make_borrowing("REQ-P", self.now, picked_days_ago=2, days=3)
        self.assertEqual(request.due_at, compute_due_at(request.picked_up_at, 3))
        self.assertNotEqual(request.due_at, compute_due_at(request.approved_at, 3))


# ======================================================================
# 2. THE READ-ONLY SERVICE FILTER (temporary database, no window)
# ======================================================================
class LoadBorrowingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.service = RequestService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")

    def tearDown(self):
        self.tmp.cleanup()

    def row_counts(self):
        conn = sqlite3.connect(self.db)
        try:
            return tuple(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                         for t in ("students", "borrow_requests", "borrow_request_history"))
        finally:
            conn.close()

    def test_new_student_has_no_borrowings(self):
        result = self.service.load_borrowings(self.ana.id)
        self.assertEqual(result.requests, [])
        self.assertEqual(result.skipped, 0)

    def test_only_confirmed_borrowings_are_loaded(self):
        seed_samples(self.db, self.ana.id)
        everything = self.service.load_requests(self.ana.id).requests
        borrowings = self.service.load_borrowings(self.ana.id).requests
        self.assertEqual(len(everything), 8)
        self.assertEqual({r.status.value for r in borrowings}, BORROWING_VALUES)
        self.assertEqual(len(borrowings), 3)
        self.assertTrue(all(r.picked_up_at is not None for r in borrowings))

    def test_loaded_borrowing_keeps_pickup_based_due_date(self):
        now = now_fixed()
        request = make_borrowing("REQ-DUE1", now, picked_days_ago=2, days=3)
        insert_request(self.db, self.ana.id, request, "k1")
        loaded = self.service.load_borrowings(self.ana.id).requests[0]
        self.assertEqual(loaded.picked_up_at, request.picked_up_at)
        self.assertEqual(loaded.due_at, compute_due_at(request.picked_up_at, 3))

    def test_students_never_see_each_others_borrowings(self):
        seed_samples(self.db, self.ana.id, prefix="A")
        insert_request(self.db, self.ben.id,
                       make_borrowing("REQ-BEN1", now_fixed(), picked_days_ago=1, days=2), "kb")
        ana_ids = {r.request_id for r in self.service.load_borrowings(self.ana.id).requests}
        ben_ids = {r.request_id for r in self.service.load_borrowings(self.ben.id).requests}
        self.assertEqual(ben_ids, {"REQ-BEN1"})
        self.assertTrue(ana_ids and all(i.startswith("AREQ-") for i in ana_ids))
        self.assertFalse(ana_ids & ben_ids)

    def test_submitting_and_cancelling_never_create_a_borrowing(self):
        draft_time = (datetime.now().astimezone() + timedelta(hours=48)).replace(
            minute=0, second=0, microsecond=0)
        item = AVAILABLE[0]
        draft = RequestDraft(item=item, pickup_at=draft_time, days=1,
                             max_days=get_max_borrow_days(item))
        saved = self.service.submit_requests(self.ana.id, [draft], "key-1")
        self.assertEqual(self.service.load_borrowings(self.ana.id).requests, [])
        self.service.cancel_request(self.ana.id, saved[0].request_id)
        self.assertEqual(self.service.load_borrowings(self.ana.id).requests, [])
        self.assertEqual(len(self.service.load_requests(self.ana.id).requests), 1)

    def test_loading_borrowings_changes_nothing_in_the_database(self):
        seed_samples(self.db, self.ana.id)
        before = self.row_counts()
        self.service.load_borrowings(self.ana.id)
        self.service.load_borrowings(self.ben.id)
        self.assertEqual(self.row_counts(), before)
        self.assertEqual(self.auth.login("ana@csucc.edu.ph", PW).id, self.ana.id)


# ======================================================================
# 3 + 4. THE SCREEN AND THE DASHBOARD (need PySide6; run invisibly)
# ======================================================================
try:
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
    from app.my_borrowings_screen import TAB_ACTIVE, TAB_HISTORY, TAB_RETURN_PENDING
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class MyBorrowingsScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.my_borrowings_screen import MyBorrowingsScreen
        self.now = now_fixed()
        self.screen = MyBorrowingsScreen([], clock=lambda: self.now, stored_locally=True)

    def cards(self, layout=None):
        layout = layout if layout is not None else self.screen.rows_layout
        return [layout.itemAt(i).widget() for i in range(layout.count())]

    def all_cards(self):
        """Cards of every tab, one tab at a time."""
        shown = []
        for tab in (TAB_ACTIVE, TAB_RETURN_PENDING, TAB_HISTORY):
            self.screen.set_tab(tab)
            shown += self.cards()
        self.screen.set_tab(TAB_ACTIVE)
        return shown

    def test_empty_screen_shows_the_empty_state(self):
        self.assertFalse(self.screen.empty_state.isHidden())
        self.assertTrue(self.screen.rows_container.isHidden())
        self.assertEqual(self.screen.empty_title.text(), "No borrowed items yet")
        self.assertFalse(self.screen.empty_button.isHidden())
        self.assertEqual([b.text() for b in self.screen._tab_buttons.values()],
                         ["Active  0", "Return Pending  0", "History  0"])

    def test_empty_state_button_opens_my_requests(self):
        opened = []
        self.screen.my_requests_requested.connect(lambda: opened.append(True))
        self.screen.empty_button.click()
        self.assertEqual(opened, [True])

    def test_screen_given_every_status_shows_only_real_borrowings(self):
        self.screen.set_borrowings(build_sample_requests(self.now))
        shown = self.all_cards()
        statuses = {card.request.status.value for card in shown}
        self.assertEqual(statuses, BORROWING_VALUES)
        self.assertEqual(len(shown), 3)
        self.assertTrue(self.screen.empty_state.isHidden())

    def test_each_status_lives_in_its_own_tab(self):
        self.screen.set_borrowings(build_sample_requests(self.now))
        for tab, status in ((TAB_ACTIVE, "borrowed"), (TAB_RETURN_PENDING, "return_pending"),
                            (TAB_HISTORY, "returned")):
            self.screen.set_tab(tab)
            self.assertEqual(self.screen.current_tab, tab)
            self.assertEqual({r.status.value for r in self.screen.visible_requests}, {status})
            self.assertEqual({c.request.status.value for c in self.cards()}, {status})

    def test_pending_and_approved_are_not_shown_even_if_passed_in(self):
        pending_and_approved = [r for r in build_sample_requests(self.now)
                                if r.status in (RequestStatus.PENDING, RequestStatus.APPROVED)]
        self.screen.set_borrowings(pending_and_approved)
        self.assertEqual(self.all_cards(), [])
        self.assertFalse(self.screen.empty_state.isHidden())

    def test_cards_have_no_cancel_button(self):
        self.screen.set_borrowings(build_sample_requests(self.now))
        for card in self.all_cards():
            self.assertFalse(hasattr(card, "cancel_button"))
            self.assertEqual(card.findChildren(QPushButton), [])

    def test_cards_show_item_pickup_due_and_status(self):
        self.screen.set_borrowings(build_sample_requests(self.now))
        card = self.cards()[0]
        text = " ".join(label.text() for label in card.findChildren(QLabel))
        self.assertIn(card.request.item.title, text)
        self.assertIn("PICKED UP", text)
        self.assertIn("DUE", text)
        self.assertIn(format_dt(card.request.picked_up_at), text)
        self.assertIn(format_dt(card.request.due_at), text)  # the existing due_at, unchanged
        self.assertEqual(card.status_pill.text(), card.request.status.info.label)

    def test_overdue_is_highlighted_only_on_overdue_borrowed_cards(self):
        overdue = make_borrowing("REQ-OD", self.now, picked_days_ago=10, days=2)
        self.screen.set_borrowings(build_sample_requests(self.now) + [overdue])
        cards = self.cards()
        flags = {c.request.request_id: c.is_overdue for c in cards}
        self.assertTrue(flags["REQ-OD"])
        self.assertEqual(sum(flags.values()), 1)
        self.assertEqual(cards[0].request.request_id, "REQ-OD")  # most urgent first
        self.assertEqual(cards[0].status_pill.text(), "Overdue")
        self.assertTrue(cards[0].property("overdue"))
        self.screen.set_tab(TAB_RETURN_PENDING)  # a reported return is never overdue
        self.assertFalse(self.cards()[0].is_overdue)

    def test_counts_and_tab_labels(self):
        overdue = make_borrowing("REQ-OD", self.now, picked_days_ago=10, days=2)
        self.screen.set_borrowings(build_sample_requests(self.now) + [overdue])
        self.assertEqual([b.text() for b in self.screen._tab_buttons.values()],
                         ["Active  2", "Return Pending  1", "History  1"])
        counts = self.screen.counts_text
        for part in ("2</b> borrowed", "1</b> overdue", "1</b> return pending",
                     "1</b> returned"):
            self.assertIn(part, counts)
        self.assertEqual(len(self.screen.current_requests), 3)
        self.assertEqual(len(self.screen.history_requests), 1)
        self.assertEqual(self.screen.current_requests[0].request_id, "REQ-OD")

    def test_no_overdue_text_in_counts_when_nothing_is_overdue(self):
        self.screen.set_borrowings(build_sample_requests(self.now))
        self.assertNotIn("overdue", self.screen.counts_text)

    def test_history_only_has_clean_empty_states_for_the_other_tabs(self):
        returned = make_borrowing("REQ-H", self.now, picked_days_ago=9, days=3,
                                  status=RequestStatus.RETURNED)
        self.screen.set_borrowings([returned])
        self.assertEqual(self.screen.current_requests, [])
        self.assertFalse(self.screen.empty_state.isHidden())
        self.assertEqual(self.screen.empty_title.text(), "Nothing borrowed right now")
        self.assertTrue(self.screen.empty_button.isHidden())
        self.screen.set_tab(TAB_RETURN_PENDING)
        self.assertEqual(self.screen.empty_title.text(), "No returns waiting")
        self.screen.set_tab(TAB_HISTORY)
        self.assertTrue(self.screen.empty_state.isHidden())
        self.assertEqual(len(self.cards()), 1)

    def test_unknown_tab_is_rejected(self):
        with self.assertRaises(ValueError):
            self.screen.set_tab("nope")

    def test_guide_is_collapsed_until_opened(self):
        self.assertTrue(self.screen.guide_body.isHidden())
        self.screen.guide_toggle.click()
        self.assertFalse(self.screen.guide_body.isHidden())

    def test_theme_is_limited_to_this_screen(self):
        import re
        from app.my_borrowings_theme import MY_BORROWINGS_V2_QSS
        for group in re.findall(r"^([^\n{}/][^{}]*)\{", MY_BORROWINGS_V2_QSS, re.M):
            for selector in group.split(","):
                self.assertTrue(selector.strip().startswith("QWidget#myBorrowingsScreen"),
                                selector.strip())

    def test_duplicate_ids_are_rejected(self):
        one = make_borrowing("REQ-X", self.now, picked_days_ago=1, days=2)
        with self.assertRaises(ValueError):
            self.screen.set_borrowings([one, one])

    def test_replacing_the_list_clears_old_cards(self):
        self.screen.set_borrowings(build_sample_requests(self.now))
        self.screen.set_borrowings([])
        self.assertEqual(self.screen.current_requests, [])
        self.assertEqual(self.screen.history_requests, [])
        self.assertFalse(self.screen.empty_state.isHidden())


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardBorrowingsTests(unittest.TestCase):
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

    def test_new_account_opens_an_empty_my_borrowings_page(self):
        dash = self.build(self.ana)
        dash.go_to("borrowings")
        self.assertIs(dash.content_stack.currentWidget(), dash.my_borrowings_page)
        self.assertEqual(dash.my_borrowings_page.current_requests, [])
        self.assertFalse(dash.my_borrowings_page.empty_state.isHidden())

    def test_dashboard_shows_only_this_students_confirmed_borrowings(self):
        seed_samples(self.db, self.ana.id, prefix="A")
        seed_samples(self.db, self.ben.id, prefix="B")
        dash = self.build(self.ana)
        page = dash.my_borrowings_page
        ids = {r.request_id for r in page.current_requests + page.history_requests}
        self.assertEqual(len(ids), 3)
        self.assertTrue(all(i.startswith("AREQ-") for i in ids))
        # My Requests still shows all eight of Ana's requests
        self.assertEqual(len(dash.my_requests_page.requests), 8)

    def test_submitting_a_request_does_not_create_a_borrowing(self):
        dash = self.build(self.ana)
        item = AVAILABLE[0]
        when = (datetime.now().astimezone() + timedelta(hours=48)).replace(
            minute=0, second=0, microsecond=0)
        draft = RequestDraft(item=item, pickup_at=when, days=1, max_days=get_max_borrow_days(item))
        dash._submit_drafts([draft], "key-dash-1")
        self.assertEqual(len(dash.my_requests_page.requests), 1)
        self.assertEqual(dash.my_borrowings_page.current_requests, [])
        self.assertEqual(dash.my_borrowings_page.history_requests, [])

    def test_logout_clears_the_borrowings_page(self):
        seed_samples(self.db, self.ana.id)
        dash = self.build(self.ana)
        self.assertTrue(dash.my_borrowings_page.current_requests)
        logged_out = []
        dash.logout_requested.connect(lambda: logged_out.append(True))
        dash._emit_exit()
        self.assertEqual(logged_out, [True])
        self.assertEqual(dash.my_borrowings_page.current_requests, [])
        self.assertEqual(dash.my_borrowings_page.history_requests, [])

    def test_empty_state_button_goes_to_my_requests(self):
        dash = self.build(self.ana)
        dash.go_to("borrowings")
        dash.my_borrowings_page.my_requests_requested.emit()
        self.assertIs(dash.content_stack.currentWidget(), dash.my_requests_page)

    def test_other_pages_still_open(self):
        dash = self.build(self.ana)
        for key, attr in (("catalog", "catalog_page"), ("my_list", "my_list_page"),
                          ("my_requests", "my_requests_page")):
            dash.go_to(key)
            self.assertIs(dash.content_stack.currentWidget(), getattr(dash, attr))
        dash.go_to("notifications")  # a real page since Step 11
        self.assertIs(dash.content_stack.currentWidget(), dash.my_notifications_page)
        dash.go_to("settings")  # a real page since Step 12
        self.assertIs(dash.content_stack.currentWidget(), dash.settings_page)


if __name__ == "__main__":
    unittest.main()
