"""Preview the My Borrowings screen (Step 9, redesigned in Step 25). Run from the project folder:

    python preview_my_borrowings.py            screen alone, with SAMPLE borrowings
    python preview_my_borrowings.py --empty    screen alone, empty (what a real student sees today)
    python preview_my_borrowings.py --full     the REAL app (login + dashboard + database), using a
                                               TEMPORARY database with a throwaway test account

Nothing here touches your real KitLend database or your real account. `--full`
creates a temporary database, adds a test student and eight sample requests (one
for every status), logs in, and opens My Borrowings. The temporary database is
deleted when you close the window.

In `--full` you should see ONLY the three real borrowings on My Borrowings
(Borrowed in Active, Return Verification Pending in Return Pending, Returned in History). The other five requests
(Pending, Approved, Rejected, Cancelled, Expired) must appear only in My Requests.
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))  # reuse the test helper that writes rows into SQLite

from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from app.my_borrowings_screen import MyBorrowingsScreen  # noqa: E402
from app.my_requests_screen import build_sample_requests  # noqa: E402
from app.theme import STYLESHEET  # noqa: E402

TEST_EMAIL = "preview.student@csucc.edu.ph"
TEST_PASSWORD = "preview-only-password"


def show_screen_alone(empty: bool):
    window = QMainWindow()
    window.setWindowTitle("My Borrowings preview — " + ("empty" if empty else "sample data"))
    requests = []
    if not empty:
        from seed_helpers import make_borrowing
        from app.my_requests_screen import now_local
        requests = build_sample_requests() + [  # one overdue sample so the highlight is visible
            make_borrowing("REQ-OVERDUE", now_local(), picked_days_ago=10, days=2)]
    screen = MyBorrowingsScreen(requests)
    window.setCentralWidget(screen)
    window.resize(1000, 700)
    window.show()
    return window, None


def show_full_app():
    from app.auth_service import AuthService
    from app.main_window import MainWindow
    from app.request_service import RequestService
    from seed_helpers import seed_samples

    tmp = tempfile.TemporaryDirectory()
    db_path = str(Path(tmp.name) / "preview.db")
    auth = AuthService(db_path)
    student = auth.register("Preview Student", TEST_EMAIL, TEST_PASSWORD, TEST_PASSWORD)
    seed_samples(db_path, student.id)

    window = MainWindow(auth_service=auth, request_service=RequestService(db_path))
    window.setWindowTitle("KitLend Desktop — PREVIEW (temporary database)")
    window.show()
    window.handle_login(TEST_EMAIL, TEST_PASSWORD)
    window.dashboard.go_to("borrowings")
    print(f"Temporary test account: {TEST_EMAIL} (already logged in). Deleted on exit.")
    return window, tmp


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setStyleSheet(STYLESHEET)
    if "--full" in sys.argv:
        window, keep = show_full_app()
    else:
        window, keep = show_screen_alone("--empty" in sys.argv)
    code = qt_app.exec()
    if keep is not None:
        keep.cleanup()
    sys.exit(code)


if __name__ == "__main__":
    main()
