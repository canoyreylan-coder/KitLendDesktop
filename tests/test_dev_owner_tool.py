"""Tests for the DEVELOPMENT-ONLY Student Owner approval tool (dev_tools/dev_owner_approval.py).

No window needed. Checks that the tool works for ONE account, leaves everything else alone,
and that the real application has no way to reach it.
"""
import importlib.util
import io
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auth_service import AuthService  # noqa: E402
from app.student_owner_service import StudentOwnerService  # noqa: E402
from app.workspace_service import WorkspaceService  # noqa: E402

spec = importlib.util.spec_from_file_location("dev_owner_approval",
                                              ROOT / "dev_tools" / "dev_owner_approval.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

PW = "correct horse"


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "test.db")
        auth = AuthService(self.db)
        self.ana = auth.register("Ana Reyes", "ana@csucc.edu.ph", PW, PW, student_id_number="ID-A1")
        self.ben = auth.register("Ben Cruz", "ben@csucc.edu.ph", PW, PW, student_id_number="ID-B2")
        self.owner = StudentOwnerService(self.db)
        self.workspaces = WorkspaceService(self.owner)

    def run_tool(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = tool.run(["--db", self.db, *args])
        return code, out.getvalue()

    def keys(self, student):
        return [w.key for w in self.workspaces.assigned_workspaces(student.id)]

    def rows(self, sql, params=()):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_approve_opens_owner_workspace_for_that_account_only(self):
        code, _ = self.run_tool("--email", "ana@csucc.edu.ph", "--approve", "--confirm-dev")
        self.assertEqual(code, 0)
        self.assertEqual(self.keys(self.ana), ["student", "student_owner"])
        self.assertEqual(self.keys(self.ben), ["student"])

    def test_refuses_to_write_without_confirm_dev(self):
        code, text = self.run_tool("--email", "ana@csucc.edu.ph", "--approve")
        self.assertEqual(code, 2)
        self.assertIn("--confirm-dev", text)
        self.assertEqual(self.keys(self.ana), ["student"])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM student_owner_applications")[0][0], 0)

    def test_status_is_read_only_and_unknown_email_changes_nothing(self):
        code, text = self.run_tool("--email", "ana@csucc.edu.ph", "--status")
        self.assertEqual(code, 0)
        self.assertIn("not available", text)
        code, _ = self.run_tool("--email", "nobody@csucc.edu.ph", "--approve", "--confirm-dev")
        self.assertEqual(code, 1)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM student_owner_applications")[0][0], 0)

    def test_other_data_is_untouched(self):
        before = self.rows("SELECT * FROM students ORDER BY id")
        self.run_tool("--email", "ana@csucc.edu.ph", "--approve", "--confirm-dev")
        self.assertEqual(self.rows("SELECT * FROM students ORDER BY id"), before)
        self.assertTrue(os.path.exists(self.db + ".before-dev-owner.bak"))

    def test_approve_is_marked_and_repeatable_without_duplicates(self):
        self.run_tool("--email", "ana@csucc.edu.ph", "--approve", "--confirm-dev")
        _, text = self.run_tool("--email", "ana@csucc.edu.ph", "--approve", "--confirm-dev")
        self.assertIn("Already approved", text)
        rows = self.rows("SELECT status, review_note FROM student_owner_applications")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "Approved")
        self.assertTrue(rows[0][1].startswith("DEV TEST APPROVAL"))

    def test_pending_application_is_approved_and_restored_on_revoke(self):
        application = self.owner.submit_application(
            self.ana.id, "I have spare lab equipment and would like to help classmates.",
            "A scientific calculator and a soldering kit.", True)
        self.run_tool("--email", "ana@csucc.edu.ph", "--approve", "--confirm-dev")
        self.assertEqual(self.keys(self.ana), ["student", "student_owner"])
        self.run_tool("--email", "ana@csucc.edu.ph", "--revoke", "--confirm-dev")
        self.assertEqual(self.keys(self.ana), ["student"])
        current = self.owner.current_application(self.ana.id)
        self.assertEqual((current.application_id, current.status), (application.application_id, "Pending"))

    def test_revoke_removes_access_and_never_touches_a_real_approval(self):
        self.run_tool("--email", "ana@csucc.edu.ph", "--approve", "--confirm-dev")
        self.run_tool("--email", "ana@csucc.edu.ph", "--revoke", "--confirm-dev")
        self.assertEqual(self.keys(self.ana), ["student"])
        # a genuine (non-dev) approval is left alone
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE student_owner_applications SET status='Approved', review_note='Looks good'")
        conn.commit()
        conn.close()
        _, text = self.run_tool("--email", "ana@csucc.edu.ph", "--revoke", "--confirm-dev")
        self.assertIn("left alone", text)
        self.assertEqual(self.keys(self.ana), ["student", "student_owner"])


class NoBypassTests(unittest.TestCase):
    def test_the_app_never_references_the_dev_tool(self):
        for path in (ROOT / "app").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("dev_owner_approval", text, path.name)
            self.assertNotIn("dev_tools", text, path.name)
        self.assertNotIn("dev_tools", (ROOT / "main.py").read_text(encoding="utf-8"))

    def test_the_service_still_has_no_way_to_approve(self):
        for name in dir(StudentOwnerService):
            if not name.startswith("_"):
                for word in ("approve", "reject", "review", "set_status", "update", "grant"):
                    self.assertNotIn(word, name)
        for name in dir(WorkspaceService):
            if not name.startswith("_"):
                for word in ("grant", "approve", "set", "add", "unlock"):
                    self.assertNotIn(word, name)


if __name__ == "__main__":
    unittest.main()
