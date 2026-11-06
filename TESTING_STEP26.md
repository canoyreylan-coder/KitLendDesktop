# Step 26 — Notifications redesign

Looks and layout only. Notification records, read/unread state, `NotificationService` and the
dashboard wiring (Mark as read, Mark all as read, Browse Catalog) are unchanged.

## What changed
- `app/notifications_screen.py` — **All / Unread / Read** tabs (with counts) and compact rows:
  title, message, date/time and a small Unread/Read label. Unread rows have a lavender dot, thin
  lavender edge and faint tint; read rows are quiet text. Per-row **Mark as read** and the
  toolbar **Mark all as read** work as before. The explanation text is a collapsed
  "About notifications". Summary tiles and big cards are gone.
- `app/notifications_theme.py` — soft-dark styles scoped to `QWidget#notificationsScreen`.
- Clean empty states per tab; "Browse Catalog" only when there are no notifications at all.
- The selected tab is kept when notifications refresh. No mascot on this screen.

## Check it
    python -m unittest discover -s tests -v
