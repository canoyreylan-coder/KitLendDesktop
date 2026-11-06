# KitLend Desktop - Step 24 (My Requests refinement): testing on Windows + VS Code

Run: `python main.py`   Tests: `python -m unittest discover -s tests` (expect a final OK)
Only this page's tests: `python -m unittest discover -s tests -p "test_my_requests_tabs.py" -v`

## Manual check (about 5 minutes)
1. My Requests: one quiet "Stored on this computer only" line, a compact counts line, and a collapsed
   "Borrowing Guide" (click to open/close). No big stat cards, no wall of status buttons.
2. Tabs: **Active** (Pending, Approved, Borrowed, Return Pending), **History** (Returned, Rejected,
   Expired), **Cancelled**. The small dropdown at the right appears in Active only.
3. Request something in the Catalog -> it shows under Active (Pending). Cancel it -> it moves to Cancelled.
4. Cancelled tab -> **Clear Cancelled** -> confirm. The entries disappear. Restart the app: still gone.
   History tab -> **Clear History** works the same way. Active requests can never be cleared.
5. Other pages still show those finished requests (My Borrowings history, Reservations, Dashboard).
   Clearing only hides them on My Requests; nothing is deleted from the database.
6. Sidebar drag/resize/avatar, Catalog, My List, Settings: unchanged.

To see finished requests with a fresh account, finished statuses can't be created in the app yet
(that needs a lender/administrator), so use a test database or the preview: `python preview_my_requests.py`.
