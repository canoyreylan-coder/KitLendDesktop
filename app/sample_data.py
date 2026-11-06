"""Sample data for the Student Dashboard DEMO.

Everything in this file is MADE UP. Nothing is read from, or saved to, a
database, and nobody is authenticated. Dates are calculated from today's date
so the demo always looks fresh (e.g. "Due tomorrow" is always true).

This file has no PySide6 code on purpose: it is just plain Python, which makes
it easy to read and to replace with real data in a later step.
"""
from dataclasses import dataclass
from datetime import date, timedelta


# ---------- small text helpers ----------
def plural(count: int, word: str) -> str:
    """plural(1, 'item') -> '1 item', plural(3, 'item') -> '3 items'."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def format_short_date(day: date) -> str:
    """date(2026, 10, 20) -> 'Oct 20' (works the same on Windows/Mac/Linux)."""
    return f"{day:%b} {day.day}"


def format_weekday_date(day: date) -> str:
    """date(2026, 10, 20) -> 'Tue, Oct 20'."""
    return f"{day:%a}, {day:%b} {day.day}"


def describe_days_left(days_left: int) -> str:
    """Turn a number of days into friendly text for a status pill."""
    if days_left < 0:
        return f"Overdue {plural(-days_left, 'day')}"
    if days_left == 0:
        return "Due today"
    if days_left == 1:
        return "Due tomorrow"
    return f"{days_left} days left"


def due_tone(days_left: int) -> str:
    """Pick a pill color name (see theme.py) based on how urgent a due date is."""
    if days_left < 0:
        return "alert"
    if days_left <= 1:
        return "pink"
    if days_left <= 3:
        return "purple"
    return "mint"


def describe_days_ago(days_ago: int) -> str:
    if days_ago <= 0:
        return "Today"
    if days_ago == 1:
        return "Yesterday"
    return f"{days_ago} days ago"


# ---------- the data shapes ----------
@dataclass(frozen=True)
class DemoStudent:
    full_name: str

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0]

    @property
    def initials(self) -> str:
        parts = self.full_name.split()
        return (parts[0][0] + parts[-1][0]).upper()


@dataclass(frozen=True)
class BorrowedItem:
    title: str
    category: str      # "Book", "Gadget" or "Tool"
    borrowed_on: date
    due_on: date

    @property
    def days_left(self) -> int:
        return (self.due_on - date.today()).days

    @property
    def loan_progress(self) -> int:
        """How much of the loan period has passed, as a 0-100 percentage."""
        total_days = max((self.due_on - self.borrowed_on).days, 1)
        used_days = (date.today() - self.borrowed_on).days
        return max(0, min(100, round(used_days / total_days * 100)))


@dataclass(frozen=True)
class Reservation:
    title: str
    category: str
    status: str        # "Ready for pickup" or "In queue"
    detail: str        # e.g. "Pick up by Oct 19"

    @property
    def is_ready(self) -> bool:
        return self.status == "Ready for pickup"


@dataclass(frozen=True)
class Notification:
    title: str
    message: str
    days_ago: int
    unread: bool


@dataclass(frozen=True)
class ActivityEntry:
    kind: str          # "borrowed", "returned", "reserved" or "renewed"
    text: str
    days_ago: int


@dataclass(frozen=True)
class DemoData:
    """Everything the demo dashboard shows, bundled in one object."""

    student: DemoStudent
    borrowings: list[BorrowedItem]
    reservations: list[Reservation]
    notifications: list[Notification]
    activity: list[ActivityEntry]

    def due_soon(self, within_days: int = 3) -> list[BorrowedItem]:
        soon = [item for item in self.borrowings if item.days_left <= within_days]
        return sorted(soon, key=lambda item: item.due_on)

    def borrowings_by_due_date(self) -> list[BorrowedItem]:
        return sorted(self.borrowings, key=lambda item: item.due_on)

    @property
    def unread_count(self) -> int:
        return sum(1 for note in self.notifications if note.unread)

    @property
    def ready_reservation_count(self) -> int:
        return sum(1 for reservation in self.reservations if reservation.is_ready)


def build_demo_data() -> DemoData:
    """Create a fresh set of realistic sample data (dates are relative to today)."""
    today = date.today()

    def from_today(days: int) -> date:
        return today + timedelta(days=days)

    return DemoData(
        student=DemoStudent(full_name="Juan Dela Cruz"),
        borrowings=[
            BorrowedItem("Arduino Uno Starter Kit", "Gadget", from_today(-6), from_today(1)),
            BorrowedItem("Introduction to Algorithms (CLRS)", "Book", from_today(-11), from_today(3)),
            BorrowedItem("Casio fx-991EX Calculator", "Gadget", from_today(-3), from_today(4)),
            BorrowedItem("Digital Multimeter", "Tool", from_today(-1), from_today(6)),
        ],
        reservations=[
            Reservation(
                "Operating System Concepts", "Book", "Ready for pickup",
                f"Pick up by {format_short_date(from_today(2))}",
            ),
            Reservation(
                "Raspberry Pi 4 Starter Kit", "Gadget", "In queue",
                "Position #2 in line",
            ),
        ],
        notifications=[
            Notification("Due tomorrow", "Arduino Uno Starter Kit is due tomorrow.", 0, True),
            Notification("Reservation ready", "Operating System Concepts is ready for pickup.", 0, True),
            Notification("Due date approaching", "Introduction to Algorithms (CLRS) is due in 3 days.", 1, True),
            Notification("Welcome to KitLend!", "Return items on time to keep borrowing smoothly.", 6, False),
        ],
        activity=[
            ActivityEntry("borrowed", "Borrowed Digital Multimeter", 1),
            ActivityEntry("reserved", "Reserved Raspberry Pi 4 Starter Kit", 2),
            ActivityEntry("borrowed", "Borrowed Casio fx-991EX Calculator", 3),
            ActivityEntry("reserved", "Reserved Operating System Concepts", 4),
            ActivityEntry("returned", "Returned Soldering Iron Kit", 5),
            ActivityEntry("borrowed", "Borrowed Arduino Uno Starter Kit", 6),
            ActivityEntry("renewed", "Renewed Introduction to Algorithms (CLRS)", 8),
        ],
    )


def build_empty_data(full_name: str) -> DemoData:
    """Data for a REAL signed-in student: nothing borrowed, reserved or notified yet.

    Real borrowing records will come from the backend in a later step.
    """
    return DemoData(
        student=DemoStudent(full_name=full_name),
        borrowings=[],
        reservations=[],
        notifications=[],
        activity=[],
    )
