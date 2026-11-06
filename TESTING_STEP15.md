# KitLend Desktop - Step 15 (Stage 2A: Dashboard redesign): testing on Windows + VS Code

## Run the app
`python main.py`  (first time: `python -m venv .venv`, `.venv\Scripts\Activate.ps1`, `pip install -r requirements.txt`)

## Automated tests (no window appears)
- Dashboard only: `python -m unittest discover -s tests -p "test_dashboard_home.py" -v`
- Everything:     `python -m unittest discover -s tests`   -> expect a final `OK`

## Manual check (about 5 minutes) - set the window to 1366x768 if you can
1. Log in with a NEW account. Dashboard shows a compact welcome bar ("Good <time>, <first name>"),
   four dark tiles all at 0, and friendly empty states in every card. No fake records.
2. Catalog -> request an item. Back on Dashboard: **Pending Requests = 1**, the request is listed,
   Recent Activity shows "Requested <item>", the summary line says "1 pending request", and
   Unread Notifications = 1.
3. Cancel it in My Requests: Pending goes back to 0; activity shows the cancellation.
4. Click each tile, each "View all" link and each Quick Action: each opens the matching page.
5. Drag the window narrower: cards stack, no sideways scrollbar.
6. Sidebar: resize/drag icons, change the avatar, hover tooltips, restart: all as in Step 14F.
7. Open Catalog, My List, My Requests, My Borrowings, Reservations, Notifications, Settings
   (including Student Owner) - they look exactly as before. Log out and back in: still works.
8. (Optional) Log in as a second account: it never shows the first account's records.
