# Workspaces: what Step 12 does and what a later phase must build

## Done in Step 12
- Settings has a **Workspaces** section listing the workspaces the account is authorized to use.
- The list comes from `app/workspace_service.py -> WorkspaceService.assigned_workspaces(student_id)`.
- Today that always returns **Student** (the default). Nothing else can be confirmed
  safely, because the app has no server, no administrator or lender features, and the
  SQLite file is editable by whoever owns the computer.
- The screen has **no** switch, apply or "become" button. Nothing in the UI can add a workspace.
- The six workspace names (Student, Student Lender, Library Admin, Laboratory Admin,
  Moderator, Super Admin) exist only as display text. Having a name grants nothing.

## Deliberately NOT done (to avoid placeholder permissions)
- No roles table, no "role" column on `students`, no local admin/lender flags.
- No Student Lender application form, no approval queue.
- No workspace switching and no admin or lender dashboards.

## Required backend work for a later phase
1. **Central backend + real sessions.** Login returns a signed token (e.g. JWT or server
   session). Every request is authorized on the server, never in the desktop UI.
2. **Roles and assignments (server side).**
   `workspace_assignments(account_id, workspace, status, granted_by, granted_at, revoked_at)`
   with a full audit log. Student is implicit for verified student accounts.
3. **Student Lender flow.** `lender_applications(id, account_id, status, submitted_at,
   reviewed_by, reviewed_at, note)`. Approval by an authorized reviewer creates the assignment.
4. **Administrative roles.** Library Admin, Laboratory Admin and Moderator are assigned only
   by a Super Admin. The first Super Admin is created out-of-band (server setup), never from the app.
5. **Workspace switching.** The client asks the backend for the account's assignments and
   shows a switch control only for returned roles. Each workspace API call is re-checked by
   the server, so a modified client gains nothing.
6. **Replace one method.** Point `WorkspaceService.assigned_workspaces` at the backend. The
   Settings screen and its tests stay the same.
7. **Email verification first.** Changing the registered email, and any admin/lender
   assignment tied to an email, should wait for email ownership verification.
8. **Password change on the backend.** Move `AuthService.change_password` server side, add
   rate limiting / lockout on wrong current passwords, and revoke other sessions after a change.
9. **Preferences sync.** `notification_preferences` (student_id, event_type, enabled) maps
   1:1 to a server table. "No row = on" should be kept.

## Step 13 addendum: Student Owner applications
- Settings has **Become a Student Owner**; applications are stored in `student_owner_applications`
  (migration 5) via `app/student_owner_service.py`. The service can only submit and read.
- Nothing grants permission: Approved is displayed information only. `WorkspaceService` still
  returns Student only. The future review system/backend must set status, `reviewed_at`
  and `review_note`, and the server (not this SQLite file) must be the authority on access.
- The partial unique index keeps at most one Pending-or-Approved application per student.
