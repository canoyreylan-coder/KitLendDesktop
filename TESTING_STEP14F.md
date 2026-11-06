# Step 14F - Freeform sidebar editor (Windows / VS Code)

1. Open the folder in VS Code, activate your venv, then run:  `python main.py`
2. Log in -> sidebar icons look exactly like Step 14E.
3. Settings -> Appearance -> **Customize Sidebar**. Controls appear; the sidebar icons get dashed outlines.
4. Click an icon (avatar, any page icon, Log Out) to select it. It does NOT navigate while editing.
5. Drag it anywhere inside the sidebar. Use the **Size** slider / - / + and the **X / Y** boxes for fine control.
   Dropping an icon mostly on top of another snaps it back (make room by moving the neighbour first).
6. **Save Changes** = save, keep editing. **Finish Editing** = save and leave. **Cancel Changes** = discard and leave.
   **Reset Selected Icon** / **Reset All to Default** change the preview; Save/Finish keeps them.
7. Close and reopen KitLend, log in again: sizes and positions are remembered. Another account keeps its own layout.
8. Resize the window: saved positions stay (icons are only kept inside the visible sidebar).

Tests (first real run of the Qt tests): `python -m unittest discover -s tests -v`
New tests: `tests/test_sidebar_layout.py`. Storage: new table `sidebar_layouts` (migration 6), additive only.
