"""Step 31C tests: listing photos and item availability.

Run:   python -m unittest discover -s tests -p "test_listing_photos_availability.py" -v
Groups 1-4 need no window (a stand-in picture processor copies the file). Groups 5-6 use Qt's
invisible "offscreen" mode and real pictures; they are skipped when PySide6 is missing.
Temporary databases and folders only.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import connect  # noqa: E402
from app.owner_availability import (  # noqa: E402
    AvailabilityError,
    AvailabilitySchedule,
    format_minute,
)
from app.owner_listing_photos import (  # noqa: E402
    MAX_PHOTOS,
    OwnerListingPhotoService,
)
from app.owner_listing_service import OwnerListingError, OwnerListingService  # noqa: E402
from app.photo_service import PhotoError, PhotoService  # noqa: E402
from test_owner_listings import CATEGORIES, Base, good  # noqa: E402

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False

WEEKDAYS = {d: [(9 * 60, 17 * 60)] for d in range(5)}   # Mon-Fri 9-5


def fake_process(source, base):
    """Stand-in for the Qt picture processor: copy the file next to `base`."""
    target = base + Path(source).suffix.lower()
    shutil.copyfile(source, target)
    return target


class PhotoBase(Base):
    def setUp(self):
        super().setUp()
        self.photos_dir = Path(self.tmp.name) / "photos"
        self.src = Path(self.tmp.name) / "src"
        self.src.mkdir()
        self.approve(self.ana)
        self.approve(self.ben)
        self.service = OwnerListingPhotoService(
            self.db, self.listings, self.photos_dir, image_processor=fake_process)
        self.draft = self.listings.create_draft(self.ana.id, good())

    def picture(self, name="a.jpg", data=b"fake-picture-bytes"):
        path = self.src / name
        path.write_bytes(data)
        return str(path)

    def photo_rows(self):
        return self.rows("SELECT * FROM listing_photos ORDER BY photo_id")


# ======================================================================
# 1. Availability model (no database)
# ======================================================================
class ScheduleModelTests(unittest.TestCase):
    def test_valid_schedule_is_sorted_and_read_back(self):
        schedule = AvailabilitySchedule.from_dict(
            {2: [(600, 720)], 0: [(13 * 60, 15 * 60), (9 * 60, 11 * 60)]})
        self.assertEqual(schedule.weekdays, (0, 2))
        self.assertEqual(schedule.windows_on(0), ((540, 660), (780, 900)))
        self.assertEqual(schedule.windows_on(5), ())
        self.assertFalse(schedule.is_empty)
        self.assertTrue(AvailabilitySchedule.from_dict({}).is_empty)
        self.assertTrue(AvailabilitySchedule.from_dict(None).is_empty)
        self.assertTrue(AvailabilitySchedule.from_dict({1: []}).is_empty)

    def test_invalid_schedules_are_refused_with_friendly_messages(self):
        bad = [
            {7: [(540, 600)]}, {-1: [(540, 600)]}, {"0": [(540, 600)]},
            {0: [(600, 600)]}, {0: [(700, 600)]},          # must end after it starts
            {0: [(600, 610)]},                              # shorter than 15 minutes
            {0: [(-5, 600)]}, {0: [(0, 1441)]}, {0: [(1440, 1500)]},
            {0: [(540, 700), (650, 800)]},                  # overlap
            {0: [(0, 60), (120, 180), (240, 300), (360, 420)]},   # 4 windows
            {0: [540]}, {0: [(540, "x")]}, {0: [(True, 600)]}, "Mon", [1, 2],
        ]
        for raw in bad:
            with self.assertRaises(AvailabilityError, msg=str(raw)) as ctx:
                AvailabilitySchedule.from_dict(raw)
            self.assertTrue(ctx.exception.is_user_facing)
            self.assertTrue(str(ctx.exception))

    def test_summary_groups_days_with_the_same_hours(self):
        self.assertEqual(AvailabilitySchedule.from_dict(WEEKDAYS).summary(),
                         "Mon-Fri · 9:00 AM - 5:00 PM")
        self.assertEqual(AvailabilitySchedule.empty().summary(), "No pickup days set")
        every = {d: [(480, 1200)] for d in range(7)}
        self.assertEqual(AvailabilitySchedule.from_dict(every).summary(),
                         "Every day · 8:00 AM - 8:00 PM")
        mixed = AvailabilitySchedule.from_dict({0: [(540, 600)], 2: [(540, 600)], 5: [(600, 720)]})
        self.assertEqual(mixed.summary(), "Mon, Wed · 9:00 AM - 10:00 AM; Sat · 10:00 AM - 12:00 PM")

    def test_format_minute(self):
        self.assertEqual([format_minute(m) for m in (0, 60, 540, 720, 780, 1020, 1410, 1440)],
                         ["12:00 AM", "1:00 AM", "9:00 AM", "12:00 PM", "1:00 PM", "5:00 PM",
                          "11:30 PM", "12:00 AM"])

    def test_future_pickup_validation_helpers(self):
        schedule = AvailabilitySchedule.from_dict(WEEKDAYS)
        monday = datetime(2026, 11, 2)       # a Monday
        self.assertEqual(monday.weekday(), 0)
        self.assertTrue(schedule.allows_pickup(monday.replace(hour=9)))
        self.assertTrue(schedule.allows_pickup(monday.replace(hour=16, minute=59)))
        self.assertFalse(schedule.allows_pickup(monday.replace(hour=17)))     # closing minute
        self.assertFalse(schedule.allows_pickup(monday.replace(hour=8, minute=59)))
        self.assertFalse(schedule.allows_pickup(datetime(2026, 11, 7, 10)))  # Saturday
        self.assertFalse(AvailabilitySchedule.empty().allows_pickup(monday.replace(hour=10)))
        self.assertTrue(AvailabilitySchedule.allows_borrow_days(3, 3))
        self.assertTrue(AvailabilitySchedule.allows_borrow_days(1, 3))
        self.assertFalse(AvailabilitySchedule.allows_borrow_days(4, 3))
        self.assertFalse(AvailabilitySchedule.allows_borrow_days(0, 3))
        self.assertFalse(AvailabilitySchedule.allows_borrow_days(True, 3))


# ======================================================================
# 2. Availability saved per listing in SQLite
# ======================================================================
class AvailabilityStorageTests(Base):
    def setUp(self):
        super().setUp()
        self.approve(self.ana)
        self.approve(self.ben)

    def slots(self, listing_id=None):
        sql = "SELECT * FROM listing_availability"
        params = ()
        if listing_id:
            sql, params = sql + " WHERE listing_id = ?", (listing_id,)
        return self.rows(sql + " ORDER BY listing_id, weekday, start_minute", params)

    def test_migration_creates_the_table_and_touches_nothing_else(self):
        draft = self.listings.create_draft(self.ana.id, good())
        names = {r[0] for r in self.rows("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("listing_availability", names)
        self.assertEqual(self.slots(), [])
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]["listing_id"], draft.listing_id)
        versions = [r["version"] for r in self.rows("SELECT version FROM schema_migrations")]
        self.assertIn(14, versions)

    def test_a_draft_without_availability_has_an_empty_schedule(self):
        draft = self.listings.create_draft(self.ana.id, good())
        self.assertTrue(self.listings.get_availability(self.ana.id, draft.listing_id).is_empty)

    def test_availability_is_saved_with_the_draft_and_comes_back(self):
        draft = self.listings.create_draft(self.ana.id, good(), WEEKDAYS)
        schedule = self.listings.get_availability(self.ana.id, draft.listing_id)
        self.assertEqual(schedule.as_dict(), WEEKDAYS)
        self.assertEqual(len(self.slots(draft.listing_id)), 5)

    def test_it_survives_a_restart(self):
        draft = self.listings.create_draft(self.ana.id, good(), WEEKDAYS)
        again = OwnerListingService(self.db, self.workspaces, CATEGORIES)
        self.assertEqual(again.get_availability(self.ana.id, draft.listing_id).as_dict(), WEEKDAYS)

    def test_editing_a_draft_without_availability_keeps_the_schedule(self):
        draft = self.listings.create_draft(self.ana.id, good(), WEEKDAYS)
        self.listings.update_draft(self.ana.id, draft.listing_id, good(title="Casio Calculator"))
        self.assertEqual(
            self.listings.get_availability(self.ana.id, draft.listing_id).as_dict(), WEEKDAYS)

    def test_editing_replaces_the_schedule_and_an_empty_one_clears_it(self):
        draft = self.listings.create_draft(self.ana.id, good(), WEEKDAYS)
        new = {5: [(600, 720)]}
        self.listings.update_draft(self.ana.id, draft.listing_id, good(), new)
        self.assertEqual(self.listings.get_availability(self.ana.id, draft.listing_id).as_dict(), new)
        self.assertEqual(len(self.slots(draft.listing_id)), 1)
        self.listings.update_draft(self.ana.id, draft.listing_id, good(), {})
        self.assertTrue(self.listings.get_availability(self.ana.id, draft.listing_id).is_empty)

    def test_a_bad_schedule_saves_nothing_at_all(self):
        with self.assertRaises(OwnerListingError):
            self.listings.create_draft(self.ana.id, good(), {0: [(700, 600)]})
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.slots(), [])
        draft = self.listings.create_draft(self.ana.id, good(), WEEKDAYS)
        with self.assertRaises(OwnerListingError):
            self.listings.update_draft(self.ana.id, draft.listing_id,
                                       good(title="Changed title"), {0: [(700, 600)]})
        self.assertEqual(self.listings.get(self.ana.id, draft.listing_id).title, good()["title"])
        self.assertEqual(len(self.slots(draft.listing_id)), 5)

    def test_a_bad_draft_does_not_change_the_schedule(self):
        draft = self.listings.create_draft(self.ana.id, good(), WEEKDAYS)
        with self.assertRaises(OwnerListingError):
            self.listings.update_draft(self.ana.id, draft.listing_id, good(title=""), {6: [(600, 700)]})
        self.assertEqual(
            self.listings.get_availability(self.ana.id, draft.listing_id).as_dict(), WEEKDAYS)

    def test_save_availability_can_be_used_on_its_own_at_any_time(self):
        draft = self.listings.create_draft(self.ana.id, good())
        before = self.listings.get(self.ana.id, draft.listing_id).updated_at
        saved = self.listings.save_availability(self.ana.id, draft.listing_id, WEEKDAYS)
        self.assertEqual(saved.as_dict(), WEEKDAYS)
        self.assertGreater(self.listings.get(self.ana.id, draft.listing_id).updated_at, before)
        self.listings.save_availability(self.ana.id, draft.listing_id, {2: [(480, 540)]})
        self.assertEqual(self.listings.get_availability(self.ana.id, draft.listing_id).weekdays, (2,))
        with self.assertRaises(OwnerListingError):
            self.listings.save_availability(self.ana.id, draft.listing_id, {0: [(5, 1)]})
        self.assertEqual(self.listings.get_availability(self.ana.id, draft.listing_id).weekdays, (2,))

    def test_longest_loan_is_untouched_by_availability(self):
        draft = self.listings.create_draft(self.ana.id, good(max_borrow_days=4), WEEKDAYS)
        self.listings.save_availability(self.ana.id, draft.listing_id, {1: [(540, 600)]})
        self.assertEqual(self.listings.get(self.ana.id, draft.listing_id).max_borrow_days, 4)

    def test_schedules_are_private_per_owner(self):
        mine = self.listings.create_draft(self.ana.id, good(), WEEKDAYS)
        theirs = self.listings.create_draft(self.ben.id, good(title="Soldering kit"), {6: [(600, 660)]})
        self.assertEqual(set(self.listings.availability_for_all(self.ana.id)), {mine.listing_id})
        self.assertEqual(set(self.listings.availability_for_all(self.ben.id)), {theirs.listing_id})
        for call in (lambda: self.listings.get_availability(self.ben.id, mine.listing_id),
                     lambda: self.listings.save_availability(self.ben.id, mine.listing_id, {}),
                     lambda: self.listings.update_draft(self.ben.id, mine.listing_id, good(), {})):
            with self.assertRaises(OwnerListingError):
                call()
        self.assertEqual(self.listings.get_availability(self.ana.id, mine.listing_id).as_dict(), WEEKDAYS)

    def test_students_who_are_not_owners_cannot_read_or_write_schedules(self):
        draft = self.listings.create_draft(self.ana.id, good(), WEEKDAYS)
        for call in (lambda: self.listings.get_availability(self.cai.id, draft.listing_id),
                     lambda: self.listings.availability_for_all(self.cai.id),
                     lambda: self.listings.save_availability(self.cai.id, draft.listing_id, {}),
                     lambda: self.listings.create_draft(self.cai.id, good(), WEEKDAYS)):
            with self.assertRaises(OwnerListingError):
                call()

    def test_database_refuses_nonsense_rows(self):
        draft = self.listings.create_draft(self.ana.id, good())
        conn = connect(self.db)
        try:
            for values in ((7, 540, 600), (0, 600, 600), (0, 1500, 1600), (0, 0, 1441)):
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("INSERT INTO listing_availability (listing_id, weekday, "
                                 "start_minute, end_minute) VALUES (?, ?, ?, ?)",
                                 (draft.listing_id, *values))
        finally:
            conn.close()

    def test_existing_drafts_and_other_tables_are_not_changed(self):
        draft = self.listings.create_draft(self.ana.id, good(), WEEKDAYS)
        self.listings.update_draft(self.ana.id, draft.listing_id, good(title="Edited name"))
        self.assertEqual(len(self.listings.list_drafts(self.ana.id)), 1)
        self.assertEqual(self.listings.list_drafts(self.ana.id)[0].title, "Edited name")


# ======================================================================
# 3. Listing photos (service)
# ======================================================================
class PhotoServiceTests(PhotoBase):
    def test_add_stores_a_copy_in_the_photos_folder_and_a_database_row(self):
        photo = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture())
        self.assertTrue(photo.is_primary)                                   # the first is primary
        self.assertTrue(Path(photo.path).is_file())
        self.assertEqual(Path(photo.path).parent, self.photos_dir / self.draft.listing_id)
        row = self.photo_rows()[0]
        self.assertEqual(row["listing_key"], self.draft.listing_id)
        self.assertFalse(os.path.isabs(row["file_path"]))                   # relative: portable
        os.remove(self.src / "a.jpg")                                       # the original may go
        self.assertTrue(Path(photo.path).is_file())

    def test_the_existing_gallery_reads_these_photos_by_listing_id(self):
        first = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("1.png"))
        second = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("2.jpg"))
        gallery = PhotoService(self.db, self.photos_dir)        # what the Catalog/Details use
        self.assertEqual([p.path for p in gallery.photos_for(self.draft.listing_id)],
                         [first.path, second.path])
        self.assertEqual(gallery.primary_photo_paths()[self.draft.listing_id], first.path)

    def test_one_to_five_photos_and_no_more(self):
        for i in range(MAX_PHOTOS):
            self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture(f"{i}.jpg"))
        self.assertEqual(len(self.service.photos(self.ana.id, self.draft.listing_id)), 5)
        with self.assertRaises(PhotoError) as ctx:
            self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("6.jpg"))
        self.assertIn("at most 5", str(ctx.exception))
        self.assertEqual(len(self.photo_rows()), 5)
        self.assertEqual(len(list((self.photos_dir / self.draft.listing_id).iterdir())), 5)

    def test_exactly_one_primary_and_it_can_be_changed(self):
        a = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("a.jpg"))
        b = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("b.jpg"))
        c = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("c.jpg"))
        self.assertEqual([r["is_primary"] for r in self.photo_rows()], [1, 0, 0])
        self.service.set_primary(self.ana.id, self.draft.listing_id, c.photo_id)
        photos = self.service.photos(self.ana.id, self.draft.listing_id)
        self.assertEqual([p.photo_id for p in photos], [c.photo_id, a.photo_id, b.photo_id])
        self.assertEqual(sum(r["is_primary"] for r in self.photo_rows()), 1)
        with self.assertRaises(PhotoError):
            self.service.set_primary(self.ana.id, self.draft.listing_id, 9999)

    def test_removing_deletes_the_row_and_the_file_and_promotes_the_next_photo(self):
        a = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("a.jpg"))
        b = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("b.jpg"))
        self.service.remove_photo(self.ana.id, self.draft.listing_id, a.photo_id)
        self.assertFalse(Path(a.path).exists())
        self.assertTrue(Path(b.path).exists())
        rows = self.photo_rows()
        self.assertEqual([(r["photo_id"], r["is_primary"]) for r in rows], [(b.photo_id, 1)])
        self.service.remove_photo(self.ana.id, self.draft.listing_id, b.photo_id)
        self.assertEqual(self.photo_rows(), [])
        self.assertFalse(self.service.has_photo(self.ana.id, self.draft.listing_id))
        with self.assertRaises(PhotoError):
            self.service.remove_photo(self.ana.id, self.draft.listing_id, b.photo_id)

    def test_removing_a_non_primary_photo_keeps_the_primary(self):
        a = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("a.jpg"))
        b = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("b.jpg"))
        self.service.remove_photo(self.ana.id, self.draft.listing_id, b.photo_id)
        self.assertEqual([p.photo_id for p in self.service.photos(self.ana.id, self.draft.listing_id)],
                         [a.photo_id])
        self.assertTrue(self.service.photos(self.ana.id, self.draft.listing_id)[0].is_primary)

    def test_a_removed_slot_can_be_refilled(self):
        added = [self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture(f"{i}.jpg"))
                 for i in range(5)]
        self.service.remove_photo(self.ana.id, self.draft.listing_id, added[2].photo_id)
        self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("new.jpg"))
        self.assertEqual(len(self.photo_rows()), 5)

    def test_bad_files_are_refused_and_leave_nothing_behind(self):
        cases = [(self.picture("doc.txt"), "not supported"), (self.picture("x.gif"), "not supported"),
                 (self.picture("empty.jpg", b""), "empty"), ("", "Choose a photo"),
                 (str(self.src / "missing.jpg"), "could not be opened")]
        for path, text in cases:
            with self.assertRaises(PhotoError) as ctx:
                self.service.add_photo(self.ana.id, self.draft.listing_id, path)
            self.assertIn(text, str(ctx.exception))
        self.assertEqual(self.photo_rows(), [])
        self.assertFalse((self.photos_dir / self.draft.listing_id).exists()
                         and any((self.photos_dir / self.draft.listing_id).iterdir()))

    def test_oversized_files_are_refused(self):
        import app.owner_listing_photos as module
        original = module.MAX_FILE_BYTES
        module.MAX_FILE_BYTES = 10
        try:
            with self.assertRaises(PhotoError) as ctx:
                self.service.add_photo(self.ana.id, self.draft.listing_id,
                                       self.picture("big.jpg", b"x" * 11))
        finally:
            module.MAX_FILE_BYTES = original
        self.assertIn("too large", str(ctx.exception))
        self.assertEqual(self.photo_rows(), [])

    def test_an_unreadable_picture_is_refused_and_its_file_is_cleaned_up(self):
        def failing(source, base):
            Path(base + ".jpg").write_bytes(b"half")
            raise PhotoError("That file is not a readable picture.")
        service = OwnerListingPhotoService(self.db, self.listings, self.photos_dir,
                                           image_processor=failing)
        with self.assertRaises(PhotoError):
            service.add_photo(self.ana.id, self.draft.listing_id, self.picture())
        self.assertEqual(self.photo_rows(), [])

    def test_a_database_failure_removes_the_new_file(self):
        class Broken(PhotoService):
            def add_photo(self, *args, **kwargs):
                raise PhotoError("Could not save the photo. Nothing was changed.")
        service = OwnerListingPhotoService(self.db, self.listings, self.photos_dir,
                                           image_processor=fake_process)
        service._photos = Broken(self.db, self.photos_dir)
        with self.assertRaises(PhotoError):
            service.add_photo(self.ana.id, self.draft.listing_id, self.picture())
        folder = self.photos_dir / self.draft.listing_id
        self.assertEqual(list(folder.iterdir()) if folder.exists() else [], [])

    def test_only_the_owner_can_change_photos(self):
        photo = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture())
        for call in (
            lambda: self.service.add_photo(self.ben.id, self.draft.listing_id, self.picture("b.jpg")),
            lambda: self.service.add_photo(self.cai.id, self.draft.listing_id, self.picture("c.jpg")),
            lambda: self.service.remove_photo(self.ben.id, self.draft.listing_id, photo.photo_id),
            lambda: self.service.set_primary(self.ben.id, self.draft.listing_id, photo.photo_id),
            lambda: self.service.photos(self.ben.id, self.draft.listing_id),
        ):
            with self.assertRaises(PhotoError):
                call()
        self.assertEqual(len(self.photo_rows()), 1)
        self.assertTrue(Path(photo.path).exists())

    def test_a_photo_id_of_another_listing_cannot_be_removed_through_mine(self):
        mine = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture("m.jpg"))
        other = self.listings.create_draft(self.ana.id, good(title="Soldering kit"))
        theirs = self.service.add_photo(self.ana.id, other.listing_id, self.picture("o.jpg"))
        with self.assertRaises(PhotoError):
            self.service.remove_photo(self.ana.id, self.draft.listing_id, theirs.photo_id)
        with self.assertRaises(PhotoError):
            self.service.set_primary(self.ana.id, self.draft.listing_id, theirs.photo_id)
        self.assertTrue(Path(theirs.path).exists())
        self.assertTrue(Path(mine.path).exists())

    def test_withdrawn_approval_blocks_photo_changes(self):
        application = self.rows("SELECT application_id FROM student_owner_applications "
                                "WHERE student_id = ?", (self.ana.id,))[0]["application_id"]
        self.set_status(application, "Rejected")
        with self.assertRaises(PhotoError):
            self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture())

    def test_photos_persist_across_a_restart(self):
        photo = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture())
        again = OwnerListingPhotoService(self.db, OwnerListingService(
            self.db, self.workspaces, CATEGORIES), self.photos_dir, image_processor=fake_process)
        self.assertEqual([p.path for p in again.photos(self.ana.id, self.draft.listing_id)],
                         [photo.path])

    def test_a_missing_file_is_skipped_not_fatal(self):
        photo = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture())
        os.remove(photo.path)
        self.assertEqual(self.service.photos(self.ana.id, self.draft.listing_id), [])
        self.assertEqual(len(self.photo_rows()), 1)

    def test_counts_and_primary_paths_for_my_listings(self):
        other = self.listings.create_draft(self.ana.id, good(title="Soldering kit"))
        photo = self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture())
        self.assertEqual(self.service.counts(self.ana.id),
                         {self.draft.listing_id: 1, other.listing_id: 0})
        self.assertEqual(self.service.primary_paths(self.ana.id), {self.draft.listing_id: photo.path})
        self.assertEqual(self.service.primary_paths(self.ben.id), {})

    def test_delete_never_touches_files_outside_the_photos_folder(self):
        outside = Path(self.tmp.name) / "precious.jpg"
        outside.write_bytes(b"keep me")
        self.service._delete_file(outside)
        self.assertTrue(outside.exists())

    def test_photos_do_not_change_the_draft_or_its_schedule(self):
        self.listings.save_availability(self.ana.id, self.draft.listing_id, WEEKDAYS)
        self.service.add_photo(self.ana.id, self.draft.listing_id, self.picture())
        self.assertEqual(self.listings.get(self.ana.id, self.draft.listing_id).title, good()["title"])
        self.assertEqual(self.listings.get_availability(
            self.ana.id, self.draft.listing_id).as_dict(), WEEKDAYS)


# ======================================================================
# 4. The previous step still works (drafts, access)
# ======================================================================
class PreviousStepTests(Base):
    def test_create_and_update_still_work_with_the_old_two_argument_calls(self):
        self.approve(self.ana)
        draft = self.listings.create_draft(self.ana.id, good())
        updated = self.listings.update_draft(self.ana.id, draft.listing_id, good(title="New name"))
        self.assertEqual(updated.title, "New name")
        self.assertEqual(self.listings.list_drafts(self.ana.id)[0].listing_id, draft.listing_id)


# ======================================================================
# 5-6. With Qt: real pictures, the editor widgets and the dashboard
# ======================================================================
def make_picture(path, width, height, color=0xFF3366CC, fmt="PNG", alpha=False):
    from PySide6.QtGui import QImage
    image = QImage(width, height, QImage.Format_ARGB32 if alpha else QImage.Format_RGB32)
    image.fill(color)
    assert image.save(str(path), fmt), path
    return str(path)


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class RealPictureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def process(self, source, name="out"):
        from app.owner_listing_photos import process_image
        return Path(process_image(source, str(self.dir / name)))

    def test_large_photos_are_shrunk_without_stretching(self):
        from PySide6.QtGui import QImage
        out = self.process(make_picture(self.dir / "big.png", 3200, 1600))
        image = QImage(str(out))
        self.assertEqual((image.width(), image.height()), (1600, 800))   # same 2:1 shape
        self.assertEqual(out.suffix, ".jpg")

    def test_small_photos_are_kept_at_their_size(self):
        from PySide6.QtGui import QImage
        out = self.process(make_picture(self.dir / "s.png", 300, 200))
        self.assertEqual((QImage(str(out)).width(), QImage(str(out)).height()), (300, 200))

    def test_transparent_pictures_stay_png(self):
        out = self.process(make_picture(self.dir / "t.png", 200, 200, 0x80FF0000, alpha=True))
        self.assertEqual(out.suffix, ".png")

    def test_jpg_and_png_are_accepted_and_rubbish_is_refused(self):
        make_picture(self.dir / "p.jpg", 200, 200, fmt="JPG")
        self.assertTrue(self.process(str(self.dir / "p.jpg"), "o1").is_file())
        (self.dir / "fake.jpg").write_bytes(b"this is not a picture at all")
        with self.assertRaises(PhotoError):
            self.process(str(self.dir / "fake.jpg"), "o2")
        with self.assertRaises(PhotoError):    # too small
            self.process(make_picture(self.dir / "tiny.png", 20, 20), "o3")

    def test_service_end_to_end_with_the_real_processor(self):
        base = PhotoBase("setUp")
        # a tiny harness so we do not duplicate the setup code
        PhotoBase.setUp(base)
        base.addCleanup = self.addCleanup
        service = OwnerListingPhotoService(base.db, base.listings, base.photos_dir)
        photo = service.add_photo(base.ana.id, base.draft.listing_id,
                                  make_picture(self.dir / "real.png", 2400, 1200))
        self.assertTrue(Path(photo.path).is_file())
        self.assertTrue(photo.path.endswith(".jpg"))
        gallery = PhotoService(base.db, base.photos_dir)
        self.assertEqual([p.path for p in gallery.photos_for(base.draft.listing_id)], [photo.path])
        base.tmp.cleanup()


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class EditorWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def form(self):
        from app.owner_listing_service import CONDITIONS
        from app.owner_workspace import OwnerListingFormPage
        form = OwnerListingFormPage(CATEGORIES, CONDITIONS)
        self.addCleanup(form.deleteLater)
        form.start_new()
        return form

    def pics(self, count):
        return [make_picture(self.dir / f"p{i}.png", 200, 150) for i in range(count)]

    def test_availability_editor_shows_and_returns_a_schedule(self):
        editor = self.form().availability_editor
        self.assertEqual(editor.schedule(), {})
        self.assertIn("No pickup days", editor.summary_label.text())
        editor.set_schedule(AvailabilitySchedule.from_dict(WEEKDAYS))
        self.assertEqual(editor.schedule(), WEEKDAYS)
        self.assertEqual(editor.summary_label.text(), "Mon-Fri · 9:00 AM - 5:00 PM")
        self.assertTrue(editor.start_combos[0].isEnabled())
        self.assertFalse(editor.start_combos[6].isEnabled())

    def test_ticking_days_and_changing_hours_updates_the_schedule(self):
        editor = self.form().availability_editor
        changes = []
        editor.changed.connect(lambda: changes.append(1))
        editor.day_boxes[1].setChecked(True)
        self.assertEqual(editor.schedule(), {1: [(540, 1020)]})            # default 9-5
        editor._set_minute(editor.start_combos[1], 600)
        editor._set_minute(editor.end_combos[1], 720)
        editor.day_boxes[3].setChecked(True)                                # copies Tuesday's hours
        self.assertEqual(editor.schedule(), {1: [(600, 720)], 3: [(600, 720)]})
        editor.day_boxes[1].setChecked(False)
        self.assertEqual(editor.schedule(), {3: [(600, 720)]})
        self.assertGreaterEqual(len(changes), 3)

    def test_a_range_that_would_end_before_it_starts_is_nudged_not_broken(self):
        editor = self.form().availability_editor
        editor.day_boxes[0].setChecked(True)
        editor._set_minute(editor.end_combos[0], 600)                       # ends 10:00
        editor.start_combos[0].setCurrentIndex(editor.start_combos[0].findData(660))   # start 11:00
        (start, end), = editor.schedule()[0]
        self.assertLess(start, end)

    def test_presets(self):
        editor = self.form().availability_editor
        editor.weekdays_button.click()
        self.assertEqual(sorted(editor.schedule()), [0, 1, 2, 3, 4])
        editor.every_day_button.click()
        self.assertEqual(sorted(editor.schedule()), list(range(7)))
        editor.clear_button.click()
        self.assertEqual(editor.schedule(), {})

    def test_loading_a_schedule_does_not_signal_and_extra_windows_are_kept(self):
        editor = self.form().availability_editor
        changes = []
        editor.changed.connect(lambda: changes.append(1))
        two = AvailabilitySchedule.from_dict({0: [(540, 660), (780, 900)]})
        editor.set_schedule(two)
        self.assertEqual(changes, [])
        self.assertEqual(editor.schedule(), {0: [(540, 660), (780, 900)]})   # nothing lost

    def test_an_unusual_saved_time_is_shown_not_dropped(self):
        editor = self.form().availability_editor
        editor.set_schedule({2: [(545, 1000)]})
        self.assertEqual(editor.schedule(), {2: [(545, 1000)]})

    def test_photo_manager_for_a_new_listing_stages_photos_in_the_form(self):
        form = self.form()
        manager = form.photos
        self.assertEqual(manager.count, 0)
        self.assertTrue(manager.preview.has_picture is False)
        first, second, third = self.pics(3)
        form._on_photos_add([first, second, third])
        self.assertEqual(manager.count, 3)
        self.assertEqual(manager.primary_key, first)
        self.assertTrue(manager.preview.has_picture)
        manager.select(third)
        manager.primary_button.click()
        self.assertEqual(manager.primary_key, third)
        self.assertEqual(form.staged_photos()[0], third)
        self.assertFalse(manager.primary_button.isEnabled())               # already primary
        manager.remove_button.click()                                       # removes the selected (third)
        self.assertEqual(manager.count, 2)
        self.assertEqual(form.staged_photos(), [first, second])
        self.assertEqual(manager.primary_key, first)

    def test_staging_respects_the_limit_and_the_file_types(self):
        form = self.form()
        form._on_photos_add(self.pics(5))
        self.assertEqual(form.photos.count, 5)
        self.assertFalse(form.photos.add_button.isEnabled())
        form._on_photos_add([make_picture(self.dir / "six.png", 100, 100)])
        self.assertEqual(form.photos.count, 5)
        self.assertIn("at most 5", form.photos.note.text())
        (self.dir / "notes.txt").write_text("hi")
        form.start_new()
        form._on_photos_add([str(self.dir / "notes.txt")])
        self.assertEqual(form.photos.count, 0)
        self.assertIn("JPG, PNG or WEBP", form.photos.note.text())
        (self.dir / "fake.png").write_bytes(b"not an image")
        form._on_photos_add([str(self.dir / "fake.png")])
        self.assertEqual(form.photos.count, 0)

    def test_the_form_resets_for_the_next_listing(self):
        form = self.form()
        form._on_photos_add(self.pics(2))
        form.availability_editor.weekdays_button.click()
        form.start_new()
        self.assertEqual(form.staged_photos(), [])
        self.assertEqual(form.photos.count, 0)
        self.assertEqual(form.availability(), {})

    def test_saved_listing_stages_photo_changes_until_save(self):
        from types import SimpleNamespace
        form = self.form()
        listing = SimpleNamespace(
            listing_id="LD-1", title="Calc", category="Mathematics", condition="Good",
            description="A calculator", max_borrow_days=2, extra_rules="")
        photos = self.pics(2)
        form.load(listing, [(10, photos[0], True), (11, photos[1], False)], WEEKDAYS)
        self.assertEqual(form.photos.count, 2)
        self.assertEqual(form.availability(), WEEKDAYS)
        seen = []
        form.photo_add_requested.connect(lambda *a: seen.append(("add",) + a))
        form.photo_remove_requested.connect(lambda *a: seen.append(("remove",) + a))
        form.photo_primary_requested.connect(lambda *a: seen.append(("primary",) + a))
        added = self.pics(1)[0]
        form._on_photos_add([added])
        form.photos.select(11)
        form.photos.primary_button.click()
        form.photos.remove_button.click()
        self.assertEqual(seen, [])
        self.assertEqual(form.photos.count, 2)
        self.assertEqual(form.photo_change_plan(),
                         {"add": [added], "remove": [11], "primary": 10})

    def test_an_unreadable_saved_schedule_is_never_overwritten_by_an_untouched_form(self):
        from types import SimpleNamespace
        form = self.form()
        listing = SimpleNamespace(
            listing_id="LD-1", title="Calc", category="Mathematics", condition="Good",
            description="A calculator", max_borrow_days=2, extra_rules="")
        form.load(listing, [], None)                    # schedule could not be loaded
        self.assertIsNone(form.availability())          # -> the dashboard leaves it alone
        form.availability_editor.clear_button.click()
        self.assertEqual(form.availability(), {})
        self.assertTrue(form.has_unsaved_changes)       # an explicit clear is not "untouched"
        form.load(listing, [], None)
        form.availability_editor.weekdays_button.click()  # ...unless the owner edits it
        self.assertEqual(sorted(form.availability()), [0, 1, 2, 3, 4])
        form.load(listing, [], AvailabilitySchedule.empty())
        self.assertEqual(form.availability(), {})       # a known empty schedule is saved as empty

    def test_listing_card_shows_the_thumbnail_and_the_pickup_line(self):
        from types import SimpleNamespace
        from app.owner_workspace import OwnerListingsPage
        page = OwnerListingsPage()
        self.addCleanup(page.deleteLater)
        listing = SimpleNamespace(
            listing_id="LD-1", title="Calc", category="Mathematics", condition="Good",
            description="A calculator", max_borrow_days=2)
        picture = self.pics(1)[0]
        page.set_listings([listing], {"LD-1": picture},
                          {"LD-1": AvailabilitySchedule.from_dict(WEEKDAYS)})
        card = page.cards[0]
        self.assertTrue(card.has_photo)
        self.assertIn("Mon-Fri", card.pickup_label.text())
        page.set_listings([listing])
        self.assertFalse(page.cards[0].has_photo)
        self.assertIn("not set", page.cards[0].pickup_label.text())


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DashboardFlowTests(Base):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def build(self, student):
        from app.dashboard_screen import StudentDashboard
        from app.request_service import RequestService
        from app.sample_data import build_empty_data
        dash = StudentDashboard(
            build_empty_data(student.full_name), signed_in_email=student.email,
            student_id=student.id, request_service=RequestService(self.db))
        self.addCleanup(dash.deleteLater)
        return dash

    def owner_dash(self, student=None):
        student = student or self.ana
        self.approve(student)
        dash = self.build(student)
        self.assertTrue(dash.switch_workspace("student_owner"))
        return dash

    def fill(self, page, **changes):
        data = good(**changes)
        page.title_input.setText(data["title"])
        page.category_combo.setCurrentText(data["category"])
        page.condition_combo.setCurrentText(data["condition"])
        page.description_input.setPlainText(data["description"])
        page.days_input.setValue(data["max_borrow_days"])
        page.rules_input.setPlainText(data["extra_rules"])

    def pic(self, name, w=240, h=160):
        folder = Path(self.tmp.name) / "pics"
        folder.mkdir(exist_ok=True)
        return make_picture(folder / name, w, h)

    def slots(self):
        return self.rows("SELECT * FROM listing_availability")

    def test_new_listing_with_photos_and_availability_is_saved_together(self):
        dash = self.owner_dash()
        listings, form = dash.owner_listings_page, dash.owner_form_page
        listings.empty_add_button.click()
        self.fill(form)
        form._on_photos_add([self.pic("a.png"), self.pic("b.png")])
        form.availability_editor.weekdays_button.click()
        form.save_button.click()
        self.assertIs(dash.content_stack.currentWidget(), listings)
        self.assertEqual(len(self.rows()), 1)
        listing_id = self.rows()[0]["listing_id"]
        self.assertEqual(len(self.slots()), 5)
        photo_rows = self.rows("SELECT * FROM listing_photos ORDER BY photo_id")
        self.assertEqual([r["listing_key"] for r in photo_rows], [listing_id, listing_id])
        self.assertEqual([r["is_primary"] for r in photo_rows], [1, 0])
        card = listings.cards[0]
        self.assertTrue(card.has_photo)
        self.assertIn("Mon-Fri", card.pickup_label.text())
        # photo files sit under the app's photos folder (here: beside the temporary database)
        self.assertTrue((Path(self.db).parent / "photos" / listing_id).is_dir())

    def test_reopening_shows_saved_photos_and_schedule_and_edits_apply(self):
        dash = self.owner_dash()
        listings, form = dash.owner_listings_page, dash.owner_form_page
        listings.empty_add_button.click()
        self.fill(form)
        form._on_photos_add([self.pic("a.png"), self.pic("b.png")])
        form.availability_editor.weekdays_button.click()
        form.save_button.click()
        listings.cards[0].edit_button.click()
        self.assertTrue(form.is_editing)
        self.assertEqual(form.photos.count, 2)
        self.assertEqual(sorted(form.availability()), [0, 1, 2, 3, 4])
        # change the schedule (any time) and save
        form.availability_editor.clear_button.click()
        form.availability_editor.day_boxes[5].setChecked(True)
        form.save_button.click()
        self.assertEqual([(r["weekday"]) for r in self.slots()], [5])
        self.assertEqual(len(self.rows()), 1)

    def test_photo_changes_on_a_saved_listing_are_staged_until_save(self):
        dash = self.owner_dash()
        listings, form = dash.owner_listings_page, dash.owner_form_page
        listings.empty_add_button.click()
        self.fill(form)
        form.save_button.click()
        listings.cards[0].edit_button.click()
        form._on_photos_add([self.pic("a.png"), self.pic("b.png"), self.pic("c.png")])
        self.assertEqual(len(self.rows("SELECT * FROM listing_photos")), 0)
        self.assertEqual(form.photos.count, 3)
        keys = form.photos.keys
        form.photos.select(keys[2])
        form.photos.primary_button.click()
        self.assertEqual(form.photos.primary_key, keys[2])
        self.assertEqual(len(self.rows("SELECT * FROM listing_photos")), 0)
        form.photos.remove_button.click()                        # removes the selected photo
        self.assertEqual(form.photos.count, 2)
        self.assertEqual(len(self.rows("SELECT * FROM listing_photos")), 0)
        form.save_button.click()
        self.assertEqual(len(self.rows("SELECT * FROM listing_photos")), 2)
        self.assertEqual(sum(r["is_primary"] for r in self.rows("SELECT * FROM listing_photos")), 1)
        self.assertEqual(len(list((Path(self.db).parent / "photos").rglob("p_*"))), 2)

    def test_a_bad_photo_shows_a_message_and_changes_nothing(self):
        dash = self.owner_dash()
        listings, form = dash.owner_listings_page, dash.owner_form_page
        listings.empty_add_button.click()
        self.fill(form)
        form.save_button.click()
        listings.cards[0].edit_button.click()
        bad = Path(self.tmp.name) / "fake.jpg"
        bad.write_bytes(b"not a picture")
        form._on_photos_add([str(bad)])
        self.assertEqual(self.rows("SELECT * FROM listing_photos"), [])
        self.assertFalse(form.photos.note.isHidden())
        self.assertTrue(form.photos.note.property("error"))

    def test_schedule_and_photos_come_back_after_a_restart_and_stay_private(self):
        dash = self.owner_dash()
        dash.owner_listings_page.empty_add_button.click()
        self.fill(dash.owner_form_page)
        dash.owner_form_page._on_photos_add([self.pic("a.png")])
        dash.owner_form_page.availability_editor.every_day_button.click()
        dash.owner_form_page.save_button.click()
        again = self.build(self.ana)
        again.switch_workspace("student_owner")
        again.owner_rail.buttons["my_listings"].click()
        card = again.owner_listings_page.cards[0]
        self.assertTrue(card.has_photo)
        self.assertIn("Every day", card.pickup_label.text())
        other = self.owner_dash(self.ben)
        other.owner_rail.buttons["my_listings"].click()
        self.assertEqual(other.owner_listings_page.cards, [])

    def test_a_student_who_is_not_an_owner_cannot_change_photos(self):
        dash = self.build(self.cai)
        dash._on_listing_photos_add("LD-NOPE", [self.pic("a.png")])
        dash._on_listing_photo_remove("LD-NOPE", 1)
        self.assertEqual(self.rows("SELECT * FROM listing_photos"), [])

    def test_invalid_schedule_keeps_the_form_open(self):
        dash = self.owner_dash()
        form = dash.owner_form_page
        dash.owner_listings_page.empty_add_button.click()
        self.fill(form)
        form.availability = lambda: {0: [(700, 600)]}     # something the editor can never make
        form.save_button.click()
        self.assertIs(dash.content_stack.currentWidget(), form)
        self.assertFalse(form.message.isHidden())
        self.assertEqual(self.rows(), [])

    def test_student_workspace_and_catalog_gallery_still_work(self):
        dash = self.owner_dash()
        dash.owner_listings_page.empty_add_button.click()
        self.fill(dash.owner_form_page)
        dash.owner_form_page._on_photos_add([self.pic("a.png")])
        dash.owner_form_page.save_button.click()
        dash.owner_rail.buttons["switch"].click()
        dash.go_to("catalog")
        self.assertIs(dash.content_stack.currentWidget(), dash.catalog_page)
        dash._refresh_catalog_photos()    # reads every listing_photos row; must not fail


if __name__ == "__main__":
    unittest.main()
