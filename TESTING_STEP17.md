# KitLend Desktop - Step 17 (Browse Catalog Grid / List view): testing on Windows + VS Code

## Run the app
`python main.py`  (first time: `python -m venv .venv`, `.venv\Scripts\Activate.ps1`, `pip install -r requirements.txt`)

## Automated tests (no window appears)
- This step only:  `python -m unittest discover -s tests -p "test_catalog_view.py" -v`
- Everything:      `python -m unittest discover -s tests`   -> expect a final `OK`

Four older tests now expect database migration **7** instead of 6 (the new `student_preferences` table).
That is the only change to existing tests.

## Manual check (about 5 minutes) - try 1366x768, then a small window, then maximize
1. Log in with a NEW account, open Browse Catalog. Cards (Grid) show, and the **Grid** button (right of
   "Showing N of M items") is highlighted.
2. Click **List**. The same items appear as horizontal rows: picture tile, name + author/brand,
   kind/category, ownership + pickup place, availability, **Request Now**, and the star. Switching is instant.
3. Type "python" in the search, tick "Available now only", pick a category. Click Grid/List back and forth:
   the search text, filters and results stay exactly the same in both views.
4. List view: Request Now (available item) opens the same request preview as before; an unavailable item's
   button is disabled. Star an item: it also shows as starred in Grid and appears in My List.
5. Search for nonsense: the "No items found" card with **Clear filters** appears in BOTH views.
6. Narrow the window (drag the edge, or restore down): rows fold the category/ownership columns into one
   grey line under the name, then (very narrow) drop the small picture tile. Request Now and the star never
   disappear and nothing is cut off. Grid cards re-flow into fewer columns as before.
7. Choose **List**, close KitLend completely, start it, log in again: the Catalog opens in List.
   Log in with a different account: it opens in Grid. (A choice is saved per account.)
8. Sidebar: drag icons, resize icons, change the avatar, maximize/restore - all as in Step 16.
9. Open Dashboard, My List, My Requests, My Borrowings, Reservations, Notifications, Settings: unchanged.

Notes
- Items have no "condition" data yet, so no condition is shown (nothing is invented). If an item ever has
  one, the List row shows "Condition: ..." automatically.
- New table `student_preferences` (migration 7, additive). Accounts, requests and notifications are untouched;
  a one-time `.before-v7.bak` copy is made next to your database the first time it is upgraded.
