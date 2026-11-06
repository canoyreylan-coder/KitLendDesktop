# Step 22 - My List visual redesign: quick testing (Windows + VS Code)
1. `python main.py`, log in, save a few items with the star in **Browse Catalog**, open **My List**.
2. Soft-dark header, toolbar, saved-item cards (photo or placeholder, title, category, owner, availability, Remove) and a bottom action bar.
3. Tick available items: the card highlights, the bottom button shows the count. Unavailable items cannot be ticked. "Select all eligible" / "Clear selection" work.
4. **Request Selected** opens the same request form: calendar/date picker, pickup time, borrowing days and Confirm are unchanged.
5. Remove an item; empty the list to see the new empty state and its Browse Catalog button.
6. Shrink the window (about 800 px wide): the mascot hides and cards stack availability + Remove under the text. Maximize: cards stretch cleanly.
7. Check Catalog, Item Details, My Requests and the sidebar look and behave as before.
8. Tests: `python -m unittest discover -s tests` -> last line `OK`.
