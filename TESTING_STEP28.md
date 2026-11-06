# Step 28 — Settings & Profile redesign + profile photos

## What changed
- `app/settings_screen.py` — Settings & Profile, grouped under text headings: PROFILE, ACCOUNT,
  APPEARANCE, NOTIFICATIONS, WORKSPACES. Every existing card and its behaviour is kept
  (account info, change password, sidebar customization, notification preferences, workspaces,
  Become a Student Owner).
- `app/settings_theme.py` — soft-dark styles scoped to `QWidget#settingsScreen` (no other screen is affected).
- `app/profile_photo_service.py` — saves/removes a photo per account (JPG, PNG, WEBP, up to 10 MB).
  The picture is centre-cropped to a square (never stretched) and stored as a PNG in a `profile_photos`
  folder next to `kitlend_local.db` (`%APPDATA%\KitLend\profile_photos` on Windows). No database change.
- `app/profile_avatar.py` — round avatar widget (photo, or initials when there is none).
- `app/dashboard_screen.py` — loads the photo at login, saves/removes it, and updates the sidebar avatar at once.
  Sidebar icon positions and sizes are untouched.
- Tests: `tests/test_profile_photo.py` (new). `tests/test_dashboard_home.py`: one assertion now expects
  the new `settingsScreen` object name.

## Check it
    python -m unittest discover -s tests -v
    python main.py

1. Settings → Profile photo → Upload photo → pick a JPG/PNG/WEBP. The Settings picture and the sidebar avatar change at once.
2. Try a wide and a tall picture: both become a clean circle, not stretched.
3. Change photo, then Remove photo → initials return in both places.
4. Close KitLend, start it, log in again: the photo is still there. Another account shows its own photo/initials.
5. Try a .txt or a renamed non-picture: a short message appears and nothing changes.
6. Sidebar: icon positions/sizes, Customize Sidebar, tooltips unchanged.
