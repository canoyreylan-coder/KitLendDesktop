# Step 27 — Reservations redesign

Looks and layout only. Reservation rules (`app/reservation_rules.py`), records, dates and the
dashboard wiring are unchanged. Nothing is approved, expired or cancelled from this screen.

## What changed
- `app/my_reservations_screen.py` — tabs by real status: **Awaiting Pickup** (Approved),
  **Expired**, **Cancelled** (cancelled after approval). Compact `ReservationCard`s show item,
  reserved date, confirmed pickup, pickup deadline / time to collect (or the expired/cancelled
  date), the status pill and any saved note. Summary tiles, the info box and the section lists
  are gone; the rule text is a collapsed **Reservation Guide**. No cancel button (cancelling
  stays in My Requests); no due date (it starts only at confirmed pickup).
- `app/my_reservations_theme.py` — soft-dark styles scoped to `QWidget#reservationsScreen`.
- A still-Approved reservation past its pickup deadline gets one soft rose tone (text + faint tint).
- Clean empty states per tab; "View My Requests" only when there are no reservations at all.
  Cards and date columns re-flow in small and maximized windows. No mascot on this screen.

## Check it
    python -m unittest discover -s tests -v
    python preview_my_reservations.py
