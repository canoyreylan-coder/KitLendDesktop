# Step 18 - Catalog horizontal filtering: quick testing (Windows + VS Code)
1. Terminal in the project folder: `.venv\Scripts\Activate.ps1`, then `python main.py`; log in, open **Browse Catalog**.
2. Below the search bar you now see dropdowns: Category, Ownership, Availability (and Collection).
3. Pick values in each, then in combination, and type in the search bar: results must satisfy ALL of them.
4. Chips appear under the dropdowns. Click a chip's x: only that filter resets. "Clear all filters" resets the dropdowns but keeps your search text and the Grid/List choice.
5. Switch Grid/List: filters, chips, search and results stay the same. Make a search that finds nothing: a readable message appears.
6. Shrink the window (about 1000 px wide): dropdowns and chips wrap, nothing overlaps.
7. Check Request Now / star buttons, My List, Dashboard and the sidebar still behave as before.
8. Tests: `python -m unittest discover -s tests` -> last line `OK`.
