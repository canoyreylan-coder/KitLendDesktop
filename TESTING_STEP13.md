# KitLend Desktop - Step 13 (Student Owner application): testing on Windows + VS Code

## Run the app
`python main.py`  (same setup as before: venv + `pip install -r requirements.txt`)

## Automated tests (no window appears)
- Step 13 only: `python -m unittest discover -s tests -p "test_student_owner.py" -v`
- Everything:   `python -m unittest discover -s tests`   -> expect a final `OK`
(Three older tests now expect migration list [1, 2, 3, 4, 5] because Step 13 adds migration 5.)

## Manual check (about 5 minutes)
1. Log in -> **Settings** -> scroll to **Become a Student Owner** (under Workspaces).
   Status says "You have not applied yet." Workspaces still lists only **Student**.
2. Click **Submit Application** with everything empty -> red message, nothing saved.
3. Fill the reason (20+ characters) and items, leave the box unticked -> red "must agree" message.
4. Tick the agreement and submit -> green message with an ID like `SO-1A2B3C4D`; status pill
   **Pending**; the form disappears; "Your applications" lists it.
5. Open **Catalog** and request an item -> borrowing works normally while Pending.
6. Log out and in again, and restart the app -> still Pending, no second submit possible.
7. Register a second account -> its Settings shows "not applied yet" (accounts are separate).
8. Rejected / Approved cannot be set from the app (there is no admin yet). To see those looks
   during testing ONLY, close the app and run this in a terminal (replace the ID):
   `python -c "import sqlite3,os;c=sqlite3.connect(os.path.expandvars(r'%APPDATA%\KitLend\kitlend_local.db'));c.execute(\"UPDATE student_owner_applications SET status='Rejected', review_note='Please list real items.' WHERE application_id='SO-XXXXXXXX'\");c.commit()"`
   Reopen -> **Rejected** pill, the reason, and the form is back. Submit again -> a NEW ID,
   Pending, and the rejected one stays in the list. Use `status='Approved'` to see that the
   form is gone for good and nothing else changes (still only the Student workspace).

Your database is upgraded automatically; a one-time copy `kitlend_local.db.before-v5.bak` is saved.
