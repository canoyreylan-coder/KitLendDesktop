# Step 31B — My Listings & Add Listing

Use the Step 31A dev tool to approve a test student (`dev_tools/dev_owner_approval.py`), then:

1. Sign in, Settings → switch to Student Owner workspace.
2. My Listings → "+ Add Listing" (also on the empty state).
3. Fill name, category, condition, description, max borrow days, optional extra rules → Save Draft.
4. The draft appears in My Listings (status "Draft"); click a card or Edit to reopen and change it.
5. Owner Dashboard shows the draft count.
6. A student who is not an approved Student Owner cannot open the workspace or manage listings
   (checked in the service and in the dashboard on every action).

Not included: photos, publishing, borrowing approvals.

Tests: `python -m unittest tests.test_owner_listings -v` (service tests run anywhere;
UI tests need PySide6 and are skipped otherwise).
