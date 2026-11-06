"""KitLend Student Dashboard screen.

Two modes:
  * Demo (default, `signed_in_email=None`): sample data, not logged in.
  * Authenticated (`signed_in_email="..."`): shows the real student with
    their own (currently empty) data and a Logout button.

Safety notes (by design):
  * This screen is built from a `DemoData` object and nothing else. It has no
    user account, no role, and no login state.
  * Stage 1B/1C: the sidebar is a compact icon-only rail (labels are hover tooltips). The
    student's avatar at its top opens Settings and the Log Out icon at its bottom is the only
    logout control (the old top banner and its duplicate button are gone).
  * The sidebar only contains student pages. There are no lender or
    administrator pages, and nothing here can switch to them.
  * The only way out is the `exit_demo_requested` signal -> back to Login.
  * Workspace switching will be added ONLY inside Settings, and only for workspaces the
    backend says the account has. Step 12's Settings page lists the assigned workspaces
    (today only Student) and has no control that can unlock another one.
"""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QDialog,
    QInputDialog,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.auth_service import AuthError, AuthService
from app.catalog_screen import CatalogItem, CatalogScreen, SAMPLE_ITEMS
from app.item_details_screen import ItemDetailsScreen, ReportListingDialog
from app.listing_category_service import OwnerCategoryAccess
from app.owner_listing_service import (
    CONDITIONS,
    MAX_DAYS,
    MIN_DAYS,
    STATUS_DRAFT,
    STATUS_PAUSED,
    STATUS_PUBLISHED,
    OwnerListingError,
    OwnerListingService,
)
from app.owner_listing_photos import OwnerListingPhotoService
from app.photo_service import PhotoError, PhotoService
from app.profile_photo_service import ProfilePhotoError, ProfilePhotoService
from app.report_service import ReportError, ReportService
from app.saved_items_service import SavedItemsError, SavedItemsService
from app.dashboard_home import DashboardHomePage
from app.my_borrowings_screen import MyBorrowingsScreen
from app.my_list_screen import MyListScreen, RequestPreviewDialog
from app.my_requests_screen import FILTER_ALL, MyRequestsScreen
from app.my_reservations_screen import MyReservationsScreen
from app.notification_service import NotificationError, NotificationService
from app.notifications_screen import NotificationsScreen
from app.preference_service import PreferenceError, PreferenceService
from app.dashboard_widgets import PlaceholderPage
from app.request_service import RequestError, RequestService
from app.sample_data import DemoData, plural
from app.settings_screen import SettingsScreen
from app.student_owner_service import StudentOwnerError, StudentOwnerService
from app.owner_workspace import (
    OWNER_DASHBOARD,
    OWNER_LISTINGS,
    OWNER_REQUESTS,
    OwnerDashboardPage,
    OwnerIncomingRequestsPage,
    OwnerListingFormPage,
    OwnerListingPreviewPage,
    OwnerListingsPage,
    OwnerRail,
)
from app.workspace_service import (
    WORKSPACE_STUDENT,
    WORKSPACE_STUDENT_OWNER,
    WorkspaceService,
)
from app.sidebar_icons import circular_pixmap, make_nav_icon
from app.sidebar_indicator import UnreadDot
from app.sidebar_layout import (
    ITEM_LABELS,
    KEY_AVATAR,
    KEY_LOGOUT,
    SidebarLayout,
    size_range,
)
from app.sidebar_layout_service import SidebarLayoutError, SidebarLayoutService
from app import design_tokens as tk
from app.sidebar_rail import SidebarRail
from app.floating_layout import effective_margin, shell_margin
from app.floating_shell import FloatingShell
from app.theme import (
    AVATAR_SIZE,
    SIDEBAR_STYLESHEET,
    SIDEBAR_WIDTH,
)


@dataclass(frozen=True)
class NavItem:
    key: str
    icon: str
    label: str
    message: str  # shown on the placeholder page ("" for the real Dashboard page)


NAV_ITEMS = [
    NavItem("dashboard", "🏠", "Dashboard", ""),
    NavItem("catalog", "🔍", "Browse Catalog",
            "Browse Catalog is coming in a later step. Soon you will be able to "
            "search and filter books, gadgets, and tools here."),
    NavItem("my_list", "⭐", "My List", ""),
    NavItem("my_requests", "📋", "My Requests", ""),
    NavItem("borrowings", "📚", "My Borrowings",
            "Log in with your school account to see your borrowings here."),
    NavItem("reservations", "🔖", "Reservations",
            "Log in with your school account to see your reservations here."),
    NavItem("notifications", "🔔", "Notifications",
            "Log in with your school account to see your notifications here."),
    NavItem("settings", "⚙️", "Settings",
            "Log in with your school account to open your settings."),
]


class StudentDashboard(QWidget):
    """Banner + sidebar + a content area that shows one page at a time."""

    exit_demo_requested = Signal()
    logout_requested = Signal()

    def __init__(self, data: DemoData, signed_in_email: str | None = None, parent=None, *,
                 student_id: int | None = None,
                 request_service: RequestService | None = None,
                 notification_service: NotificationService | None = None,
                 auth_service: AuthService | None = None,
                 workspace_service: WorkspaceService | None = None,
                 student_owner_service: StudentOwnerService | None = None,
                 sidebar_layout_service: SidebarLayoutService | None = None,
                 preference_service: PreferenceService | None = None,
                 report_service: ReportService | None = None,
                 photo_service: PhotoService | None = None,
                 saved_items_service: SavedItemsService | None = None,
                 profile_photo_service: ProfilePhotoService | None = None,
                 owner_listing_service: OwnerListingService | None = None,
                 owner_photo_service: OwnerListingPhotoService | None = None):
        super().__init__(parent)
        self._signed_in_email = signed_in_email
        # Step 8C: with a student id + service, requests are really saved (locally).
        # Without them (demo mode, previews) everything stays preview-only.
        self._student_id = student_id
        self._request_service = request_service
        # Step 11: notifications live in the same local database as the requests.
        if notification_service is None and request_service is not None:
            notification_service = NotificationService(request_service.db_path)
        self._notification_service = notification_service
        # Step 12: Settings reads the account and changes the password through the SAME
        # authentication service (and database file) used for login.
        if auth_service is None and request_service is not None:
            auth_service = AuthService(request_service.db_path)
        self._auth_service = auth_service
        # Step 13: Student Owner applications live in the same local database too.
        if student_owner_service is None and request_service is not None:
            student_owner_service = StudentOwnerService(request_service.db_path)
        self._student_owner_service = student_owner_service
        # Step 31A: an APPROVED application is what opens the Student Owner workspace.
        self._workspace_service = (
            workspace_service if workspace_service is not None
            else WorkspaceService(student_owner_service))
        self._workspace = WORKSPACE_STUDENT  # every login starts in the Student workspace
        # Step 31B: owner listing drafts (same database); every call re-checks approval.
        if owner_listing_service is None and request_service is not None:
            owner_listing_service = OwnerListingService(
                request_service.db_path, self._workspace_service)
        self._owner_listing_service = owner_listing_service
        # Step 14F: each student's sidebar sizes/positions, in the same local database.
        if sidebar_layout_service is None and request_service is not None:
            sidebar_layout_service = SidebarLayoutService(request_service.db_path)
        self._sidebar_layout_service = sidebar_layout_service
        self._saved_sidebar_layout = None  # what is saved right now (set when the rail is built)
        # Step 17: small per-student preferences (today: the Catalog's Grid/List view).
        if preference_service is None and request_service is not None:
            preference_service = PreferenceService(request_service.db_path)
        self._preference_service = preference_service
        # Step 19: listing reports live in the same local database too.
        if report_service is None and request_service is not None:
            report_service = ReportService(request_service.db_path)
        self._report_service = report_service
        # Step 21: photo references (read only here; no uploading yet), same database.
        # (the pictures live in a `photos` folder beside the database: the application-data
        # folder in a normal run, a temporary one in tests)
        if photo_service is None and request_service is not None:
            photo_service = PhotoService(request_service.db_path,
                                         Path(request_service.db_path).parent / "photos")
        self._photo_service = photo_service
        # Step 31C: owners add/remove/choose the primary photo of their listings. The files go
        # in the same photos folder, keyed by the listing ID, so the existing gallery reads them.
        if owner_photo_service is None and request_service is not None \
                and self._owner_listing_service is not None:
            owner_photo_service = OwnerListingPhotoService(
                request_service.db_path, self._owner_listing_service,
                photos_dir=(self._photo_service.photos_dir if self._photo_service is not None
                            else None))
        self._owner_photo_service = owner_photo_service
        # Step 28: each student's profile photo is a file in a `profile_photos` folder next to
        # the local database (the real application-data folder in a normal run).
        if profile_photo_service is None and request_service is not None:
            profile_photo_service = ProfilePhotoService(
                Path(request_service.db_path).parent / "profile_photos")
        self._profile_photo_service = profile_photo_service
        # My List: the bookmarked items are saved per student in the same local database.
        if saved_items_service is None and request_service is not None:
            saved_items_service = SavedItemsService(request_service.db_path)
        self._saved_items_service = saved_items_service
        self._catalog_scroll_before_details = 0
        self._report_dialog_open = False
        self.setObjectName("dashboardScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._data = data
        self._nav_items = {item.key: item for item in NAV_ITEMS}
        self._nav_buttons = {}
        # Step 8B: state belongs to this Dashboard/login session only.
        self._bookmarks = []
        self.prepared_drafts = []  # validated previews, not submitted requests
        self._request_dialog_open = False
        self._pages = {}
        self._build_ui()
        self._load_sidebar_layout()  # this student's saved icon sizes and positions
        self._load_profile_photo()  # this student's saved profile photo (or the initials)
        self._load_saved_items()  # this student's My List, straight from SQLite
        self._reload_requests()  # this student's saved requests, straight from SQLite
        self._reload_notifications()  # this student's saved notifications, same database
        if not self.stores_notifications:  # demo: no database, use the sample data's own flags
            self._update_notification_dot(self._data.unread_count > 0)
        self.go_to("dashboard")

    @property
    def is_authenticated(self) -> bool:
        return self._signed_in_email is not None

    @property
    def stores_requests(self) -> bool:
        """True when requests are saved to the local database for this student."""
        return (self.is_authenticated and self._student_id is not None
                and self._request_service is not None)

    @property
    def stores_notifications(self) -> bool:
        """True when notifications are read from / saved to the local database."""
        return self.stores_requests and self._notification_service is not None

    @property
    def stores_settings(self) -> bool:
        """True when Settings can read the account and change the password."""
        return (self.is_authenticated and self._student_id is not None
                and self._auth_service is not None)

    @property
    def stores_sidebar_layout(self) -> bool:
        """True when this student's sidebar layout can be loaded and saved."""
        return (self.is_authenticated and self._student_id is not None
                and self._sidebar_layout_service is not None)

    @property
    def stores_preferences(self) -> bool:
        """True when this student's preferences (Catalog view) can be loaded and saved."""
        return (self.is_authenticated and self._student_id is not None
                and self._preference_service is not None)

    @property
    def stores_saved_items(self) -> bool:
        """True when My List is saved to / loaded from the local database."""
        return (self.is_authenticated and self._student_id is not None
                and self._saved_items_service is not None)

    @property
    def stores_reports(self) -> bool:
        """True when listing reports can be saved to the local database."""
        return (self.is_authenticated and self._student_id is not None
                and self._report_service is not None)

    @property
    def stores_owner_applications(self) -> bool:
        """True when Student Owner applications can be read from / saved to the database."""
        return (self.is_authenticated and self._student_id is not None
                and self._student_owner_service is not None)

    def _on_exit_clicked(self):
        """The Log Out / Back to Login control. A signed-in student is asked to confirm first;
        Cancel changes nothing (they stay signed in, with every page as it was)."""
        if self.has_unsaved_listing_changes():
            self._request_listing_form_leave(self._finish_exit_clicked)
            return
        self._finish_exit_clicked()

    def _listing_form_is_active(self) -> bool:
        return (hasattr(self, "owner_form_page")
                and self.content_stack.currentWidget() is self.owner_form_page)

    def has_unsaved_listing_changes(self) -> bool:
        return (self._listing_form_is_active()
                and self.owner_form_page.has_unsaved_changes)

    def request_listing_form_leave(self, continuation) -> bool:
        """Guard an external leave request, including the main-window close action."""
        return self._request_listing_form_leave(continuation)

    def _request_listing_form_leave(self, continuation) -> bool:
        if not self._listing_form_is_active() or not self.owner_form_page.has_unsaved_changes:
            continuation()
            return True
        action = self._choose_listing_leave_action()
        if action == "keep":
            if self._workspace == WORKSPACE_STUDENT_OWNER:
                self.owner_rail.select(OWNER_LISTINGS)
            return False
        if action == "discard":
            if not self._restore_listing_form():
                return False
            continuation()
            return True
        if action == "save":
            self._pending_form_leave = continuation
            self.owner_form_page._on_save()
            return False
        return False

    def _choose_listing_leave_action(self) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unsaved listing changes")
        box.setText("You have unsaved listing changes.")
        box.setInformativeText("Save your draft before leaving, discard your changes, or keep editing.")
        keep = box.addButton("Keep Editing", QMessageBox.ButtonRole.RejectRole)
        save = box.addButton("Save Draft & Leave", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard Changes", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(keep)
        box.setEscapeButton(keep)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return "save"
        if clicked is discard:
            return "discard"
        return "keep"

    def _restore_listing_form(self) -> bool:
        form = self.owner_form_page
        if not form.is_editing:
            form.start_new()
            return True
        try:
            listing = self._owner_listing_service.get(self._student_id, form.listing_id)
            schedule = self._owner_listing_service.get_availability(
                self._student_id, form.listing_id)
            form.load(listing, self._saved_photo_items(form.listing_id), schedule)
        except Exception:
            form.show_error("Could not reload the saved draft. Your changes are still here.")
            return False
        return True

    def _finish_exit_clicked(self):
        if self.is_authenticated and not self.sidebar_rail.editing:
            if not self._confirm_logout():
                return
        self._emit_exit()

    def _confirm_logout(self) -> bool:
        """Ask 'Log out?' with Cancel and Log Out buttons. True only if Log Out was chosen."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Log out")
        box.setText("Log out of KitLend?")
        box.setInformativeText("You will need to log in again to continue.")
        cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        logout = box.addButton("Log Out", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(cancel)   # Enter / closing the window = stay signed in
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is logout

    def _emit_exit(self):
        if self.sidebar_rail.editing:  # in editing mode the icon is only selected (see below)
            self.sidebar_rail.select(KEY_LOGOUT)
            return
        if self.is_authenticated:
            # Make sure another login cannot inherit temporary session data.
            self._bookmarks.clear()
            self.prepared_drafts.clear()
            self._pages["catalog"].set_bookmarked_items([])
            self.item_details_page.clear()
            self._pages["my_list"].set_saved_items([])
            self._pages["my_requests"].set_requests([])
            self._pages["borrowings"].set_borrowings([])
            self._pages["reservations"].set_reservations([])
            self._pages["notifications"].set_notifications([])
            self.home_page.set_notifications([], 0)
            self.home_page.set_requests([])  # Stage 2A: no borrowings/requests left on screen
            self.settings_page.clear()  # no password text or account details left behind
            self._workspace = WORKSPACE_STUDENT
            self.owner_listings_page.set_listings([])
            self.owner_form_page.start_new()
            self.logout_requested.emit()
        else:
            self.exit_demo_requested.emit()

    # ---------- UI construction ----------
    def _build_ui(self):
        # Step 30A: everything (sidebar + pages) lives in ONE rounded, floating container
        # that sits on a slightly darker window background. The gap grows with the window.
        root = QVBoxLayout(self)
        root.setSpacing(0)
        self._root_layout = root
        self.shell = FloatingShell()
        self.setStyleSheet(  # only this widget's own background (see app/theme.py)
            f"QWidget#dashboardScreen {{ background-color: {tk.COLOR_BG_WINDOW}; }}")
        self._update_shell_margin()
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.shell.setLayout(body)
        root.addWidget(self.shell, 1)
        body.addWidget(self._build_sidebar())
        # Step 31A: the Student Owner rail takes the student sidebar's place (the student
        # sidebar is only hidden, so its customisation is never touched). Hidden until switched.
        self.owner_rail = OwnerRail(self._data.student.initials)
        self.owner_rail.hide()
        body.addWidget(self.owner_rail)

        self.content_stack = QStackedWidget()
        self.home_page = DashboardHomePage(
            self._data,
            role_label="Student" if self.is_authenticated else "Student · Demo",
        )
        self.placeholder_page = PlaceholderPage()
        self.content_stack.addWidget(self.home_page)
        self.content_stack.addWidget(self.placeholder_page)

        # The demo remains read-only. Only signed-in students get the actual
        # Catalog, My List and My Requests pages.
        if self.is_authenticated:
            self.catalog_page = CatalogScreen()
            self._refresh_catalog_photos()  # Step 21: primary photos (none exist yet)
            self._load_catalog_view()  # Step 17: this student's saved Grid/List choice
            self.my_list_page = MyListScreen([])
            self._refresh_catalog_photos()  # Step 22: photos on the saved-item cards
            self.my_requests_page = MyRequestsScreen(
                [],
                stored_locally=self.stores_requests,
                cancel_handler=self._cancel_request if self.stores_requests else None,
                hide_handler=self._hide_requests if self.stores_requests else None,
            )
            # Step 9: only real, confirmed borrowings (never Pending or Approved requests)
            self.my_borrowings_page = MyBorrowingsScreen(
                [], stored_locally=self.stores_requests)
            # Step 10: only approved reservations and their history (never Pending requests)
            self.my_reservations_page = MyReservationsScreen(
                [], stored_locally=self.stores_requests)
            # Step 11: this student's own notifications (empty until a real event happens)
            self.my_notifications_page = NotificationsScreen(
                [], stored_locally=self.stores_notifications)
            # Step 12: account, password, notification preferences and workspaces
            self.settings_page = SettingsScreen(stored_locally=self.stores_settings)
            self.settings_page.set_account(self._data.student.full_name, self._signed_in_email)
            self.settings_page.set_password_enabled(self.stores_settings)
            self.settings_page.set_student_id_enabled(self.stores_settings)
            self.settings_page.student_id_submitted.connect(self._on_student_id_submitted)
            self.settings_page.set_preferences_enabled(self.stores_notifications)
            self.settings_page.set_student_owner_enabled(self.stores_owner_applications)
            if self.stores_requests:
                self.my_list_page.set_submit_handler(self._submit_drafts)
            self._pages = {
                "catalog": self.catalog_page,
                "my_list": self.my_list_page,
                "my_requests": self.my_requests_page,
                "borrowings": self.my_borrowings_page,
                "reservations": self.my_reservations_page,
                "notifications": self.my_notifications_page,
                "settings": self.settings_page,
            }
            for page in self._pages.values():
                self.content_stack.addWidget(page)
            # Step 19: the Item Details page (opened from the Catalog, not a sidebar page)
            self.item_details_page = ItemDetailsScreen()
            self.content_stack.addWidget(self.item_details_page)
            # Step 31A: Owner Dashboard + My Listings (reachable only in the Owner workspace)
            self.owner_dashboard_page = OwnerDashboardPage()
            self.owner_listings_page = OwnerListingsPage()
            self.owner_requests_page = OwnerIncomingRequestsPage()
            categories = (self._owner_listing_service.categories
                          if self._owner_listing_service is not None else ())
            # Step 31D: categories + subcategories come from the SHARED registry; "+ New ..."
            # creates them for every owner at once.
            category_source = None
            if (self._owner_listing_service is not None and self._student_id is not None
                    and self._owner_listing_service.category_service is not None):
                category_source = OwnerCategoryAccess(
                    self._owner_listing_service.category_service, self._student_id)
            self.owner_form_page = OwnerListingFormPage(
                categories, CONDITIONS, MIN_DAYS, MAX_DAYS, category_source=category_source)
            self.content_stack.addWidget(self.owner_form_page)
            self.owner_dashboard_page.set_identity(
                self._data.student.full_name, self._signed_in_email)
            self.content_stack.addWidget(self.owner_dashboard_page)
            self.content_stack.addWidget(self.owner_listings_page)
            self.content_stack.addWidget(self.owner_requests_page)
            self._owner_pages = {OWNER_DASHBOARD: self.owner_dashboard_page,
                                 OWNER_LISTINGS: self.owner_listings_page,
                                 OWNER_REQUESTS: self.owner_requests_page}
            self.owner_rail.nav_requested.connect(self._on_owner_nav)
            self.owner_rail.avatar_clicked.connect(lambda: self._on_owner_nav("settings"))
            self.owner_rail.switch_requested.connect(
                lambda: self.switch_workspace(WORKSPACE_STUDENT))
            self.owner_rail.logout_requested.connect(self._on_exit_clicked)
            self.owner_dashboard_page.switch_to_student_requested.connect(
                lambda: self.switch_workspace(WORKSPACE_STUDENT))
            self.owner_dashboard_page.settings_requested.connect(
                lambda: self._on_owner_nav("settings"))
            self.owner_listings_page.back_requested.connect(
                lambda: self._on_owner_nav(OWNER_DASHBOARD))
            self.owner_listings_page.add_requested.connect(self._on_add_listing)
            self.owner_listings_page.edit_requested.connect(self._on_edit_listing)
            self.owner_listings_page.preview_requested.connect(self._on_preview_listing)
            self.owner_listings_page.publish_requested.connect(self._on_publish_listing)
            self.owner_listings_page.pause_requested.connect(self._on_pause_listing)
            self.owner_listings_page.resume_requested.connect(self._on_resume_listing)
            self.owner_listings_page.delete_requested.connect(self._on_delete_listing)
            self.owner_requests_page.approve_requested.connect(
                self._on_approve_owner_request)
            self.owner_requests_page.reject_requested.connect(
                self._on_reject_owner_request)
            self.owner_form_page.save_requested.connect(self._on_listing_save)
            self.owner_form_page.back_requested.connect(
                lambda: self._on_owner_nav(OWNER_LISTINGS))
            self.owner_form_page.cancel_requested.connect(
                lambda: self._on_owner_nav(OWNER_LISTINGS))
            self.owner_form_page.photo_add_requested.connect(self._on_listing_photos_add)
            self.owner_form_page.photo_remove_requested.connect(self._on_listing_photo_remove)
            self.owner_form_page.photo_primary_requested.connect(self._on_listing_photo_primary)
            self.settings_page.workspace_switch_requested.connect(self.switch_workspace)
            self.catalog_page.item_selected.connect(self._open_item_details)
            self.item_details_page.back_requested.connect(self._close_item_details)
            self.item_details_page.request_clicked.connect(self._on_direct_request)
            self.item_details_page.bookmark_toggled.connect(self._on_details_bookmark_toggled)
            self.item_details_page.report_requested.connect(self._on_report_requested)
            self.catalog_page.bookmark_toggled.connect(self._on_catalog_bookmark_toggled)
            self.catalog_page.direct_request_requested.connect(self._on_direct_request)
            self.catalog_page.view_mode_changed.connect(self._on_catalog_view_changed)
            self.my_list_page.item_removed.connect(self._on_my_list_item_removed)
            self.my_list_page.browse_catalog_requested.connect(lambda: self.go_to("catalog"))
            self.my_list_page.request_drafts_prepared.connect(self._on_request_drafts_prepared)
            self.my_requests_page.browse_catalog_requested.connect(lambda: self.go_to("catalog"))
            self.my_requests_page.request_cancelled.connect(self._on_request_cancelled)
            self.my_requests_page.requests_cleared.connect(lambda _cleared: self._reload_requests())
            self.my_borrowings_page.my_requests_requested.connect(
                lambda: self.go_to("my_requests"))
            self.my_reservations_page.my_requests_requested.connect(
                lambda: self.go_to("my_requests"))
            self.my_notifications_page.browse_catalog_requested.connect(
                lambda: self.go_to("catalog"))
            self.my_notifications_page.mark_read_requested.connect(
                self._on_notification_mark_read)
            self.my_notifications_page.mark_all_read_requested.connect(
                self._on_notifications_mark_all_read)
            self.settings_page.change_password_requested.connect(self._on_change_password)
            self.settings_page.preference_changed.connect(self._on_preference_changed)
            self.settings_page.owner_application_submitted.connect(
                self._on_owner_application_submitted)
            self.settings_page.profile_photo_chosen.connect(self._on_profile_photo_chosen)
            self.settings_page.profile_photo_remove_requested.connect(
                self._on_profile_photo_remove_requested)
            self.settings_page.outer_margin_changed.connect(self._on_outer_margin_changed)
            self.settings_page.outer_margin_save_requested.connect(self._on_outer_margin_save)
            self._connect_sidebar_editor()
            self._load_outer_margin()  # this account's saved container margin (or automatic)

        body.addWidget(self.content_stack, 1)
        self.shell.raise_overlay()  # keep the rounded corners above every page

        self.home_page.navigate_requested.connect(self.go_to)
        self.placeholder_page.back_requested.connect(lambda: self.go_to("dashboard"))

    def _update_shell_margin(self):
        """Gap around the floating container: the student's Outer Margin (previewed or saved),
        or the automatic gap. It is reduced in small windows so nothing is clipped."""
        override = getattr(self, "_margin_override", None)  # None = automatic
        margin = effective_margin(override, self.width(), self.height())
        self._root_layout.setContentsMargins(margin, margin, margin, margin)
        if self.is_authenticated and hasattr(self, "settings_page"):
            self.settings_page.set_auto_margin(shell_margin(self.width(), self.height()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_root_layout"):
            self._update_shell_margin()

    def _build_sidebar(self) -> QFrame:
        """A compact, permanently icon-only rail. Labels appear as hover tooltips.

        Step 14F: the rail has no Qt layout. Every item (avatar, page icons, Log Out) is a
        button placed by pixel position from a SidebarLayout, so each one can have its own
        size and place. Untouched items sit where the Step 14E layout put them.
        """
        sidebar = SidebarRail()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setStyleSheet(SIDEBAR_STYLESHEET)  # scoped to the sidebar only (see theme.py)
        self.sidebar_rail = sidebar

        self._build_avatar(sidebar)

        # Exclusive group: exactly one nav button is highlighted at a time
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for item in NAV_ITEMS:
            button = QPushButton(sidebar)  # icon only: the label is the tooltip
            button.setObjectName("navButton")
            button.setToolTip(item.label)
            button.setAccessibleName(item.label)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.TabFocus)  # a mouse click never leaves a focus outline
            button.clicked.connect(lambda _checked=False, key=item.key: self._on_nav_clicked(key))
            self._nav_group.addButton(button)
            self._nav_buttons[item.key] = button
            sidebar.register_item(item.key, button, self._icon_applier(button, item.key))
            if item.key == "notifications":
                self._notification_dot = UnreadDot(button)  # shown only while something is unread

        back_text = "Log Out" if self.is_authenticated else "Back to Login"
        back = QPushButton(sidebar)
        back.setObjectName("sidebarExitButton")
        back.setToolTip(back_text)
        back.setAccessibleName(back_text)
        back.setCursor(Qt.PointingHandCursor)
        back.setFocusPolicy(Qt.TabFocus)
        back.clicked.connect(self._on_exit_clicked)
        self.sidebar_exit_button = back
        sidebar.register_item(KEY_LOGOUT, back, self._icon_applier(back, "logout"))

        sidebar.selection_changed.connect(self._on_sidebar_selection_changed)
        sidebar.layout_edited.connect(self._on_sidebar_layout_edited)
        sidebar.refused.connect(self._on_sidebar_change_refused)
        return sidebar

    @staticmethod
    def _icon_applier(button: QPushButton, icon_key: str):
        """The function the rail calls to redraw one page/Log Out icon at a new size."""
        def apply(size: int):
            button.setIcon(make_nav_icon(icon_key, size))
            button.setIconSize(QSize(size, size))
        return apply

    def _build_avatar(self, sidebar: SidebarRail) -> QPushButton:
        """The student's circular avatar at the top of the rail; clicking it opens Settings.

        Shows initials for now. `set_profile_photo()` is the hook for a saved photo later
        (uploading and storing photos is not built yet). It only opens the Settings page: no
        menu and no account or workspace switching.
        """
        avatar = QPushButton(self._data.student.initials, sidebar)
        avatar.setObjectName("avatar")
        avatar.setCursor(Qt.PointingHandCursor)
        avatar.setFocusPolicy(Qt.TabFocus)
        who = self._signed_in_email if self.is_authenticated else "Demo student"
        avatar.setToolTip(f"{self._data.student.full_name}\n{who}\nOpen Settings")
        avatar.setAccessibleName(f"{self._data.student.full_name}: open Settings")
        avatar.clicked.connect(lambda _checked=False: self._on_avatar_clicked())
        self.avatar_button = avatar
        self._avatar_size = AVATAR_SIZE
        self._avatar_photo = None  # the photo last given to set_profile_photo (or None)
        sidebar.register_item(KEY_AVATAR, avatar, self._apply_avatar_size)
        return avatar

    def _apply_avatar_size(self, diameter: int):
        """Resize the round avatar: the corner radius and initials grow with it."""
        self._avatar_size = diameter
        self.avatar_button.setStyleSheet(
            f"border-radius: {diameter // 2}px; font-size: {max(10, diameter // 3)}px;")
        self._show_avatar_photo()

    def set_profile_photo(self, source=None):
        """Show a profile photo (a file path or QPixmap) in the avatar; None restores initials.

        Display only: nothing is uploaded or saved here. An unreadable image falls back to the
        initials, so a missing or damaged file can never break the sidebar.
        """
        self._avatar_photo = source
        self._show_avatar_photo()
        if hasattr(self, "owner_rail"):  # one shared profile picture in both workspaces
            self.owner_rail.set_profile(self._data.student.initials, source)

    def _show_avatar_photo(self):
        inner = self._avatar_size - 2
        photo = (circular_pixmap(self._avatar_photo, inner)
                 if self._avatar_photo is not None else None)
        if photo is None:
            self.avatar_button.setIcon(QIcon())
            self.avatar_button.setText(self._data.student.initials)
            return
        self.avatar_button.setText("")
        self.avatar_button.setIcon(QIcon(photo))
        self.avatar_button.setIconSize(QSize(inner, inner))

    # ---------- Step 14F: sidebar clicks (normal mode vs editing mode) ----------
    def _on_nav_clicked(self, key: str):
        if self.sidebar_rail.editing:  # editing: a click only selects the icon
            self.sidebar_rail.select(key)
        else:
            self.go_to(key)

    def _on_avatar_clicked(self):
        if self.sidebar_rail.editing:
            self.sidebar_rail.select(KEY_AVATAR)
        else:
            self.go_to("settings")

    # ---------- Step 28: profile photo ----------
    @property
    def stores_profile_photo(self) -> bool:
        """True when this student's profile photo can be loaded, saved and removed."""
        return (self.is_authenticated and self._student_id is not None
                and self._profile_photo_service is not None)

    def _show_profile_photo(self, path):
        """One place that updates BOTH the sidebar avatar and the Settings picture."""
        self.set_profile_photo(path)  # sidebar avatar, immediately
        if self.is_authenticated:
            self.settings_page.set_profile(self._data.student.initials, path)

    def _load_profile_photo(self):
        if not self.is_authenticated:
            return  # demo mode: initials only, nothing to load
        path = None
        if self.stores_profile_photo:
            try:
                path = self._profile_photo_service.photo_path(
                    self._student_id, self._signed_in_email)
            except Exception:  # a photo problem must never stop the app from opening
                path = None
        self._show_profile_photo(path)
        self.settings_page.set_profile_photo_enabled(self.stores_profile_photo)

    def _on_profile_photo_chosen(self, source_path: str):
        if not self.stores_profile_photo:
            return
        page = self.settings_page
        try:
            stored = self._profile_photo_service.save_photo(
                self._student_id, self._signed_in_email, source_path)
        except ProfilePhotoError as exc:
            page.show_photo_result(str(exc), error=True)
            return
        except Exception:
            page.show_photo_result("Something went wrong. Your photo was not changed.", error=True)
            return
        self._show_profile_photo(stored)
        page.show_photo_result("Profile photo updated.", error=False)

    def _on_profile_photo_remove_requested(self):
        if not self.stores_profile_photo:
            return
        page = self.settings_page
        try:
            self._profile_photo_service.remove_photo(self._student_id, self._signed_in_email)
        except Exception:
            page.show_photo_result("Something went wrong. Your photo was not changed.", error=True)
            return
        self._show_profile_photo(None)
        page.show_photo_result("Profile photo removed.", error=False)

    # ---------- Step 14F: loading, editing and saving the sidebar layout ----------
    def _load_sidebar_layout(self):
        """Show this student's saved layout (or the default look if none / unreadable)."""
        layout = SidebarLayout()
        if self.stores_sidebar_layout:
            try:
                layout = self._sidebar_layout_service.get_layout(self._student_id)
            except Exception:  # a layout problem must never stop the app from opening
                layout = SidebarLayout()
        self._saved_sidebar_layout = layout
        self.sidebar_rail.set_sidebar_layout(layout)
        if self.is_authenticated:
            self.settings_page.set_sidebar_edit_enabled(self.stores_sidebar_layout)

    def _connect_sidebar_editor(self):
        self.settings_page.sidebar_edit_requested.connect(self._start_sidebar_editing)
        editor = self.settings_page.sidebar_editor
        editor.size_changed.connect(self._on_editor_size_changed)
        editor.position_changed.connect(self._on_editor_position_changed)
        editor.reset_item_requested.connect(self._on_editor_reset_item)
        editor.reset_all_requested.connect(lambda: self.sidebar_rail.reset_all())
        editor.save_requested.connect(self._save_sidebar_layout)
        editor.cancel_requested.connect(self._cancel_sidebar_editing)
        editor.finish_requested.connect(self._finish_sidebar_editing)

    def _start_sidebar_editing(self):
        if not self.stores_sidebar_layout or self.sidebar_rail.editing:
            return
        if self._workspace != WORKSPACE_STUDENT:
            self.settings_page.show_message(
                "Switch to the Student workspace to customize the sidebar.")
            return
        self.sidebar_rail.set_editing(True)
        self.settings_page.set_sidebar_editing(True)
        editor = self.settings_page.sidebar_editor
        editor.set_unsaved(False)
        editor.show_status("Editing mode is on. Changes show in the sidebar right away.")
        self._refresh_editor_controls()

    def _end_sidebar_editing(self):
        self.sidebar_rail.set_editing(False)
        self.settings_page.set_sidebar_editing(False)
        self.settings_page.sidebar_editor.show_status("")

    def _sidebar_has_unsaved_changes(self) -> bool:
        return self.sidebar_rail.sidebar_layout() != self._saved_sidebar_layout

    def _refresh_editor_controls(self):
        """Make the panel's slider and position boxes describe the selected icon."""
        editor = self.settings_page.sidebar_editor
        key = self.sidebar_rail.selected_key
        if not key:
            editor.set_selection(None)
            return
        x, y, box = self.sidebar_rail.geometry_of(key)
        editor.set_selection(
            ITEM_LABELS[key], size=self.sidebar_rail.size_of(key), size_range=size_range(key),
            x=x, y=y, max_x=SIDEBAR_WIDTH - box,
            max_y=max(self.sidebar_rail.height() - box, 0))

    def _on_sidebar_selection_changed(self, _key: str):
        if self.sidebar_rail.editing:
            self._refresh_editor_controls()

    def _on_sidebar_layout_edited(self, _key: str):
        if not self.sidebar_rail.editing:
            return
        editor = self.settings_page.sidebar_editor
        editor.set_unsaved(self._sidebar_has_unsaved_changes())
        editor.show_status("")
        self._refresh_editor_controls()

    def _on_sidebar_change_refused(self, text: str):
        if self.sidebar_rail.editing:
            self.settings_page.sidebar_editor.show_status(text, error=True)
            self._refresh_editor_controls()  # put the slider/boxes back to the real values

    def _on_editor_size_changed(self, size: int):
        key = self.sidebar_rail.selected_key
        if key:
            self.sidebar_rail.set_item_size(key, size)

    def _on_editor_position_changed(self, x: int, y: int):
        key = self.sidebar_rail.selected_key
        if key:
            self.sidebar_rail.set_item_position(key, x, y)

    def _on_editor_reset_item(self):
        key = self.sidebar_rail.selected_key
        if key:
            self.sidebar_rail.reset_item(key)

    def _save_sidebar_layout(self) -> bool:
        """Save what the sidebar looks like now. Stays in editing mode. True on success."""
        editor = self.settings_page.sidebar_editor
        layout = self.sidebar_rail.sidebar_layout()
        try:
            self._sidebar_layout_service.save_layout(self._student_id, layout)
        except SidebarLayoutError as exc:
            editor.show_status(str(exc), error=True)
            return False
        except Exception:
            editor.show_status(
                "Something went wrong, so your sidebar layout was not saved.", error=True)
            return False
        self._saved_sidebar_layout = layout
        editor.set_unsaved(False)
        editor.show_status("Saved. Your sidebar layout is remembered for this account.")
        return True

    def _cancel_sidebar_editing(self):
        """Throw away unsaved changes, show the last saved layout and leave editing mode."""
        self.sidebar_rail.set_sidebar_layout(self._saved_sidebar_layout)
        self._end_sidebar_editing()
        self.settings_page.show_message("Sidebar changes cancelled. Your saved layout is back.")

    def _finish_sidebar_editing(self):
        """Save (if anything changed) and leave editing mode. A failed save keeps you here."""
        if self._sidebar_has_unsaved_changes() and not self._save_sidebar_layout():
            return
        self._end_sidebar_editing()
        self.settings_page.show_message("Sidebar layout saved.")

    # ---------- Step 8B: shared in-memory student state ----------
    # ---------- Step 17: Catalog Grid/List preference ----------
    def _load_catalog_view(self):
        """Show this student's saved Catalog layout. New accounts (no row) get Grid."""
        if not self.stores_preferences:
            return
        mode = self._preference_service.get_catalog_view(self._student_id)  # never raises
        self.catalog_page.set_view_mode(mode, emit=False)  # restoring is not a new choice

    def _on_catalog_view_changed(self, mode: str):
        """Remember the choice for THIS student. A failed save never interrupts browsing."""
        if not self.stores_preferences:
            return
        try:
            self._preference_service.set_catalog_view(self._student_id, mode)
        except PreferenceError:
            pass  # the view still switched; it just will not be remembered

    # ---------- Outer Margin (size of the floating container) ----------
    def _load_outer_margin(self):
        """Apply this account's saved margin. No saved value (or an unreadable one) = automatic."""
        saved = None
        if self.stores_preferences:
            saved = self._preference_service.get_outer_margin(self._student_id)  # never raises
        self.settings_page.set_outer_margin_enabled(self.stores_preferences)
        self.settings_page.set_outer_margin(saved or 0)
        self._margin_override = saved
        self._update_shell_margin()

    def _on_outer_margin_changed(self, value: int):
        """Live preview from the slider / Cancel / Reset (0 = automatic). Saves nothing."""
        self._margin_override = value or None
        self._update_shell_margin()

    def _on_outer_margin_save(self, value: int):
        """Save pressed: remember the margin for THIS account only (0 = back to automatic)."""
        page = self.settings_page
        if not self.stores_preferences:
            page.show_margin_result("Log in with your school account to save this.", error=True)
            return
        try:
            if value:
                self._preference_service.set_outer_margin(self._student_id, value)
            else:
                self._preference_service.reset_outer_margin(self._student_id)
        except PreferenceError as exc:
            page.show_margin_result(str(exc), error=True)  # the preview stays, just not saved
            return
        page.mark_margin_saved(value)

    # ---------- Step 21: photos ----------
    def _refresh_catalog_photos(self):
        """Give every Catalog card/row its primary photo (or the placeholder). Never raises."""
        if self._photo_service is None:
            return
        paths = self._photo_service.primary_photo_paths()
        self.catalog_page.set_primary_photos(paths)
        my_list = getattr(self, "my_list_page", None)   # Step 22: My List cards use them too
        if my_list is not None:
            my_list.set_primary_photos(paths)

    def _refresh_published_catalog(self):
        """Merge only saved Published Student Owner listings into the existing Catalog."""
        if not self.is_authenticated or self._owner_listing_service is None:
            return
        try:
            published = self._owner_listing_service.list_published_catalog()
        except OwnerListingError as exc:
            self.catalog_page.show_data_error(str(exc))
            return
        except Exception:
            self.catalog_page.show_data_error("Could not load published Student Owner listings.")
            return

        owner_items = [
            CatalogItem(
                title=entry.listing.title,
                creator=entry.owner_name,
                category=entry.listing.category,
                kind="Item",
                ownership="student",
                owner_note=f"Shared by {entry.owner_name}",
                copies_total=entry.listing.stock_quantity,
                copies_available=entry.listing.available_copies,
                record_id=entry.listing.listing_id,
                subcategory=entry.listing.subcategory,
                condition=entry.listing.condition,
                description=entry.listing.description,
                extra_rules=entry.listing.extra_rules,
                max_borrow_days=entry.listing.max_borrow_days,
                pickup_schedule_text=entry.availability.summary(),
                pickup_schedule=entry.availability.as_dict(),
                request_enabled=(
                    entry.listing.owner_student_id != self._student_id
                    and entry.listing.available_copies > 0),
                owner_student_id=entry.listing.owner_student_id,
                request_disabled_reason=(
                    "You cannot request to borrow your own listing."
                    if entry.listing.owner_student_id == self._student_id else
                    "Out of Stock. This listing cannot accept new requests."
                    if entry.listing.stock_quantity == 0 else
                    "All copies are currently committed and unavailable."
                    if entry.listing.available_copies == 0 else ""),
            )
            for entry in published
        ]
        items = list(SAMPLE_ITEMS) + owner_items
        self.catalog_page.set_items(items)
        self.catalog_page.show_data_error("")

        by_key = {item.listing_key: item for item in items}
        if self.stores_saved_items:
            saved_keys = self._saved_items_service.list_keys(self._student_id)
        else:
            saved_keys = [item.listing_key for item in self._bookmarks]
        self._bookmarks = [by_key[key] for key in saved_keys if key in by_key]
        self.catalog_page.set_bookmarked_items(self._bookmarks)
        self.my_list_page.set_saved_items(self._bookmarks)
        self._refresh_catalog_photos()

    # ---------- Step 19: Item Details + Report Listing ----------
    def _open_item_details(self, item):
        if self.sidebar_rail.editing:  # sidebar editing keeps you on Settings
            return
        self._catalog_scroll_before_details = self.catalog_page.scroll_position()
        reported = False
        if self.stores_reports:
            reported = self._report_service.has_reported(self._student_id, item.listing_key)
        photos = []
        if self._photo_service is not None:
            photos = [photo.path for photo in self._photo_service.photos_for(item.listing_key)]
        self.item_details_page.show_item(item, item in self._bookmarks, reported, photos)
        self._nav_buttons["catalog"].setChecked(True)  # Details belongs to Browse Catalog
        self.content_stack.setCurrentWidget(self.item_details_page)

    def _close_item_details(self):
        """Back to Catalog: the Catalog page was never rebuilt, so search, filters, Grid/List
        and the saved stars are exactly as they were; only the scroll position is restored."""
        self.go_to("catalog")
        self.catalog_page.restore_scroll_position(self._catalog_scroll_before_details)

    def _on_details_bookmark_toggled(self, item, is_bookmarked: bool):
        self._on_catalog_bookmark_toggled(item, is_bookmarked)  # same My List behaviour
        self.catalog_page.set_bookmarked_items(self._bookmarks)  # keep the Catalog stars in sync

    def _on_report_requested(self, item):
        if self._report_dialog_open:
            return
        if not self.stores_reports:
            QMessageBox.information(
                self, "Report Listing",
                "Reports can only be sent from a signed-in account on this computer.")
            return
        self._report_dialog_open = True
        try:
            def save(reason, description):
                self._report_service.submit_report(self._student_id, item, reason, description)

            dialog = ReportListingDialog(item, self, submit_handler=save)
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._report_dialog_open = False
        if accepted or self._report_service.has_reported(self._student_id, item.listing_key):
            if self.item_details_page.item == item:
                self.item_details_page.set_reported(True)

    # ---------- My List persistence ----------
    def _load_saved_items(self):
        """Show this student's saved items (Catalog stars + My List) after login."""
        if not self.stores_saved_items:
            return
        by_key = {item.listing_key: item for item in self.catalog_page._items}
        keys = self._saved_items_service.list_keys(self._student_id)  # never raises
        self._bookmarks = [by_key[key] for key in keys if key in by_key]
        self.catalog_page.set_bookmarked_items(self._bookmarks)
        self.my_list_page.set_saved_items(self._bookmarks)

    def _store_saved_item(self, item, saved: bool) -> bool:
        """Write one add/remove to SQLite right away. False (with a message) if it failed."""
        if not self.stores_saved_items:
            return True  # demo / no database: session-only, as before
        try:
            if saved:
                self._saved_items_service.add(self._student_id, item.listing_key)
            else:
                self._saved_items_service.remove(self._student_id, item.listing_key)
        except SavedItemsError as exc:
            self.my_list_page.show_message(str(exc))
            return False
        except Exception:
            self.my_list_page.show_message("Could not update your My List. Nothing was changed.")
            return False
        return True

    def _on_catalog_bookmark_toggled(self, item, is_bookmarked: bool):
        if not self._store_saved_item(item, is_bookmarked):
            # Not saved: show what is really saved instead of a star that would not last.
            self.catalog_page.set_bookmarked_items(self._bookmarks)
            if self.item_details_page.item == item:
                self.item_details_page.set_bookmarked(item in self._bookmarks)
            return
        if is_bookmarked and item not in self._bookmarks:
            self._bookmarks.append(item)
        elif not is_bookmarked and item in self._bookmarks:
            self._bookmarks.remove(item)
        self.my_list_page.set_saved_items(self._bookmarks)
        if self.item_details_page.item == item:
            self.item_details_page.set_bookmarked(is_bookmarked)
        # Catalog has already updated the clicked star, so no feedback loop.

    def _on_my_list_item_removed(self, item):
        if not self._store_saved_item(item, False):
            self.my_list_page.set_saved_items(self._bookmarks)  # still saved: put it back
            return
        if item in self._bookmarks:
            self._bookmarks.remove(item)
        self.catalog_page.set_bookmarked_items(self._bookmarks)
        if self.item_details_page.item == item:
            self.item_details_page.set_bookmarked(False)

    def _on_request_drafts_prepared(self, drafts):
        # Without storage a validated preview is not a submitted request.
        self.prepared_drafts = list(drafts)
        if self.stores_requests:  # My List's dialog already saved them (see _submit_drafts)
            self._show_saved_requests(len(drafts))

    def _on_direct_request(self, item):
        """Catalog -> Request Now uses the existing single-item preview form."""
        if (self._request_dialog_open or not item.is_available
                or not item.request_enabled):
            return
        self._request_dialog_open = True
        try:
            dialog = RequestPreviewDialog(
                [item], self,
                submit_handler=self._submit_drafts if self.stores_requests else None,
            )
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._request_dialog_open = False
        if accepted and dialog.drafts and self.stores_requests:
            self.prepared_drafts = list(dialog.drafts)
            self._show_saved_requests(len(dialog.saved_requests) or len(dialog.drafts))
        elif accepted and dialog.drafts:
            self.prepared_drafts = list(dialog.drafts)
            QMessageBox.information(
                self, "Preview Only",
                "Your request draft is ready. Nothing was submitted or saved. "
                "Actual request submission will be added in a later step.",
            )

    # ---------- Step 8C: saving, loading and cancelling requests ----------
    def _submit_drafts(self, drafts, submission_key):
        """Called by the request dialog on Confirm. Raises RequestError on failure."""
        saved = self._request_service.submit_requests(self._student_id, drafts, submission_key)
        self._reload_requests()  # already saved: a display problem must not look like a failure
        self._reload_notifications()  # the notification was saved in the same transaction
        return saved

    def _cancel_request(self, request, when):
        """Called by My Requests BEFORE it changes anything. Raises RequestError on failure."""
        try:
            self._request_service.cancel_request(self._student_id, request.request_id, when)
        except RequestError:
            self._reload_requests()  # show what the database really says
            raise
        self._reload_notifications()  # saved together with the cancellation

    def _hide_requests(self, request_ids, when):
        """Called by My Requests BEFORE it hides anything (Clear History / Clear Cancelled).

        Only records "hidden" for this student; no request is changed or deleted.
        Raises RequestError on failure.
        """
        self._request_service.hide_closed_requests(self._student_id, request_ids, when)

    def _on_request_cancelled(self, _request):
        self._reload_requests()  # the database is the source of truth
        self._reload_notifications()

    def _reload_requests(self):
        """Load THIS student's requests (and only theirs) into My Requests."""
        if not self.stores_requests:
            return
        try:
            result = self._request_service.load_requests(self._student_id)
        except RequestError as exc:
            self.my_requests_page.show_message(str(exc))
            self.my_borrowings_page.show_message(str(exc))
            self.my_reservations_page.show_message(str(exc))
            return
        except Exception:
            self.my_requests_page.show_message("Could not load your saved requests.")
            self.my_borrowings_page.show_message("Could not load your saved borrowings.")
            self.my_reservations_page.show_message("Could not load your saved reservations.")
            return
        # My Requests alone leaves out what the student cleared (hidden, never deleted);
        # every other page below still gets the full list.
        try:
            hidden = self._request_service.hidden_request_ids(self._student_id)
        except Exception:
            hidden = set()
        self.my_requests_page.set_requests(
            [r for r in result.requests if r.request_id not in hidden])
        # Same data, filtered by the page itself: only confirmed borrowings show there.
        self.my_borrowings_page.set_borrowings(result.requests)
        self.my_reservations_page.set_reservations(result.requests)  # filtered by the page
        self.home_page.set_requests(result.requests)  # Stage 2A: Dashboard cards and tiles
        if result.skipped:
            message = (f"{plural(result.skipped, 'saved request')} could not be read and "
                       "is not shown.")
            self.my_requests_page.show_message(message)
            self.my_borrowings_page.show_message(message)
            self.my_reservations_page.show_message(message)

    # ---------- Step 11: notifications ----------
    def _reload_notifications(self):
        """Load THIS student's notifications (and only theirs) into the page and the Dashboard.

        Only reads. It never creates notifications, so refreshing or reopening the app
        cannot duplicate anything.
        """
        if not self.stores_notifications:
            return
        try:
            notes = self._notification_service.list_notifications(self._student_id)
        except NotificationError as exc:
            self.my_notifications_page.show_message(str(exc))
            return
        except Exception:
            self.my_notifications_page.show_message("Could not load your notifications.")
            return
        self.my_notifications_page.set_notifications(notes)
        self.home_page.set_notifications(
            [(note.title, note.message, note.is_unread) for note in notes],
            sum(1 for note in notes if note.is_unread),  # real unread records, not a guess
        )
        self._update_notification_dot(any(note.is_unread for note in notes))

    def _update_notification_dot(self, unread: bool):
        """Dot on the bell: shown while any notification is unread, never a number."""
        dot = getattr(self, "_notification_dot", None)
        if dot is None:
            return
        dot.set_unread(unread)
        button = self._nav_buttons["notifications"]
        button.setAccessibleDescription("You have unread notifications" if unread else "")

    def _on_notification_mark_read(self, notification_id: int):
        if not self.stores_notifications:
            return
        try:
            self._notification_service.mark_read(self._student_id, notification_id)
        except NotificationError as exc:
            self.my_notifications_page.show_message(str(exc))
        except Exception:
            self.my_notifications_page.show_message(
                "Something went wrong, so the notification was not changed.")
        self._reload_notifications()  # show what the database really says

    def _on_notifications_mark_all_read(self):
        if not self.stores_notifications:
            return
        try:
            changed = self._notification_service.mark_all_read(self._student_id)
        except NotificationError as exc:
            self.my_notifications_page.show_message(str(exc))
            self._reload_notifications()
            return
        except Exception:
            self.my_notifications_page.show_message(
                "Something went wrong, so your notifications were not changed.")
            self._reload_notifications()
            return
        self._reload_notifications()
        self.my_notifications_page.show_message(
            f"Done! {plural(changed, 'notification')} marked as read."
            if changed else "You have no unread notifications.")

    # ---------- Step 29D: add a missing Student ID Number ----------
    def _on_student_id_submitted(self, student_id_number: str):
        page = self.settings_page
        if not self.stores_settings:
            return
        try:
            saved = self._auth_service.set_student_id(self._student_id, student_id_number)
        except AuthError as exc:
            page.show_message(str(exc))
            return
        except Exception:
            page.show_message("Something went wrong, so your Student ID Number was not saved.")
            return
        page.student_id_input.clear()
        page.set_student_id(saved)
        page.show_message("Done! Your Student ID Number was saved.")

    # ---------- Step 12: settings ----------
    def _reload_settings(self):
        """Refresh the Settings page from the database. Read-only; creates nothing."""
        page = self.settings_page
        if self.stores_settings:
            try:
                account = self._auth_service.get_account(self._student_id)
                page.set_account(account.full_name, account.email)
                page.set_student_id(account.student_id_number)
            except AuthError as exc:
                page.show_message(str(exc))
            except Exception:
                page.show_message("Could not load your account details.")
        if self.stores_notifications:
            try:
                page.set_preferences(
                    self._notification_service.get_preferences(self._student_id))
            except NotificationError as exc:
                page.show_message(str(exc))
            except Exception:
                page.show_message("Could not load your notification settings.")
        page.set_workspaces(self._workspace_service.assigned_workspaces(self._student_id),
                            self._workspace)
        self._reload_owner_applications()

    def _reload_owner_applications(self):
        """Show this student's own applications and whether they may apply. Read-only."""
        page = self.settings_page
        if not self.stores_owner_applications:
            page.set_student_owner_state([], "Applications need you to be logged in.")
            return
        try:
            applications = self._student_owner_service.list_applications(self._student_id)
            block = self._student_owner_service.apply_block_reason(self._student_id)
        except StudentOwnerError as exc:
            page.show_message(str(exc))
            return
        except Exception:
            page.show_message("Could not load your Student Owner application.")
            return
        page.set_student_owner_state(applications, block)

    def _on_owner_application_submitted(self, reason: str, items: str, agreed: bool):
        if not self.stores_owner_applications:
            return
        try:
            application = self._student_owner_service.submit_application(
                self._student_id, reason, items, agreed)
        except StudentOwnerError as exc:
            self.settings_page.show_owner_result(str(exc), error=True)
            self._reload_owner_applications()  # e.g. a duplicate: show what is really saved
            return
        except Exception:  # never show technical details or crash on storage problems
            self.settings_page.show_owner_result(
                "Something went wrong, so your application was not saved.", error=True)
            return
        self._reload_owner_applications()
        self.settings_page.show_owner_result(
            f"Application {application.application_id} sent. Its status is Pending. "
            "You are not a Student Owner until it is reviewed and approved.", error=False)

    def _on_change_password(self, current: str, new: str, confirm: str):
        if not self.stores_settings:
            return
        try:
            self._auth_service.change_password(self._student_id, current, new, confirm)
        except AuthError as exc:
            self.settings_page.show_password_result(str(exc), error=True)
            return
        except Exception:  # never show technical details or crash on storage problems
            self.settings_page.show_password_result(
                "Something went wrong, so your password was not changed.", error=True)
            return
        self.settings_page.show_password_result(
            "Password changed. Use your new password the next time you log in.", error=False)

    def _on_preference_changed(self, event_type: str, enabled: bool):
        if not self.stores_notifications:
            return
        try:
            self._notification_service.set_preference(self._student_id, event_type, enabled)
        except NotificationError as exc:
            self.settings_page.show_preferences_message(str(exc))
        except Exception:
            self.settings_page.show_preferences_message(
                "Something went wrong, so your notification settings were not changed.")
        else:
            self.settings_page.show_preferences_message(
                "Saved. This applies to future notifications only.")
        self._reload_settings()  # show what the database really says

    def _show_saved_requests(self, count: int):
        self.my_requests_page.set_filter(FILTER_ALL)
        self.go_to("my_requests")
        statuses = {
            "Pending Owner Approval" if draft.item.owner_student_id is not None else "Pending"
            for draft in self.prepared_drafts
        }
        status_text = (next(iter(statuses)) if len(statuses) == 1 else
                       "Pending or Pending Owner Approval")
        self.my_requests_page.show_message(
            f"Saved! {plural(count, 'request')} saved as {status_text}. Stored on this computer "
            "only and not sent to school administrators."
        )

    # ---------- Step 31A: Student / Student Owner workspaces ----------
    @property
    def current_workspace(self) -> str:
        return self._workspace

    def switch_workspace(self, key: str) -> bool:
        """Switch between the Student and Student Owner workspaces. One account, one profile,
        one Settings page: only the rail and the pages around them change.

        The Student Owner workspace opens ONLY while WorkspaceService confirms an approved
        application, checked again on every switch. Returns True if the workspace changed.
        """
        if not self.is_authenticated or not hasattr(self, "owner_rail"):
            return False
        if key == self._workspace:
            return False
        if self.has_unsaved_listing_changes():
            self._request_listing_form_leave(lambda: self.switch_workspace(key))
            return False
        if self.sidebar_rail.editing:  # finish or cancel the sidebar edit first
            self.settings_page.show_message(
                "Finish or cancel sidebar editing before switching workspaces.")
            return False
        if key == WORKSPACE_STUDENT_OWNER:
            if not self._workspace_service.can_use(self._student_id, WORKSPACE_STUDENT_OWNER):
                self.settings_page.show_message(
                    "The Student Owner workspace is only available after your application "
                    "is approved.")
                self._reload_settings()
                return False
            self._workspace = WORKSPACE_STUDENT_OWNER
            self.sidebar_rail.hide()
            self.owner_rail.show()
            self.owner_rail.set_profile(self._data.student.initials, self._avatar_photo)
            self.settings_page.revert_unsaved_margin()
            self._on_owner_nav(OWNER_DASHBOARD)
            return True
        if key == WORKSPACE_STUDENT:
            self._workspace = WORKSPACE_STUDENT
            self.owner_rail.hide()
            self.sidebar_rail.show()
            self.go_to("dashboard")
            return True
        return False

    def _on_owner_nav(self, key: str):
        """Owner rail: Owner Dashboard, My Listings, or the shared Settings page."""
        if self._workspace != WORKSPACE_STUDENT_OWNER:
            return
        if self.has_unsaved_listing_changes():
            self._request_listing_form_leave(lambda: self._on_owner_nav(key))
            return
        if not self._workspace_service.can_use(self._student_id, WORKSPACE_STUDENT_OWNER):
            self.switch_workspace(WORKSPACE_STUDENT)   # access was withdrawn: back to Student
            return
        self.owner_rail.select(key)
        if key == "settings":
            self._reload_settings()
            self.content_stack.setCurrentWidget(self._pages["settings"])
        elif key in self._owner_pages:
            self._reload_owner_listings()   # read-only refresh of this owner's drafts
            if key in (OWNER_DASHBOARD, OWNER_REQUESTS):
                self._reload_owner_requests()
            self.content_stack.setCurrentWidget(self._owner_pages[key])

    def _reload_owner_requests(self):
        if (self._request_service is None or self._student_id is None
                or not hasattr(self, "owner_requests_page")):
            return
        try:
            requests = self._request_service.list_incoming_requests(self._student_id)
        except RequestError as exc:
            self.owner_requests_page.set_requests([])
            self.owner_requests_page.show_message(str(exc), error=True)
            self.owner_dashboard_page.set_pending_request_count(0)
            return
        pending_count = sum(
            entry.request.status.value == "pending_owner_approval" for entry in requests)
        self.owner_requests_page.set_requests(requests)
        self.owner_requests_page.show_message("")
        self.owner_dashboard_page.set_pending_request_count(pending_count)

    def _on_approve_owner_request(self, request_id: str):
        if not self._owner_may_manage() or self._request_service is None:
            return
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Approve borrowing request?")
        dialog.setText("Approve this request?")
        dialog.setInformativeText(
            "One available copy will be reserved. The borrowing period will not start "
            "until pickup is confirmed.")
        approve_button = dialog.addButton(
            "Approve Request", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        if dialog.clickedButton() is not approve_button:
            return
        try:
            self._request_service.approve_owner_request(self._student_id, request_id)
        except RequestError as exc:
            self._reload_owner_requests()
            self.owner_requests_page.show_message(str(exc), error=True)
            return
        self._reload_owner_requests()
        self.owner_requests_page.show_message(
            "Request approved. One copy is reserved; no borrowing countdown has started.")

    def _on_reject_owner_request(self, request_id: str):
        if not self._owner_may_manage() or self._request_service is None:
            return
        reason, accepted = QInputDialog.getMultiLineText(
            self, "Reject borrowing request?",
            "Reject this request? You may include an optional reason for the borrower.",
        )
        if not accepted:
            return
        try:
            self._request_service.reject_owner_request(
                self._student_id, request_id, reason)
        except RequestError as exc:
            self._reload_owner_requests()
            self.owner_requests_page.show_message(str(exc), error=True)
            return
        self._reload_owner_requests()
        self.owner_requests_page.show_message("Request rejected.")

    # ---------- Step 31B: owner listings (drafts only) ----------
    def _owner_may_manage(self) -> bool:
        """True only inside the Owner workspace for a student who is STILL an approved owner.
        If approval was withdrawn, the student is sent back to the Student workspace."""
        if self._workspace != WORKSPACE_STUDENT_OWNER or self._owner_listing_service is None:
            return False
        if not self._owner_listing_service.can_manage(self._student_id):
            self.switch_workspace(WORKSPACE_STUDENT)
            return False
        return True

    def _reload_owner_listings(self):
        if self._owner_listing_service is None or not self._owner_listing_service.can_manage(
                self._student_id):
            return
        try:
            listings = self._owner_listing_service.list_listings(self._student_id)
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            return
        except Exception:
            self.owner_listings_page.show_message("Could not load your listings.")
            return
        photos, schedules = {}, {}
        try:   # pictures and pickup times only decorate the cards; a problem never hides drafts
            if self._owner_photo_service is not None:
                for listing in listings:
                    listing_photos = self._owner_photo_service.photos(
                        self._student_id, listing.listing_id)
                    if listing_photos:
                        photos[listing.listing_id] = listing_photos[0].path
            schedules = self._owner_listing_service.availability_for_all(self._student_id)
        except Exception:
            pass
        self.owner_listings_page.set_listings(listings, photos, schedules)
        draft_count = sum(listing.status == STATUS_DRAFT for listing in listings)
        self.owner_dashboard_page.set_draft_count(draft_count)

    def _on_publish_listing(self, listing_id: str):
        if not self._owner_may_manage():
            return
        try:
            listing = self._owner_listing_service.get(self._student_id, listing_id)
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            self._reload_owner_listings()
            return
        except Exception:
            self.owner_listings_page.show_message("Could not load this listing.")
            return
        if listing.status != STATUS_DRAFT:
            self.owner_listings_page.show_message("Only draft listings can be published.")
            self._reload_owner_listings()
            return
        if not self._confirm_listing_publish(listing.title):
            return
        try:
            photos_dir = (
                self._owner_photo_service.photos_dir
                if self._owner_photo_service is not None else None)
            published = self._owner_listing_service.publish(
                self._student_id, listing_id, photos_dir=photos_dir)
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            return
        except Exception:
            self.owner_listings_page.show_message(
                "Something went wrong, so the listing was not published.")
            return
        self._reload_owner_listings()
        self._refresh_published_catalog()
        self.owner_listings_page.show_message(
            f"“{published.title}” is published and now appears in the Catalog.")

    def _on_pause_listing(self, listing_id: str):
        if not self._owner_may_manage():
            return
        try:
            listing = self._owner_listing_service.get(self._student_id, listing_id)
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            self._reload_owner_listings()
            return
        except Exception:
            self.owner_listings_page.show_message("Could not load this listing.")
            return
        if listing.status != STATUS_PUBLISHED:
            self.owner_listings_page.show_message("Only published listings can be paused.")
            self._reload_owner_listings()
            return
        if not self._confirm_listing_pause(listing.title):
            return
        try:
            paused = self._owner_listing_service.pause_listing(self._student_id, listing_id)
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            self._reload_owner_listings()
            return
        except Exception:
            self.owner_listings_page.show_message("Something went wrong, so it was not paused.")
            return
        self._reload_owner_listings()
        self._refresh_published_catalog()
        self.owner_listings_page.show_message(
            f"“{paused.title}” is paused and hidden from the Catalog.")

    def _confirm_listing_pause(self, title: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Pause listing?")
        dialog.setText(f"Pause “{title}”?")
        dialog.setInformativeText(
            "Borrowers will no longer see it in the Catalog. Its information and photos will "
            "be kept, and you can resume it later.")
        pause_button = dialog.addButton("Pause Listing", QMessageBox.ButtonRole.AcceptRole)
        keep_button = dialog.addButton("Keep Published", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(keep_button)
        dialog.setEscapeButton(keep_button)
        dialog.exec()
        return dialog.clickedButton() is pause_button

    def _on_resume_listing(self, listing_id: str):
        if not self._owner_may_manage():
            return
        try:
            photos_dir = (
                self._owner_photo_service.photos_dir
                if self._owner_photo_service is not None else None)
            resumed = self._owner_listing_service.resume_listing(
                self._student_id, listing_id, photos_dir=photos_dir)
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            self._reload_owner_listings()
            return
        except Exception:
            self.owner_listings_page.show_message("Something went wrong, so it was not resumed.")
            return
        self._reload_owner_listings()
        self._refresh_published_catalog()
        self.owner_listings_page.show_message(
            f"“{resumed.title}” is published and visible in the Catalog again.")

    def _on_delete_listing(self, listing_id: str):
        if not self._owner_may_manage():
            return
        try:
            listing = self._owner_listing_service.get(self._student_id, listing_id)
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            self._reload_owner_listings()
            return
        except Exception:
            self.owner_listings_page.show_message("Could not load this listing.")
            return
        if not self._confirm_listing_delete(listing.title):
            return
        try:
            self._owner_listing_service.delete_listing(self._student_id, listing_id)
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            self._reload_owner_listings()
            return
        except Exception:
            self.owner_listings_page.show_message("Something went wrong, so it was not deleted.")
            return
        self._reload_owner_listings()
        self._refresh_published_catalog()
        self.owner_listings_page.show_message(
            f"“{listing.title}” was removed from My Listings and borrower visibility.")

    def _confirm_listing_delete(self, title: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Delete listing?")
        dialog.setText(f"Delete “{title}”?")
        dialog.setInformativeText(
            "It will be removed from My Listings and borrower visibility. Listing data, photos, "
            "and history are retained safely.")
        cancel_button = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        delete_button = dialog.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        return dialog.clickedButton() is delete_button

    def _confirm_listing_publish(self, title: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Publish listing?")
        dialog.setText(f"Publish “{title}”?")
        dialog.setInformativeText(
            "This changes the listing status to Published. It will not be added to the Catalog.")
        publish_button = dialog.addButton("Publish Listing", QMessageBox.AcceptRole)
        keep_draft_button = dialog.addButton("Keep as Draft", QMessageBox.RejectRole)
        dialog.setDefaultButton(keep_draft_button)
        dialog.exec()
        return dialog.clickedButton() is publish_button

    def _show_owner_form(self):
        self.owner_rail.select(OWNER_LISTINGS)   # the form belongs to My Listings
        self.content_stack.setCurrentWidget(self.owner_form_page)

    def _on_add_listing(self):
        if not self._owner_may_manage():
            return
        if self.has_unsaved_listing_changes():
            self._request_listing_form_leave(self._on_add_listing)
            return
        self.owner_form_page.start_new()
        self._show_owner_form()

    def _on_edit_listing(self, listing_id: str):
        if not self._owner_may_manage():
            return
        if self.has_unsaved_listing_changes():
            self._request_listing_form_leave(
                lambda: self._on_edit_listing(listing_id))
            return
        try:
            listing = self._owner_listing_service.get(self._student_id, listing_id)
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            self._reload_owner_listings()
            return
        except Exception:
            self.owner_listings_page.show_message("Could not open this listing.")
            return
        schedule = None
        try:
            schedule = self._owner_listing_service.get_availability(self._student_id, listing_id)
        except Exception:
            pass   # the draft still opens; the schedule just shows as not set
        self.owner_form_page.load(listing, self._saved_photo_items(listing_id), schedule)
        self._show_owner_form()

    def _on_preview_listing(self, listing_id: str):
        if not self._owner_may_manage():
            return
        if self.has_unsaved_listing_changes():
            self._request_listing_form_leave(
                lambda: self._on_preview_listing(listing_id))
            return
        try:
            listing = self._owner_listing_service.get(self._student_id, listing_id)
            schedule = self._owner_listing_service.get_availability(self._student_id, listing_id)
            photos = (self._owner_photo_service.photos(self._student_id, listing_id)
                      if self._owner_photo_service is not None else [])
        except OwnerListingError as exc:
            self.owner_listings_page.show_message(str(exc))
            return
        except Exception:
            self.owner_listings_page.show_message("Could not preview this draft.")
            return
        old_preview = getattr(self, "_owner_preview_page", None)
        if old_preview is not None:
            self.content_stack.removeWidget(old_preview)
            old_preview.deleteLater()
        preview = OwnerListingPreviewPage(
            listing, [photo.path for photo in photos], schedule)
        preview.back_requested.connect(self._on_preview_back)
        self._owner_preview_page = preview
        self.content_stack.addWidget(preview)
        self.content_stack.setCurrentWidget(preview)

    def _on_preview_back(self):
        """Return without reloading My Listings so its current view and state are preserved."""
        if not self._owner_may_manage():
            return
        self.owner_rail.select(OWNER_LISTINGS)
        self.content_stack.setCurrentWidget(self.owner_listings_page)

    def _saved_photo_items(self, listing_id: str) -> list:
        """(photo id, path, is_primary) of the listing's saved photos (empty on any problem)."""
        if self._owner_photo_service is None:
            return []
        try:
            photos = self._owner_photo_service.photos(self._student_id, listing_id)
        except Exception:
            return []
        return [(photo.photo_id, photo.path, photo.is_primary) for photo in photos]

    def _on_listing_save(self, fields: dict, listing_id):
        if (self._workspace != WORKSPACE_STUDENT_OWNER
                or self._owner_listing_service is None
                or not self._owner_listing_service.can_manage(self._student_id)):
            self._pending_form_leave = None
            self.owner_form_page.show_error(
                "Student Owner access is no longer available. Your changes are still here.")
            return
        form = self.owner_form_page
        if listing_id is not None and form.is_published:
            if not self._confirm_published_listing_save(form.title_input.text().strip()):
                self._pending_form_leave = None
                return
        availability = self.owner_form_page.availability()
        try:
            if listing_id is None:
                saved = self._owner_listing_service.create_draft(
                    self._student_id, fields, availability)
                self.owner_form_page.adopt_created_listing(saved)
                message = f"Draft “{saved.title}” saved."
            else:
                if form.is_published:
                    saved = self._owner_listing_service.update_published(
                        self._student_id, listing_id, fields, availability)
                    message = f"Published listing “{saved.title}” updated."
                else:
                    saved = self._owner_listing_service.update_draft(
                        self._student_id, listing_id, fields, availability)
                    message = f"Changes to “{saved.title}” saved."
        except OwnerListingError as exc:
            self._pending_form_leave = None
            self.owner_form_page.show_error(str(exc))   # stay on the form; nothing is lost
            return
        except Exception:
            self._pending_form_leave = None
            self.owner_form_page.show_error(
                "Something went wrong, so your draft was not saved.")
            return
        self.owner_form_page.mark_fields_saved()
        if not self._apply_pending_listing_photos(saved.listing_id):
            self._pending_form_leave = None
            return
        if saved.status in (STATUS_PUBLISHED, STATUS_PAUSED):
            self._refresh_published_catalog()
        try:
            saved = self._owner_listing_service.get(self._student_id, saved.listing_id)
            schedule = self._owner_listing_service.get_availability(
                self._student_id, saved.listing_id)
            photo_items = self._saved_photo_items(saved.listing_id)
        except Exception:
            self._pending_form_leave = None
            self.owner_form_page.show_error("Your draft was saved, but it could not be reloaded.")
            return
        self.owner_form_page.load(saved, photo_items, schedule)
        pending_leave = getattr(self, "_pending_form_leave", None)
        self._pending_form_leave = None
        if pending_leave is not None:
            pending_leave()
        else:
            self._on_owner_nav(OWNER_LISTINGS)
            self.owner_listings_page.show_message(message)

    def _confirm_published_listing_save(self, title: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Save published listing changes?")
        dialog.setText(f"Save changes to “{title}”?")
        dialog.setInformativeText(
            "The listing will remain Published, and updated details will appear in the Catalog.")
        save_button = dialog.addButton("Save Changes", QMessageBox.ButtonRole.AcceptRole)
        keep_button = dialog.addButton("Keep Editing", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(keep_button)
        dialog.setEscapeButton(keep_button)
        dialog.exec()
        return dialog.clickedButton() is save_button

    def _apply_pending_listing_photos(self, listing_id: str) -> bool:
        """Persist staged photo edits; leave the form open and retryable on any failure."""
        form = self.owner_form_page
        plan = form.photo_change_plan()
        service = self._owner_photo_service
        if service is None and (plan["add"] or plan["remove"]):
            form.show_photo_note("Photo storage is unavailable. Your changes are still here.",
                                 error=True)
            form.show_error("Could not save photo changes. Your draft remains open.")
            return False
        try:
            for source in list(plan["add"]):
                photo = service.add_photo(self._student_id, listing_id, source)
                form.photo_added_committed(source, photo)
            for photo_id in list(plan["remove"]):
                service.remove_photo(self._student_id, listing_id, photo_id)
                form.photo_removed_committed(photo_id)
            primary = form.photo_change_plan()["primary"]
            if primary is not None:
                current = next((photo for photo in service.photos(self._student_id, listing_id)
                                if photo.photo_id == primary), None)
                if current is not None and not current.is_primary:
                    service.set_primary(self._student_id, listing_id, primary)
                form.photo_primary_committed(primary)
        except PhotoError as exc:
            form.show_photo_note(str(exc), error=True)
            form.show_error("Your listing details were saved, but the photo changes were not "
                            "fully saved. Your remaining changes are still here.")
            return False
        except Exception:
            form.show_photo_note("Something went wrong. Your remaining photo changes are still here.",
                                 error=True)
            form.show_error("Your listing details were saved, but the photo changes were not "
                            "fully saved. Your remaining changes are still here.")
            return False
        return True

    def _save_staged_photos(self, listing_id: str, paths) -> list:
        """Add the photos picked while the listing was new; return the problems (text)."""
        problems = []
        if self._owner_photo_service is None:
            return ["photos are not available"] if paths else []
        for path in paths:
            try:
                self._owner_photo_service.add_photo(self._student_id, listing_id, path)
            except PhotoError as exc:
                problems.append(str(exc))
            except Exception:
                problems.append("an unexpected problem")
        return problems

    # ---------- Step 31C: photos of a saved listing (applied right away) ----------
    def _photo_action(self, listing_id: str, action) -> bool:
        """Run one photo change, refresh the form's photos, and report what happened."""
        form = self.owner_form_page
        if not self._owner_may_manage() or self._owner_photo_service is None:
            return False
        ok = True
        try:
            action()
        except PhotoError as exc:
            form.show_photo_note(str(exc), error=True)
            ok = False
        except Exception:
            form.show_photo_note("Something went wrong. Nothing was changed.", error=True)
            ok = False
        form.set_photos(self._saved_photo_items(listing_id))
        return ok

    def _on_listing_photos_add(self, listing_id: str, paths: list):
        errors, added = [], 0
        for path in paths:
            if self._photo_action(listing_id, lambda p=path: self._owner_photo_service.add_photo(
                    self._student_id, listing_id, p)):
                added += 1
            else:
                errors.append(path)
        if added and not errors:
            self.owner_form_page.show_photo_note(
                f"{added} photo{'s' if added != 1 else ''} added.", error=False)
        elif added and errors:
            self.owner_form_page.show_photo_note(
                f"{added} added, {len(errors)} could not be added.", error=True)
        # (a single failure keeps the specific message _photo_action already showed)

    def _on_listing_photo_remove(self, listing_id: str, photo_id):
        if self._photo_action(listing_id, lambda: self._owner_photo_service.remove_photo(
                self._student_id, listing_id, photo_id)):
            self.owner_form_page.show_photo_note("Photo removed.", error=False)

    def _on_listing_photo_primary(self, listing_id: str, photo_id):
        if self._photo_action(listing_id, lambda: self._owner_photo_service.set_primary(
                self._student_id, listing_id, photo_id)):
            self.owner_form_page.show_photo_note("Primary photo changed.", error=False)

    # ---------- navigation ----------
    def go_to(self, key: str):
        """Open existing student pages; keep unfinished destinations as placeholders."""
        item = self._nav_items.get(key)
        if item is None:
            return
        if self.has_unsaved_listing_changes():
            self._request_listing_form_leave(lambda: self.go_to(key))
            return
        if self.sidebar_rail.editing and key != "settings":
            return  # Step 14F: while editing the sidebar, stay on Settings (its controls)
        if self._workspace == WORKSPACE_STUDENT_OWNER and key != "settings":
            return  # Step 31A: student pages belong to the Student workspace
        if self._workspace == WORKSPACE_STUDENT_OWNER:
            self.owner_rail.select("settings")
            self._reload_settings()
            self.content_stack.setCurrentWidget(self._pages["settings"])
            return
        if key != "settings" and self.is_authenticated and hasattr(self, "settings_page"):
            self.settings_page.revert_unsaved_margin()  # an unsaved margin preview is dropped
        self._nav_buttons[key].setChecked(True)
        if key == "catalog" and self.is_authenticated:
            self._refresh_published_catalog()
        if key in ("catalog", "my_list") and self.is_authenticated and key in self._pages:
            self._refresh_catalog_photos()  # picks up photos added since last visit
        if key == "dashboard":
            self.content_stack.setCurrentWidget(self.home_page)
        elif self.is_authenticated and key in self._pages:
            if key in ("borrowings", "reservations"):
                self._pages[key].refresh()  # keep "time remaining / to collect" current
            elif key == "notifications":
                self._reload_notifications()  # read-only refresh from SQLite
            elif key == "settings":
                self._reload_settings()  # read-only refresh from SQLite
            self.content_stack.setCurrentWidget(self._pages[key])
        else:
            self.placeholder_page.set_content(item.label, item.message)
            self.content_stack.setCurrentWidget(self.placeholder_page)
