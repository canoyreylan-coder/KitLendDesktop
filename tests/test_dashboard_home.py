"""Stage 2A tests: the redesigned Dashboard home page (real data bindings, empty states,
navigation, 1366x768 layout, and that nothing else was touched).

Run from the project folder:   python -m unittest discover -s tests -p "test_dashboard_home.py" -v
Groups 1-2 need no window. Group 3 opens widgets in Qt's invisible "offscreen" mode.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import design_tokens as tk  # noqa: E402
from app.dashboard_view import EMPTY_VIEW, view_from_demo, view_from_requests  # noqa: E402
from app.my_requests_screen import RequestStatus  # noqa: E402
from app.sample_data import build_demo_data  # noqa: E402
from seed_helpers import (  # noqa: E402
    AVAILABLE,
    insert_request,
    make_borrowing,
    make_reservation,
    now_fixed,
)
from test_notifications import TempDbCase, make_draft  # noqa: E402


# ======================================================================
# 1. WHAT THE DASHBOARD SHOWS (plain data, real rules)
# ======================================================================
class ViewFromRequestsTests(unittest.TestCase):
    def setUp(self):
        self.now = now_fixed()

    def test_no_records_means_empty_lists_and_a_friendly_summary(self):
        view = view_from_requests([], self.now)
        self.assertEqual((view.borrowings, view.reservations, view.pending, view.activity),
                         ((), (), (), ()))
        self.assertIn("Nothing is borrowed", view.summary)
        self.assertEqual(view, EMPTY_VIEW)

    def test_a_confirmed_borrowing_shows_its_due_date_and_progress(self):
        request = make_borrowing("B1", self.now, picked_days_ago=2, days=5)
        view = view_from_requests([request], self.now)
        row = view.borrowings[0]
        self.assertEqual(row.title, request.item.title)
        self.assertEqual(row.pill_text, "3 days left")
        self.assertIn("Due", row.meta)
        self.assertTrue(0 < row.progress < 100)
        self.assertEqual(view.due_soon_count, 1)

    def test_overdue_and_return_reported_are_labelled(self):
        late = make_borrowing("B2", self.now, picked_days_ago=10, days=2)
        sent = make_borrowing("B3", self.now, picked_days_ago=3, days=5,
                              status=RequestStatus.RETURN_PENDING, item=AVAILABLE[1])
        view = view_from_requests([late, sent], self.now)
        texts = {row.title: row.pill_text for row in view.borrowings}
        self.assertTrue(texts[late.item.title].startswith("Overdue"))
        self.assertEqual(texts[sent.item.title], "Return reported")
        self.assertEqual(view.borrowings[0].pill_tone, "rose")  # most urgent first

    def test_returned_items_are_not_active_borrowings(self):
        done = make_borrowing("B4", self.now, picked_days_ago=5, days=3,
                              status=RequestStatus.RETURNED)
        self.assertEqual(view_from_requests([done], self.now).borrowings, ())

    def test_approved_awaiting_pickup_is_a_reservation_not_a_borrowing(self):
        reservation = make_reservation("R1", self.now)
        view = view_from_requests([reservation], self.now)
        self.assertEqual(len(view.reservations), 1)
        self.assertEqual(view.reservations[0].pill_text, "Awaiting pickup")
        self.assertEqual(view.borrowings, ())
        self.assertEqual(view.ready_count, 1)

    def test_pending_requests_are_listed_newest_first_and_only_pending(self):
        from app.my_requests_screen import BorrowRequest
        older = BorrowRequest("P1", AVAILABLE[0], 7, 2, self.now - timedelta(days=2),
                              RequestStatus.PENDING)
        newer = BorrowRequest("P2", AVAILABLE[1], 7, 3, self.now - timedelta(hours=1),
                              RequestStatus.PENDING)
        cancelled = BorrowRequest("P3", AVAILABLE[2], 7, 1, self.now - timedelta(days=1),
                                  RequestStatus.CANCELLED,
                                  status_changed_at=self.now - timedelta(hours=5))
        view = view_from_requests([older, newer, cancelled], self.now)
        self.assertEqual([r.title for r in view.pending],
                         [AVAILABLE[1].title, AVAILABLE[0].title])
        self.assertEqual(view.borrowings, ())
        self.assertEqual(view.reservations, ())

    def test_owner_approval_requests_render_as_pending_dashboard_activity(self):
        from app.my_requests_screen import BorrowRequest
        request = BorrowRequest(
            "P-owner", AVAILABLE[0], 7, 2, self.now,
            RequestStatus.PENDING_OWNER_APPROVAL, owner_listing_id="owner-listing")

        view = view_from_requests([request], self.now)

        self.assertEqual(len(view.pending), 1)
        self.assertEqual(view.pending[0].pill_text, "Pending Owner Approval")
        self.assertEqual(view.activity[0].title,
                         f"Awaiting owner approval: {request.item.title}")

    def test_activity_is_real_newest_first_and_limited(self):
        from app.my_requests_screen import BorrowRequest
        requests = [BorrowRequest(f"P{i}", AVAILABLE[i % len(AVAILABLE)], 7, 1,
                                  self.now - timedelta(days=i), RequestStatus.PENDING)
                    for i in range(8)]
        view = view_from_requests(requests, self.now)
        self.assertEqual(len(view.activity), 5)
        self.assertEqual(view.activity[0].meta, "Today")
        self.assertTrue(all(r.title.startswith("Requested ") for r in view.activity))
        three = view_from_requests(requests[:3], self.now)
        self.assertEqual(len(three.activity), 3)  # never padded with made-up entries

    def test_summary_counts_match_the_lists(self):
        view = view_from_requests(
            [make_borrowing("B5", self.now, picked_days_ago=1, days=7),
             make_reservation("R2", self.now)], self.now)
        self.assertIn("1 active borrowing", view.summary)
        self.assertIn("0 pending requests", view.summary)
        self.assertIn("1 reservation", view.summary)


class DemoViewTests(unittest.TestCase):
    def test_demo_view_mirrors_the_sample_data_and_has_no_pending_requests(self):
        data = build_demo_data()
        view = view_from_demo(data)
        self.assertEqual(len(view.borrowings), len(data.borrowings))
        self.assertEqual(len(view.reservations), len(data.reservations))
        self.assertEqual(view.pending, ())
        self.assertEqual(view.ready_count, data.ready_reservation_count)
        self.assertEqual(view.due_soon_count, len(data.due_soon()))


# ======================================================================
# 2. DESIGN RULES (no window)
# ======================================================================
class StyleTests(unittest.TestCase):
    def test_home_style_uses_the_dark_tokens_and_no_cream_or_thick_outlines(self):
        from app.home_theme import HOME_STYLESHEET
        for token in (tk.COLOR_BG_APP, tk.COLOR_BG_SURFACE, tk.COLOR_BORDER):
            self.assertIn(token, HOME_STYLESHEET)
        for old in ("#FFF9EF", "#F4F5FF", "3px solid", "2px solid"):
            self.assertNotIn(old, HOME_STYLESHEET)

    def test_every_tone_used_by_the_view_has_a_style(self):
        from app.home_theme import DOT_COLORS, PILL_TONES
        import app.dashboard_view as dv
        tones = set(dv._DUE_TONES.values()) | {t for _, t in dv._ACTIVITY.values()}
        tones |= {"muted", "lavender", "mint"}
        self.assertTrue(tones <= set(PILL_TONES) and tones <= set(DOT_COLORS), tones)

    def test_pill_text_is_readable_on_its_background(self):
        from app.home_theme import PILL_TONES
        from test_design_tokens import contrast
        for tone, (bg, fg) in PILL_TONES.items():
            self.assertGreaterEqual(contrast(bg, fg), 4.5, tone)


# ======================================================================
# 3. THE PAGE ITSELF (needs a real PySide6)
# ======================================================================
try:
    import PySide6
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False) and \
        type(QApplication).__name__ != "MagicMock"
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class HomePageTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def build(self, student):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        return StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests, auth_service=self.auth)

    def stats(self, dash):
        h = dash.home_page
        return [t.number_label.text() for t in
                (h.borrowings_stat, h.pending_stat, h.reservations_stat, h.notification_stat)]

    def texts(self, widget):
        return [l.text() for l in widget.findChildren(QLabel)]

    def test_new_student_sees_zeros_empty_states_and_no_invented_records(self):
        dash = self.build(self.ana)
        home = dash.home_page
        self.assertEqual(self.stats(dash), ["0", "0", "0", "0"])
        for note in ("You have no active borrowings.", "You have no pending requests.",
                     "You have no reservations.", "No notifications yet.",
                     "No recent activity."):
            self.assertIn(note, self.texts(home))
        self.assertIn("Ana", home.findChild(QLabel, "homeTitle").text())

    def test_submitting_a_request_updates_pending_activity_and_summary(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        home = dash.home_page
        self.assertEqual(self.stats(dash), ["0", "1", "0", "1"])
        self.assertEqual(home.pending_card._rows.count(), 1)
        self.assertEqual(home.activity_card._rows.count(), 1)
        self.assertIn("1 pending request", home.summary_label.text())

    def test_real_borrowings_and_reservations_appear_from_the_database(self):
        now = now_fixed()
        insert_request(self.db, self.ana.id,
                       make_borrowing("B9", now, picked_days_ago=1, days=4), "kb")
        insert_request(self.db, self.ana.id, make_reservation("R9", now, item=AVAILABLE[1]), "kr")
        dash = self.build(self.ana)
        self.assertEqual(self.stats(dash)[:3], ["1", "0", "1"])
        self.assertEqual(dash.home_page.borrowings_card._rows.count(), 1)
        self.assertEqual(dash.home_page.reservations_card._rows.count(), 1)

    def test_students_never_see_each_others_records(self):
        dash_ana = self.build(self.ana)
        dash_ana._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        dash_ben = self.build(self.ben)
        self.assertEqual(self.stats(dash_ben), ["0", "0", "0", "0"])

    def test_logout_clears_the_dashboard(self):
        dash = self.build(self.ana)
        dash._submit_drafts([make_draft(AVAILABLE[0])], "k1")
        dash._emit_exit()
        self.assertEqual(self.stats(dash), ["0", "0", "0", "0"])
        self.assertEqual(dash.home_page.pending_card._rows.count(), 1)  # the empty note

    def test_tiles_links_and_quick_actions_navigate(self):
        dash = self.build(self.ana)
        home = dash.home_page
        seen = []
        home.navigate_requested.connect(seen.append)
        for tile in (home.borrowings_stat, home.pending_stat, home.reservations_stat,
                     home.notification_stat):
            tile.clicked.emit()
        self.assertEqual(seen, ["borrowings", "my_requests", "reservations", "notifications"])
        seen.clear()
        by_text = {b.text(): b for b in home.findChildren(QPushButton)}
        for text, page in (("Browse Catalog", "catalog"), ("My List", "my_list"),
                           ("My Requests", "my_requests"), ("My Borrowings", "borrowings")):
            by_text[text].click()
            self.assertEqual(seen[-1], page)
        for card, page in ((home.borrowings_card, "borrowings"),
                           (home.pending_card, "my_requests"),
                           (home.reservations_card, "reservations"),
                           (home.notifications_card, "notifications")):
            card.action_clicked.emit()
            self.assertEqual(seen[-1], page)

    def test_navigation_from_the_dashboard_opens_the_real_pages(self):
        dash = self.build(self.ana)
        dash.home_page.navigate_requested.emit("catalog")
        self.assertIs(dash.content_stack.currentWidget(), dash.catalog_page)

    def test_no_dashed_mascot_placeholder_is_shown(self):
        dash = self.build(self.ana)
        self.assertFalse(any("placeholder" in t.lower() for t in self.texts(dash.home_page)))
        self.assertLessEqual(len(dash.home_page.findChildren(QLabel, "homeMascot")), 1)

    def test_it_fits_a_1366_by_768_window_without_sideways_scrolling(self):
        dash = self.build(self.ana)
        dash.resize(1366, 768)
        dash.show()
        self.qt_app.processEvents()
        home = dash.home_page
        self.assertEqual(home.horizontalScrollBar().maximum(), 0)
        from PySide6.QtWidgets import QFrame
        welcome = home.findChild(QFrame, "homeWelcome")
        self.assertLess(welcome.height(), 140)
        tops = {t.mapTo(home.widget(), t.rect().topLeft()).y() for t in
                (home.borrowings_stat, home.pending_stat, home.reservations_stat,
                 home.notification_stat)}
        self.assertEqual(len(tops), 1)  # four tiles in one row
        for tile in (home.borrowings_stat, home.notification_stat):
            right = tile.mapTo(home.widget(), tile.rect().topRight()).x()
            self.assertLessEqual(right, home.viewport().width())
        dash.resize(900, 700)  # a narrow window stacks instead of overflowing
        self.qt_app.processEvents()
        self.assertEqual(home.horizontalScrollBar().maximum(), 0)

    def test_other_pages_keep_their_original_style_and_the_sidebar_still_works(self):
        dash = self.build(self.ana)
        self.assertEqual(dash.settings_page.objectName(), "settingsScreen")  # Step 28 redesign
        self.assertNotIn("homeCard", dash.settings_page.styleSheet())
        self.assertEqual(dash.home_page.objectName(), "homeScroll")
        for key in ("catalog", "my_list", "my_requests", "borrowings", "reservations",
                    "notifications", "settings", "dashboard"):
            dash.go_to(key)


if __name__ == "__main__":
    unittest.main()
