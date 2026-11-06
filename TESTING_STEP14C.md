# Step 14C (Stage 1B: icon-only sidebar) - quick testing
1. VS Code terminal in the project folder: `.venv\Scripts\Activate.ps1`, then `python main.py`.
2. Log in (or use demo). Check the left rail:
   - narrow (72px), icons only, no text, also after clicking;
   - hover each icon: a dark tooltip shows its name; the open page's icon is lavender on a soft lavender tile;
   - all 8 pages open; "K" mark at the top; initials at the bottom (hover: name + email); door icon at the bottom logs out.
   - the top "SIGNED IN" banner and its Log Out button are still there (removed in Stage 1C).
   - shrink the window to about 800x500: the icons scroll with the mouse wheel instead of forcing the window taller.
3. Tests: `python -m unittest discover -s tests` -> last line must be `OK` (321 tests; 31 are new, in tests/test_sidebar.py).
