"""My List persistence tests: bookmarked items are saved per student in SQLite.

Groups 1 needs no window (temporary database). Group 2 opens the real dashboard in Qt's
invisible "offscreen" mode and is skipped if PySide6 is not installed.

Run from the project folder:   python -m unittest discover -s tests -p "test_saved_items.py" -v
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

from app import database  # noqa: E402
from app.auth_service import AuthService  # noqa: E402
from app.saved_items_service import SavedItemsError, SavedItemsService  # noqa: E402

try:
    import PySide6
    from PySide6.QtWidgets import QApplication
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False

PW = "correct horse"


class TempDbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")

    def rows(self, sql, params=()):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()


# ======================================================================
# 1. THE SERVICE (temporary database, no window)
# ======================================================================
class SavedItemsServiceTests(TempDbCase):
    def setUp(self):
        super().setUp()
        self.service = SavedItemsService(self.db)

    def test_a_new_student_has_an_empty_list(self):
        self.assertEqual(self.service.list_keys(self.ana.id), [])

    def test_saved_items_survive_a_restart(self):
        self.assertTrue(self.service.add(self.ana.id, "school|Room 1|Book A"))
        self.assertTrue(self.service.add(self.ana.id, "school|Room 1|Book B"))
        again = SavedItemsService(self.db)  # a brand-new service = a restarted app
        self.assertEqual(again.list_keys(self.ana.id),
                         ["school|Room 1|Book A", "school|Room 1|Book B"])

    def test_removing_is_permanent(self):
        self.service.add(self.ana.id, "k1")
        self.service.add(self.ana.id, "k2")
        self.assertTrue(self.service.remove(self.ana.id, "k1"))
        self.assertEqual(SavedItemsService(self.db).list_keys(self.ana.id), ["k2"])
        self.assertFalse(self.service.remove(self.ana.id, "k1"))  # already gone

    def test_the_same_item_cannot_be_saved_twice(self):
        self.assertTrue(self.service.add(self.ana.id, "k1"))
        self.assertFalse(self.service.add(self.ana.id, "k1"))
        self.assertEqual(self.service.list_keys(self.ana.id), ["k1"])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM saved_items")[0][0], 1)

    def test_each_account_has_its_own_list(self):
        self.service.add(self.ana.id, "k1")
        self.service.add(self.ben.id, "k2")
        self.service.add(self.ben.id, "k1")
        self.assertEqual(self.service.list_keys(self.ana.id), ["k1"])
        self.assertEqual(self.service.list_keys(self.ben.id), ["k2", "k1"])
        self.service.remove(self.ben.id, "k1")
        self.assertEqual(self.service.list_keys(self.ana.id), ["k1"])  # Ana is unaffected

    def test_bad_arguments_give_a_friendly_error(self):
        for args in ((None, "k"), (True, "k"), (self.ana.id, ""), (self.ana.id, None)):
            with self.assertRaises(SavedItemsError):
                self.service.add(*args)
            with self.assertRaises(SavedItemsError):
                self.service.remove(*args)
        self.assertEqual(self.service.list_keys(None), [])

    def test_the_migration_is_additive_and_upgrades_an_older_database(self):
        old = os.path.join(self.tmp.name, "old.db")
        conn = sqlite3.connect(old)
        conn.row_factory = sqlite3.Row
        conn.executescript(database.SCHEMA)
        conn.execute(database._MIGRATION_TABLE)
        for version, name, statements in database.MIGRATIONS:
            if version <= 9:
                for statement in statements:
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migrations VALUES (?, ?, 't')", (version, name))
        conn.commit()
        conn.close()
        auth = AuthService(old)  # opens the database -> applies migration 10
        student = auth.register("Old Account", "old@csucc.edu.ph", PW, PW, student_id_number="ID-OLD")
        service = SavedItemsService(old)
        self.assertEqual(service.list_keys(student.id), [])
        service.add(student.id, "k1")
        self.assertEqual(SavedItemsService(old).list_keys(student.id), ["k1"])
        self.assertEqual(auth.login("old@csucc.edu.ph", PW).id, student.id)

    def test_an_unreadable_database_never_stops_the_list_from_loading(self):
        broken = os.path.join(self.tmp.name, "broken.db")
        Path(broken).write_text("this is not a database", encoding="utf-8")
        self.assertEqual(SavedItemsService(broken).list_keys(1), [])


# ======================================================================
# 2. THE REAL DASHBOARD (needs PySide6)
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardMyListTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        from app.catalog_screen import SAMPLE_ITEMS
        from app.request_service import RequestService
        self.items = SAMPLE_ITEMS
        self.requests = RequestService(self.db)
        self.dash = self.open_dash(self.ana)

    def open_dash(self, student):
        """Open the dashboard exactly like a login does (a new one = an app restart)."""
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        return StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests, auth_service=self.auth)

    def saved_keys(self, student):
        return SavedItemsService(self.db).list_keys(student.id)

    def star(self, dash, item):
        """Click the Catalog star of `item` (the same signal a real click sends)."""
        dash.catalog_page.bookmark_toggled.emit(item, True)

    def unstar(self, dash, item):
        dash.catalog_page.bookmark_toggled.emit(item, False)

    def test_a_star_is_saved_immediately(self):
        self.star(self.dash, self.items[0])
        self.assertEqual(self.saved_keys(self.ana), [self.items[0].listing_key])
        self.assertEqual(self.dash.my_list_page._saved_items, [self.items[0]])

    def test_saved_items_come_back_after_restarting(self):
        self.star(self.dash, self.items[0])
        self.star(self.dash, self.items[1])
        again = self.open_dash(self.ana)
        self.assertEqual(again._bookmarks, [self.items[0], self.items[1]])
        self.assertEqual(again.my_list_page._saved_items, [self.items[0], self.items[1]])
        self.assertEqual(again.catalog_page._bookmarked, {self.items[0], self.items[1]})

    def test_removing_from_the_catalog_is_saved_and_stays_removed_after_restart(self):
        self.star(self.dash, self.items[0])
        self.unstar(self.dash, self.items[0])
        self.assertEqual(self.saved_keys(self.ana), [])
        again = self.open_dash(self.ana)
        self.assertEqual(again.my_list_page._saved_items, [])
        self.assertEqual(again.catalog_page._bookmarked, set())

    def test_removing_from_my_list_is_saved_and_the_catalog_star_clears(self):
        self.star(self.dash, self.items[0])
        self.star(self.dash, self.items[1])
        self.dash.my_list_page.remove_item(self.items[0])
        self.assertEqual(self.saved_keys(self.ana), [self.items[1].listing_key])
        self.assertEqual(self.dash.catalog_page._bookmarked, {self.items[1]})
        again = self.open_dash(self.ana)
        self.assertEqual(again.my_list_page._saved_items, [self.items[1]])

    def test_item_details_star_saves_and_keeps_everything_in_sync(self):
        item = self.items[2]
        self.dash._open_item_details(item)
        self.dash.item_details_page.bookmark_toggled.emit(item, True)
        self.assertEqual(self.saved_keys(self.ana), [item.listing_key])
        self.assertIn(item, self.dash.catalog_page._bookmarked)
        self.assertEqual(self.dash.my_list_page._saved_items, [item])
        self.dash.item_details_page.bookmark_toggled.emit(item, False)
        self.assertEqual(self.saved_keys(self.ana), [])
        self.assertNotIn(item, self.dash.catalog_page._bookmarked)
        self.assertEqual(self.dash.my_list_page._saved_items, [])

    def test_saving_the_same_item_twice_keeps_one_copy(self):
        self.star(self.dash, self.items[0])
        self.star(self.dash, self.items[0])
        self.assertEqual(self.saved_keys(self.ana), [self.items[0].listing_key])
        self.assertEqual(self.dash.my_list_page._saved_items, [self.items[0]])

    def test_each_account_sees_only_its_own_saved_items(self):
        self.star(self.dash, self.items[0])
        ben = self.open_dash(self.ben)
        self.assertEqual(ben._bookmarks, [])
        self.star(ben, self.items[1])
        ana_again = self.open_dash(self.ana)
        self.assertEqual(ana_again._bookmarks, [self.items[0]])

    def test_logging_out_clears_the_screen_but_not_the_saved_list(self):
        self.star(self.dash, self.items[0])
        self.dash._emit_exit()
        self.assertEqual(self.dash._bookmarks, [])
        self.assertEqual(self.saved_keys(self.ana), [self.items[0].listing_key])
        self.assertEqual(self.open_dash(self.ana)._bookmarks, [self.items[0]])

    def test_a_saved_item_that_is_no_longer_in_the_catalog_is_ignored(self):
        SavedItemsService(self.db).add(self.ana.id, "school|nowhere|Discontinued thing")
        self.star(self.dash, self.items[0])
        again = self.open_dash(self.ana)
        self.assertEqual(again._bookmarks, [self.items[0]])

    def test_a_failed_save_does_not_leave_a_star_that_would_not_last(self):
        class Broken(SavedItemsService):
            def add(self, *args):
                raise SavedItemsError("Could not save this item to your My List.")
        self.dash._saved_items_service = Broken(self.db)
        self.star(self.dash, self.items[0])
        self.assertEqual(self.dash._bookmarks, [])
        self.assertEqual(self.dash.catalog_page._bookmarked, set())
        self.assertEqual(self.dash.my_list_page._saved_items, [])

    def test_the_demo_still_works_without_a_database(self):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_demo_data
        demo = StudentDashboard(build_demo_data())
        self.assertFalse(demo.stores_saved_items)

    def test_requests_and_accounts_are_untouched(self):
        before = self.rows("SELECT COUNT(*) FROM students")[0][0]
        self.star(self.dash, self.items[0])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM students")[0][0], before)
        self.assertEqual(self.auth.login(self.ana.email, PW).id, self.ana.id)


if __name__ == "__main__":
    unittest.main()
