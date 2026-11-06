# KitLend Desktop - Step 30A (floating app container): testing on Windows + VS Code

Run: `python main.py`   Tests: `python -m unittest discover -s tests` (expect a final OK)
Only this step: `python -m unittest discover -s tests -p "test_floating_shell.py" -v`

## Manual check (about 3 minutes)
1. Log in. The sidebar and the page now sit in ONE rounded container with a gap around it, on a
   slightly darker background. Corners are rounded all around, with a faint outline.
2. Drag the window larger/smaller and maximize it: the gap grows to a comfortable 30 px, the
   container always fills the rest. At the smallest window size the gap closes (the sidebar needs
   the height).
3. Visit Dashboard, Catalog (and an item's details), My List, My Requests, My Borrowings,
   Reservations, Notifications, Settings: all inside the same container.
4. Sidebar: Settings -> edit the sidebar (drag, resize icons, avatar), save, restart: unchanged.
   Maximize after customising in a small window: no strange gaps. The notification dot still shows.
5. Login and Register screens are NOT wrapped (they are not student screens).
