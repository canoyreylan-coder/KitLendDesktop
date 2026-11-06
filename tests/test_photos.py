"""Step 21 tests: listing photo references and the compact gallery.

Run:   python -m unittest discover -s tests -p "test_photos.py" -v
Groups 1-2 need no window. Group 3 uses Qt's invisible "offscreen" mode and small pictures
generated into a temporary folder. Your real database and photos are never touched.
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
from app.photo_service import MAX_PHOTOS, PhotoError, PhotoService  # noqa: E402

try:
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication
    from app.catalog_screen import SAMPLE_ITEMS
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

PW = "correct horse"
KEY = "student|Shared by Mark D.|Clean Code"


class TempFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.photos = os.path.join(self.tmp.name, "photos")
        os.makedirs(self.photos)
        self.auth = AuthService(self.db)
        self.service = PhotoService(self.db, self.photos)

    def make_file(self, name, color="#4466cc", size=(120, 80)):
        """A real picture file when Qt is available, otherwise a stand-in file."""
        path = os.path.join(self.photos, name)
        if HAVE_QT:
            image = QImage(size[0], size[1], QImage.Format_RGB32)
            image.fill(QColor(color))
            image.save(path)
        else:
            Path(path).write_bytes(b"x")
        return path


class PhotoServiceTests(TempFolder):
    def test_new_database_has_no_photos_and_none_are_invented(self):
        self.assertEqual(self.service.photos_for(KEY), [])
        self.assertEqual(self.service.primary_photo_paths(), {})
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM listing_photos").fetchone()[0], 0)
        conn.close()

    def test_first_photo_is_primary_and_order_is_kept(self):
        a, b, c = (self.make_file(n) for n in ("a.png", "b.png", "c.png"))
        self.service.add_photo(KEY, a)
        self.service.add_photo(KEY, b)
        self.service.add_photo(KEY, c, make_primary=True)
        photos = self.service.photos_for(KEY)
        self.assertEqual([p.path for p in photos], [c, a, b])  # primary first, then by position
        self.assertEqual([p.is_primary for p in photos], [True, False, False])
        self.assertEqual(self.service.primary_photo_paths(), {KEY: c})

    def test_at_most_five_photos(self):
        for i in range(MAX_PHOTOS):
            self.service.add_photo(KEY, self.make_file(f"p{i}.png"))
        with self.assertRaises(PhotoError):
            self.service.add_photo(KEY, self.make_file("extra.png"))
        self.assertEqual(len(self.service.photos_for(KEY)), 5)

    def test_duplicate_file_and_bad_type_are_rejected(self):
        a = self.make_file("a.png")
        self.service.add_photo(KEY, a)
        with self.assertRaises(PhotoError):
            self.service.add_photo(KEY, a)
        with self.assertRaises(PhotoError):
            self.service.add_photo(KEY, "notes.txt")
        with self.assertRaises(PhotoError):
            self.service.add_photo(KEY, "")

    def test_only_one_primary_per_listing(self):
        a, b = self.make_file("a.png"), self.make_file("b.png")
        self.service.add_photo(KEY, a)
        second = self.service.add_photo(KEY, b)
        self.service.set_primary(KEY, second.photo_id)
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute(
            "SELECT COUNT(*) FROM listing_photos WHERE is_primary = 1").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):  # the database refuses a second primary
            conn.execute("UPDATE listing_photos SET is_primary = 1")
        conn.close()
        with self.assertRaises(PhotoError):
            self.service.set_primary(KEY, 9999)

    def test_missing_files_are_skipped_safely(self):
        a, b = self.make_file("a.png"), self.make_file("b.png")
        self.service.add_photo(KEY, a)
        self.service.add_photo(KEY, b)
        os.remove(a)                                   # the primary file disappears
        self.assertEqual([p.path for p in self.service.photos_for(KEY)], [b])
        self.assertEqual(self.service.primary_photo_paths(), {KEY: b})
        os.remove(b)
        self.assertEqual(self.service.photos_for(KEY), [])
        self.assertEqual(self.service.primary_photo_paths(), {})
        self.assertEqual(len(self.service.photos_for(KEY, usable_only=False)), 2)

    def test_relative_paths_live_in_the_photos_folder_and_survive_reopening(self):
        self.make_file("rel.png")
        self.service.add_photo(KEY, "rel.png")
        again = PhotoService(self.db, self.photos)
        self.assertEqual([p.path for p in again.photos_for(KEY)],
                         [os.path.join(self.photos, "rel.png")])

    def test_photos_are_per_listing(self):
        self.service.add_photo(KEY, self.make_file("a.png"))
        self.assertEqual(self.service.photos_for("school|Main Library|Other"), [])

    def test_step20_database_is_upgraded(self):
        self.service.photos_for(KEY)   # creates the database with every migration
        conn = sqlite3.connect(self.db)
        conn.execute("DROP TABLE listing_photos")
        conn.execute("DELETE FROM schema_migrations WHERE version = 9")
        conn.commit()
        conn.close()
        self.assertEqual(self.service.photos_for(KEY), [])   # reconnecting re-applies migration 9
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM listing_photos").fetchone()[0], 0)
        conn.close()


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class GalleryTests(TempFolder):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.item = next(i for i in SAMPLE_ITEMS if i.title == "Clean Code")
        self.key = self.item.listing_key

    def page(self, photos=()):
        from app.item_details_screen import ItemDetailsScreen
        page = ItemDetailsScreen()
        self.addCleanup(page.deleteLater)
        page.show_item(self.item, photos=list(photos))
        return page

    def test_no_photos_shows_placeholder_and_no_thumbnails(self):
        page = self.page()
        self.assertFalse(page.image_slot.has_photo)
        self.assertEqual(page.thumb_buttons, [])
        self.assertIsNone(page.main_photo_path)

    def test_single_photo_shows_no_thumbnail_strip(self):
        page = self.page([self.make_file("a.png")])
        self.assertTrue(page.image_slot.has_photo)
        self.assertEqual(page.thumb_buttons, [])

    def test_thumbnails_swap_the_main_image_in_place(self):
        files = [self.make_file(f"{i}.png", c) for i, c in enumerate(("#cc3344", "#33cc44", "#3344cc"))]
        page = self.page(files)
        self.assertEqual(len(page.thumb_buttons), 3)
        self.assertEqual(page.main_photo_path, files[0])
        self.assertTrue(page.thumb_buttons[0].isChecked())
        before = self.app.topLevelWidgets()
        page.thumb_buttons[2].click()
        self.assertEqual(page.main_photo_path, files[2])
        self.assertTrue(page.thumb_buttons[2].isChecked())
        self.assertFalse(page.thumb_buttons[0].isChecked())
        self.assertEqual(len(self.app.topLevelWidgets()), len(before))  # no new window
        self.assertTrue(page.image_slot.has_photo)

    def test_gallery_is_compact(self):
        page = self.page([self.make_file(f"{i}.png") for i in range(5)])
        self.assertEqual(len(page.thumb_buttons), 5)
        self.assertLessEqual(page.image_slot.width(), 260)
        self.assertLessEqual(page.image_slot.height(), 200)
        self.assertLessEqual(page.thumb_buttons[0].width(), 48)

    def test_unreadable_files_are_dropped_and_extra_photos_ignored(self):
        bad = os.path.join(self.photos, "broken.png")
        Path(bad).write_bytes(b"not a picture")
        good = [self.make_file(f"{i}.png") for i in range(6)]
        page = self.page([bad, os.path.join(self.photos, "gone.png")] + good)
        self.assertEqual(len(page.photo_paths), 3)   # only the first 5 are looked at; 3 are readable
        self.assertNotIn(bad, page.photo_paths)
        only_bad = self.page([bad])
        self.assertFalse(only_bad.image_slot.has_photo)

    def test_catalog_grid_and_list_show_the_primary_photo(self):
        from app.catalog_screen import CatalogScreen
        screen = CatalogScreen()
        self.addCleanup(screen.deleteLater)
        path = self.make_file("p.png")
        screen.set_primary_photos({self.key: path})
        card = next(c for c in screen._cards if c.item == self.item)
        row = next(r for r in screen._rows if r.item == self.item)
        other = next(c for c in screen._cards if c.item != self.item)
        self.assertTrue(card.image_slot.has_photo)
        self.assertTrue(row.thumb.has_photo)
        self.assertFalse(other.image_slot.has_photo)       # no invented photos
        screen.set_primary_photos({self.key: os.path.join(self.photos, "gone.png")})
        self.assertFalse(card.image_slot.has_photo)         # missing file -> placeholder
        screen.set_primary_photos({})
        self.assertFalse(row.thumb.has_photo)

    def test_photo_does_not_change_catalog_state(self):
        from app.catalog_screen import CatalogScreen
        screen = CatalogScreen()
        self.addCleanup(screen.deleteLater)
        screen.search_input.setText("python")
        shown = [i.title for i in screen.visible_items]
        screen.set_primary_photos({self.key: self.make_file("p.png")})
        self.assertEqual([i.title for i in screen.visible_items], shown)
        self.assertEqual(screen.search_input.text(), "python")

    def test_dashboard_uses_saved_photos_and_keeps_report_menu(self):
        from app.dashboard_screen import StudentDashboard
        from app.request_service import RequestService
        from app.sample_data import build_empty_data
        self.service.add_photo(self.key, self.make_file("a.png"))
        self.service.add_photo(self.key, self.make_file("b.png"))
        dash = StudentDashboard(
            build_empty_data("Ana Reyes"), signed_in_email=self.ana.email,
            student_id=self.ana.id, request_service=RequestService(self.db),
            photo_service=self.service)
        self.addCleanup(dash.deleteLater)
        card = next(c for c in dash.catalog_page._cards if c.item == self.item)
        self.assertTrue(card.image_slot.has_photo)
        dash._open_item_details(self.item)
        page = dash.item_details_page
        self.assertEqual(len(page.thumb_buttons), 2)
        self.assertTrue(page.report_action.isEnabled())     # three-dot menu still there
        self.assertEqual(page.menu_button.text(), "⋮")


if __name__ == "__main__":
    unittest.main()
