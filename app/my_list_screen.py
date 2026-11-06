"""KitLend My List screen (UI only - sample data, no database, no real requests).

What this file contains, from top to bottom:
  1. SAMPLE DATA      - a few saved items, picked from the Catalog's own sample items
  2. BORROWING LIMITS - SAMPLE-ONLY maximum borrowing days (not real school policy)
  3. REQUEST DRAFTS   - the RequestDraft dataclass + small validation helpers
  3b. PICKUP AVAILABILITY - SAMPLE per-lender/admin pickup days + hours, and the
                        plain-Python scheduling rules (next free slot, 30-minute
                        times, explanations). No Qt in this part.
  4. SMALL HELPERS    - who approves an item, plus the little icon badge
  5. ROW WIDGETS      - one saved-item row, calendar popup, one request-form row per item
  6. REQUEST DIALOG   - "Review your requests" form (pickup date + time + days per item)
  7. MY LIST SCREEN   - the whole screen that puts everything together
  8. STYLES (QSS)     - only the NEW My List styles; Catalog styles are reused

Borrowing policy (the request form only EXPLAINS it; nothing here enforces it):
  1. Submitting a request does not begin borrowing.
  2. Approval reserves the item.
  3. Approval does NOT start the borrowing countdown.
  4. The scheduled pickup does NOT start the countdown either.
  5. The lender/administrator manually confirms the physical handover.
  6. Only the ACTUAL confirmed pickup starts the countdown:
         Due Date = Actual Confirmed Pickup + Requested Borrowing Days
     (one borrowing day = 24 consecutive hours).
  So this file NEVER shows a due date: the item has not been collected yet.

Pickup scheduling (Step 7C.1): the student picks a preferred pickup DATE in a
calendar and a TIME from a dropdown of 30-minute slots. Only dates and times that
the responsible lender/administrator offers can be chosen, and each item uses its
OWN availability (a school pickup location's schedule, or one student lender's).
Pickup availability is separate from the borrowing-duration limits. The form
opens on the next valid slot, and everything is re-checked at confirmation.

One batch submission creates SEPARATE requests. Each item's lender or
administrator approves it on their own. One rejection does not cancel the others.

Both entry points use the SAME dialog (RequestPreviewDialog):
  - Catalog -> Request Now          (one item, opened by the preview runner)
  - My List -> Request Selected     (one or many items, opened in this file)
After the dialog is accepted, `dialog.drafts` holds the validated RequestDrafts.

Nothing here touches a database, logs anyone in, sends anything, or opens the
dashboard. Everything stays in memory.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QDateTime, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
    QPen,
    QPixmap,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QBoxLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# Reuse the Catalog's item model, sample items, pills and styles.
from app.header_style import HEADER_QSS, accent_html
from app.catalog_screen import (
    CATALOG_STYLESHEET,
    CATEGORY_BY_NAME,
    CURIOUS_MASCOT_PATH,
    HAPPY_MASCOT_PATH,
    KIND_ICONS,
    LIGHT_PERIWINKLE,
    MUTED_TEXT,
    SAMPLE_ITEMS,
    SOFT_LAVENDER,
    CatalogItem,
    ItemThumb,
    TagPill,
    _cover_tone,
)
from app.my_list_theme import MY_LIST_V2_STYLESHEET
from app.dashboard_widgets import ElidedLabel
from app.theme import CREAM, MINT, NAVY, PERIWINKLE, PINK

UNAVAILABLE_HINT = "Unavailable items can stay in your list, but can't be requested yet."
ERROR_RED = "#C2386B"  # same red the Catalog uses for "unavailable"


# ======================================================================
# 1. SAMPLE DATA
# ======================================================================
# Titles of Catalog sample items that start out "saved". A mix of available,
# low-stock and unavailable items, from both school and students.
SAMPLE_SAVED_TITLES = (
    "Introduction to Algorithms (CLRS)",
    "Grokking Algorithms",
    "TI-84 Plus Graphing Calculator",      # unavailable (currently borrowed)
    "Arduino Uno Starter Kit",
    "Clean Code",                          # unavailable (currently borrowed)
    "Digital Multimeter",
)


def sample_saved_items() -> list:
    """Return the sample saved list (real CatalogItem objects from the Catalog)."""
    by_title = {item.title: item for item in SAMPLE_ITEMS}
    return [by_title[title] for title in SAMPLE_SAVED_TITLES if title in by_title]


# ======================================================================
# 2. BORROWING LIMITS - SAMPLE ONLY
# ======================================================================
# IMPORTANT: these numbers are made up so the preview can show different
# limits. They are NOT official school policy. Later, a database will store
# the real maximum that each lender or school administrator sets per item.
#
# CatalogItem has no "max days" field (and we must not change it), so we look
# the limit up by the item's title. Titles are unique in the sample data.
SAMPLE_MAX_BORROW_DAYS = {
    "Calculus: Early Transcendentals": 14,
    "Discrete Mathematics and Its Applications": 5,
    "Introduction to Algorithms (CLRS)": 3,          # high demand, short loan
    "Data Structures and Algorithms in Python": 10,
    "Python Crash Course": 14,
    "Grokking Algorithms": 7,
    "Casio fx-991EX Scientific Calculator": 1,       # exam-day gear
    "Arduino Uno Starter Kit": 5,
    "Digital Multimeter": 2,
    "Soldering Iron Kit (60W)": 1,
    "Digital Vernier Caliper": 2,
    "Power Bank (10,000 mAh)": 2,
}

# Fallback so EVERY sample item still gets a limit, by kind of item.
SAMPLE_MAX_DAYS_BY_KIND = {"Book": 7, "Gadget": 3, "Tool": 2, "Accessory": 3}
SAMPLE_MAX_DAYS_FALLBACK = 3  # for any kind not listed above


def get_max_borrow_days(item: CatalogItem) -> int:
    """Return a saved item limit when present, otherwise its sample display value."""
    saved_days = getattr(item, "max_borrow_days", None)
    if isinstance(saved_days, int) and not isinstance(saved_days, bool) and saved_days >= 1:
        return saved_days
    days = SAMPLE_MAX_BORROW_DAYS.get(item.title)
    if days is None:
        days = SAMPLE_MAX_DAYS_BY_KIND.get(item.kind, SAMPLE_MAX_DAYS_FALLBACK)
    return max(1, days)


# ======================================================================
# 3. REQUEST DRAFTS + VALIDATION HELPERS (plain Python - easy to test)
# ======================================================================
def plural(count: int, word: str) -> str:
    """plural(1, 'day') -> '1 day'   plural(3, 'day') -> '3 days'"""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def local_now() -> datetime:
    """The current time as a timezone-aware datetime in the computer's timezone."""
    return datetime.now().astimezone()


def local_timezone_label() -> str:
    """Something like 'UTC+08:00' (shown so students know which clock is meant)."""
    offset = local_now().strftime("%z")  # e.g. '+0800'
    if len(offset) != 5:
        return "your local time"
    return f"UTC{offset[:3]}:{offset[3:]}"


def format_pickup(moment: datetime) -> str:
    """Friendly text like 'Mon, Oct 19, 2026 at 2:30 PM'."""
    hour = moment.hour % 12 or 12
    am_pm = "AM" if moment.hour < 12 else "PM"
    return f"{moment:%a, %b} {moment.day}, {moment.year} at {hour}:{moment.minute:02d} {am_pm}"


def qdatetime_to_local_aware(value: QDateTime) -> datetime:
    """Turn the picker's QDateTime into a timezone-aware local Python datetime."""
    # toPython() may give a "naive" datetime (no timezone). astimezone() treats
    # a naive one as local time and attaches the local timezone to it.
    return value.toPython().astimezone()


def suggested_pickup(now: datetime) -> datetime:
    """Older generic suggestion (an hour from now, on a :00 or :30).

    The request form no longer uses it - it opens on the lender's next available
    slot instead (see PickupAvailability.next_available_slot). Kept so older
    code that imports it keeps working.
    """
    start = now.replace(second=0, microsecond=0) + timedelta(hours=1)
    extra_minutes = (30 - start.minute % 30) % 30
    return start + timedelta(minutes=extra_minutes)


def validate_pickup(pickup_at: datetime, now: datetime | None = None) -> str:
    """Check a preferred pickup moment. Returns "" if fine, else what is wrong.

    Later today is fine if the time is still ahead. Any past date or time is not.
    """
    if pickup_at.tzinfo is None:
        return "The pickup time is missing its time zone."
    now = now or local_now()
    pickup_local = pickup_at.astimezone(now.tzinfo)
    if pickup_local.date() < now.date():
        return "That date has already passed. Please choose today or a later date."
    if pickup_local <= now:
        return "That time has already passed. Please choose a time that is still ahead."
    return ""


def validate_days(days, max_days: int) -> str:
    """Check the requested borrowing days. Returns "" if fine, else what is wrong."""
    if isinstance(days, bool) or not isinstance(days, int):
        return "Please enter a whole number of days."
    if days < 1:
        return "Please borrow for at least 1 day."
    if days > max_days:
        return f"This item can be borrowed for at most {plural(max_days, 'day')}."
    return ""


@dataclass(frozen=True)
class RequestDraft:
    """One prepared (NOT submitted) borrowing request for ONE item.

    The student's pickup time is only a PREFERENCE. The borrowing period starts
    later, when the lender/admin confirms the real handover.
    """

    item: CatalogItem
    pickup_at: datetime   # preferred pickup, timezone-aware (local time zone)
    days: int             # requested borrowing days (1 .. max_days)
    max_days: int         # this item's maximum (sample value in this preview)

    @property
    def pickup_text(self) -> str:
        return format_pickup(self.pickup_at)

    @property
    def days_text(self) -> str:
        return plural(self.days, "day")


# ======================================================================
# 3b. PICKUP AVAILABILITY + SCHEDULING (plain Python - no Qt, easy to test)
# ======================================================================
# "When can this lender/administrator hand the item over?" is answered here.
# It is completely separate from "how long may the item be borrowed?" (the
# sample borrowing limits in section 2): changing one never affects the other.
#
# Every responsible person (a school pickup location or a student lender) has
# their OWN PickupAvailability. Nothing assumes weekends are closed, and nothing
# assumes two lenders share a schedule. The weekly hours are plain data
# ({weekday: windows}), so a future settings screen / database row can build
# the same object without touching any of the code below.
#
# Pickup times are offered in 30-minute steps. A window such as 9:00-16:00
# offers 9:00 AM ... 3:30 PM (the last 30-minute slot must END by 4:00 PM).
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_ABBREVIATIONS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
PICKUP_SLOT_MINUTES = 30
PICKUP_HORIZON_DAYS = 60   # how far ahead a pickup can be requested


def format_minute(minute: int) -> str:
    """570 -> '9:30 AM' (minutes since midnight)."""
    hour24, minutes = divmod(minute, 60)
    hour = hour24 % 12 or 12
    return f"{hour}:{minutes:02d} {'AM' if hour24 < 12 else 'PM'}"


def format_day(day: date) -> str:
    """Friendly text like 'Mon, Oct 19, 2026'."""
    return f"{day:%a, %b} {day.day}, {day.year}"


def _minute_of(value) -> int:
    """Minutes since midnight from a datetime.time, 'HH:MM' text or a whole number."""
    if isinstance(value, time):
        minute = value.hour * 60 + value.minute
    elif isinstance(value, int) and not isinstance(value, bool):
        minute = value
    else:
        try:
            hours_text, minutes_text = str(value).strip().split(":")
            minute = int(hours_text) * 60 + int(minutes_text)
        except ValueError:
            raise ValueError(f"Not a valid clock time: {value!r}") from None
    if not 0 <= minute <= 24 * 60:
        raise ValueError(f"Clock time out of range: {value!r}")
    return minute


def _clean_windows(windows) -> tuple:
    """Validate (start, end) pairs, sort them and merge overlaps -> ((start_min, end_min), ...)."""
    pairs = []
    for start, end in windows:
        start_minute, end_minute = _minute_of(start), _minute_of(end)
        if end_minute <= start_minute:
            raise ValueError("A pickup window must end after it starts.")
        pairs.append((start_minute, end_minute))
    pairs.sort()
    merged = []
    for start_minute, end_minute in pairs:
        if merged and start_minute <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end_minute))
        else:
            merged.append((start_minute, end_minute))
    return tuple(merged)


def _weekday_index(name: str) -> int:
    try:
        return WEEKDAY_ABBREVIATIONS.index(name.strip()[:3].title())
    except ValueError:
        raise ValueError(f"Unknown weekday: {name!r}") from None


def parse_weekly_hours(*rules) -> dict:
    """Readable way to write a weekly schedule.

    Each rule is (days, window, window, ...):
        parse_weekly_hours(("Mon-Fri", "9:00-12:00", "13:00-16:00"), ("Sat", "10:00-14:00"))
    `days` may be a range ("Mon-Fri"), a list ("Tue,Thu") or both ("Mon-Wed,Sat").
    Weekdays that are not mentioned are unavailable.
    """
    weekly = {}
    for days_text, *window_texts in rules:
        weekdays = []
        for token in days_text.split(","):
            first, dash, last = token.partition("-")
            low = _weekday_index(first)
            high = _weekday_index(last) if dash else low
            if high < low:
                raise ValueError(f"Day range runs backwards: {token!r}")
            weekdays.extend(range(low, high + 1))
        windows = []
        for text in window_texts:
            start, _, end = text.partition("-")
            windows.append((start, end))
        for weekday in weekdays:
            weekly.setdefault(weekday, []).extend(windows)
    return weekly


def _days_label(weekdays) -> str:
    """[0,1,2,3,4] -> 'Mon-Fri'   [1,3] -> 'Tue, Thu'"""
    runs, current = [], []
    for weekday in sorted(weekdays):
        if current and weekday == current[-1] + 1:
            current.append(weekday)
        else:
            current = [weekday]
            runs.append(current)
    parts = []
    for run in runs:
        if len(run) >= 3:
            parts.append(f"{WEEKDAY_ABBREVIATIONS[run[0]]}–{WEEKDAY_ABBREVIATIONS[run[-1]]}")
        else:
            parts.extend(WEEKDAY_ABBREVIATIONS[weekday] for weekday in run)
    return ", ".join(parts)


def _windows_label(windows) -> str:
    """((540, 720), (780, 960)) -> '9:00 AM–12:00 PM & 1:00 PM–4:00 PM'"""
    return " & ".join(f"{format_minute(start)}–{format_minute(end)}" for start, end in windows)


class PickupAvailability:
    """When ONE lender or administrator can hand items over (their own settings).

    owner_label     who this is, used in messages ("Main Library", "Ana M.")
    weekly_hours    {weekday (0=Mon .. 6=Sun): [(start, end), ...]}; a missing or
                    empty weekday means "not available that day"
                    (use parse_weekly_hours for a readable way to build it)
    blocked_dates   optional specific dates that are closed (holidays, trips)
    slot_minutes    spacing of the pickup times that are offered
    horizon_days    how many days ahead a pickup may be requested
    """

    def __init__(self, owner_label, weekly_hours, *, blocked_dates=(),
                 slot_minutes=PICKUP_SLOT_MINUTES, horizon_days=PICKUP_HORIZON_DAYS):
        if slot_minutes < 1:
            raise ValueError("slot_minutes must be at least 1.")
        if horizon_days < 1:
            raise ValueError("horizon_days must be at least 1.")
        self._owner_label = owner_label
        self._slot_minutes = int(slot_minutes)
        self._horizon_days = int(horizon_days)
        self._blocked = frozenset(blocked_dates)

        self._hours = {}               # weekday -> ((start_min, end_min), ...)
        self._slots_by_weekday = {}    # weekday -> (minute, minute, ...) that can be offered
        for weekday, windows in dict(weekly_hours).items():
            if weekday not in range(7):
                raise ValueError(f"Weekday must be 0 (Mon) to 6 (Sun), not {weekday!r}.")
            cleaned = _clean_windows(windows)
            slots = []
            for start, end in cleaned:
                minute = start
                while minute + self._slot_minutes <= end:
                    slots.append(minute)
                    minute += self._slot_minutes
            if cleaned:
                self._hours[weekday] = cleaned
            if slots:
                self._slots_by_weekday[weekday] = tuple(slots)

    # ---------- plain facts ----------
    @property
    def owner_label(self) -> str:
        return self._owner_label

    @property
    def slot_minutes(self) -> int:
        return self._slot_minutes

    @property
    def horizon_days(self) -> int:
        return self._horizon_days

    @property
    def has_usable_slots(self) -> bool:
        """False when the settings can never produce a pickup time."""
        return bool(self._slots_by_weekday)

    @property
    def schedule_text(self) -> str:
        """Short summary such as 'Mon–Fri 9:00 AM–4:00 PM; Sat, Sun 10:00 AM–2:00 PM'."""
        if not self._slots_by_weekday:
            return "no pickup hours set"
        by_windows = {}
        for weekday in sorted(self._slots_by_weekday):
            by_windows.setdefault(self._hours[weekday], []).append(weekday)
        if len(by_windows) == 1 and len(next(iter(by_windows.values()))) == 7:
            return f"every day {_windows_label(next(iter(by_windows)))}"
        return "; ".join(
            f"{_days_label(weekdays)} {_windows_label(windows)}"
            for windows, weekdays in by_windows.items()
        )

    # ---------- slots ----------
    def last_day(self, now: datetime) -> date:
        return now.date() + timedelta(days=self._horizon_days)

    @staticmethod
    def slot_start(day: date, minute: int, tz) -> datetime:
        """The timezone-aware moment for `minute` (since midnight) on `day`."""
        return datetime.combine(day, time(minute // 60, minute % 60), tzinfo=tz)

    def is_open_on(self, day: date) -> bool:
        """Does this person offer pickup on that date at all (ignoring the clock)?"""
        return day not in self._blocked and day.weekday() in self._slots_by_weekday

    def minutes_on(self, day: date, now: datetime) -> list:
        """Pickup times (minutes since midnight) that can still be chosen on `day`."""
        today = now.date()
        if day < today or day > self.last_day(now) or not self.is_open_on(day):
            return []
        minutes = list(self._slots_by_weekday[day.weekday()])
        if day == today:   # later today is fine, as long as the slot is still ahead
            minutes = [m for m in minutes if self.slot_start(day, m, now.tzinfo) > now]
        return minutes

    def has_slots_on(self, day: date, now: datetime) -> bool:
        return bool(self.minutes_on(day, now))

    def next_available_slot(self, now: datetime):
        """The earliest still-bookable pickup moment, or None when there is none.

        Walks at most `horizon_days` + 1 dates (a few dozen cheap checks), so a
        schedule with no usable slots returns None quickly instead of looping.
        """
        if not self._slots_by_weekday:
            return None
        today = now.date()
        for offset in range(self._horizon_days + 1):
            day = today + timedelta(days=offset)
            minutes = self.minutes_on(day, now)
            if minutes:
                return self.slot_start(day, minutes[0], now.tzinfo)
        return None

    # ---------- explaining problems in plain words ----------
    def _hours_text(self, weekday: int) -> str:
        return _windows_label(self._hours[weekday])

    def _day_rule_problem(self, day: date, now: datetime) -> str:
        """Why `day` can't be used at all ('' if the date itself is fine)."""
        if day < now.date():
            return "That date has already passed. Please choose today or a later date."
        if day > self.last_day(now):
            return (f"Pickups can only be requested up to {plural(self._horizon_days, 'day')} "
                    "ahead. Please choose an earlier date.")
        if not self._slots_by_weekday:
            return f"{self._owner_label} hasn't set any pickup times yet."
        if day in self._blocked:
            return f"{self._owner_label} is not available for pickup on {format_day(day)}."
        if day.weekday() not in self._slots_by_weekday:
            return (f"{self._owner_label} isn't available for pickup on "
                    f"{WEEKDAY_NAMES[day.weekday()]}s. Available: {self.schedule_text}.")
        return ""

    def day_problem(self, day: date, now: datetime) -> str:
        """'' if `day` still has at least one pickup time, else why it has none."""
        problem = self._day_rule_problem(day, now)
        if problem:
            return problem
        if not self.minutes_on(day, now):
            return (f"All of today's pickup times with {self._owner_label} have passed "
                    f"({self._hours_text(day.weekday())}). Please choose another day.")
        return ""

    def no_slots_message(self) -> str:
        return (f"{self._owner_label} has no pickup times available in the next "
                f"{plural(self._horizon_days, 'day')}. Please contact them to arrange a "
                "pickup, or try again later.")

    def check(self, pickup_at: datetime, now: datetime) -> str:
        """Is this exact moment one of the offered pickup times? '' if yes, else why not."""
        if pickup_at.tzinfo is None:
            return "The pickup time is missing its time zone."
        local = pickup_at.astimezone(now.tzinfo)
        day = local.date()
        problem = self._day_rule_problem(day, now)
        if problem:
            return problem
        minute = local.hour * 60 + local.minute
        if (local.second or local.microsecond
                or minute not in self._slots_by_weekday.get(day.weekday(), ())):
            return (f"{self._owner_label} doesn't offer a pickup at {format_minute(minute)} on "
                    f"{WEEKDAY_NAMES[day.weekday()]}s. Pickup times: "
                    f"{self._hours_text(day.weekday())}.")
        return ""


class PickupSchedule:
    """The student's pickup choice for ONE item: a date plus a time of day.

    Plain Python (no widgets), so the rules are easy to test. The request form
    just displays this object. Each item gets its OWN PickupSchedule, so
    changing one item never changes another.
    """

    def __init__(self, availability: PickupAvailability, now: datetime):
        self.availability = availability
        self.day = now.date()
        self.minute = None   # minutes since midnight; None = no time chosen
        self.hint = ""       # a friendly note after the form adjusts the TIME for a new date
        self.jump_to_next(now)

    def jump_to_next(self, now: datetime) -> bool:
        """Select the next available date and time. False if there is none."""
        slot = self.availability.next_available_slot(now)
        if slot is None:
            return False
        self.day = slot.date()
        self.minute = slot.hour * 60 + slot.minute
        self.hint = ""
        return True

    def slot_minutes(self, now: datetime) -> list:
        """The times that can be chosen on the selected date."""
        return self.availability.minutes_on(self.day, now)

    def set_day(self, day: date, now: datetime):
        """Choose a date. Keeps the chosen time if that date offers it too;
        otherwise shows the first available time and explains the change in `hint`."""
        previous = self.minute
        self.day = day
        self.hint = ""
        minutes = self.slot_minutes(now)
        if not minutes:
            self.minute = None
        elif previous in minutes:
            self.minute = previous
        else:
            self.minute = minutes[0]
            if previous is not None:
                self.hint = (f"{format_minute(previous)} isn't offered on "
                             f"{WEEKDAY_NAMES[day.weekday()]}s, so the time now shows "
                             f"{format_minute(self.minute)}. Change it if you prefer.")

    def set_minute(self, minute):
        self.minute = minute
        self.hint = ""

    def forget_time(self):
        """Drop the chosen time (the student must pick again)."""
        self.minute = None
        self.hint = ""

    def pickup_at(self, tz):
        """The chosen moment as a timezone-aware datetime, or None if no time is chosen."""
        if self.minute is None:
            return None
        return self.availability.slot_start(self.day, self.minute, tz)

    def problem(self, now: datetime) -> str:
        """Re-check the whole choice against `now`. '' means it is valid."""
        if self.minute is None:
            return (self.availability.day_problem(self.day, now)
                    or "Please choose a pickup time.")
        pickup = self.pickup_at(now.tzinfo)
        return validate_pickup(pickup, now) or self.availability.check(pickup, now)


# ---------- SAMPLE availability (made-up settings, NOT real policy) ----------
# School pickup locations stand for school administrators' schedules; student
# lenders have their own. Later, each person's real settings come from the
# database and are turned into a PickupAvailability the same way.
SAMPLE_SCHOOL_PICKUP_RULES = {
    "Main Library": (("Mon-Fri", "9:00-16:00"),),
    "Student Services Desk": (("Mon-Fri", "9:00-12:00", "13:00-16:00"),),   # lunch break
    "Electronics Lab": (("Mon-Thu", "13:00-17:00"),),
    "Engineering Workshop": (("Tue-Fri", "9:00-15:00"),),
    "Science Lab": (("Mon,Wed,Fri", "10:00-14:00"),),
}
SAMPLE_SCHOOL_DEFAULT_RULES = (("Mon-Fri", "9:00-16:00"),)

SAMPLE_STUDENT_PICKUP_RULES = {
    "Ana M.": (("Sat-Sun", "10:00-18:00"), ("Wed", "17:00-20:00")),
    "Paolo R.": (("Tue,Thu", "16:30-19:30"), ("Sat", "9:00-12:00")),
    "Ria L.": (("Mon-Fri", "17:00-20:00"), ("Sun", "13:00-17:00")),
    "Mark D.": (("Fri", "15:00-18:00"),),
    "Jenna T.": (("Mon-Fri", "12:00-13:00"), ("Sat", "9:00-11:00")),
    "Carlo V.": (("Sat-Sun", "8:00-12:00"),),
}
# Only for a lender who has no sample settings yet (still named in the messages).
SAMPLE_STUDENT_DEFAULT_RULES = (("Mon-Fri", "17:00-19:00"),)


class SamplePickupAvailabilityStore:
    """SAMPLE ONLY: hands out the PickupAvailability for a Catalog item.

    School items are keyed by their pickup location (the item's owner_note);
    student items by the lender's name. A real store (database-backed) would
    offer the same `for_item(item)` method.
    """

    def __init__(self, school_rules=None, student_rules=None,
                 school_default=SAMPLE_SCHOOL_DEFAULT_RULES,
                 student_default=SAMPLE_STUDENT_DEFAULT_RULES):
        self._school_rules = dict(SAMPLE_SCHOOL_PICKUP_RULES if school_rules is None else school_rules)
        self._student_rules = dict(SAMPLE_STUDENT_PICKUP_RULES if student_rules is None else student_rules)
        self._school_default = school_default
        self._student_default = student_default
        self._cache = {}

    @staticmethod
    def owner_key(item) -> str:
        note = item.owner_note.strip()
        return note if item.ownership == "school" else note.removeprefix("Shared by ").strip()

    def for_item(self, item) -> PickupAvailability:
        is_school = item.ownership == "school"
        key = self.owner_key(item)
        cache_key = (is_school, key)
        if cache_key not in self._cache:
            table = self._school_rules if is_school else self._student_rules
            rules = table.get(key, self._school_default if is_school else self._student_default)
            self._cache[cache_key] = PickupAvailability(key, parse_weekly_hours(*rules))
        return self._cache[cache_key]


SAMPLE_AVAILABILITY_STORE = SamplePickupAvailabilityStore()


def get_pickup_availability(item) -> PickupAvailability:
    """Pickup availability for the lender/administrator responsible for `item`."""
    saved_schedule = getattr(item, "pickup_schedule", None)
    if saved_schedule is not None:
        return PickupAvailability(
            item.owner_note.removeprefix("Shared by ").strip(),
            saved_schedule)
    return SAMPLE_AVAILABILITY_STORE.for_item(item)


# ======================================================================
# 4. SMALL HELPERS
# ======================================================================
def lender_name(item: CatalogItem) -> str:
    """'Shared by Ana M.' -> 'Ana M.'"""
    return item.owner_note.removeprefix("Shared by ")


def approver_text(item: CatalogItem) -> str:
    """Who would approve a request for this item (used in the request form)."""
    if item.ownership == "student":
        return f"Approved by lender: {lender_name(item)}"
    return f"Approved by school administrator · Pickup: {item.owner_note}"


def make_icon_badge(item: CatalogItem) -> QLabel:
    """Small colored square with the item's kind icon (stands in for a cover)."""
    category = CATEGORY_BY_NAME.get(item.category)
    color = category.cover_color if category else LIGHT_PERIWINKLE
    badge = QLabel(KIND_ICONS.get(item.kind, "📦"))
    badge.setObjectName("myListIcon")
    badge.setStyleSheet(f"background-color: {color};")  # only the color differs per item
    badge.setAlignment(Qt.AlignCenter)
    badge.setFixedSize(54, 54)
    return badge


# ======================================================================
# 5. ROW WIDGETS
# ======================================================================
class SavedItemRow(QFrame):
    """One saved item as a soft-dark card (Step 22): checkbox, photo/placeholder, title,
    category, owner, availability and Remove.

    Wide cards keep availability + Remove in a column on the right; narrow ones move them
    under the text (see resizeEvent). Signals, the check button and the Remove button are the
    same as before, so the screen's logic is unchanged.
    """

    selection_changed = Signal(object, bool)  # (CatalogItem, is_selected)
    remove_clicked = Signal(object)           # CatalogItem

    COMPACT_BELOW = 520   # px: below this width the side column folds under the text

    def __init__(self, item: CatalogItem, selected: bool = False, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("mlCard")
        self.setProperty("unavailable", not item.is_available)
        self.setProperty("selected", False)
        self._compact = False

        self._outer = QHBoxLayout(self)
        self._outer.setContentsMargins(14, 12, 14, 12)
        self._outer.setSpacing(14)

        # --- selection check (disabled for unavailable items) ---
        self.check = QPushButton("")
        self.check.setObjectName("mlCheck")
        self.check.setCheckable(True)
        self.check.setFixedSize(26, 26)
        self.check.setAccessibleName(f"Select {item.title}")
        if item.is_available and item.request_enabled:
            self.check.setCursor(Qt.PointingHandCursor)
            self.check.setToolTip("Select this item to request it")
            self.check.toggled.connect(self._on_toggled)
            self.set_checked(selected)
        else:
            self.check.setEnabled(False)
            self.check.setToolTip(
                item.request_disabled_reason or UNAVAILABLE_HINT)
        self._outer.addWidget(self.check, alignment=Qt.AlignVCenter)

        # --- photo (the item's primary photo when it has one, else the placeholder) ---
        self.thumb = ItemThumb(KIND_ICONS.get(item.kind, "📦"), _cover_tone(item))
        self.thumb.setFixedSize(64, 64)
        self._outer.addWidget(self.thumb, alignment=Qt.AlignVCenter)

        # --- title / category / owner ---
        self._body = QVBoxLayout()
        self._body.setSpacing(3)
        title = ElidedLabel(item.title)
        title.setObjectName("mlItemTitle")
        self._body.addWidget(title)

        category = CATEGORY_BY_NAME.get(item.category)
        icon = f"{category.icon} " if category else ""
        category_line = ElidedLabel(f"{icon}{item.category_label} · {item.kind}")
        category_line.setObjectName("mlItemMeta")
        self._body.addWidget(category_line)

        owner_row = QHBoxLayout()
        owner_row.setSpacing(8)
        owner_row.addWidget(_ml_pill(item.ownership_label, item.ownership))
        note = ElidedLabel(item.owner_note)
        note.setObjectName("mlItemNote")
        owner_row.addWidget(note, 1)
        self._body.addLayout(owner_row)
        self._outer.addLayout(self._body, 1)

        # --- availability + remove (one widget that moves between the two layouts) ---
        self.side = QWidget()
        self._side_layout = QBoxLayout(QBoxLayout.TopToBottom, self.side)
        self._side_layout.setContentsMargins(0, 0, 0, 0)
        self._side_layout.setSpacing(8)
        self._availability = _ml_pill(item.availability_text, item.availability_tone)
        self._side_layout.addWidget(self._availability, alignment=Qt.AlignRight)
        remove = QPushButton("Remove")
        remove.setObjectName("myListRemoveButton")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setToolTip("Remove from My List")
        remove.clicked.connect(lambda: self.remove_clicked.emit(self.item))
        self._side_layout.addWidget(remove, alignment=Qt.AlignRight)
        self.remove_button = remove
        self._outer.addWidget(self.side, alignment=Qt.AlignVCenter)

    @property
    def is_compact(self) -> bool:
        return self._compact

    def set_photo(self, path):
        """Show the item's primary photo (None = placeholder)."""
        self.thumb.set_photo(path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_compact(self.width() < self.COMPACT_BELOW)

    def _set_compact(self, compact: bool):
        if compact == self._compact:
            return
        self._compact = compact
        if compact:   # availability + Remove sit side by side under the text
            self._outer.removeWidget(self.side)
            self._body.addWidget(self.side)
            self._side_layout.setDirection(QBoxLayout.LeftToRight)
        else:
            self._body.removeWidget(self.side)
            self._outer.addWidget(self.side, alignment=Qt.AlignVCenter)
            self._side_layout.setDirection(QBoxLayout.TopToBottom)

    def set_checked(self, checked: bool):
        """Change the check without sending a signal (the screen already knows)."""
        if not self.item.is_available or not self.item.request_enabled:
            return
        self.check.blockSignals(True)
        self.check.setChecked(checked)
        self.check.setText("✓" if checked else "")
        self.check.blockSignals(False)
        self._mark_selected(checked)

    def _mark_selected(self, selected: bool):
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)

    def _on_toggled(self, checked: bool):
        self.check.setText("✓" if checked else "")
        self._mark_selected(checked)
        self.selection_changed.emit(self.item, checked)


def _ml_pill(text: str, tone: str) -> QLabel:
    """Small rounded tag for My List cards (tone: school, student, ok, low, none)."""
    label = QLabel(text)
    label.setObjectName("mlPill")
    label.setProperty("tone", tone)
    label.setAlignment(Qt.AlignCenter)
    label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return label


class PreviewRow(QFrame):
    """A read-only summary row for one item.

    The request form no longer uses this (it uses RequestDraftRow below). It is
    kept so older code that imports PreviewRow keeps working.
    """

    def __init__(self, item: CatalogItem, parent=None):
        super().__init__(parent)
        self.setObjectName("myListPreviewRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        layout.addWidget(make_icon_badge(item), alignment=Qt.AlignVCenter)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = ElidedLabel(item.title)
        title.setObjectName("catalogItemTitle")
        texts.addWidget(title)
        meta = ElidedLabel(f"{item.category} · {item.ownership_label}")
        meta.setObjectName("catalogItemCreator")
        texts.addWidget(meta)
        approver = ElidedLabel(approver_text(item))
        approver.setObjectName("catalogItemNote")
        texts.addWidget(approver)
        layout.addLayout(texts, 1)


class NoWheelComboBox(QComboBox):
    """A dropdown that ignores the mouse wheel unless it has keyboard focus.

    The request form scrolls; without this, scrolling over a dropdown would
    silently change the student's pickup time.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


def _to_qdate(day: date) -> QDate:
    return QDate(day.year, day.month, day.day)


def _set_property(widget, name: str, value):
    """Set a dynamic property and re-apply the stylesheet so the QSS sees it."""
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class AvailabilityCalendar(QCalendarWidget):
    """A calendar that draws each day by whether the lender/admin offers pickup.

      mint circle      -> pickup is available (can be chosen)
      navy circle      -> the date chosen right now
      struck-out grey  -> not available (closed day, or no times left today)
      plain light grey -> already past / too far ahead
      pink ring        -> today

    QCalendarWidget cannot disable individual days, so unavailable days are
    drawn clearly as unavailable and the popup refuses to pick them (it explains
    why instead). Weekends are NOT treated specially: only the lender's own
    availability decides.
    """

    def __init__(self, availability: PickupAvailability, now: datetime,
                 chosen_day: date, parent=None):
        super().__init__(parent)
        self._availability = availability
        self._now = now
        self._today = now.date()
        self._last = availability.last_day(now)
        self._chosen = chosen_day
        self._pickable_cache = {}

        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setSelectionMode(QCalendarWidget.SelectionMode.SingleSelection)
        self.setMinimumDate(_to_qdate(self._today))
        self.setMaximumDate(_to_qdate(self._last))
        self.setMinimumSize(320, 236)

        # Qt paints Saturday/Sunday headers red by default; nothing here is
        # "weekend = unavailable", so give every weekday the same header look.
        header_format = QTextCharFormat()
        header_format.setForeground(QColor(NAVY))
        header_format.setFontWeight(QFont.Weight.Bold)
        self.setHeaderTextFormat(header_format)
        plain_format = QTextCharFormat()
        plain_format.setForeground(QColor(NAVY))
        for weekday in (Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday,
                        Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday, Qt.DayOfWeek.Saturday,
                        Qt.DayOfWeek.Sunday):
            self.setWeekdayTextFormat(weekday, plain_format)

        start = chosen_day if self._today <= chosen_day <= self._last else self._today
        self.setSelectedDate(_to_qdate(start))  # also opens the calendar on that month

    def is_pickable(self, day: date) -> bool:
        if day not in self._pickable_cache:
            self._pickable_cache[day] = (
                self._today <= day <= self._last
                and self._availability.has_slots_on(day, self._now)
            )
        return self._pickable_cache[day]

    def paintCell(self, painter, rect, date):  # noqa: N802 (Qt's own method name)
        day = date.toPython() if isinstance(date, QDate) else date
        in_month = day.year == self.yearShown() and day.month == self.monthShown()
        pickable = self.is_pickable(day)
        chosen = day == self._chosen
        cursor = day == self.selectedDate().toPython() and not chosen  # keyboard position

        fill = None
        ring = None
        text_color = QColor("#CFD1EA")      # past / out of range: plain light grey
        font = painter.font()
        if pickable:
            text_color = QColor(NAVY)
            fill = QColor(MINT)
            if not in_month:                # days of the neighbouring months: softer
                fill.setAlpha(110)
            font.setBold(in_month)
        elif self._today <= day <= self._last:
            text_color = QColor("#9A9CC4")  # not offered: grey and struck out
            font.setStrikeOut(in_month)
        if chosen:
            if pickable:
                fill = QColor(NAVY)
                text_color = QColor(CREAM)
                font.setBold(True)
            else:
                ring = QColor(PINK)         # the shown date has no times (explained in the form)
        elif day == self._today:
            ring = QColor(PINK)
        elif cursor:
            ring = QColor(NAVY)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        size = max(10, min(rect.width(), rect.height()) - 6)
        circle = QRect(0, 0, size, size)
        circle.moveCenter(rect.center())
        if fill is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawEllipse(circle)
        if ring is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 2))
            painter.drawEllipse(circle.adjusted(1, 1, -1, -1))
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(day.day))
        painter.restore()


class PickupCalendarPopup(QFrame):
    """The calendar that pops open under the date button.

    Click an available (mint) date to choose it. Clicking an unavailable date
    keeps the popup open and says why, so nothing is chosen by accident.
    """

    date_chosen = Signal(object)   # a datetime.date

    def __init__(self, availability: PickupAvailability, now: datetime,
                 chosen_day: date, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("myListCalendarPopup")
        self.setStyleSheet(CALENDAR_POPUP_STYLESHEET)
        self._availability = availability
        self._now = now

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("Choose a pickup date")
        title.setObjectName("myListCalendarTitle")
        layout.addWidget(title)

        who = QLabel(f"{availability.owner_label} · {availability.schedule_text}")
        who.setObjectName("myListCalendarLegend")
        who.setWordWrap(True)
        layout.addWidget(who)

        self.calendar = AvailabilityCalendar(availability, now, chosen_day)
        self.calendar.clicked.connect(self._on_day_clicked)
        self.calendar.activated.connect(self._on_day_clicked)   # Enter key
        layout.addWidget(self.calendar)

        legend = QLabel(
            f"<span style='color:{NAVY};'>●</span> Chosen &nbsp;&nbsp; "
            f"<span style='color:#4FBF9F;'>●</span> Available &nbsp;&nbsp; "
            "<s style='color:#9A9CC4;'>12</s> Unavailable &nbsp;&nbsp; "
            f"<span style='color:{PINK};'>◯</span> Today"
        )
        legend.setObjectName("myListCalendarLegend")
        legend.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(legend)

        self.note = QLabel("Pick one of the green dates.")
        self.note.setObjectName("myListCalendarNote")
        self.note.setWordWrap(True)
        self.note.setMinimumHeight(40)   # room for a two-line explanation without resizing
        self.note.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.note)

    def _on_day_clicked(self, qdate):
        day = qdate.toPython()
        problem = self._availability.day_problem(day, self._now)
        if problem:
            self.note.setText(problem)
            _set_property(self.note, "tone", "warn")
            self.calendar.update()
            return
        self.date_chosen.emit(day)
        self.close()

    def show_below(self, anchor: QWidget):
        self.ensurePolished()
        self.layout().activate()
        self.adjustSize()

        screen = anchor.screen()

        if screen is not None:
            area = screen.availableGeometry()

            below = anchor.mapToGlobal(
                QPoint(0, anchor.height() + 4)
            )

            space_needed = (
                below.y() + self.height() + 8 - area.bottom()
            )

            # Scroll the form upward to make room for the calendar.
            if space_needed > 0:
                parent = anchor.parentWidget()

                while parent is not None:
                    if isinstance(parent, QScrollArea):
                        scrollbar = parent.verticalScrollBar()
                        scrollbar.setValue(
                            scrollbar.value() + space_needed
                        )
                        break

                    parent = parent.parentWidget()

            # Recalculate after scrolling.
            below = anchor.mapToGlobal(
                QPoint(0, anchor.height() + 4)
            )

            x = max(
                area.left(),
                min(below.x(), area.right() - self.width())
            )

            self.move(QPoint(x, below.y()))

        else:
            self.move(
                anchor.mapToGlobal(
                    QPoint(0, anchor.height() + 4)
                )
            )

        self.show()

class RequestDraftRow(QFrame):
    """The request form for ONE item: pickup date + time, and borrowing days.

    Every row owns its own widgets, its own PickupSchedule and its own pickup
    availability, so changing one item never changes another.
    """

    def __init__(self, item: CatalogItem, now: datetime | None = None, parent=None, *,
                 availability: PickupAvailability | None = None):
        super().__init__(parent)
        self.item = item
        self.max_days = get_max_borrow_days(item)
        self.availability = availability or get_pickup_availability(item)
        self.setObjectName("myListDraftRow")

        now = now or local_now()
        self._tz = now.tzinfo
        self.schedule = PickupSchedule(self.availability, now)   # opens on the next valid slot

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        # --- item information (title, category, owner, lender/admin) ---
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(make_icon_badge(item), alignment=Qt.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = ElidedLabel(item.title)
        title.setObjectName("catalogItemTitle")
        texts.addWidget(title)
        meta = ElidedLabel(f"{item.category} · {item.ownership_label}")
        meta.setObjectName("catalogItemCreator")
        texts.addWidget(meta)
        approver = ElidedLabel(approver_text(item))
        approver.setObjectName("catalogItemNote")
        texts.addWidget(approver)
        top.addLayout(texts, 1)
        outer.addLayout(top)

        # --- preferred pickup DATE (calendar button) and TIME (dropdown) ---
        self.date_button = QPushButton("")
        self.date_button.setObjectName("myListDateButton")
        self.date_button.setCursor(Qt.PointingHandCursor)
        self.date_button.setAutoDefault(False)   # Enter must never open it / confirm
        self.date_button.setMinimumHeight(38)
        self.date_button.setAccessibleName(f"Preferred pickup date for {item.title}")
        self.date_button.setToolTip(
            "Open the calendar. Green dates are available; struck-out dates are not."
        )
        self.date_button.clicked.connect(self._open_calendar)

        self.time_combo = NoWheelComboBox()
        self.time_combo.setObjectName("myListTimeCombo")
        self.time_combo.setView(QListView())   # lets the QSS size and color the list items
        self.time_combo.setMaxVisibleItems(8)
        self.time_combo.setMinimumHeight(38)
        self.time_combo.setMinimumWidth(130)
        self.time_combo.setAccessibleName(f"Preferred pickup time for {item.title}")
        self.time_combo.setToolTip("Only times this lender or administrator offers are listed.")
        self.time_combo.currentIndexChanged.connect(self._on_time_changed)

        schedule_grid = QGridLayout()
        self.schedule_grid = schedule_grid
        schedule_grid.setHorizontalSpacing(12)
        schedule_grid.setVerticalSpacing(4)
        schedule_grid.setColumnStretch(0, 3)
        schedule_grid.setColumnStretch(1, 2)
        schedule_grid.addWidget(self._field_label("Preferred Pickup Date"), 0, 0)
        schedule_grid.addWidget(self._field_label("Preferred Pickup Time"), 0, 1)
        schedule_grid.addWidget(self.date_button, 1, 0)
        schedule_grid.addWidget(self.time_combo, 1, 1)
        outer.addLayout(schedule_grid)

        self.availability_label = QLabel(
            f"🕘 {self.availability.owner_label} pickup: {self.availability.schedule_text}"
        )
        self.availability_label.setObjectName("myListScheduleHint")
        self.availability_label.setWordWrap(True)
        outer.addWidget(self.availability_label)

        self.schedule_note = QLabel("")   # live explanation about the chosen date/time
        self.schedule_note.setObjectName("myListScheduleNote")
        self.schedule_note.setWordWrap(True)
        self.schedule_note.hide()
        outer.addWidget(self.schedule_note)

        self.jump_button = QPushButton("")   # only shown when the chosen date has no times
        self.jump_button.setObjectName("myListJumpButton")
        self.jump_button.setCursor(Qt.PointingHandCursor)
        self.jump_button.setAutoDefault(False)
        self.jump_button.clicked.connect(self._jump_to_next)
        self.jump_button.hide()
        outer.addWidget(self.jump_button, alignment=Qt.AlignLeft)

        # --- borrowing days (independent of pickup availability) ---
        self.days_spin = QSpinBox()
        self.days_spin.setObjectName("myListDaysSpin")
        self.days_spin.setRange(1, self.max_days)
        self.days_spin.setValue(1)
        self.days_spin.setMinimumWidth(96)
        self.days_spin.setAlignment(Qt.AlignCenter)
        self.days_spin.setAccessibleName(f"Borrowing days for {item.title}")
        # Our own - / + buttons look better than the built-in tiny arrows (the QSS
        # below hides those). Typing a number, arrow keys and mouse wheel still work.
        self._update_days_suffix(1)

        minus_button = self._step_button("−", "One day less", -1)
        plus_button = self._step_button("+", "One day more", +1)

        max_label = "Owner max" if item.owner_student_id is not None else "Sample max"
        max_pill = QLabel(f"{max_label}: {plural(self.max_days, 'day')}")
        max_pill.setObjectName("myListMaxPill")
        max_pill.setToolTip(
            "The maximum borrowing duration saved by the Student Owner."
            if item.owner_student_id is not None else
            "A sample limit for this preview only. The real limit will be set by "
            "the lender or administrator.")

        duration_row = QHBoxLayout()
        duration_row.setSpacing(6)
        duration_row.addWidget(self._field_label("Borrow for"))
        duration_row.addSpacing(6)
        duration_row.addWidget(minus_button)
        duration_row.addWidget(self.days_spin)
        duration_row.addWidget(plus_button)
        duration_row.addSpacing(6)
        duration_row.addWidget(max_pill)
        duration_row.addStretch()
        outer.addLayout(duration_row)

        # --- live summary + error message ---
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("myListDraftSummary")
        self.summary_label.setWordWrap(True)
        outer.addWidget(self.summary_label)

        self.error_label = QLabel("")
        self.error_label.setObjectName("myListFieldError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        outer.addWidget(self.error_label)

        self.days_spin.valueChanged.connect(self._on_input_changed)
        self._render_schedule(now)

    # ---------- reading the student's choices ----------
    def pickup_at(self) -> datetime | None:
        """The preferred pickup (timezone-aware), or None while no time is chosen."""
        return self.schedule.pickup_at(self._tz)

    def days(self) -> int:
        return self.days_spin.value()

    def validate(self, now: datetime | None = None) -> bool:
        """Check every field of this row, show any problems, return True if all fine.

        The pickup is re-checked against the CURRENT time and this lender's
        availability, so a time that slipped into the past while the form was
        open is caught here. Nothing is changed for the student: a stale time is
        cleared (so it can't be confirmed by accident) and they choose again.
        """
        now = now or local_now()
        schedule_error = self.schedule.problem(now)
        days_error = validate_days(self.days(), self.max_days)
        availability_error = "" if self.item.is_available else (
            "This item is no longer available, so it can't be requested."
        )

        self._mark_invalid(self.date_button, bool(schedule_error))
        self._mark_invalid(self.time_combo, bool(schedule_error))
        self._mark_invalid(self.days_spin, bool(days_error))

        messages = [m for m in (availability_error, schedule_error, days_error) if m]
        self.error_label.setText("\n".join(messages))
        self.error_label.setVisible(bool(messages))

        if schedule_error:
            self.schedule.forget_time()      # never keep a choice that just failed
            self._render_schedule(now)       # and list only the times that are left
        return not messages

    def to_draft(self) -> RequestDraft:
        """Build the RequestDraft (call only after validate() returned True)."""
        return RequestDraft(
            item=self.item,
            pickup_at=self.pickup_at(),
            days=self.days(),
            max_days=self.max_days,
        )

    # ---------- the date calendar and the time dropdown ----------
    def _open_calendar(self):
        popup = getattr(self, "_calendar_popup", None)

        if popup is not None:
            if popup.isVisible():
                popup.close()
                return
            popup.deleteLater()

        popup = PickupCalendarPopup(
            self.availability,
            local_now(),
            self.schedule.day,
            self.date_button
        )

        popup.date_chosen.connect(self._on_date_chosen)
        self._calendar_popup = popup
        popup.show_below(self.date_button)

    def _on_date_chosen(self, day: date):
        now = local_now()
        self.schedule.set_day(day, now)   # keeps the time if offered, else says what changed
        self._clear_errors()
        self._render_schedule(now)

    def _on_time_changed(self, _index: int):
        data = self.time_combo.currentData()
        self.schedule.set_minute(data if isinstance(data, int) and data >= 0 else None)
        self._clear_errors()
        self._update_notes(local_now())

    def _jump_to_next(self):
        now = local_now()
        self.schedule.jump_to_next(now)
        self._clear_errors()
        self._render_schedule(now)

    def _render_schedule(self, now: datetime):
        """Show the chosen date, refill the time dropdown for that date, update notes."""
        self.date_button.setText(f"📅  {format_day(self.schedule.day)}   ▾")
        self._fill_time_combo(self.schedule.slot_minutes(now))
        self._update_notes(now)

    def _fill_time_combo(self, minutes: list):
        combo = self.time_combo
        combo.blockSignals(True)   # refilling is not the student choosing a time
        combo.clear()
        if minutes:
            if self.schedule.minute is None:
                combo.addItem("Choose a time", -1)
            for minute in minutes:
                combo.addItem(format_minute(minute), minute)
            index = combo.findData(self.schedule.minute) if self.schedule.minute is not None else 0
            combo.setCurrentIndex(max(index, 0))
            combo.setEnabled(True)
        else:
            combo.addItem("No times available", -1)
            combo.setCurrentIndex(0)
            combo.setEnabled(False)
        combo.blockSignals(False)

    def _update_notes(self, now: datetime):
        """Explain the chosen date when it has no times; offer a way to the next one."""
        day_problem = self.availability.day_problem(self.schedule.day, now)
        next_slot = self.availability.next_available_slot(now) if day_problem else None
        if day_problem:
            text = day_problem
            if next_slot is None:   # nothing bookable at all: friendly message, no dead end
                text += "\n" + self.availability.no_slots_message()
            self._set_note(text, "warn")
        elif self.schedule.hint:
            self._set_note(self.schedule.hint, "info")
        else:
            self.schedule_note.hide()

        if next_slot is not None and next_slot.date() != self.schedule.day:
            self.jump_button.setText(
                f"Go to the next available day: {format_day(next_slot.date())}"
            )
            self.jump_button.show()
        else:
            self.jump_button.hide()
        self._refresh_summary()

    def _set_note(self, text: str, tone: str):
        self.schedule_note.setText(text)
        _set_property(self.schedule_note, "tone", tone)
        self.schedule_note.show()

    # ---------- small internal helpers ----------
    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("myListFieldLabel")
        return label

    def _step_button(self, text: str, tooltip: str, step: int) -> QPushButton:
        """A small round button that changes the number of days by `step`."""
        button = QPushButton(text)
        button.setObjectName("myListStepButton")
        button.setFixedSize(30, 30)
        button.setAutoDefault(False)  # pressing Enter must never "click" it
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tooltip)
        button.clicked.connect(lambda: self.days_spin.stepBy(step))
        return button

    def _update_days_suffix(self, value: int):
        self.days_spin.setSuffix(" day" if value == 1 else " days")

    def _mark_invalid(self, widget, invalid: bool):
        """Turn the red 'invalid' border on or off (the QSS reads this property)."""
        _set_property(widget, "invalid", invalid)

    def _clear_errors(self):
        """The student is fixing things: hide the old complaint until Confirm again."""
        self._mark_invalid(self.date_button, False)
        self._mark_invalid(self.time_combo, False)
        self._mark_invalid(self.days_spin, False)
        self.error_label.hide()

    def _on_input_changed(self, _value=None):
        self._update_days_suffix(self.days_spin.value())
        self._clear_errors()
        self._refresh_summary()

    def _refresh_summary(self):
        # No due date here on purpose: the clock only starts at the confirmed handover.
        pickup = self.pickup_at()
        when = (f"preferred pickup {format_pickup(pickup)}" if pickup is not None
                else "choose an available pickup date and time")
        self.summary_label.setText(f"Request: borrow for {plural(self.days(), 'day')} · {when}")


# ======================================================================
# 6. REQUEST DIALOG
# ======================================================================
class RequestPreviewDialog(QDialog):
    """'Review your requests' - the borrowing request form. Submits nothing.

    Usage (same for Catalog and My List):
        dialog = RequestPreviewDialog(items, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            drafts = dialog.drafts      # list of RequestDraft, one per item

    Confirm validates EVERYTHING again (item availability, pickup date/time
    against the lender's or administrator's pickup availability and the current
    clock, borrowing days). If anything is wrong the dialog stays open and
    explains it. Cancel / closing the window never produces drafts.

    `availability_lookup` (optional) is a function item -> PickupAvailability.
    The default uses the SAMPLE availability; a real settings store can be
    plugged in here later.

    `submit_handler` (optional, Step 8C) is a function (drafts, submission_key)
    -> saved requests. When given, Confirm SAVES the requests (locally) before
    the dialog closes. If saving fails, the dialog stays open, shows the problem,
    and nothing is reported as saved. The same `submission_key` is reused on a
    retry, so a retry can never create duplicate records. Without a handler the
    dialog behaves exactly as before (preview only).
    """

    def __init__(self, items, parent=None, *, availability_lookup=None, submit_handler=None):
        super().__init__(parent)
        self._availability_lookup = availability_lookup or get_pickup_availability
        self._submit_handler = submit_handler
        self._submission_key = uuid.uuid4().hex   # one per dialog = one per batch
        self._saved_requests = []
        self._submitting = False
        self.setObjectName("myListDialog")
        self.setWindowTitle("Review your requests")
        self.setModal(True)
        self.setStyleSheet(CATALOG_STYLESHEET + MY_LIST_STYLESHEET)
        self._fit_to_screen()

        # Remove duplicates but keep the order; split requestable / not requestable.
        unique = []
        for item in items:
            if item not in unique:
                unique.append(item)
        requestable = [
            item for item in unique if item.is_available and item.request_enabled
        ]
        blocked = [item for item in unique if item not in requestable]

        self._rows = []        # one RequestDraftRow per requestable item
        self._drafts = []      # filled only after a successful Confirm
        self._finished = False  # stops a second accept (no duplicate confirmations)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        tag = QLabel(
            "Saved on this computer only · Not sent to school administrators"
            if self._submit_handler is not None else "Preview only · Nothing is sent yet"
        )
        tag.setObjectName("catalogTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout.addWidget(tag, alignment=Qt.AlignLeft)

        title = QLabel("Review your requests")
        title.setObjectName("myListDialogTitle")
        layout.addWidget(title)

        # Notes + one form per item scroll together; the buttons stay visible below.
        self.scroll = QScrollArea()
        self.scroll.setObjectName("mlScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("catalogContent")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 6, 0)
        inner_layout.setSpacing(10)

        inner_layout.addWidget(self._build_info_box())
        if blocked:
            inner_layout.addWidget(self._build_blocked_box(blocked))

        now = local_now()
        for item in requestable:
            row = RequestDraftRow(item, now, availability=self._availability_lookup(item))
            self._rows.append(row)
            inner_layout.addWidget(row)

        if self._submit_handler is not None:
            created_verb = (
                "will be saved as Pending Owner Approval"
                if requestable and all(item.owner_student_id is not None for item in requestable)
                else "will be saved as Pending or Pending Owner Approval"
                if any(item.owner_student_id is not None for item in requestable)
                else "will be saved as Pending"
            )
        else:
            created_verb = "would be created"

        footnote_text = (
            "Each item becomes its own separate request, and each lender or administrator "
            "approves theirs independently - one rejection won't cancel the others. "
            f"Times use your local time zone ({local_timezone_label()})."
        )
        if self._submit_handler is not None:
            if requestable and all(item.owner_student_id is not None for item in requestable):
                footnote_text += (
                    " Pickup availability and borrowing limits come from the saved owner listings.")
            elif any(item.owner_student_id is not None for item in requestable):
                footnote_text += (
                    " Student Owner schedules and limits use saved listing data; school item "
                    "schedules and limits are preview values.")
            else:
                footnote_text += (
                    " School item pickup availability and borrowing limits are preview values.")
        else:
            footnote_text += (
                " Pickup availability and borrowing limits shown here are sample values "
                "for this preview only.")
        footnote = QLabel(footnote_text)
        footnote.setObjectName("myListFootnote")
        footnote.setWordWrap(True)
        inner_layout.addWidget(footnote)
        inner_layout.addStretch()
        self.scroll.setWidget(inner)
        layout.addWidget(self.scroll, 1)

        count = len(self._rows)
        self.summary_label = QLabel(
            f"{plural(count, 'separate request')} {created_verb}"
            if count else "There is nothing to request"
        )
        self.summary_label.setObjectName("myListDialogSummary")
        layout.addWidget(self.summary_label)

        self.form_error = QLabel("")
        self.form_error.setObjectName("myListFormError")
        self.form_error.setWordWrap(True)
        self.form_error.hide()
        layout.addWidget(self.form_error)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancel")  # same wording for Catalog and My List
        self.cancel_button.setObjectName("myListBackButton")
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.confirm_button = QPushButton(
            "Confirm Request" if self._submit_handler is not None else "Confirm (Preview Only)"
        )
        self.confirm_button.setObjectName("catalogPrimaryButton")
        self.confirm_button.setCursor(Qt.PointingHandCursor)
        self.confirm_button.setAutoDefault(False)  # Enter inside a field must not confirm
        self.confirm_button.setEnabled(bool(self._rows))
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(self.confirm_button)
        layout.addLayout(buttons)

    # ---------- public API ----------
    @property
    def drafts(self) -> list:
        """The validated RequestDrafts. Empty unless the dialog was accepted."""
        return list(self._drafts)

    @property
    def saved_requests(self) -> list:
        """The requests saved by the submit handler (empty without one / on failure)."""
        return list(self._saved_requests)

    @property
    def rows(self) -> list:
        """The per-item forms (handy for testing)."""
        return list(self._rows)

    def accept(self):
        """Confirm: validate every item again, and only then close with drafts."""
        if self._finished:
            return  # already confirmed once; never send a second confirmation
        if not self._rows:
            self._show_form_error("There are no available items to request.")
            return

        now = local_now()  # one clock reading for every item
        first_problem = None
        for row in self._rows:
            if not row.validate(now) and first_problem is None:
                first_problem = row
        if first_problem is not None:
            self._show_form_error(
                "Please fix the highlighted fields before confirming. "
                "Nothing was changed for you."
            )
            self.scroll.ensureWidgetVisible(first_problem)
            return

        drafts = [row.to_draft() for row in self._rows]
        if self._submit_handler is not None:
            if self._submitting:
                return  # a save is already running: never start a second one
            self._submitting = True
            self.confirm_button.setEnabled(False)
            try:
                self._saved_requests = list(self._submit_handler(drafts, self._submission_key) or [])
                if len(self._saved_requests) != len(drafts):
                    raise RuntimeError("The saved request count did not match the submission.")
            except Exception as exc:  # stay open; nothing is reported as saved
                reason = str(exc) if getattr(exc, "is_user_facing", False) else (
                    "Something went wrong while saving your request."
                )
                self._saved_requests = []
                self._show_form_error(f"{reason} Nothing was saved, so you can safely try again.")
                self.confirm_button.setEnabled(True)
                return
            finally:
                self._submitting = False

        self._drafts = drafts
        self._finished = True
        self.form_error.hide()
        super().accept()

    # ---------- building pieces ----------
    def _build_info_box(self) -> QFrame:
        info = QFrame()
        info.setObjectName("myListInfo")
        layout = QVBoxLayout(info)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(4)
        # Kept short so the forms below get most of the space on a laptop screen.
        notes = (
            "Choose a pickup date and time the lender or administrator offers. They approve "
            "it or arrange an alternative.",
            "Your borrowing period will begin once the lender or administrator confirms "
            "that you received the item.",
            "Need to collect your item earlier? Contact the lender or administrator "
            "to arrange pickup.",
        )
        for text in notes:
            label = QLabel("•  " + text)
            label.setObjectName("myListInfoText")
            label.setWordWrap(True)
            layout.addWidget(label)
        return info

    def _build_blocked_box(self, blocked) -> QFrame:
        box = QFrame()
        box.setObjectName("myListBlocked")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 10)
        names = ", ".join(f"“{item.title}”" for item in blocked)
        label = QLabel(f"Can't be requested right now (unavailable): {names}")
        label.setObjectName("myListBlockedText")
        label.setWordWrap(True)
        layout.addWidget(label)
        return box

    def _show_form_error(self, text: str):
        self.form_error.setText(text)
        self.form_error.show()

    def _fit_to_screen(self):
        """Roomy on big screens, but never taller than a small laptop screen."""
        height = 700
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            height = min(height, screen.availableGeometry().height() - 60)
        self.resize(720, max(height, 440))
        self.setMinimumSize(560, 420)


# ======================================================================
# 7. MY LIST SCREEN
# ======================================================================
class MyListScreen(QWidget):
    """Saved items with selection, removal and the borrowing request form.

    Signals (nothing is connected to them yet):
      browse_catalog_requested   - "Browse Catalog" button in the empty state
      item_removed(item)         - an item was removed from the saved list
      request_preview_confirmed(items) - confirm pressed in the request form.
                                   Payload: the selected CatalogItems (same as
                                   before). NO request is created.
      request_drafts_prepared(drafts)  - NEW. Same moment, but the payload is
                                   the list of validated RequestDrafts (pickup
                                   time + days for each item). Also NO request.
    Both confirmation signals fire exactly once per successful confirmation,
    and never when the form is cancelled or closed.
    """

    browse_catalog_requested = Signal()
    item_removed = Signal(object)
    request_preview_confirmed = Signal(list)
    request_drafts_prepared = Signal(list)

    def __init__(self, saved_items=None, parent=None):
        super().__init__(parent)
        self.setObjectName("myListScreen")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(MY_LIST_V2_STYLESHEET + HEADER_QSS)  # only this screen (Step 22 soft-dark)

        self._saved_items = []   # CatalogItem objects, in the order they were saved
        self._selected = set()   # the selected ones (always available items)
        self._rows = {}          # CatalogItem -> SavedItemRow
        self._prepared_drafts = []   # drafts from the latest successful confirmation
        self._dialog_open = False    # stops two forms from opening at once
        self._submit_handler = None  # Step 8C: set by the Dashboard to really save requests
        self._photo_paths = {}       # Step 22: {listing_key: primary photo path}

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(4000)
        self._banner_timer.timeout.connect(lambda: self.banner.hide())

        self._build_ui()
        self.set_saved_items(saved_items if saved_items is not None else [])

    # ---------- public API (for the Catalog / tests) ----------
    @property
    def saved_items(self) -> list:
        return list(self._saved_items)

    @property
    def selected_items(self) -> list:
        """Selected items, in the same order as the list."""
        return [item for item in self._saved_items if item in self._selected]

    @property
    def prepared_drafts(self) -> list:
        """RequestDrafts from the latest successful confirmation (kept in memory only)."""
        return list(self._prepared_drafts)

    def set_primary_photos(self, photo_paths):
        """Step 22: {listing_key: file path}. Items without a (readable) photo keep the
        placeholder. Only changes pictures: the list, selection and ticks stay as they are."""
        self._photo_paths = dict(photo_paths or {})
        for item, row in self._rows.items():
            row.set_photo(self._photo_paths.get(item.listing_key))

    def set_submit_handler(self, handler):
        """Step 8C: a function (drafts, submission_key) -> saved requests, or None."""
        self._submit_handler = handler

    def set_saved_items(self, items):
        """Replace the whole saved list (duplicates are ignored)."""
        selected_keys = {item.listing_key for item in self._selected}
        unique = []
        for item in items:
            if all(existing.listing_key != item.listing_key for existing in unique):
                unique.append(item)
        self._saved_items = unique
        self._selected = {
            item for item in unique
            if item.listing_key in selected_keys
            and item.is_available and item.request_enabled
        }
        self._refresh()

    def add_item(self, item: CatalogItem):
        """Bookmark an item (does nothing if it is already saved)."""
        if item not in self._saved_items:
            self.set_saved_items(self._saved_items + [item])

    def remove_item(self, item: CatalogItem):
        if item in self._saved_items:
            self._selected.discard(item)
            self._saved_items.remove(item)
            self._refresh()
            self.item_removed.emit(item)

    # ---------- building ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 24)   # same page margins as the Catalog
        root.setSpacing(12)

        # Header, toolbar, rows and empty state all scroll together;
        # only the action bar stays fixed at the bottom.
        scroll = QScrollArea()
        scroll.setObjectName("catalogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("mlContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 6, 8)
        layout.setSpacing(14)

        layout.addWidget(self._build_header())

        self.banner = QLabel("")
        self.banner.setObjectName("myListBanner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        layout.addWidget(self.banner)

        self.toolbar = self._build_toolbar()
        layout.addWidget(self.toolbar)

        self.rows_container = QWidget()
        self.rows_container.setObjectName("mlRows")
        self._rows_layout = QVBoxLayout(self.rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(12)
        layout.addWidget(self.rows_container)

        self.empty_state = self._build_empty_state()
        layout.addWidget(self.empty_state)
        layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.action_bar = self._build_action_bar()
        root.addWidget(self.action_bar)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("mlHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(2, 6, 2, 10)
        layout.setSpacing(16)

        texts = QVBoxLayout()
        texts.setSpacing(4)
        tag = QLabel("Preview · Sample data only")
        tag.setObjectName("mlTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        texts.addWidget(tag, alignment=Qt.AlignLeft)
        texts.addSpacing(4)

        title = QLabel(accent_html("My List", "List"))
        title.setObjectName("mlTitle")
        texts.addWidget(title)

        subtitle = QLabel(
            "Items you saved for later. Select the available ones and request "
            "them together."
        )
        subtitle.setObjectName("mlSubtitle")
        subtitle.setWordWrap(True)
        texts.addWidget(subtitle)
        texts.addStretch()
        layout.addLayout(texts, 1)

        self.mascot_label = None  # the Kit mascot lives on the Dashboard only
        return header

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.mascot_label is not None:  # small windows: give the text the room
            self.mascot_label.setVisible(self.width() >= 640)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("mlToolbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(12)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("mlSummary")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label, 1)

        self.select_all_button = QPushButton("Select all eligible")
        self.select_all_button.setObjectName("mlSelectAll")
        self.select_all_button.setCursor(Qt.PointingHandCursor)
        self.select_all_button.clicked.connect(self._on_select_all_clicked)
        layout.addWidget(self.select_all_button)
        return bar

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("mlActionBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 10, 12, 10)
        layout.setSpacing(12)

        self.selected_label = QLabel("")
        self.selected_label.setObjectName("mlSelectedLabel")
        layout.addWidget(self.selected_label, 1)

        self.request_button = QPushButton("Request Selected")
        self.request_button.setObjectName("mlRequestButton")
        self.request_button.setCursor(Qt.PointingHandCursor)
        self.request_button.clicked.connect(self._on_request_clicked)
        layout.addWidget(self.request_button)
        return bar

    def _build_empty_state(self) -> QFrame:
        box = QFrame()
        box.setObjectName("mlEmpty")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignHCenter)

        pixmap = QPixmap()  # Kit appears on the Dashboard only
        icon = QLabel()
        icon.setObjectName("mlEmptyIcon")
        icon.setAlignment(Qt.AlignCenter)
        if not pixmap.isNull():
            icon.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon.setText("🔖")  # a missing image file must never crash the app
        layout.addWidget(icon)

        title = QLabel("Your list is empty")
        title.setObjectName("mlEmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        text = QLabel(
            "Found something you like? Save it from the catalog and it will "
            "wait for you here, ready to request whenever you are."
        )
        text.setObjectName("mlEmptyText")
        text.setAlignment(Qt.AlignCenter)
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addSpacing(6)

        button = QPushButton("Browse Catalog")
        button.setObjectName("mlPrimaryButton")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.browse_catalog_requested.emit)
        layout.addWidget(button, alignment=Qt.AlignHCenter)
        return box

    # ---------- refreshing what is shown ----------
    def _eligible_items(self) -> list:
        return [
            item for item in self._saved_items
            if item.is_available and item.request_enabled
        ]

    def _refresh(self):
        """Rebuild the rows and update every label/button from the current state."""
        while self._rows_layout.count():
            widget = self._rows_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self._rows = {}

        for item in self._saved_items:
            row = SavedItemRow(item, selected=item in self._selected)
            row.selection_changed.connect(self._on_row_selection_changed)
            row.remove_clicked.connect(self._on_remove_clicked)
            row.set_photo(self._photo_paths.get(item.listing_key))
            self._rows_layout.addWidget(row)
            self._rows[item] = row

        has_items = bool(self._saved_items)
        self.rows_container.setVisible(has_items)
        self.toolbar.setVisible(has_items)
        self.action_bar.setVisible(has_items)
        self.empty_state.setVisible(not has_items)
        self._update_status()

    def _update_status(self):
        """Update counts, the Select-all button and the Request button."""
        saved = len(self._saved_items)
        eligible = self._eligible_items()
        selected = len(self._selected)
        unavailable = saved - len(eligible)

        parts = [f"{saved} saved", f"{len(eligible)} can be requested"]
        if unavailable:
            parts.append(f"{unavailable} unavailable")
        self.summary_label.setText(" · ".join(parts))

        all_selected = bool(eligible) and all(item in self._selected for item in eligible)
        self.select_all_button.setEnabled(bool(eligible))
        self.select_all_button.setText("Clear selection" if all_selected else "Select all eligible")

        if selected:
            self.selected_label.setText(f"{selected} item{'s' if selected != 1 else ''} selected")
            self.request_button.setText(f"Request Selected ({selected})")
        else:
            self.selected_label.setText("Select available items to request them")
            self.request_button.setText("Request Selected")
        self.request_button.setEnabled(selected > 0)

    def show_message(self, text: str):
        """Show a short friendly banner that hides itself after a few seconds."""
        self.banner.setText(text)
        self.banner.show()
        self._banner_timer.start()

    # ---------- reacting to clicks ----------
    def _on_row_selection_changed(self, item, checked: bool):
        if checked:
            self._selected.add(item)
        else:
            self._selected.discard(item)
        self._update_status()

    def _on_select_all_clicked(self):
        eligible = self._eligible_items()
        if eligible and all(item in self._selected for item in eligible):
            self._selected.clear()
        else:
            self._selected = set(eligible)
        for item, row in self._rows.items():
            row.set_checked(item in self._selected)
        self._update_status()

    def _on_remove_clicked(self, item):
        self.remove_item(item)
        self.show_message(f"Removed “{item.title}” from your list.")

    def _on_request_clicked(self):
        chosen = self.selected_items
        if not chosen or self._dialog_open:
            return
        self._dialog_open = True
        try:
            dialog = RequestPreviewDialog(chosen, self, submit_handler=self._submit_handler)
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._dialog_open = False
        if not accepted:
            return  # Cancel / closed: no signals, nothing changes

        drafts = dialog.drafts
        if not drafts:
            return  # safety net: an accepted dialog always has drafts
        self._prepared_drafts = drafts
        # Same payload as before: the selected CatalogItems (one per draft).
        self.request_preview_confirmed.emit([draft.item for draft in drafts])
        self.request_drafts_prepared.emit(drafts)
        if self._submit_handler is not None:
            # Saved for real (locally). Clear the ticks so Request Selected can't be
            # pressed again by accident; the items stay in My List.
            self._selected.clear()
            for row in self._rows.values():
                row.set_checked(False)
            self._update_status()
            statuses = {
                "Pending Owner Approval" if draft.item.owner_student_id is not None else "Pending"
                for draft in drafts
            }
            status_text = (next(iter(statuses)) if len(statuses) == 1 else
                           "Pending or Pending Owner Approval")
            self.show_message(
                f"{plural(len(drafts), 'request')} saved as {status_text} on this computer. "
                "Not sent to school administrators."
            )
        else:
            self.show_message(
                f"Preview only: {plural(len(drafts), 'request draft')} prepared. "
                "NOTHING was actually sent, saved or bookmarked."
            )


# ======================================================================
# 8. STYLES (QSS) - only what is NEW here; the Catalog styles are reused
# ======================================================================
MY_LIST_STYLESHEET = f"""
QWidget#myListScreen {{
    background-color: {NAVY};
}}

QDialog#myListDialog {{
    background-color: {NAVY};
}}

/* ---------- Saved item rows ---------- */
QFrame#myListRow {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 22px;
}}

QFrame#myListRow:hover {{
    background-color: white;
    border-color: {PINK};
}}

QFrame#myListRow[unavailable="true"] {{
    background-color: #ECEDFA;
    border: 3px dashed #B5B7D6;
}}

QFrame#myListRow[unavailable="true"]:hover {{
    background-color: #ECEDFA;
    border-color: #B5B7D6;
}}

QLabel#myListIcon {{
    border: 2px solid {NAVY};
    border-radius: 16px;
    font-size: 24px;
}}

QPushButton#myListCheck {{
    background-color: white;
    color: {NAVY};
    border: 3px solid {NAVY};
    border-radius: 10px;
    padding: 0px;
    font-size: 16px;
    font-weight: bold;
}}

QPushButton#myListCheck:hover {{
    border-color: {PERIWINKLE};
}}

QPushButton#myListCheck:checked {{
    background-color: {MINT};
    border-color: {NAVY};
}}

QPushButton#myListCheck:disabled {{
    background-color: #E3E4FA;
    border: 3px dashed #B5B7D6;
}}

QPushButton#myListRemoveButton {{
    background: transparent;
    color: {ERROR_RED};
    border: 2px solid {ERROR_RED};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: bold;
}}

QPushButton#myListRemoveButton:hover {{
    background-color: #FFD9E6;
}}

/* ---------- Toolbar (summary + select all) ---------- */
QFrame#myListToolbar {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 18px;
}}

QLabel#myListSummary {{
    color: {NAVY};
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#myListSelectAll {{
    background-color: {SOFT_LAVENDER};
    color: {NAVY};
    border: 2px solid {PERIWINKLE};
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton#myListSelectAll:hover {{
    background-color: {MINT};
    border-color: {NAVY};
}}

QPushButton#myListSelectAll:disabled {{
    color: #B5B7D6;
    border-color: #DDDFFA;
}}

/* ---------- Banner ---------- */
QLabel#myListBanner {{
    background-color: {MINT};
    color: {NAVY};
    border: 2px solid {NAVY};
    border-radius: 14px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: bold;
}}

/* ---------- Bottom action bar ---------- */
QFrame#myListActionBar {{
    background-color: #3A3D7A;
    border: 2px solid {PINK};
    border-radius: 18px;
}}

QLabel#myListSelectedLabel {{
    color: {CREAM};
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#myListRequestButton {{
    background-color: {MINT};
    color: {NAVY};
    border: 3px solid {NAVY};
    border-radius: 16px;
    padding: 10px 22px;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#myListRequestButton:hover {{
    background-color: {PINK};
}}

QPushButton#myListRequestButton:disabled {{
    background-color: #5A5C8F;
    color: #B5B7D6;
    border: 3px dashed #8D90BD;
}}

/* ---------- Request form (dialog) ---------- */
QLabel#myListDialogTitle {{
    color: {CREAM};
    font-size: 26px;
    font-weight: bold;
}}

QFrame#myListInfo {{
    background-color: rgba(183, 241, 225, 30);
    border: 2px solid {MINT};
    border-radius: 16px;
}}

QLabel#myListInfoText {{
    color: {MINT};
    font-size: 12px;
}}

QLabel#myListFootnote {{
    color: #B5B7D6;
    font-size: 11px;
    padding: 2px 4px;
}}

QPushButton#myListStepButton {{
    background-color: {MINT};
    color: {NAVY};
    border: 2px solid {NAVY};
    border-radius: 15px;
    padding: 0px;
    font-size: 16px;
    font-weight: bold;
}}

QPushButton#myListStepButton:hover {{
    background-color: {PINK};
}}

QFrame#myListBlocked {{
    background-color: rgba(244, 168, 196, 40);
    border: 2px solid {PINK};
    border-radius: 16px;
}}

QLabel#myListBlockedText {{
    color: {PINK};
    font-size: 13px;
    font-weight: bold;
}}

QFrame#myListPreviewRow {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 18px;
}}

/* One request form per item */
QFrame#myListDraftRow {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 20px;
}}

QLabel#myListFieldLabel {{
    color: {NAVY};
    font-size: 12px;
    font-weight: bold;
}}

QSpinBox#myListDaysSpin {{
    background-color: white;
    color: {NAVY};
    border: 2px solid {PERIWINKLE};
    border-radius: 12px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: {PERIWINKLE};
    selection-color: white;
}}

/* Hide the spin box's own tiny arrows; the round - / + buttons replace them.
   (Hiding them here, instead of setButtonSymbols(NoButtons), keeps the text visible.) */
QSpinBox#myListDaysSpin::up-button, QSpinBox#myListDaysSpin::down-button {{
    subcontrol-origin: border;
    width: 1px;
    height: 1px;
    border: none;
    background: transparent;
}}

QSpinBox#myListDaysSpin:focus {{
    border-color: {NAVY};
}}

QSpinBox#myListDaysSpin[invalid="true"] {{
    border-color: {ERROR_RED};
    background-color: #FFF0F5;
}}

/* ---------- Pickup date button + time dropdown ---------- */
QPushButton#myListDateButton {{
    background-color: white;
    color: {NAVY};
    border: 2px solid {PERIWINKLE};
    border-radius: 12px;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: bold;
    text-align: left;
}}

QPushButton#myListDateButton:hover, QPushButton#myListDateButton:focus {{
    border-color: {NAVY};
    background-color: #F1FFFA;
}}

QComboBox#myListTimeCombo {{
    background-color: white;
    color: {NAVY};
    border: 2px solid {PERIWINKLE};
    border-radius: 12px;
    padding: 6px 10px;
    font-size: 13px;
    font-weight: bold;
}}

QComboBox#myListTimeCombo:hover, QComboBox#myListTimeCombo:focus {{
    border-color: {NAVY};
}}

QComboBox#myListTimeCombo:disabled {{
    background-color: #ECEDFA;
    color: #8D90BD;
    border: 2px dashed #B5B7D6;
}}

QPushButton#myListDateButton[invalid="true"], QComboBox#myListTimeCombo[invalid="true"] {{
    border-color: {ERROR_RED};
    background-color: #FFF0F5;
}}

QComboBox#myListTimeCombo QAbstractItemView {{
    background-color: white;
    color: {NAVY};
    border: 2px solid {PERIWINKLE};
    selection-background-color: {MINT};
    selection-color: {NAVY};
    outline: 0;
    padding: 4px;
}}

QComboBox#myListTimeCombo QAbstractItemView::item {{
    min-height: 28px;
    padding-left: 8px;
}}

QLabel#myListScheduleHint {{
    color: {MUTED_TEXT};
    font-size: 12px;
}}

QLabel#myListScheduleNote {{
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: bold;
}}

QLabel#myListScheduleNote[tone="warn"] {{
    background-color: #FFD9E6;
    color: {ERROR_RED};
    border: 2px solid {ERROR_RED};
}}

QLabel#myListScheduleNote[tone="info"] {{
    background-color: {SOFT_LAVENDER};
    color: {NAVY};
    border: 2px solid {LIGHT_PERIWINKLE};
}}

QPushButton#myListJumpButton {{
    background-color: {MINT};
    color: {NAVY};
    border: 2px solid {NAVY};
    border-radius: 12px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: bold;
}}

QPushButton#myListJumpButton:hover {{
    background-color: {PINK};
}}

QLabel#myListMaxPill {{
    background-color: {SOFT_LAVENDER};
    color: {NAVY};
    border: 2px solid {LIGHT_PERIWINKLE};
    border-radius: 11px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: bold;
}}

QLabel#myListDraftSummary {{
    color: {MUTED_TEXT};
    font-size: 12px;
}}

QLabel#myListFieldError {{
    color: {ERROR_RED};
    font-size: 12px;
    font-weight: bold;
}}

QLabel#myListFormError {{
    background-color: #FFD9E6;
    color: {ERROR_RED};
    border: 2px solid {ERROR_RED};
    border-radius: 12px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: bold;
}}

QLabel#myListDialogSummary {{
    color: {CREAM};
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#myListBackButton {{
    background: transparent;
    color: {PINK};
    border: 3px solid {PINK};
    border-radius: 16px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: bold;
}}

QPushButton#myListBackButton:hover {{
    background-color: {PINK};
    color: {NAVY};
}}
"""


# The calendar popup is its own top-level window, so it carries its own styles.
CALENDAR_POPUP_STYLESHEET = f"""
QFrame#myListCalendarPopup {{
    background-color: {CREAM};
    border: 3px solid {PERIWINKLE};
    border-radius: 18px;
}}

QLabel#myListCalendarTitle {{
    color: {NAVY};
    font-size: 15px;
    font-weight: bold;
}}

QLabel#myListCalendarLegend {{
    color: {MUTED_TEXT};
    font-size: 11px;
}}

QLabel#myListCalendarNote {{
    color: {MUTED_TEXT};
    font-size: 12px;
}}

QLabel#myListCalendarNote[tone="warn"] {{
    color: {ERROR_RED};
    font-weight: bold;
}}

QCalendarWidget {{
    background-color: transparent;
}}

QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {SOFT_LAVENDER};
    border: 2px solid {LIGHT_PERIWINKLE};
    border-radius: 12px;
}}

QCalendarWidget QToolButton {{
    color: {NAVY};
    font-size: 13px;
    font-weight: bold;
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 4px 10px;
}}

QCalendarWidget QToolButton:hover {{
    background-color: {MINT};
}}

QCalendarWidget QToolButton::menu-indicator {{
    image: none;
}}

QCalendarWidget QMenu {{
    background-color: white;
    color: {NAVY};
    border: 2px solid {PERIWINKLE};
}}

QCalendarWidget QMenu::item:selected {{
    background-color: {MINT};
    color: {NAVY};
}}

QCalendarWidget QSpinBox {{
    background-color: white;
    color: {NAVY};
    border: 2px solid {PERIWINKLE};
    border-radius: 8px;
    padding: 2px 6px;
    selection-background-color: {PERIWINKLE};
    selection-color: white;
}}

QCalendarWidget QAbstractItemView:enabled {{
    background-color: white;
    color: {NAVY};
    selection-background-color: transparent;
    selection-color: {NAVY};
    outline: 0;
    border: none;
}}

QCalendarWidget QAbstractItemView:disabled {{
    color: #B5B7D6;
}}
"""
