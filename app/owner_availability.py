"""Pickup availability of an owner's listing (Step 31C). No Qt, no database in this file.

An owner chooses the weekdays an item can be collected and a pickup time range for each
(for example Mon-Fri, 9:00 AM - 5:00 PM). The longest loan is the listing's existing
`max_borrow_days`. This file holds the plain data shape, the validation and the questions
a FUTURE borrower pickup form will ask. Nothing calls them yet:

  schedule.allows_pickup(datetime)            is this pickup date/time inside a window?
  schedule.allows_borrow_days(n, max_days)    is n days within the owner's longest loan?
  schedule.summary()                          short text such as "Mon-Fri · 9:00 AM - 5:00 PM"

Weekday numbers follow Python: 0 = Monday ... 6 = Sunday. Times are minutes after midnight
(0..1440). A pickup at exactly the closing minute is NOT allowed (the window is half open).
"""
from dataclasses import dataclass

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MIN_WINDOW_MINUTES = 15
MAX_WINDOWS_PER_DAY = 3
DAY_MINUTES = 24 * 60


class AvailabilityError(Exception):
    """A schedule problem; str(error) is safe to show to the student."""

    is_user_facing = True


def format_minute(minute: int) -> str:
    """0 -> '12:00 AM', 540 -> '9:00 AM', 1020 -> '5:00 PM', 1440 -> '12:00 AM'."""
    minute = int(minute) % DAY_MINUTES
    hour, mins = divmod(minute, 60)
    suffix = "AM" if hour < 12 else "PM"
    return f"{hour % 12 or 12}:{mins:02d} {suffix}"


def _is_minute(value, low, high) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


@dataclass(frozen=True)
class AvailabilitySchedule:
    """days: {weekday: ((start_minute, end_minute), ...)} - only days that have windows."""

    days: tuple   # ((weekday, ((start, end), ...)), ...) sorted; use .as_dict() to read

    @staticmethod
    def empty() -> "AvailabilitySchedule":
        return AvailabilitySchedule(())

    @staticmethod
    def from_dict(raw) -> "AvailabilitySchedule":
        """Validate and normalise {weekday: [(start, end), ...]}; raise AvailabilityError."""
        if raw is None:
            return AvailabilitySchedule.empty()
        if isinstance(raw, AvailabilitySchedule):
            return raw
        if not isinstance(raw, dict):
            raise AvailabilityError("The availability schedule is not valid.")
        days = []
        for weekday in sorted(raw):
            if not _is_minute(weekday, 0, 6):
                raise AvailabilityError("The availability schedule has an unknown day.")
            name = WEEKDAY_NAMES[weekday]
            windows = []
            for window in raw[weekday] or ():
                try:
                    start, end = window
                except (TypeError, ValueError):
                    raise AvailabilityError(f"{name}: a pickup time range is not valid.") from None
                if not (_is_minute(start, 0, DAY_MINUTES - 1) and _is_minute(end, 1, DAY_MINUTES)):
                    raise AvailabilityError(f"{name}: a pickup time is not valid.")
                if end <= start:
                    raise AvailabilityError(f"{name}: the pickup window must end after it starts.")
                if end - start < MIN_WINDOW_MINUTES:
                    raise AvailabilityError(
                        f"{name}: a pickup window must be at least {MIN_WINDOW_MINUTES} minutes long.")
                windows.append((start, end))
            windows.sort()
            if len(windows) > MAX_WINDOWS_PER_DAY:
                raise AvailabilityError(
                    f"{name}: at most {MAX_WINDOWS_PER_DAY} pickup windows per day.")
            for (_s1, e1), (s2, _e2) in zip(windows, windows[1:]):
                if s2 < e1:
                    raise AvailabilityError(f"{name}: pickup windows must not overlap.")
            if windows:
                days.append((weekday, tuple(windows)))
        return AvailabilitySchedule(tuple(days))

    # ---------- reading ----------
    def as_dict(self) -> dict:
        return {weekday: list(windows) for weekday, windows in self.days}

    @property
    def is_empty(self) -> bool:
        return not self.days

    @property
    def weekdays(self) -> tuple:
        return tuple(weekday for weekday, _ in self.days)

    def windows_on(self, weekday: int) -> tuple:
        for day, windows in self.days:
            if day == weekday:
                return windows
        return ()

    # ---------- questions for the future borrower pickup form ----------
    def allows_pickup(self, when) -> bool:
        """True if this datetime falls on an available day inside a pickup window."""
        minute = when.hour * 60 + when.minute
        return any(start <= minute < end for start, end in self.windows_on(when.weekday()))

    @staticmethod
    def allows_borrow_days(days: int, max_borrow_days: int) -> bool:
        """True if a loan of `days` is at least one day and within the owner's longest loan."""
        return (isinstance(days, int) and not isinstance(days, bool)
                and 1 <= days <= max_borrow_days)

    # ---------- text ----------
    def summary(self) -> str:
        """A short readable line; days with the same hours are grouped (Mon-Fri)."""
        if self.is_empty:
            return "No pickup days set"
        groups = []   # [(windows, [weekdays])] in weekday order
        for weekday, windows in self.days:
            for entry in groups:
                if entry[0] == windows:
                    entry[1].append(weekday)
                    break
            else:
                groups.append((windows, [weekday]))
        parts = []
        for windows, weekdays in groups:
            hours = ", ".join(f"{format_minute(s)} - {format_minute(e)}" for s, e in windows)
            parts.append(f"{_day_text(weekdays)} · {hours}")
        return "; ".join(parts)


def _day_text(weekdays) -> str:
    """[0,1,2,3,4] -> 'Mon-Fri'; [0,2] -> 'Mon, Wed'; [0..6] -> 'Every day'."""
    if len(weekdays) == 7:
        return "Every day"
    pieces, run = [], [weekdays[0]]
    for day in weekdays[1:]:
        if day == run[-1] + 1:
            run.append(day)
        else:
            pieces.append(run)
            run = [day]
    pieces.append(run)
    texts = []
    for run in pieces:
        if len(run) >= 3:
            texts.append(f"{WEEKDAY_SHORT[run[0]]}-{WEEKDAY_SHORT[run[-1]]}")
        else:
            texts.extend(WEEKDAY_SHORT[day] for day in run)
    return ", ".join(texts)
