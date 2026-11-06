# Step 31D — Shared Listing Categories

Use the Step 31A dev tool (`dev_tools/dev_owner_approval.py`) to approve two test students, then:

1. Sign in as owner A → Settings → switch to Student Owner → My Listings → **+ Add Listing**.
2. **Category** lists the shared categories (Electronics, Engineering, Mathematics, Programming, Science, Study Gear).
   Click **+ New category**, type `Books` → *Create category*. It is selected in the form.
3. Choose Books, then **+ New subcategory**, type `Fantasy` → *Create subcategory*. Save the draft:
   My Listings shows `Books › Fantasy`. Reopen the draft: both choices are still selected.
4. Type `  books ` in **+ New category**: it says the name already exists and offers *Use existing* (nothing is created).
   Type `Book`: similar names are listed; pick one, or press *Create anyway*.
5. Sign in as owner B (a second account on the same database): `Books` and `Fantasy` are already in the lists.
   If B's form was already open, opening the Category list refreshes it.
6. Existing listings keep their categories. Before the upgrade a safety copy `kitlend_local.db.before-v15.bak` is made.

## What was added
- `app/listing_category_service.py` — the shared registry: duplicate check (ignores capitals/extra spaces), similar-name
  warnings, create (approved Student Owners only), and `OwnerCategoryAccess` for the form.
- Migration 15: tables `listing_categories` (unique indexes refuse duplicates) and `listing_category_links`
  (listing → category + optional subcategory). The six existing categories are seeded; any other category an existing listing
  already uses is kept too. `owner_listings.category` is unchanged.
- `app/owner_category_dialog.py` — the "New category / subcategory" dialog.
- `OwnerListingService` reads categories from the registry and saves the subcategory with the draft (same transaction).
- `app/owner_workspace.py` / `app/dashboard_screen.py` — Subcategory field, "+ New" buttons, refresh-on-open lists.

Not included: renaming/deleting categories, publishing, Catalog category filters from the registry.
