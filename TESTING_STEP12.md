# KitLend Desktop - Step 12 (Settings): testing on Windows + VS Code

## Run the app
1. Open the project folder in VS Code (the folder that contains `main.py`).
2. Terminal -> New Terminal (PowerShell). First time only:
   `python -m venv .venv` then `.venv\Scripts\Activate.ps1` then `pip install -r requirements.txt`
   (if PowerShell blocks the script: `Set-ExecutionPolicy -Scope Process Bypass`).
3. `python main.py`

## Run the automated tests (no window appears)
- All tests:        `python -m unittest discover -s tests`
- Step 12 only:     `python -m unittest discover -s tests -p "test_settings.py" -v`
Expected: a final line `OK`. The full suite takes about one minute.

## Manual check (5 minutes)
1. Log in, click **Settings** in the sidebar. Name and email are shown and cannot be edited.
2. **Change Password:** enter a wrong current password -> red error; mismatched or
   too-short new password -> red error; correct current + valid new -> green success.
3. Click **Log Out**, log in with the OLD password (must fail), then with the NEW one (must work).
4. Close and reopen the app, log in with the new password again.
5. **Notification Preferences:** untick "Request submitted". Submit a request from the Catalog.
   Dashboard unread count and the Notifications page must NOT gain a new item; the request
   still appears in My Requests as Pending. Tick it again, submit another -> a notification appears.
6. Untick "Request cancelled", cancel a request -> it is cancelled, no new notification.
7. Log out/in and restart: the ticks stay as you left them.
8. **Workspaces** lists only "Student - Default · Current". There is no switch button.

Your existing database (in `%APPDATA%\KitLend\kitlend_local.db`) is upgraded automatically and
safely; a one-time copy `kitlend_local.db.before-v4.bak` is saved next to it.
