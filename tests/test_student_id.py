"""Step 29D tests: required, unique Student ID Number (saved in SQLite, private to Settings).

Groups 1-2 need no window. Group 3 opens the real screens (needs PySide6).
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
from app.auth_service import (  # noqa: E402
    ID_TAKEN_MESSAGE, MAX_STUDENT_ID_LENGTH, AuthError, AuthService, validate_student_id)

try:
    import PySide6
    from PySide6.QtWidgets import QApplication
    HAVE_QT = not getattr(PySide6, "__KITLEND_STUB__", False)
except ImportError:  # pragma: no cover
    HAVE_QT = False

PW = "Passw0rd-long"


class TempDbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)

    def rows(self, sql, params=(), db=None):
        conn = sqlite3.connect(db or self.db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def make_old_database(self, path, up_to=11):
        """A database exactly as an older version left it (no Student ID column)."""
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.executescript(database.SCHEMA)
        conn.execute(database._MIGRATION_TABLE)
        for version, name, statements in database.MIGRATIONS:
            if version <= up_to:
                for statement in statements:
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_migrations VALUES (?, ?, 't')", (version, name))
        conn.commit()
        conn.close()


# ======================================================================
# 1. VALIDATION (no format assumed)
# ======================================================================
class ValidationTests(unittest.TestCase):
    def test_any_reasonable_format_is_accepted(self):
        for value in ("2024-00123", "20240123", "CSU/2024/0001", "ab 12 cd", "S1", "٢٠٢٤٠١"):
            self.assertEqual(validate_student_id(value), " ".join(value.split()))

    def test_spaces_around_and_inside_are_tidied(self):
        self.assertEqual(validate_student_id("  2024   0001 "), "2024 0001")

    def test_empty_too_long_and_control_characters_are_refused(self):
        for bad in ("", "   ", None):
            with self.assertRaises(AuthError):
                validate_student_id(bad)
        with self.assertRaises(AuthError):
            validate_student_id("x" * (MAX_STUDENT_ID_LENGTH + 1))
        validate_student_id("x" * MAX_STUDENT_ID_LENGTH)
        with self.assertRaises(AuthError):
            validate_student_id("12\x00 34")


# ======================================================================
# 2. REGISTRATION, UNIQUENESS, ADDING AN ID LATER, MIGRATION
# ======================================================================
class RegistrationTests(TempDbCase):
    def test_registration_requires_a_student_id(self):
        self.auth._connect().close()  # make sure the database exists
        for missing in ("", "   "):
            with self.assertRaises(AuthError):
                self.auth.register("Ana", "ana@csucc.edu.ph", PW, PW, student_id_number=missing)
        with self.assertRaises(AuthError):
            self.auth.register("Ana", "ana@csucc.edu.ph", PW, PW)  # not given at all
        self.assertEqual(self.rows("SELECT COUNT(*) FROM students")[0][0], 0)

    def test_the_id_is_saved_and_comes_back_on_login_and_account(self):
        student = self.auth.register("Ana", "ana@csucc.edu.ph", PW, PW,
                                     student_id_number="  2024-0001 ")
        self.assertEqual(student.student_id_number, "2024-0001")
        self.assertEqual(self.auth.login("ana@csucc.edu.ph", PW).student_id_number, "2024-0001")
        self.assertEqual(self.auth.get_account(student.id).student_id_number, "2024-0001")
        self.assertEqual(AuthService(self.db).get_account(student.id).student_id_number,
                         "2024-0001")  # a restart

    def test_a_duplicate_id_is_refused_whatever_its_case_or_spacing(self):
        self.auth.register("Ana", "ana@csucc.edu.ph", PW, PW, student_id_number="ab-123")
        for clone in ("ab-123", "AB-123", " ab-123 "):
            with self.assertRaises(AuthError) as ctx:
                self.auth.register("Ben", "ben@csucc.edu.ph", PW, PW, student_id_number=clone)
            self.assertEqual(str(ctx.exception), ID_TAKEN_MESSAGE)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM students")[0][0], 1)  # no half account

    def test_a_duplicate_email_still_gives_the_email_message(self):
        self.auth.register("Ana", "ana@csucc.edu.ph", PW, PW, student_id_number="1")
        with self.assertRaises(AuthError) as ctx:
            self.auth.register("Ana", "ana@csucc.edu.ph", PW, PW, student_id_number="2")
        self.assertIn("email", str(ctx.exception))

    def test_the_database_itself_also_blocks_duplicates(self):
        self.auth.register("Ana", "ana@csucc.edu.ph", PW, PW, student_id_number="X-1")
        conn = sqlite3.connect(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO students (full_name, email, password_hash, salt, iterations, "
                "created_at, student_id_number) VALUES ('B','b@csucc.edu.ph','h','s',1,'t','x-1')")
        conn.close()


class AddMissingIdTests(TempDbCase):
    def setUp(self):
        super().setUp()
        old = os.path.join(self.tmp.name, "old.db")
        self.make_old_database(old)
        conn = sqlite3.connect(old)
        conn.execute("INSERT INTO students (full_name, email, password_hash, salt, iterations, "
                     "created_at) VALUES ('Old One','old@csucc.edu.ph','x','00',1,'t')")
        conn.commit()
        conn.close()
        self.db = old
        self.auth = AuthService(old)  # opens it -> migration 12 runs

    def old_student(self):
        row = self.rows("SELECT id FROM students WHERE email = 'old@csucc.edu.ph'")[0]
        return row[0]

    def test_an_older_account_has_no_id_yet(self):
        self.assertIsNone(self.auth.get_account(self.old_student()).student_id_number)

    def test_an_older_account_can_add_its_missing_id(self):
        saved = self.auth.set_student_id(self.old_student(), " 2019-77 ")
        self.assertEqual(saved, "2019-77")
        self.assertEqual(AuthService(self.db).get_account(self.old_student()).student_id_number,
                         "2019-77")

    def test_a_registered_id_cannot_be_changed(self):
        self.auth.set_student_id(self.old_student(), "FIRST-1")
        with self.assertRaises(AuthError) as ctx:
            self.auth.set_student_id(self.old_student(), "SECOND-2")
        self.assertIn("cannot be changed", str(ctx.exception))
        self.assertEqual(self.auth.get_account(self.old_student()).student_id_number, "FIRST-1")

    def test_an_id_that_belongs_to_someone_else_is_refused(self):
        self.auth.register("New", "new@csucc.edu.ph", PW, PW, student_id_number="TAKEN-9")
        with self.assertRaises(AuthError) as ctx:
            self.auth.set_student_id(self.old_student(), "taken-9")
        self.assertEqual(str(ctx.exception), ID_TAKEN_MESSAGE)
        self.assertIsNone(self.auth.get_account(self.old_student()).student_id_number)

    def test_bad_input_is_refused(self):
        for bad in ("", "  ", "x" * 99):
            with self.assertRaises(AuthError):
                self.auth.set_student_id(self.old_student(), bad)
        for bad_id in (None, True, 12345):
            with self.assertRaises(AuthError):
                self.auth.set_student_id(bad_id, "ok-1")


class MigrationTests(TempDbCase):
    def test_the_migration_keeps_every_existing_record_and_is_repeatable(self):
        old = os.path.join(self.tmp.name, "old.db")
        self.make_old_database(old)
        conn = sqlite3.connect(old)
        conn.execute("INSERT INTO students (full_name, email, password_hash, salt, iterations, "
                     "created_at) VALUES ('Old One','old@csucc.edu.ph','HASH','AB',5,'t')")
        conn.execute("INSERT INTO saved_items VALUES (1, 'k1', 't')")
        conn.commit()
        before = conn.execute("SELECT * FROM students").fetchall()
        conn.close()

        for _ in range(3):  # open it again and again: nothing may change after the first time
            AuthService(old).get_account(1)
        after = self.rows("SELECT id, full_name, email, password_hash, salt, iterations, "
                          "created_at FROM students", db=old)
        self.assertEqual(after, [tuple(row) for row in before])
        self.assertEqual(self.rows("SELECT student_id_number FROM students", db=old), [(None,)])
        self.assertEqual(self.rows("SELECT listing_key FROM saved_items", db=old), [("k1",)])
        versions = [r[0] for r in self.rows("SELECT version FROM schema_migrations ORDER BY 1", db=old)]
        self.assertEqual(versions, [m[0] for m in database.MIGRATIONS])  # each exactly once
        self.assertEqual(versions[-1], max(m[0] for m in database.MIGRATIONS))  # the newest one

    def test_existing_passwords_still_work_after_the_migration(self):
        old = os.path.join(self.tmp.name, "old2.db")
        self.make_old_database(old)
        import hashlib
        salt = bytes.fromhex("00" * 16)
        digest = hashlib.pbkdf2_hmac("sha256", PW.encode(), salt, 1000).hex()
        conn = sqlite3.connect(old)
        conn.execute("INSERT INTO students (full_name, email, password_hash, salt, iterations, "
                     "created_at) VALUES ('Old One','old@csucc.edu.ph',?,?,1000,'t')",
                     (digest, salt.hex()))
        conn.commit()
        conn.close()
        student = AuthService(old).login("old@csucc.edu.ph", PW)
        self.assertEqual(student.full_name, "Old One")
        self.assertIsNone(student.student_id_number)

    def test_an_interrupted_migration_that_already_added_the_column_still_finishes(self):
        old = os.path.join(self.tmp.name, "half.db")
        self.make_old_database(old)
        conn = sqlite3.connect(old)
        conn.execute("ALTER TABLE students ADD COLUMN student_id_number TEXT")  # column only
        conn.commit()
        conn.close()
        AuthService(old).register("Z", "z@csucc.edu.ph", PW, PW, student_id_number="Z-1")
        with self.assertRaises(AuthError):
            AuthService(old).register("Y", "y@csucc.edu.ph", PW, PW, student_id_number="z-1")

    def test_a_fresh_database_gets_the_column_and_the_unique_index(self):
        AuthService(self.db).register("A", "a@csucc.edu.ph", PW, PW, student_id_number="A-1")
        names = {r[1] for r in self.rows("PRAGMA table_info(students)")}
        self.assertIn("student_id_number", names)
        indexes = {r[0] for r in self.rows(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='students'")}
        self.assertIn("idx_students_student_id_number", indexes)


# ======================================================================
# 3. THE REAL SCREENS (needs PySide6)
# ======================================================================
@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class ScreenTests(TempDbCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_the_register_form_has_a_student_id_field_and_sends_it(self):
        from app.register_screen import RegisterScreen
        screen = RegisterScreen()
        seen = []
        screen.register_requested.connect(lambda *a: seen.append(a))
        for box, text in ((screen.name_input, "Ana"), (screen.email_input, "a@csucc.edu.ph"),
                          (screen.student_id_input, "2024-0001"),
                          (screen.password_input, PW), (screen.confirm_input, PW)):
            box.setText(text)
        screen.register_button.click()
        self.assertEqual(seen, [("Ana", "a@csucc.edu.ph", PW, PW, "2024-0001")])
        screen.reset_form()
        self.assertEqual(screen.student_id_input.text(), "")

    def test_the_main_window_registers_with_the_id_and_shows_duplicate_errors(self):
        from app.main_window import MainWindow
        window = MainWindow.__new__(MainWindow)  # only handle_register is needed
        window.auth = self.auth
        shown = []

        class Reg:
            def show_message(self, text, error=False):
                shown.append((text, error))

            def reset_form(self):
                pass
        window.register_screen = Reg()
        window.show_login = lambda: shown.append(("login", False))

        class Login:
            def prefill_email(self, email):
                pass

            def show_message(self, text, error=False):
                shown.append((text, error))
        window.login_screen = Login()
        window.handle_register("Ana", "a@csucc.edu.ph", PW, PW, "S-1")
        window.handle_register("Ben", "b@csucc.edu.ph", PW, PW, "s-1")
        self.assertEqual(shown[0], ("login", False))
        self.assertEqual(shown[-1], (ID_TAKEN_MESSAGE, True))

    def make_dash(self, student):
        from app.dashboard_screen import StudentDashboard
        from app.request_service import RequestService
        from app.sample_data import build_empty_data
        return StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=RequestService(self.db),
            auth_service=self.auth)

    def test_settings_shows_the_id_privately_and_has_no_way_to_change_it(self):
        student = self.auth.register("Ana", "a@csucc.edu.ph", PW, PW, student_id_number="2024-1")
        page = self.make_dash(student).settings_page
        self.assertEqual(page.profile_student_id.text(), "Student ID · 2024-1")
        self.assertTrue(page.student_id_form.isHidden())

    def test_an_older_account_sees_the_form_and_a_confirmed_id_is_saved_once(self):
        old = os.path.join(self.tmp.name, "old.db")
        self.make_old_database(old)
        conn = sqlite3.connect(old)
        conn.execute("INSERT INTO students (full_name, email, password_hash, salt, iterations, "
                     "created_at) VALUES ('Old One','old@csucc.edu.ph','x','00',1,'t')")
        conn.commit()
        conn.close()
        self.db, self.auth = old, AuthService(old)
        from app.auth_service import Student
        dash = self.make_dash(Student(1, "Old One", "old@csucc.edu.ph"))
        page = dash.settings_page
        self.assertFalse(page.student_id_form.isHidden() and False)
        self.assertEqual(page.profile_student_id.text(), "Student ID · not added yet")
        page._confirm_student_id = lambda value: False  # "Cancel" in the confirmation
        page.student_id_input.setText("NEW-55")
        page.student_id_button.click()
        self.assertIsNone(self.auth.get_account(1).student_id_number)
        page._confirm_student_id = lambda value: True  # "Save"
        page.student_id_button.click()
        self.assertEqual(self.auth.get_account(1).student_id_number, "NEW-55")
        self.assertEqual(page.profile_student_id.text(), "Student ID · NEW-55")
        self.assertTrue(page.student_id_form.isHidden())

    def test_the_demo_shows_no_student_id_at_all(self):
        from app.dashboard_screen import StudentDashboard
        from app.sample_data import build_demo_data
        page = StudentDashboard(build_demo_data()).settings_page
        self.assertTrue(page.profile_student_id.isHidden())
        self.assertTrue(page.student_id_form.isHidden())


if __name__ == "__main__":
    unittest.main()
