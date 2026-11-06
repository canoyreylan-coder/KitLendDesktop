# Outer Margin (adjustable floating app size): testing on Windows + VS Code

Tests: `python -m unittest discover -s tests -p "test_outer_margin.py" -v` (then the whole suite: expect a final OK)

## Manual check (about 3 minutes)
1. Log in -> Settings -> Appearance. Under "Outer margin" move the slider (12-48 px).
   The whole app container shrinks/grows at once, stays centered, corners stay rounded.
   Save / Cancel are disabled until you move the slider.
2. Move to 48, press Save, close KitLend, start it, log in: the same margin is applied.
   Another account keeps its own margin (or the automatic one).
3. Move the slider, press Cancel: back to the saved margin. Move it, then open another page
   without saving: the unsaved preview is dropped.
4. Press Reset to Default, then Save: back to "Automatic" (the gap that grows with the window).
5. Shrink the window to its smallest size with a large margin: the margin is reduced
   automatically (0 px at the smallest size), so the sidebar and pages are never clipped.
6. Sidebar icons, their sizes/positions, fonts and all other pages are unchanged.
