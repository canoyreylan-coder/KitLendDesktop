# KitLend Desktop - Step 31A (Student Owner workspace): testing on Windows + VS Code

Run: `python main.py`   Tests: `python -m unittest discover -s tests` (expect a final OK)
Only this step: `python -m unittest discover -s tests -p "test_owner_workspace.py" -v`

## Manual check
1. Normal student (no application, Pending or Rejected): Settings > Workspaces lists only **Student**, with no Switch button.
2. To try the owner side, use the development-only tool (it is NOT part of the app; close KitLend first):
   `python dev_tools/dev_owner_approval.py --email YOUR_TEST_EMAIL --status`
   `python dev_tools/dev_owner_approval.py --email YOUR_TEST_EMAIL --approve --confirm-dev`
   Undo later with `--revoke --confirm-dev`. It changes only that one account, saves a backup
   (`kitlend_local.db.before-dev-owner.bak`) first, and marks its rows "DEV TEST APPROVAL".
   Add `--db PATH` to use a different database file.
3. Log in again, open **Settings > Workspaces**: Student (Current) and Student Owner, with **Switch to Student Owner**. Click it.
4. The sidebar is replaced by the owner rail (avatar, Owner Dashboard, My Listings, Settings, Switch workspace, Log Out) inside the same floating container. Owner Dashboard and the My Listings empty state open.
5. Settings (rail icon or avatar) is the SAME page: same name, email, Student ID and profile photo; Workspaces now shows Student Owner (Current) with **Switch to Student**.
6. Switch back to Student: your sidebar is exactly as you customised it (positions, sizes). Catalog, My List, requests, borrowings, reservations all work as before.
7. Sidebar customisation is only offered in the Student workspace. The Outer Margin setting still applies in both.
8. Log out from either rail; logging in always starts in the Student workspace.
Not built yet (by design): creating listings, lending approvals, inventory.
