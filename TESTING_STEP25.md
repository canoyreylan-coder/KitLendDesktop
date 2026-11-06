# Step 25 — My Borrowings redesign

Looks and layout only. No borrowing rule, due-date calculation, record or database code changed.

## What changed
- `app/my_borrowings_screen.py` — three tabs: **Active** (Borrowed), **Return Pending**
  (Return Verification Pending), **History** (Returned). Compact `BorrowingCard`s show item,
  picked-up date, due date and status (plus time left / return date). Summary tiles, the info
  box and the two section lists are gone; the rule text is in a collapsed **Borrowing Guide**.
- `app/my_borrowings_theme.py` — new soft-dark styles, scoped to `QWidget#myBorrowingsScreen`.
- Overdue (Borrowed and past `due_at`): one soft rose tone — a small **Overdue** pill, the due
  date and "Past due by …" text, a faint card tint. Overdue items sort first. A reported return
  is never overdue.
- Clean empty states per tab; the "View My Requests" button shows only when there are no
  borrowings at all. Layout re-flows when the window is resized. No mascot on this screen.

## Check it
    python -m unittest discover -s tests -v
    python preview_my_borrowings.py            # sample data incl. one overdue item
    python preview_my_borrowings.py --empty
    python preview_my_borrowings.py --full     # real app, temporary database

Pending / Approved / Rejected / Cancelled / Expired requests must still appear only in My Requests.
