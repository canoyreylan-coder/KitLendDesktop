"""Step 28 tests: profile photos (saved per account) and the redesigned Settings & Profile.

Group 1 needs no window and no PySide6 (file handling with a fake image processor).
Groups 2-4 use real Qt images/widgets in the invisible "offscreen" mode and are skipped
automatically if PySide6 is not installed.

Run from the project folder:   python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auth_service import AuthService  # noqa: E402
from app.profile_photo_service import (  # noqa: E402
    ProfilePhotoError, ProfilePhotoService, default_profile_photos_dir)

try:
    from PySide6.QtWidgets import QApplication, QLineEdit, QSpinBox
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

PW = "Passw0rd-long"


def fake_processor(source, destination):
    """Stands in for the Qt decoder: 'stores' the bytes of the source file."""
    with open(source, "rb") as f, open(destination, "wb") as out:
        out.write(f.read())


# ======================================================================
# 1. FILE HANDLING (no Qt)
# ======================================================================
class PhotoFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "profile_photos"
        self.service = ProfilePhotoService(self.dir, processor=fake_processor)
        self.src = Path(self.tmp.name) / "me.jpg"
        self.src.write_bytes(b"picture-one")

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_photo_means_none_and_nothing_is_created_by_reading(self):
        self.assertIsNone(self.service.photo_path(1, "ana@csucc.edu.ph"))
        self.assertFalse(self.dir.exists())

    def test_saved_photo_is_found_again_by_a_new_service_object_after_a_restart(self):
        stored = self.service.save_photo(1, "ana@csucc.edu.ph", self.src)
        again = ProfilePhotoService(self.dir, processor=fake_processor)
        self.assertEqual(again.photo_path(1, "ana@csucc.edu.ph"), stored)
        self.assertEqual(Path(stored).read_bytes(), b"picture-one")

    def test_it_is_stored_in_its_own_folder_never_under_the_students_file_name(self):
        stored = Path(self.service.save_photo(1, "ana@csucc.edu.ph", self.src))
        self.assertEqual(stored.parent, self.dir)
        self.assertNotIn("me", stored.stem.replace("avatar", ""))
        self.assertEqual(stored.suffix, ".png")
        self.assertEqual(sorted(p.suffix for p in self.dir.iterdir()), [".png"])  # no .tmp left

    def test_each_account_has_its_own_photo(self):
        self.service.save_photo(1, "ana@csucc.edu.ph", self.src)
        self.assertIsNone(self.service.photo_path(2, "ben@csucc.edu.ph"))
        self.assertIsNone(self.service.photo_path(1, "ben@csucc.edu.ph"))  # same id, other email
        self.assertIsNotNone(self.service.photo_path(1, "ANA@csucc.edu.ph "))  # email case/space

    def test_changing_the_photo_replaces_it_and_leaves_exactly_one_file(self):
        first = self.service.save_photo(1, "ana@csucc.edu.ph", self.src)
        self.src.write_bytes(b"picture-two")
        second = self.service.save_photo(1, "ana@csucc.edu.ph", self.src)
        self.assertNotEqual(first, second)  # a new name, so no picture cache can show the old one
        self.assertEqual(self.service.photo_path(1, "ana@csucc.edu.ph"), second)
        self.assertEqual([p.name for p in self.dir.iterdir()], [Path(second).name])

    def test_removing_deletes_only_this_accounts_photo(self):
        self.service.save_photo(1, "ana@csucc.edu.ph", self.src)
        self.service.save_photo(2, "ben@csucc.edu.ph", self.src)
        self.assertTrue(self.service.remove_photo(1, "ana@csucc.edu.ph"))
        self.assertIsNone(self.service.photo_path(1, "ana@csucc.edu.ph"))
        self.assertIsNotNone(self.service.photo_path(2, "ben@csucc.edu.ph"))
        self.assertFalse(self.service.remove_photo(1, "ana@csucc.edu.ph"))  # nothing left

    def test_unsupported_missing_or_huge_files_are_refused_and_change_nothing(self):
        good = self.service.save_photo(1, "ana@csucc.edu.ph", self.src)
        for name in ("notes.txt", "anim.gif", "pic.bmp", "noext"):
            bad = Path(self.tmp.name) / name
            bad.write_bytes(b"x")
            with self.assertRaises(ProfilePhotoError, msg=name):
                self.service.save_photo(1, "ana@csucc.edu.ph", bad)
        with self.assertRaises(ProfilePhotoError):
            self.service.save_photo(1, "ana@csucc.edu.ph", Path(self.tmp.name) / "missing.png")
        with mock.patch("app.profile_photo_service.MAX_FILE_BYTES", 3):
            with self.assertRaises(ProfilePhotoError):
                self.service.save_photo(1, "ana@csucc.edu.ph", self.src)
        self.assertEqual(self.service.photo_path(1, "ana@csucc.edu.ph"), good)

    def test_extension_check_ignores_case(self):
        upper = Path(self.tmp.name) / "PHOTO.JPG"
        upper.write_bytes(b"x")
        self.assertIsNotNone(self.service.save_photo(1, "ana@csucc.edu.ph", upper))

    def test_a_failing_decoder_keeps_the_old_photo_and_leaves_no_temp_file(self):
        good = self.service.save_photo(1, "ana@csucc.edu.ph", self.src)

        def broken(source, destination):
            Path(destination).write_bytes(b"half")
            raise ProfilePhotoError("That picture could not be read. Please choose another one.")

        failing = ProfilePhotoService(self.dir, processor=broken)
        with self.assertRaises(ProfilePhotoError):
            failing.save_photo(1, "ana@csucc.edu.ph", self.src)
        self.assertEqual(self.service.photo_path(1, "ana@csucc.edu.ph"), good)
        self.assertEqual([p.name for p in self.dir.iterdir()], [Path(good).name])

    def test_an_empty_stored_file_counts_as_no_photo(self):
        stored = self.service.save_photo(1, "ana@csucc.edu.ph", self.src)
        Path(stored).write_bytes(b"")
        self.assertIsNone(self.service.photo_path(1, "ana@csucc.edu.ph"))

    def test_bad_student_arguments_are_refused(self):
        for student_id, email in ((None, "a@b.c"), (True, "a@b.c"), (1, ""), ("1", "a@b.c")):
            with self.assertRaises(ProfilePhotoError):
                self.service.save_photo(student_id, email, self.src)
            self.assertIsNone(self.service.photo_path(student_id, email))

    def test_default_folder_is_the_application_data_folder_not_a_temp_or_project_folder(self):
        from app.database import get_app_data_dir
        self.assertEqual(default_profile_photos_dir(), get_app_data_dir() / "profile_photos")
        self.assertNotIn(str(ROOT), str(default_profile_photos_dir()))


# ======================================================================
# 2. REAL IMAGE PROCESSING (Qt images, no window)
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class ImageProcessingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = ProfilePhotoService(Path(self.tmp.name) / "photos")

    def tearDown(self):
        self.tmp.cleanup()

    def make_image(self, name, width, height, fmt, color="#3A7BFF"):
        from PySide6.QtGui import QColor, QImage
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(QColor(color))
        path = str(Path(self.tmp.name) / name)
        self.assertTrue(image.save(path, fmt), name)
        return path

    def stored_image(self, path):
        from PySide6.QtGui import QImage
        return QImage(path)

    def test_wide_and_tall_pictures_are_cropped_to_a_square_not_stretched(self):
        for name, w, h in (("wide.png", 400, 200), ("tall.png", 200, 400), ("sq.png", 300, 300)):
            stored = self.service.save_photo(1, "ana@csucc.edu.ph",
                                             self.make_image(name, w, h, "PNG"))
            image = self.stored_image(stored)
            self.assertEqual(image.width(), image.height(), name)
            self.assertEqual(image.width(), min(w, h), name)

    def test_the_centre_of_the_picture_is_what_stays(self):
        from PySide6.QtGui import QColor, QImage, QPainter
        image = QImage(300, 100, QImage.Format_ARGB32)
        image.fill(QColor("#FF0000"))
        painter = QPainter(image)
        painter.fillRect(100, 0, 100, 100, QColor("#00FF00"))  # green middle third
        painter.end()
        path = str(Path(self.tmp.name) / "stripes.png")
        image.save(path, "PNG")
        stored = self.stored_image(self.service.save_photo(1, "ana@csucc.edu.ph", path))
        self.assertEqual(stored.width(), 100)
        self.assertEqual(QColor(stored.pixel(5, 50)).name(), "#00ff00")
        self.assertEqual(QColor(stored.pixel(94, 50)).name(), "#00ff00")

    def test_big_pictures_are_scaled_down_and_small_ones_are_not_blown_up(self):
        big = self.service.save_photo(1, "ana@csucc.edu.ph", self.make_image("big.jpg", 1600, 1200, "JPG"))
        self.assertEqual(self.stored_image(big).width(), 512)
        small = self.service.save_photo(2, "ben@csucc.edu.ph", self.make_image("sm.png", 90, 60, "PNG"))
        self.assertEqual(self.stored_image(small).width(), 60)

    def test_jpg_png_and_webp_are_accepted(self):
        from PySide6.QtGui import QImageWriter
        formats = {bytes(f).lower() for f in QImageWriter.supportedImageFormats()}
        wanted = [("a.jpg", "JPG"), ("b.jpeg", "JPG"), ("c.png", "PNG")]
        if b"webp" in formats:
            wanted.append(("d.webp", "WEBP"))
        for i, (name, fmt) in enumerate(wanted, start=1):
            stored = self.service.save_photo(i, f"s{i}@csucc.edu.ph",
                                             self.make_image(name, 80, 80, fmt))
            self.assertTrue(self.stored_image(stored).width() > 0, name)

    def test_a_gif_renamed_to_png_or_a_text_file_renamed_to_jpg_is_refused(self):
        gif = self.make_image("real.gif", 40, 40, "GIF")
        fake_png = Path(self.tmp.name) / "fake.png"
        fake_png.write_bytes(Path(gif).read_bytes())
        fake_jpg = Path(self.tmp.name) / "text.jpg"
        fake_jpg.write_text("this is not a picture")
        for bad in (fake_png, fake_jpg):
            with self.assertRaises(ProfilePhotoError, msg=bad.name):
                self.service.save_photo(1, "ana@csucc.edu.ph", bad)
        self.assertIsNone(self.service.photo_path(1, "ana@csucc.edu.ph"))


# ======================================================================
# 3. THE ROUND AVATAR AND THE SETTINGS SCREEN
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class SettingsWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self):
        from app.settings_screen import SettingsScreen
        self.tmp = tempfile.TemporaryDirectory()
        self.screen = SettingsScreen(stored_locally=True)
        self.screen.set_account("Ana Reyes", "ana@csucc.edu.ph")
        self.screen.set_profile("AR", None)
        self.screen.set_profile_photo_enabled(True)

    def tearDown(self):
        self.tmp.cleanup()

    def make_photo(self, name="p.png", w=120, h=80):
        from PySide6.QtGui import QColor, QImage
        image = QImage(w, h, QImage.Format_ARGB32)
        image.fill(QColor("#7175F5"))
        path = str(Path(self.tmp.name) / name)
        image.save(path, "PNG")
        return path

    def test_without_a_photo_the_avatar_shows_initials_and_remove_is_hidden(self):
        self.assertFalse(self.screen.avatar.has_photo)
        self.assertEqual(self.screen.avatar.initials, "AR")
        self.assertTrue(self.screen.photo_remove_button.isHidden())
        self.assertEqual(self.screen.photo_button.text(), "Upload photo")

    def test_with_a_photo_the_buttons_change_and_the_avatar_is_a_fixed_circle_box(self):
        self.screen.set_profile("AR", self.make_photo())
        self.assertTrue(self.screen.avatar.has_photo)
        self.assertFalse(self.screen.photo_remove_button.isHidden())
        self.assertEqual(self.screen.photo_button.text(), "Change photo")
        self.assertEqual((self.screen.avatar.width(), self.screen.avatar.height()), (96, 96))

    def test_a_missing_or_damaged_picture_falls_back_to_initials(self):
        bad = Path(self.tmp.name) / "bad.png"
        bad.write_text("not an image")
        for path in (str(Path(self.tmp.name) / "missing.png"), str(bad)):
            self.screen.set_profile("AR", path)
            self.assertFalse(self.screen.avatar.has_photo)
            self.assertEqual(self.screen.photo_button.text(), "Upload photo")

    def test_avatar_renders_the_photo_in_the_middle_and_not_in_the_square_corners(self):
        from PySide6.QtGui import QColor
        self.screen.set_profile("AR", self.make_photo(w=300, h=100))
        image = self.screen.avatar.grab().toImage()
        self.assertEqual(QColor(image.pixel(48, 48)).name(), "#7175f5")  # photo fills the middle
        self.assertNotEqual(QColor(image.pixel(1, 1)).name(), "#7175f5")  # corner is outside the circle

    def choose(self, path):
        with mock.patch("app.settings_screen.QFileDialog.getOpenFileName",
                        return_value=(path, "")):
            self.screen.photo_button.click()

    def test_choosing_a_file_only_previews_it_and_emits_nothing(self):
        seen = []
        self.screen.profile_photo_chosen.connect(seen.append)
        self.choose(self.make_photo())
        self.assertEqual(seen, [])
        self.assertTrue(self.screen.avatar.has_photo)  # preview shown
        self.assertFalse(self.screen.photo_save_button.isHidden())
        self.assertFalse(self.screen.photo_cancel_button.isHidden())
        self.assertTrue(self.screen.photo_button.isHidden())
        self.choose("")  # closing the file dialog changes nothing
        self.assertEqual(seen, [])

    def test_save_emits_only_after_confirmation(self):
        seen = []
        self.screen.profile_photo_chosen.connect(seen.append)
        path = self.make_photo()
        self.choose(path)
        with mock.patch.object(self.screen, "_confirm_save_photo", return_value=False):
            self.screen.photo_save_button.click()
        self.assertEqual(seen, [])
        self.assertFalse(self.screen.photo_save_button.isHidden())  # still previewing
        with mock.patch.object(self.screen, "_confirm_save_photo", return_value=True):
            self.screen.photo_save_button.click()
        self.assertEqual(seen, [path])

    def test_cancel_restores_the_previous_photo_or_initials(self):
        seen = []
        self.screen.profile_photo_chosen.connect(seen.append)
        self.choose(self.make_photo("a.png"))
        self.screen.photo_cancel_button.click()
        self.assertFalse(self.screen.avatar.has_photo)
        self.assertEqual(self.screen.photo_button.text(), "Upload photo")
        self.assertTrue(self.screen.photo_save_button.isHidden())
        self.assertFalse(self.screen.photo_button.isHidden())
        self.screen.set_profile("AR", self.make_photo("old.png", 60, 60))
        self.choose(self.make_photo("new.png"))
        self.screen.photo_cancel_button.click()
        self.assertTrue(self.screen.avatar.has_photo)
        self.assertFalse(self.screen.photo_remove_button.isHidden())
        self.assertEqual(seen, [])

    def test_an_unreadable_choice_is_not_previewed(self):
        bad = Path(self.tmp.name) / "bad.png"
        bad.write_text("nope")
        self.choose(str(bad))
        self.assertFalse(self.screen.avatar.has_photo)
        self.assertTrue(self.screen.photo_save_button.isHidden())
        self.assertIn("could not be read", self.screen.photo_message.text())

    def test_remove_asks_for_removal_only_after_confirmation(self):
        self.screen.set_profile("AR", self.make_photo())
        seen = []
        self.screen.profile_photo_remove_requested.connect(lambda: seen.append(1))
        with mock.patch.object(self.screen, "_confirm_remove_photo", return_value=False):
            self.screen.photo_remove_button.click()
        self.assertEqual(seen, [])
        self.assertTrue(self.screen.avatar.has_photo)
        with mock.patch.object(self.screen, "_confirm_remove_photo", return_value=True):
            self.screen.photo_remove_button.click()
        self.assertEqual(seen, [1])

    def test_demo_mode_disables_the_photo_buttons(self):
        self.screen.set_profile_photo_enabled(False)
        self.assertFalse(self.screen.photo_button.isEnabled())

    def test_clear_forgets_the_photo_and_initials(self):
        self.screen.set_profile("AR", self.make_photo())
        self.screen.clear()
        self.assertFalse(self.screen.avatar.has_photo)
        self.assertEqual(self.screen.avatar.initials, "")
        self.assertEqual(self.screen.profile_name.text(), "")

    def test_sections_are_in_the_requested_order_and_existing_ones_remain(self):
        from PySide6.QtWidgets import QLabel
        headings = [l.text() for l in self.screen.findChildren(QLabel, "settingsSection")]
        self.assertEqual(headings, ["PROFILE", "ACCOUNT", "APPEARANCE", "NOTIFICATIONS", "WORKSPACES"])
        titles = [l.text() for l in self.screen.findChildren(QLabel, "settingsCardTitle")]
        for expected in ("Profile photo", "Account Information", "Change Password", "Appearance",
                         "Notification Preferences", "Workspaces", "Become a Student Owner"):
            self.assertIn(expected, titles)

    def test_adding_the_photo_card_added_no_editable_text_boxes(self):
        editable = {w for w in self.screen.findChildren(QLineEdit)
                    if not isinstance(w.parent(), QSpinBox)}
        self.assertEqual(editable, {self.screen.current_input, self.screen.new_input,
                                    self.screen.confirm_input})

    def test_stylesheet_is_scoped_to_the_settings_screen_and_has_no_old_outline_look(self):
        from app.settings_theme import SETTINGS_V2_QSS
        self.assertEqual(self.screen.objectName(), "settingsScreen")
        for line in SETTINGS_V2_QSS.splitlines():
            if "{" in line:
                self.assertTrue(line.lstrip().startswith("QWidget#settingsScreen")
                                or line.lstrip().startswith("{S}"), line)
        self.assertNotIn("border: 3px", SETTINGS_V2_QSS)
        self.assertNotIn("#FFF9EF", SETTINGS_V2_QSS.upper())


# ======================================================================
# 4. THE DASHBOARD: SIDEBAR AVATAR, SAVING, RESTART
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardPhotoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])
        from app import theme
        cls.qt_app.setStyleSheet(theme.STYLESHEET)

    def setUp(self):
        from app.request_service import RequestService
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)
        self.requests = RequestService(self.db)
        self.ana = self.auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-ANA")
        self.ben = self.auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-BEN")
        self.dashes = []

    def tearDown(self):
        for dash in self.dashes:
            dash.hide()
        self.tmp.cleanup()

    def make_dash(self, student):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_empty_data
        dash = StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=self.requests, auth_service=self.auth)
        dash.resize(1100, 700)
        dash.show()
        self.qt_app.processEvents()
        self.dashes.append(dash)
        return dash

    def make_picture(self, name="me.png"):
        from PySide6.QtGui import QColor, QImage
        image = QImage(300, 200, QImage.Format_ARGB32)
        image.fill(QColor("#F4A8C4"))
        path = str(Path(self.tmp.name) / name)
        image.save(path, "PNG")
        return path

    def test_new_account_shows_initials_in_the_sidebar_and_in_settings(self):
        dash = self.make_dash(self.ana)
        self.assertEqual(dash.avatar_button.text(), "AR")
        self.assertFalse(dash.settings_page.avatar.has_photo)

    def test_uploading_updates_the_sidebar_avatar_at_once_and_settings(self):
        dash = self.make_dash(self.ana)
        dash.settings_page.profile_photo_chosen.emit(self.make_picture())
        self.assertEqual(dash.avatar_button.text(), "")
        self.assertFalse(dash.avatar_button.icon().isNull())
        self.assertTrue(dash.settings_page.avatar.has_photo)
        self.assertEqual(dash.settings_page.photo_message.text(), "Profile photo updated.")

    def test_the_photo_survives_a_restart_and_belongs_to_that_account_only(self):
        first = self.make_dash(self.ana)
        first.settings_page.profile_photo_chosen.emit(self.make_picture())
        first.hide()
        again = self.make_dash(self.ana)  # "restart": a brand-new dashboard
        self.assertEqual(again.avatar_button.text(), "")
        self.assertTrue(again.settings_page.avatar.has_photo)
        other = self.make_dash(self.ben)
        self.assertEqual(other.avatar_button.text(), "BC")
        self.assertFalse(other.settings_page.avatar.has_photo)

    def test_the_photo_is_stored_next_to_the_database_not_in_a_temp_folder_of_its_own(self):
        dash = self.make_dash(self.ana)
        dash.settings_page.profile_photo_chosen.emit(self.make_picture())
        folder = Path(self.db).parent / "profile_photos"
        self.assertEqual(len(list(folder.glob("avatar-*.png"))), 1)

    def test_changing_the_photo_shows_the_new_one_and_keeps_one_file(self):
        dash = self.make_dash(self.ana)
        dash.settings_page.profile_photo_chosen.emit(self.make_picture("a.png"))
        dash.settings_page.profile_photo_chosen.emit(self.make_picture("b.png"))
        folder = Path(self.db).parent / "profile_photos"
        self.assertEqual(len(list(folder.glob("avatar-*.png"))), 1)
        self.assertTrue(dash.settings_page.avatar.has_photo)

    def test_removing_brings_back_the_initials_everywhere_and_deletes_the_file(self):
        dash = self.make_dash(self.ana)
        dash.settings_page.profile_photo_chosen.emit(self.make_picture())
        dash.settings_page.profile_photo_remove_requested.emit()
        self.assertEqual(dash.avatar_button.text(), "AR")
        self.assertTrue(dash.avatar_button.icon().isNull())
        self.assertFalse(dash.settings_page.avatar.has_photo)
        folder = Path(self.db).parent / "profile_photos"
        self.assertEqual(list(folder.glob("avatar-*.png")), [])
        self.assertFalse(self.make_dash(self.ana).settings_page.avatar.has_photo)

    def test_a_bad_file_shows_a_message_and_changes_nothing(self):
        dash = self.make_dash(self.ana)
        bad = Path(self.tmp.name) / "notes.txt"
        bad.write_text("hello")
        dash.settings_page.profile_photo_chosen.emit(str(bad))
        self.assertIn("JPG, PNG or WEBP", dash.settings_page.photo_message.text())
        self.assertEqual(dash.avatar_button.text(), "AR")
        fake = Path(self.tmp.name) / "fake.png"
        fake.write_text("not really a picture")
        dash.settings_page.profile_photo_chosen.emit(str(fake))
        self.assertEqual(dash.avatar_button.text(), "AR")
        self.assertFalse(dash.settings_page.avatar.has_photo)

    def test_a_photo_never_moves_or_resizes_a_sidebar_icon(self):
        dash = self.make_dash(self.ana)
        rail = dash.sidebar_rail
        before = {k: w.geometry() for k, w in dash._nav_buttons.items()}
        before_avatar = dash.avatar_button.geometry()
        dash.settings_page.profile_photo_chosen.emit(self.make_picture())
        self.qt_app.processEvents()
        self.assertEqual({k: w.geometry() for k, w in dash._nav_buttons.items()}, before)
        self.assertEqual(dash.avatar_button.geometry(), before_avatar)
        self.assertIsNotNone(rail)

    def test_sidebar_avatar_changes_only_after_a_confirmed_save(self):
        dash = self.make_dash(self.ana)
        page = dash.settings_page
        with mock.patch("app.settings_screen.QFileDialog.getOpenFileName",
                        return_value=(self.make_picture(), "")):
            page.photo_button.click()
        self.assertEqual(dash.avatar_button.text(), "AR")  # preview: sidebar untouched
        folder = Path(self.db).parent / "profile_photos"
        self.assertEqual(list(folder.glob("avatar-*.png")), [])
        with mock.patch.object(page, "_confirm_save_photo", return_value=False):
            page.photo_save_button.click()
        self.assertEqual(dash.avatar_button.text(), "AR")
        self.assertEqual(list(folder.glob("avatar-*.png")), [])
        with mock.patch.object(page, "_confirm_save_photo", return_value=True):
            page.photo_save_button.click()
        self.assertEqual(dash.avatar_button.text(), "")
        self.assertFalse(dash.avatar_button.icon().isNull())
        self.assertEqual(len(list(folder.glob("avatar-*.png"))), 1)
        self.assertTrue(page.photo_save_button.isHidden())

    def test_cancelled_preview_keeps_the_saved_photo_and_sidebar(self):
        dash = self.make_dash(self.ana)
        page = dash.settings_page
        page.profile_photo_chosen.emit(self.make_picture("a.png"))
        folder = Path(self.db).parent / "profile_photos"
        before = [(f.name, f.read_bytes()) for f in folder.glob("avatar-*.png")]
        with mock.patch("app.settings_screen.QFileDialog.getOpenFileName",
                        return_value=(self.make_picture("b.png"), "")):
            page.photo_button.click()
        page.photo_cancel_button.click()
        self.assertEqual([(f.name, f.read_bytes()) for f in folder.glob("avatar-*.png")], before)
        self.assertFalse(dash.avatar_button.icon().isNull())
        self.assertTrue(page.avatar.has_photo)

    def test_remove_needs_confirmation_before_anything_is_deleted(self):
        dash = self.make_dash(self.ana)
        page = dash.settings_page
        page.profile_photo_chosen.emit(self.make_picture())
        folder = Path(self.db).parent / "profile_photos"
        with mock.patch.object(page, "_confirm_remove_photo", return_value=False):
            page.photo_remove_button.click()
        self.assertEqual(len(list(folder.glob("avatar-*.png"))), 1)
        self.assertFalse(dash.avatar_button.icon().isNull())
        with mock.patch.object(page, "_confirm_remove_photo", return_value=True):
            page.photo_remove_button.click()
        self.assertEqual(list(folder.glob("avatar-*.png")), [])
        self.assertEqual(dash.avatar_button.text(), "AR")

    def test_a_failed_save_keeps_the_previous_photo(self):
        dash = self.make_dash(self.ana)
        page = dash.settings_page
        page.profile_photo_chosen.emit(self.make_picture("a.png"))
        with mock.patch("app.settings_screen.QFileDialog.getOpenFileName",
                        return_value=(self.make_picture("b.png"), "")), \
             mock.patch.object(dash._profile_photo_service, "save_photo",
                               side_effect=RuntimeError("disk")), \
             mock.patch.object(page, "_confirm_save_photo", return_value=True):
            page.photo_button.click()
            page.photo_save_button.click()
        self.assertIn("not changed", page.photo_message.text())
        self.assertTrue(page.photo_save_button.isHidden())
        self.assertFalse(dash.avatar_button.icon().isNull())

    def test_demo_mode_has_no_photo_saving(self):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_demo_data
        demo = StudentDashboard(build_demo_data())
        self.assertFalse(demo.stores_profile_photo)


if __name__ == "__main__":
    unittest.main()
