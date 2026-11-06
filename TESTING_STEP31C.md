# Step 31C — Listing Photos & Availability

Use the Step 31A dev tool to approve a test student (`dev_tools/dev_owner_approval.py`), then:

1. Sign in → Settings → switch to the Student Owner workspace → My Listings → **+ Add Listing**.
2. **Photos**: *Add Photos* (JPG, PNG or WEBP, up to 5, 10 MB each). Click a thumbnail to preview it;
   *Make Primary* and *Remove Photo* act on the selected one. On a **new** listing photos are
   kept in the form and saved with the draft; on a **saved** draft every change applies at once.
3. **Availability**: tick the days students can collect the item and pick pickup hours for each
   (quick buttons: Weekdays / Every day / Clear). **Longest loan** is in the same card.
   *Save Draft* / *Save Changes* saves everything; reopen the draft any time to change it.
4. My Listings cards show the primary photo and a line such as `Pickup: Mon-Fri · 9:00 AM - 5:00 PM`.
5. Close and reopen KitLend: photos, primary choice and schedule are still there.

## What was added
- `app/owner_listing_photos.py` — owner-only add / remove / primary. Files are copied (shrunk to
  at most 1600 px, not cropped) into `<app data>/photos/<listing id>/`; rows go in the existing
  `listing_photos` table with the listing ID as `listing_key`, so the Catalog/Item Details gallery
  (`PhotoService.photos_for`) reads them with no extra wiring once listings are published.
- `app/owner_availability.py` — schedule model + validation, plus `allows_pickup(datetime)` and
  `allows_borrow_days(n, max)` ready for the future borrower pickup form (not used yet).
- Migration 14: new table `listing_availability` (additive only). The longest loan stays in
  `owner_listings.max_borrow_days`.
- `OwnerListingService`: `create_draft` / `update_draft` take an optional `availability` saved in the
  same transaction; `get_availability`, `availability_for_all`, `save_availability`.
- UI in `app/owner_workspace.py` (photo manager, availability editor, richer listing cards) and
  wiring in `app/dashboard_screen.py`. The default photos folder now sits beside the database
  (the same folder as before in a normal run).

Not included (by design): publishing, borrowing approvals, borrower pickup validation.
A draft may have 0 photos; the future publish step is meant to require at least one
(`MIN_PHOTOS_TO_PUBLISH`).

Tests: `python -m unittest discover -s tests -p "test_listing_photos_availability.py" -v`
(service tests run anywhere; the picture/UI/dashboard tests need PySide6).
