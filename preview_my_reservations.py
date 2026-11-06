"""Preview the Reservations screen (Step 10). Run from the project folder:

    python preview_my_reservations.py            screen alone, with SAMPLE reservations
    python preview_my_reservations.py --empty    screen alone, empty (what a real student sees today)
    python preview_my_reservations.py --full     the REAL app (login + dashboard + database), using a
                                                 TEMPORARY database with a throwaway test account

Nothing here touches your real KitLend database or your real account. `--full`
creates a temporary database, adds a test student and sample requests, logs in and
opens Reservations. The temporary database is deleted when you close the window.

In `--full` you should see on Reservations ONLY:
    Awaiting pickup (1)        Approved - Awaiting Pickup
    Reservation history (2)    Reservation Expired + Cancelled after approval
and NOT: Pending, Rejected, the request cancelled BEFORE approval, or any borrowing.
My Requests shows every request (9), and My Borrowings only its 3 real borrowings.
"""
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))  # reuse the helper that writes rows into SQLite

from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from app.my_requests_screen import RequestStatus, build_sample_requests  # noqa: E402
from app.my_reservations_screen import MyReservationsScreen  # noqa: E402
from app.theme import STYLESHEET  # noqa: E402

TEST_EMAIL = "preview.student@csucc.edu.ph"
TEST_PASSWORD = "preview-only-password"


def show_screen_alone(empty: bool):
    window = QMainWindow()
    window.setWindowTitle("Reservations preview — " + ("empty" if empty else "sample data"))
    screen = MyReservationsScreen([] if empty else build_sample_requests())
    window.setCentralWidget(screen)
    window.resize(1000, 700)
    window.show()
    return window, None


def show_full_app():
    from app.auth_service import AuthService
    from app.main_window import MainWindow
    from app.request_service import RequestService
    from seed_helpers import insert_request, make_reservation, seed_samples

    tmp = tempfile.TemporaryDirectory()
    db_path = str(Path(tmp.name) / "preview.db")
    auth = AuthService(db_path)
    student = auth.register("Preview Student", TEST_EMAIL, TEST_PASSWORD, TEST_PASSWORD)
    seed_samples(db_path, student.id)
    # One request cancelled BEFORE approval: it must NOT appear on Reservations.
    now = datetime.now().astimezone().replace(microsecond=0)
    insert_request(db_path, student.id, make_reservation(
        "REQ-CANCEL-BEFORE", now, status=RequestStatus.CANCELLED, approved=False,
        note="Cancelled by you before it was approved."), "seed-cancel-before")

    window = MainWindow(auth_service=auth, request_service=RequestService(db_path))
    window.setWindowTitle("KitLend Desktop — PREVIEW (temporary database)")
    window.show()
    window.handle_login(TEST_EMAIL, TEST_PASSWORD)
    window.dashboard.go_to("reservations")
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
