import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth_service import AuthError, AuthService  # noqa: E402
from app.sample_data import build_empty_data  # noqa: E402

PW = "correct horse"


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "test.db")
        self.auth = AuthService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def reg(self, email="Juan@csucc.edu.ph", pw=PW, name="Juan Dela Cruz"):
        return self.auth.register(name, email, pw, pw,
                                  student_id_number="ID-" + email.split("@")[0].upper())

    def test_register_and_login(self):
        s = self.reg()
        self.assertEqual(s.email, "juan@csucc.edu.ph")
        got = self.auth.login("  JUAN@csucc.edu.ph ", PW)
        self.assertEqual(got.full_name, "Juan Dela Cruz")
        self.assertEqual(got.id, s.id)

    def test_plus_address_allowed(self):
        self.assertEqual(self.reg("a+b@csucc.edu.ph").email, "a+b@csucc.edu.ph")

    def test_bad_emails_rejected(self):
        for bad in ("x@gmail.com", "@csucc.edu.ph", "a b@csucc.edu.ph",
                    "a@csucc.edu.ph.evil.com", "a@@csucc.edu.ph", "x@CSUCC.EDU.PH.com"):
            with self.assertRaises(AuthError, msg=bad):
                self.reg(bad)

    def test_duplicate_email_case_insensitive(self):
        self.reg("dup@csucc.edu.ph")
        with self.assertRaises(AuthError):
            self.reg("DUP@csucc.edu.ph")

    def test_password_length_rules(self):
        with self.assertRaises(AuthError):
            self.reg(pw="short12")
        with self.assertRaises(AuthError):
            self.reg(pw="x" * 129)
        self.reg("ok8@csucc.edu.ph", pw="x" * 8)
        self.reg("ok128@csucc.edu.ph", pw="x" * 128)

    def test_mismatch_and_required_fields(self):
        with self.assertRaises(AuthError):
            self.auth.register("A", "a@csucc.edu.ph", PW, PW + "x", student_id_number="ID-A")
        with self.assertRaises(AuthError):
            self.auth.register("", "a@csucc.edu.ph", PW, PW, student_id_number="ID-A")
        with self.assertRaises(AuthError):
            self.auth.register("A", "", PW, PW, student_id_number="ID-X")

    def test_password_is_hashed_and_salted(self):
        self.reg("one@csucc.edu.ph")
        self.reg("two@csucc.edu.ph")
        # Close the connection explicitly: Windows cannot delete test.db while a handle is open.
        with closing(sqlite3.connect(self.db)) as conn:
            rows = conn.execute(
                "SELECT password_hash, salt, iterations FROM students").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0][0], rows[1][0])  # same password, different salt
        self.assertNotEqual(rows[0][1], rows[1][1])
        for h, salt, iters in rows:
            self.assertNotIn(PW, h)
            self.assertEqual(len(h), 64)
            self.assertGreaterEqual(iters, 100_000)
        with open(self.db, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(PW.encode(), raw)

    def test_wrong_credentials_denied(self):
        self.reg()
        with self.assertRaises(AuthError):
            self.auth.login("juan@csucc.edu.ph", "wrong password")
        with self.assertRaises(AuthError):
            self.auth.login("nobody@csucc.edu.ph", PW)
        with self.assertRaises(AuthError):
            self.auth.login("juan@csucc.edu.ph", "")
        with self.assertRaises(AuthError):
            self.auth.login("", PW)

    def test_persistence_across_instances(self):
        self.reg()
        again = AuthService(self.db)
        self.assertEqual(again.login("juan@csucc.edu.ph", PW).full_name, "Juan Dela Cruz")

    def test_database_error_handled(self):
        bad = AuthService(os.path.join(self.tmp.name, "missing_dir", "x.db"))
        with self.assertRaises(AuthError):
            bad.login("a@csucc.edu.ph", PW)
        with self.assertRaises(AuthError):
            bad.register("A", "a@csucc.edu.ph", PW, PW, student_id_number="ID-A")

    def test_new_student_has_empty_data(self):
        s = self.reg()
        data = build_empty_data(s.full_name)
        self.assertEqual(data.student.full_name, "Juan Dela Cruz")
        self.assertEqual(data.student.first_name, "Juan")
        self.assertEqual(data.borrowings, [])
        self.assertEqual(data.reservations, [])
        self.assertEqual(data.notifications, [])
        self.assertEqual(data.activity, [])
        self.assertEqual(data.unread_count, 0)
        self.assertEqual(data.due_soon(), [])


if __name__ == "__main__":
    unittest.main()
