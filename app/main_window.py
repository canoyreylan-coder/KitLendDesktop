from PySide6.QtWidgets import QMainWindow, QStackedWidget

from app.auth_service import AuthError, AuthService, Student
from app.dashboard_screen import StudentDashboard
from app.login_screen import LoginScreen
from app.notification_service import NotificationService
from app.register_screen import RegisterScreen
from app.request_service import RequestService
from app.sample_data import build_empty_data


class MainWindow(QMainWindow):
    def __init__(self, auth_service: AuthService | None = None,
                 request_service: RequestService | None = None,
                 notification_service: NotificationService | None = None):
        super().__init__()

        # Window basics
        self.setWindowTitle("KitLend Desktop")
        self.resize(1000, 650)
        self.setMinimumSize(800, 500)

        # Authentication (SQLite for now; swap for a backend client later)
        self.auth = auth_service if auth_service is not None else AuthService()
        # Borrowing requests live in the same local SQLite file (Step 8C)
        self.request_service = (
            request_service if request_service is not None
            else RequestService(getattr(self.auth, "db_path", None))
        )
        # Notifications (Step 11) live in the same local SQLite file too
        self.notification_service = (
            notification_service if notification_service is not None
            else NotificationService(self.request_service.db_path)
        )
        self.current_student: Student | None = None  # the active session
        self.dashboard: StudentDashboard | None = None

        # One window, many screens: a stack shows one screen at a time
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login_screen = LoginScreen()
        self.register_screen = RegisterScreen()
        self.stack.addWidget(self.login_screen)
        self.stack.addWidget(self.register_screen)

        # Navigation
        self.login_screen.register_requested.connect(self.show_register)
        self.register_screen.back_to_login_requested.connect(self.show_login)
        self.login_screen.login_requested.connect(self.handle_login)
        self.register_screen.register_requested.connect(self.handle_register)

        # Still a placeholder until a later step
        self.login_screen.forgot_password_requested.connect(
            lambda: self.login_screen.show_message("Forgot Password screen coming in a later step.")
        )

    # ---------- navigation ----------
    def show_register(self):
        self.register_screen.reset_form()
        self.stack.setCurrentWidget(self.register_screen)

    def show_login(self):
        self.register_screen.reset_form()
        self.stack.setCurrentWidget(self.login_screen)

    # ---------- authentication flow ----------
    def handle_register(self, name: str, email: str, password: str, confirm: str,
                        student_id_number: str = ""):
        try:
            student = self.auth.register(name, email, password, confirm, student_id_number)
        except AuthError as exc:
            self.register_screen.show_message(str(exc), error=True)
            return
        except Exception:  # never crash the app on unexpected storage problems
            self.register_screen.show_message(
                "Something went wrong while creating your account. Please try again.",
                error=True,
            )
            return
        self.show_login()
        self.login_screen.prefill_email(student.email)
        self.login_screen.show_message("Account created! Please log in.")

    def handle_login(self, email: str, password: str):
        try:
            student = self.auth.login(email, password)
        except AuthError as exc:
            self.login_screen.show_message(str(exc), error=True)
            self.login_screen.password_input.clear()
            return
        except Exception:
            self.login_screen.show_message(
                "Something went wrong while logging in. Please try again.", error=True
            )
            return
        self.show_dashboard(student)

    def show_dashboard(self, student: Student):
        """The ONLY way to reach the dashboard: with a verified Student."""
        if student is None:
            return
        self.current_student = student
        self._discard_dashboard()
        # Real accounts get empty data - never the fictional demo records.
        self.dashboard = StudentDashboard(
            build_empty_data(student.full_name),
            signed_in_email=student.email,
            student_id=student.id,
            request_service=self.request_service,
            notification_service=self.notification_service,
            auth_service=self.auth,
        )
        self.dashboard.logout_requested.connect(self.handle_logout)
        self.stack.addWidget(self.dashboard)
        self.login_screen.reset_form()
        self.stack.setCurrentWidget(self.dashboard)

    def handle_logout(self):
        self.current_student = None
        self._discard_dashboard()
        self.login_screen.reset_form()
        self.stack.setCurrentWidget(self.login_screen)

    def _discard_dashboard(self):
        if self.dashboard is not None:
            self.stack.removeWidget(self.dashboard)
            self.dashboard.deleteLater()
            self.dashboard = None

    def closeEvent(self, event):
        if self.dashboard is not None and self.dashboard.has_unsaved_listing_changes():
            event.ignore()
            self.dashboard.request_listing_form_leave(self.close)
            return
        event.accept()
