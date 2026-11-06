"""Workspaces an account is allowed to use (Step 12). No GUI code in this file.

WHY THIS FILE IS SO SMALL
-------------------------
KitLend will have several workspaces under ONE account:

    Student (default) · Student Lender · Library Admin · Laboratory Admin ·
    Moderator · Super Admin

Today's storage is a single-computer SQLite file with NO server and NO administrator
or lender features. Anything stored here could be edited by whoever owns the computer,
so it cannot be a trustworthy source of administrator rights. Because of that, Step 12
deliberately does NOT invent role tables, "become a lender" switches or placeholder
permissions. The only workspace this build can honestly confirm is the default one:

  * Student  - every registered student account has it.

Everything else (Student Lender after an approved application; Library Admin,
Laboratory Admin, Moderator and Super Admin assigned by the Super Admin) must come from
the future central backend, which decides, records and enforces those rights on the
server. See docs/STEP12_WORKSPACES_ROADMAP.md.

HOW THE REST OF THE APP USES IT
-------------------------------
The Settings screen only DISPLAYS what `assigned_workspaces()` returns. When the
backend arrives, replace the body of that one method with a call to it; the screen
and its tests do not change. The screen can never add a workspace by itself.
"""
from dataclasses import dataclass

WORKSPACE_STUDENT = "student"
WORKSPACE_STUDENT_LENDER = "student_lender"
WORKSPACE_STUDENT_OWNER = "student_owner"
WORKSPACE_LIBRARY_ADMIN = "library_admin"
WORKSPACE_LABORATORY_ADMIN = "laboratory_admin"
WORKSPACE_MODERATOR = "moderator"
WORKSPACE_SUPER_ADMIN = "super_admin"


@dataclass(frozen=True)
class Workspace:
    key: str
    label: str
    description: str
    is_default: bool = False


# Names and descriptions for display only. Having an entry here grants NOTHING.
WORKSPACE_CATALOG = {
    WORKSPACE_STUDENT: Workspace(
        WORKSPACE_STUDENT, "Student",
        "Browse the catalog, request items and follow your borrowings.", True),
    WORKSPACE_STUDENT_LENDER: Workspace(
        WORKSPACE_STUDENT_LENDER, "Student Lender",
        "Lend your own items. Requires an application and approval."),
    WORKSPACE_STUDENT_OWNER: Workspace(
        WORKSPACE_STUDENT_OWNER, "Student Owner",
        "Your owner dashboard and listings. Available after an approved application."),
    WORKSPACE_LIBRARY_ADMIN: Workspace(
        WORKSPACE_LIBRARY_ADMIN, "Library Admin", "Assigned by a Super Admin."),
    WORKSPACE_LABORATORY_ADMIN: Workspace(
        WORKSPACE_LABORATORY_ADMIN, "Laboratory Admin", "Assigned by a Super Admin."),
    WORKSPACE_MODERATOR: Workspace(
        WORKSPACE_MODERATOR, "Moderator", "Assigned by a Super Admin."),
    WORKSPACE_SUPER_ADMIN: Workspace(
        WORKSPACE_SUPER_ADMIN, "Super Admin", "Assigned by the authorized Super Admin."),
}

# What a future backend can offer, shown as plain information (never as buttons).
HOW_TO_GET_ACCESS = (
    "Student Lender access needs an application that is approved. Library Admin, "
    "Laboratory Admin, Moderator and Super Admin access can only be assigned by an "
    "authorized Super Admin. Changing a setting never gives you more access."
)


class WorkspaceService:
    """Which workspaces an account may use.

    Step 31A: the Student Owner workspace is offered ONLY while the student has an
    APPROVED Student Owner application (read through StudentOwnerService). Every other state
    (no application, Pending, Rejected, a storage problem) means Student only. Today the
    status lives in the local database, so this is a local rule: the future backend must
    become the authority (replace `is_student_owner`).
    """

    def __init__(self, student_owner_service=None):
        self._owner_service = student_owner_service

    @staticmethod
    def _valid(student_id) -> bool:
        return isinstance(student_id, int) and not isinstance(student_id, bool)

    def is_student_owner(self, student_id: int) -> bool:
        """True only for an account whose current application is Approved. Never raises."""
        if not self._valid(student_id) or self._owner_service is None:
            return False
        try:
            applications = self._owner_service.list_applications(student_id)
        except Exception:
            return False  # when in doubt, no access
        return any(application.is_approved for application in applications)

    def assigned_workspaces(self, student_id: int) -> list:
        """The workspaces this account is authorized to use: Student, plus Student Owner
        for an approved Student Owner."""
        if not self._valid(student_id):
            return []
        spaces = [WORKSPACE_CATALOG[WORKSPACE_STUDENT]]
        if self.is_student_owner(student_id):
            spaces.append(WORKSPACE_CATALOG[WORKSPACE_STUDENT_OWNER])
        return spaces

    def can_use(self, student_id: int, key: str) -> bool:
        return any(space.key == key for space in self.assigned_workspaces(student_id))
