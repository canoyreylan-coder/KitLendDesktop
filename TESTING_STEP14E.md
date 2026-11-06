# Step 14E (balanced sidebar) - quick testing
1. VS Code terminal in the project folder: `.venv\Scripts\Activate.ps1`, then `python main.py`, log in.
2. Check the left rail: avatar at the top, Log Out at the bottom, the 8 icons spread evenly in between
   (equal gaps, none crowded at the top). Maximize the window, then make it short: the spacing follows the
   window; on a very short window the icons scroll with the mouse wheel instead of overlapping or being cut off.
3. Hover tooltips, the lavender active highlight, clicking the avatar (opens Settings) and all 8 pages still work.
4. Tests: `python -m unittest discover -s tests` -> last line must be `OK` (335 tests).
