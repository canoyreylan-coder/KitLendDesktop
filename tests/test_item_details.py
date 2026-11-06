"""Step 19/20 tests: Item Details page, Report Listing and its SQLite storage.

Run from the project folder:   python -m unittest discover -s tests -p "test_item_details.py" -v

Groups 1-2 need no window (temporary database only). Groups 3-4 open the real Dashboard in
Qt's invisible "offscreen" mode. Nothing here ever touches your real database.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import database  # noqa: E402
from app.auth_service import AuthService  # noqa: E402
from app.report_service import (  # noqa: E402
    MAX_DESCRIPTION_LENGTH,
    REASON_OTHER,
    REPORT_REASONS,
    ReportError,
    ReportService,
)

try:
    from PySide6.QtWidgets import QApplication
    from app.catalog_screen import SAMPLE_ITEMS
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

PW = "correct horse"


@dataclass(frozen=True)
class FakeItem:
    """Just what the report service needs (so groups 1-2 run without Qt)."""
    title: str = "Clean Code"
    owner_note: str = "Shared by Mark D."
    ownership: str = "student"

    @property
    def listing_key(self):
        return f"{self.ownership}|{self.owner_note}|{self.title}"


# ======================================================================
# 1. STORAGE + MIGRATION
# ======================================================================
class ReportStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")
        self.service = ReportService(self.db)
        self.item = FakeItem()

    def rows(self, sql="SELECT * FROM listing_reports", params=()):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_migration_adds_table_and_keeps_accounts(self):
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM students")[0]["n"], 2)
        self.assertIn(8, [r["version"] for r in self.rows("SELECT version FROM schema_migrations")])
        self.assertEqual(self.rows(), [])
        self.assertTrue(self.auth.login("ana@csucc.edu.ph", PW))  # login still works

    def test_report_is_saved_with_account_and_listing(self):
        report = self.service.submit_report(
            self.ana.id, self.item, "Inaccurate information", "  Wrong author  ")
        row = self.rows()[0]
        self.assertEqual(row["student_id"], self.ana.id)
        self.assertEqual(row["listing_key"], self.item.listing_key)
        self.assertEqual(row["listing_title"], "Clean Code")
        self.assertEqual(row["reason"], "Inaccurate information")
        self.assertEqual(row["description"], "Wrong author")
        self.assertEqual(row["status"], "Open")
        self.assertEqual(row["report_id"], report.report_id)

    def test_description_is_optional_except_for_other(self):
        self.service.submit_report(self.ana.id, self.item, "Duplicate listing")
        self.assertEqual(self.rows()[0]["description"], "")
        other = FakeItem(title="Python Crash Course")
        for text in ("", "   ", None):
            with self.assertRaises(ReportError):
                self.service.submit_report(self.ana.id, other, REASON_OTHER, text)
        self.service.submit_report(self.ana.id, other, REASON_OTHER, "Photo is wrong")
        self.assertEqual(len(self.rows()), 2)

    def test_invalid_reason_or_long_description_is_rejected(self):
        for reason in ("", None, "Made up reason", "Select a reason..."):
            with self.assertRaises(ReportError):
                self.service.submit_report(self.ana.id, self.item, reason)
        with self.assertRaises(ReportError):
            self.service.submit_report(
                self.ana.id, self.item, REPORT_REASONS[0], "x" * (MAX_DESCRIPTION_LENGTH + 1))
        self.assertEqual(self.rows(), [])

    def test_duplicate_report_is_prevented(self):
        self.service.submit_report(self.ana.id, self.item, "Inaccurate information")
        with self.assertRaises(ReportError) as ctx:
            self.service.submit_report(self.ana.id, self.item, "Inaccurate information")
        self.assertIn("already reported", str(ctx.exception))
        with self.assertRaises(ReportError):  # a different reason is still the same listing
            self.service.submit_report(self.ana.id, self.item, "Duplicate listing")
        self.assertEqual(len(self.rows()), 1)

    def test_database_itself_refuses_a_duplicate(self):
        self.service.submit_report(self.ana.id, self.item, "Inaccurate information")
        conn = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO listing_reports (report_id, student_id, listing_key, "
                    "listing_title, listing_owner, reason, status, created_at) "
                    "VALUES ('x', ?, ?, 't', 'o', 'r', 'Open', 'now')",
                    (self.ana.id, self.item.listing_key))
        finally:
            conn.close()

    def test_other_account_and_other_listing_are_independent(self):
        self.service.submit_report(self.ana.id, self.item, "Inaccurate information")
        self.assertTrue(self.service.has_reported(self.ana.id, self.item.listing_key))
        self.assertFalse(self.service.has_reported(self.ben.id, self.item.listing_key))
        self.assertFalse(self.service.has_reported(self.ana.id, FakeItem(title="Other").listing_key))
        self.service.submit_report(self.ben.id, self.item, "Duplicate listing")
        self.service.submit_report(self.ana.id, FakeItem(title="Other"), "Duplicate listing")
        self.assertEqual(len(self.rows()), 3)
        self.assertEqual(len(self.service.list_reports(self.ana.id)), 2)
        self.assertEqual(len(self.service.list_reports(self.ben.id)), 1)

    def test_logged_out_student_cannot_report(self):
        for bad in (None, "1", True):
            with self.assertRaises(ReportError):
                self.service.submit_report(bad, self.item, "Duplicate listing")

    def test_reports_survive_reopening_the_database(self):
        self.service.submit_report(self.ana.id, self.item, "Duplicate listing")
        again = ReportService(self.db)
        self.assertTrue(again.has_reported(self.ana.id, self.item.listing_key))


# ======================================================================
# 2. MIGRATION ON AN OLD (Step 18) DATABASE
# ======================================================================
class UpgradeTests(unittest.TestCase):
    def test_step18_database_is_upgraded_without_losing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "old.db")
            auth = AuthService(db)
            student = auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
            conn = sqlite3.connect(db)
            conn.execute("DROP TABLE listing_reports")
            conn.execute("DELETE FROM schema_migrations WHERE version = 8")
            conn.commit()
            conn.close()
            conn = database.connect(db)  # applies migration 8 again
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM students").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM listing_reports").fetchone()[0], 0)
            finally:
                conn.close()
            self.assertEqual(auth.login("ana@csucc.edu.ph", PW).id, student.id)


# ======================================================================
# 3. THE PAGE AND THE DIALOG (Qt, offscreen)
# ======================================================================
_app = QApplication.instance() or QApplication([]) if HAVE_QT else None


def make_dashboard(case, student):
    from app.dashboard_screen import StudentDashboard
    from app.request_service import RequestService
    from app.sample_data import build_empty_data
    dash = StudentDashboard(
        build_empty_data(student.full_name), signed_in_email=student.email,
        student_id=student.id, request_service=RequestService(case.db))
    case.addCleanup(dash.deleteLater)
    return dash


def by_title(title):
    return next(item for item in SAMPLE_ITEMS if item.title == title)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DetailsPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.dash = make_dashboard(self, self.ana)
        self.page = self.dash.item_details_page

    def texts(self):
        from PySide6.QtWidgets import QLabel
        return [label.text() for label in self.page.findChildren(QLabel)]

    def test_facts_only_use_real_data(self):
        from app.item_details_screen import NOT_RECORDED, item_facts
        item = by_title("Clean Code")
        facts = item_facts(item)
        flat = dict(row for rows in facts.values() for row in rows)
        self.assertEqual(flat["Type"], "Book")
        self.assertEqual(flat["Category"], "Programming")
        self.assertEqual(flat["Condition"], NOT_RECORDED)   # no condition data -> not invented
        self.assertEqual(flat["Owner"], "Mark D.")
        self.assertEqual(flat["Status"], "Currently borrowed")
        self.assertEqual(flat["Copies available"], "0 of 1")
        self.assertEqual(flat["Collections"], "None")
        self.assertIn("day", flat["Maximum loan"])

    def test_recorded_condition_is_shown(self):
        from dataclasses import replace
        from app.item_details_screen import item_facts
        item = replace(by_title("Clean Code"))
        object.__setattr__(item, "condition", "Good")
        self.assertIn(("Condition", "Good"), item_facts(item)["About this item"])

    def test_invalid_copy_counts_are_not_invented(self):
        from dataclasses import replace
        from app.item_details_screen import NOT_RECORDED, item_facts
        item = replace(by_title("Clean Code"), copies_available=None)
        facts = dict(item_facts(item)["Availability"])
        self.assertEqual(facts["Copies available"], NOT_RECORDED)
        self.assertEqual(facts["Status"], "Availability unknown")

    def test_clicking_a_grid_card_opens_details(self):
        catalog = self.dash.catalog_page
        self.dash.go_to("catalog")
        card = next(c for c in catalog._cards if c.item.title == "Clean Code")
        card.clicked.emit(card.item)
        self.assertIs(self.dash.content_stack.currentWidget(), self.page)
        self.assertEqual(self.page.item.title, "Clean Code")
        self.assertIn("Clean Code", self.texts())

    def test_clicking_a_list_row_opens_details(self):
        catalog = self.dash.catalog_page
        catalog.set_view_mode("list", emit=False)
        row = next(r for r in catalog._rows if r.item.title == "Python Crash Course")
        row.clicked.emit(row.item)
        self.assertIs(self.dash.content_stack.currentWidget(), self.page)
        self.assertEqual(self.page.item.title, "Python Crash Course")

    def test_back_keeps_search_filters_view_and_scroll(self):
        catalog = self.dash.catalog_page
        self.dash.resize(1100, 520)
        self.dash.show()
        self.dash.go_to("catalog")
        catalog.set_view_mode("list", emit=False)
        catalog.search_input.setText("a")
        catalog.filter_panel.combo("ownership").setCurrentIndex(1)
        _app.processEvents()
        shown_before = [i.title for i in catalog.visible_items]
        bar = catalog.catalog_scroll.verticalScrollBar()
        bar.setValue(min(120, bar.maximum()))
        wanted = bar.value()
        row = catalog.visible_rows[0]
        row.clicked.emit(row.item)
        _app.processEvents()
        self.page.back_button.click()
        _app.processEvents()
        self.assertIs(self.dash.content_stack.currentWidget(), catalog)
        self.assertEqual(catalog.view_mode, "list")
        self.assertEqual(catalog.search_input.text(), "a")
        self.assertEqual(catalog.filter_panel.combo("ownership").currentIndex(), 1)
        self.assertEqual([i.title for i in catalog.visible_items], shown_before)
        self.assertEqual(bar.value(), wanted)
        self.dash.hide()

    def test_save_to_my_list_reuses_existing_list_and_syncs_catalog(self):
        item = by_title("Grokking Algorithms")
        self.dash._open_item_details(item)
        self.page.save_button.click()
        self.assertIn(item, self.dash._bookmarks)
        self.assertIn(item, self.dash.catalog_page.bookmarked_items)
        self.page.save_button.click()
        self.assertNotIn(item, self.dash._bookmarks)
        self.assertNotIn(item, self.dash.catalog_page.bookmarked_items)

    def test_details_shows_saved_state_and_follows_my_list_removal(self):
        item = by_title("Grokking Algorithms")
        self.dash._on_catalog_bookmark_toggled(item, True)
        self.dash._open_item_details(item)
        self.assertTrue(self.page.save_button.isChecked())
        self.dash._on_my_list_item_removed(item)
        self.assertFalse(self.page.save_button.isChecked())

    def test_request_now_uses_existing_request_flow(self):
        calls = []
        self.dash._on_direct_request = lambda item: calls.append(item)
        self.page.request_clicked.disconnect()
        self.page.request_clicked.connect(lambda item: calls.append(item))
        self.dash._open_item_details(by_title("Grokking Algorithms"))
        self.page.request_button.click()
        self.assertEqual([i.title for i in calls], ["Grokking Algorithms"])

    def test_gallery_opens_in_app_viewer_from_main_photo_and_thumbnail(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPixmap
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QPushButton

        paths = []
        for index, color in enumerate(("red", "blue")):
            path = os.path.join(self.tmp.name, f"photo-{index}.png")
            pixmap = QPixmap(640, 480)
            pixmap.fill(QColor(color))
            self.assertTrue(pixmap.save(path))
            paths.append(path)

        item = by_title("Grokking Algorithms")
        self.dash.resize(1000, 700)
        self.dash.show()
        self.dash._open_item_details(item)
        self.page.show_item(item, photos=paths)
        _app.processEvents()
        QTest.mouseClick(self.page.image_slot, Qt.LeftButton)
        _app.processEvents()
        self.assertTrue(self.page.image_viewer.isVisible())
        self.assertEqual(self.page._photo_index, 0)
        self.page.viewer_close_button.click()
        self.page.thumb_buttons[1].click()
        _app.processEvents()
        self.assertTrue(self.page.image_viewer.isVisible())
        self.assertEqual(self.page._photo_index, 1)

        initial_scale = self.page._image_scale
        zoom_in = next(button for button in self.page.image_viewer.findChildren(QPushButton)
                       if button.text() == "Zoom In")
        zoom_in.click()
        self.assertGreater(self.page._image_scale, initial_scale)
        zoom_out = next(button for button in self.page.image_viewer.findChildren(QPushButton)
                        if button.text() == "Zoom Out")
        zoom_out.click()
        self.assertAlmostEqual(self.page._image_scale, initial_scale)
        fit = next(button for button in self.page.image_viewer.findChildren(QPushButton)
                   if button.text() == "Fit / Reset")
        fit.click()
        self.assertAlmostEqual(self.page._image_scale, initial_scale)
        self.page.viewer_close_button.click()
        self.assertFalse(self.page.image_viewer.isVisible())
        self.dash.hide()

    def test_details_grid_reflows_when_window_narrows(self):
        from PySide6.QtWidgets import QApplication
        from app.item_details_screen import ItemDetailsScreen

        page = ItemDetailsScreen()
        self.addCleanup(page.deleteLater)
        page.resize(1000, 700)
        page.show_item(by_title("Clean Code"))
        page.show()
        QApplication.processEvents()
        self.assertEqual(page.content_grid._columns, 2)
        page.resize(500, 700)
        QApplication.processEvents()
        self.assertEqual(page.content_grid._columns, 1)
        page.close()

    def test_sections_follow_top_row_at_full_width_and_scroll_naturally(self):
        from dataclasses import replace
        from PySide6.QtWidgets import QApplication
        from app.item_details_screen import ItemDetailsScreen

        page = ItemDetailsScreen()
        self.addCleanup(page.deleteLater)
        item = replace(by_title("Clean Code"), description="Long description " * 300)
        page.resize(1100, 560)
        page.show_item(item)
        page.show()
        QApplication.processEvents()

        self.assertEqual(page.content_grid._columns, 2)
        self.assertEqual(page.gallery_widget.geometry().top(),
                         page.information_widget.geometry().top())
        self.assertNotIn(page.description_section, page.content_grid._widgets)
        self.assertNotIn(page.borrowing_rules_section, page.content_grid._widgets)
        self.assertNotIn(page.availability_section, page.content_grid._widgets)
        content_column = page._content.layout().itemAt(0).widget()
        content_layout = content_column.layout()
        self.assertIs(content_layout.itemAt(1).widget(), page.content_grid)
        self.assertIs(content_layout.itemAt(2).widget(), page.description_section)
        self.assertIs(content_layout.itemAt(3).widget(), page.borrowing_rules_section)
        self.assertIs(content_layout.itemAt(4).widget(), page.availability_section)
        self.assertIs(page.description_section.parentWidget(), content_column)
        self.assertEqual(page.description_section.width(), content_column.width())
        self.assertGreater(page.description_section.height(), 100)
        self.assertGreater(page.scroll.verticalScrollBar().maximum(), 0)

        page.resize(520, 560)
        QApplication.processEvents()
        self.assertEqual(page.content_grid._columns, 1)
        page.close()

    def test_unavailable_item_cannot_be_requested_but_can_be_saved(self):
        self.dash._open_item_details(by_title("Clean Code"))
        self.assertFalse(self.page.request_button.isEnabled())
        self.assertTrue(self.page.save_button.isEnabled())

    def test_sidebar_keeps_browse_catalog_highlighted(self):
        self.dash._open_item_details(by_title("Clean Code"))
        self.assertTrue(self.dash._nav_buttons["catalog"].isChecked())

    def test_logout_clears_the_page(self):
        self.dash._open_item_details(by_title("Clean Code"))
        self.dash._emit_exit()
        self.assertIsNone(self.page.item)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class ReportDialogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")
        self.service = ReportService(self.db)
        self.item = by_title("Clean Code")

    def dialog(self, student=None):
        from app.item_details_screen import ReportListingDialog
        student = student or self.ana
        dlg = ReportListingDialog(
            self.item, None,
            submit_handler=lambda r, d: self.service.submit_report(student.id, self.item, r, d))
        self.addCleanup(dlg.deleteLater)
        return dlg

    def test_reason_must_be_chosen(self):
        dlg = self.dialog()
        self.assertFalse(dlg.submit())
        self.assertFalse(dlg.error_label.isHidden())
        self.assertEqual(self.service.list_reports(self.ana.id), [])

    def test_all_reasons_are_offered(self):
        dlg = self.dialog()
        offered = [dlg.reason_combo.itemText(i) for i in range(1, dlg.reason_combo.count())]
        self.assertEqual(offered, list(REPORT_REASONS))

    def test_other_requires_a_description(self):
        dlg = self.dialog()
        dlg.reason_combo.setCurrentText(REASON_OTHER)
        self.assertIn("required", dlg.description_caption.text())
        self.assertFalse(dlg.submit())
        self.assertFalse(dlg.error_label.isHidden())
        dlg.description_edit.setPlainText("The photo shows another item")
        self.assertTrue(dlg.submit())
        self.assertEqual(len(self.service.list_reports(self.ana.id)), 1)

    def test_description_is_optional_for_other_reasons(self):
        dlg = self.dialog()
        dlg.reason_combo.setCurrentText("Duplicate listing")
        self.assertTrue(dlg.submit())
        self.assertTrue(dlg.submitted)

    def test_duplicate_is_shown_in_the_dialog(self):
        self.service.submit_report(self.ana.id, self.item, "Duplicate listing")
        dlg = self.dialog()
        dlg.reason_combo.setCurrentText("Inaccurate information")
        self.assertFalse(dlg.submit())
        self.assertIn("already reported", dlg.error_label.text())
        self.assertEqual(len(self.service.list_reports(self.ana.id)), 1)

    def test_description_is_limited_while_typing(self):
        dlg = self.dialog()
        dlg.description_edit.setPlainText("x" * (MAX_DESCRIPTION_LENGTH + 50))
        self.assertEqual(len(dlg.description_edit.toPlainText()), MAX_DESCRIPTION_LENGTH)

    def test_reporting_never_removes_the_listing(self):
        count = len(SAMPLE_ITEMS)
        dlg = self.dialog()
        dlg.reason_combo.setCurrentText("Suspected scam or misuse")
        self.assertTrue(dlg.submit())
        self.assertEqual(len(SAMPLE_ITEMS), count)
        self.assertIn(self.item, SAMPLE_ITEMS)

    def test_page_report_menu_state(self):
        from app.item_details_screen import ItemDetailsScreen
        page = ItemDetailsScreen()
        self.addCleanup(page.deleteLater)
        seen = []
        page.report_requested.connect(seen.append)
        self.assertFalse(page.menu_button.isEnabled())       # no item yet
        page.show_item(self.item)
        self.assertEqual(page.menu_button.text(), "⋮")
        self.assertEqual([a.text() for a in page.menu.actions()], ["Report Listing"])
        self.assertFalse(page.report_action.icon().isNull())  # flag icon
        page.report_action.trigger()
        self.assertEqual(seen, [self.item])
        page.set_reported(True)
        self.assertFalse(page.report_action.isEnabled())
        self.assertEqual(page.report_action.text(), "Listing Reported")
        page.report_action.trigger()
        self.assertEqual(seen, [self.item])                   # no second request
        page.show_item(self.item, reported=True)
        self.assertFalse(page.report_action.isEnabled())

    def test_dialog_is_compact(self):
        dlg = self.dialog()
        dlg.show()
        self.assertEqual(dlg.width(), 400)
        self.assertLess(dlg.height(), 420)
        dlg.close()


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")
        self.item = by_title("Clean Code")

    def test_already_reported_listing_opens_with_disabled_report_button(self):
        ReportService(self.db).submit_report(self.ana.id, self.item, "Duplicate listing")
        ana = make_dashboard(self, self.ana)
        ana._open_item_details(self.item)
        self.assertFalse(ana.item_details_page.report_action.isEnabled())
        ben = make_dashboard(self, self.ben)   # another account is not affected
        ben._open_item_details(self.item)
        self.assertTrue(ben.item_details_page.report_action.isEnabled())


if __name__ == "__main__":
    unittest.main()
