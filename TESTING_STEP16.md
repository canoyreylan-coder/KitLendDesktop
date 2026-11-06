# KitLend Desktop - Step 16 (Browse Catalog visual redesign): testing on Windows + VS Code

## Run the app
`python main.py`  (first time: `python -m venv .venv`, `.venv\Scripts\Activate.ps1`, `pip install -r requirements.txt`)

## Automated tests (no window appears)
- Catalog only: `python -m unittest discover -s tests -p "test_catalog_redesign.py" -v`
- Everything:   `python -m unittest discover -s tests`   -> expect a final `OK`

## Manual check (about 5 minutes) - try 1366x768, then maximize
1. Log in, open Browse Catalog. It should look like the Dashboard: dark navy page, slightly lighter cards,
   soft lavender/pink accents, thin borders, no bright outlines.
2. Header: "Preview - Sample data only" tag, title, small mascot, and a large search bar.
3. Type "python": results narrow. Type nonsense: a readable "No items found" card appears with "Clear filters".
4. Scroll down: the compact search bar appears at the top and stays in sync with the big one.
5. Left filters (Category, Ownership, Available now only, Collections) and "Clear all" still work.
6. Cards: name, author/brand, ownership tag, pickup place / sharer, availability tag, Request Now, star.
   Hover a card: the border and background lighten slightly. Unavailable items have a disabled Request Now.
7. Star an item: it shows in My List. Request Now on an available item: opens the same request preview as before.
8. Resize the window: columns re-flow, no sideways scrollbar, cards stay the same size.
9. Sidebar: drag icons, resize icons, change avatar, hover tooltips, maximize/restore - all as in Step 15.
10. Open My List, My Requests, My Borrowings, Reservations, Notifications, Settings: unchanged from Step 15.

Note: items have no "condition" data yet, so no condition label is shown (nothing is invented).
