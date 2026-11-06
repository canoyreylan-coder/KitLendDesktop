"""KitLend My List screen (UI only - sample data, no database, no real requests).

What this file contains, from top to bottom:
  1. SAMPLE DATA      - a few saved items, picked from the Catalog's own sample items
  2. BORROWING LIMITS - SAMPLE-ONLY maximum borrowing days (not real school policy)
  3. REQUEST DRAFTS   - the RequestDraft dataclass + small validation helpers
  4. SMALL HELPERS    - who approves an item, plus the little icon badge
  5. ROW WIDGETS      - one saved-item row, one request-form row per item
  6. REQUEST DIALOG   - "Review your requests" form (pickup time + days per item)
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

One batch submission creates SEPARATE requests. Each item's lender or
administrator approves it on their own. One rejection does not cancel the others.

Both entry points use the SAME dialog (RequestPreviewDialog):
  - Catalog -> Request Now          (one item, opened by the preview runner)
  - My List -> Request Selected     (one or many items, opened in this file)
After the dialog is accepted, `dialog.drafts` holds the validated RequestDrafts.

Nothing here touches a database, logs anyone in, sends anything, or opens the
dashboard. Everything stays in memory.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# Reuse the Catalog's item model, sample items, pills and styles.
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
    TagPill,
)
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
    """Sample maximum borrowing days for this item (always at least 1)."""
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
    """A friendly starting suggestion: at least an hour from now, on a :00 or :30."""
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
    """One saved item: checkbox, icon, title, category, owner, availability, Remove."""

    selection_changed = Signal(object, bool)  # (CatalogItem, is_selected)
    remove_clicked = Signal(object)           # CatalogItem

    def __init__(self, item: CatalogItem, selected: bool = False, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("myListRow")
        self.setProperty("unavailable", not item.is_available)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        # --- selection check (disabled for unavailable items) ---
        self.check = QPushButton("")
        self.check.setObjectName("myListCheck")
        self.check.setCheckable(True)
        self.check.setFixedSize(30, 30)
        self.check.setAccessibleName(f"Select {item.title}")
        if item.is_available:
            self.check.setCursor(Qt.PointingHandCursor)
            self.check.setToolTip("Select this item to request it")
            self.check.toggled.connect(self._on_toggled)
            self.set_checked(selected)
        else:
            self.check.setEnabled(False)
            self.check.setToolTip(UNAVAILABLE_HINT)
        layout.addWidget(self.check, alignment=Qt.AlignVCenter)

        layout.addWidget(make_icon_badge(item), alignment=Qt.AlignVCenter)

        # --- title / category / owner ---
        texts = QVBoxLayout()
        texts.setSpacing(3)

        title = ElidedLabel(item.title)
        title.setObjectName("catalogItemTitle")
        texts.addWidget(title)

        category = CATEGORY_BY_NAME.get(item.category)
        icon = f"{category.icon} " if category else ""
        category_line = ElidedLabel(f"{icon}{item.category} · {item.kind}")
        category_line.setObjectName("catalogItemCreator")
        texts.addWidget(category_line)

        owner_row = QHBoxLayout()
        owner_row.setSpacing(8)
        owner_row.addWidget(TagPill(item.ownership_label, item.ownership))
        note = ElidedLabel(item.owner_note)
        note.setObjectName("catalogItemNote")
        owner_row.addWidget(note, 1)
        texts.addLayout(owner_row)
        layout.addLayout(texts, 1)

        # --- availability + remove ---
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(TagPill(item.availability_text, item.availability_tone),
                        alignment=Qt.AlignRight)
        remove = QPushButton("Remove")
        remove.setObjectName("myListRemoveButton")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setToolTip("Remove from My List")
        remove.clicked.connect(lambda: self.remove_clicked.emit(self.item))
        right.addWidget(remove, alignment=Qt.AlignRight)
        layout.addLayout(right)

    def set_checked(self, checked: bool):
        """Change the check without sending a signal (the screen already knows)."""
        if not self.item.is_available:
            return
        self.check.blockSignals(True)
        self.check.setChecked(checked)
        self.check.setText("✓" if checked else "")
        self.check.blockSignals(False)

    def _on_toggled(self, checked: bool):
        self.check.setText("✓" if checked else "")
        self.selection_changed.emit(self.item, checked)


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


class RequestDraftRow(QFrame):
    """The request form for ONE item: pickup date/time + borrowing days.

    Every row owns its own widgets, so changing one item never changes another.
    """

    def __init__(self, item: CatalogItem, now: datetime | None = None, parent=None):
        super().__init__(parent)
        self.item = item
        self.max_days = get_max_borrow_days(item)
        self.setObjectName("myListDraftRow")

        now = now or local_now()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

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

        # --- preferred pickup date and time ---
        self.pickup_edit = QDateTimeEdit()
        self.pickup_edit.setObjectName("myListPickupEdit")
        self.pickup_edit.setCalendarPopup(True)  # click the arrow to open a calendar
        self.pickup_edit.setDisplayFormat("ddd, MMM d, yyyy 'at' h:mm AP")
        self.pickup_edit.setMinimumDate(QDate(now.year, now.month, now.day))  # no past days
        first = suggested_pickup(now)
        self.pickup_edit.setDateTime(
            QDateTime(QDate(first.year, first.month, first.day), QTime(first.hour, first.minute))
        )
        self.pickup_edit.setAccessibleName(f"Preferred pickup for {item.title}")
        self.pickup_edit.setToolTip(
            "Your preferred pickup time. The lender or administrator makes the final decision."
        )

        # --- borrowing days ---
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

        max_pill = QLabel(f"Sample max: {plural(self.max_days, 'day')}")
        max_pill.setObjectName("myListMaxPill")
        max_pill.setToolTip(
            "A sample limit for this preview only. The real limit will be set by "
            "the lender or administrator."
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.addWidget(self._field_label("Preferred pickup"), 0, 0, Qt.AlignVCenter)
        grid.addWidget(self.pickup_edit, 0, 1)
        grid.addWidget(self._field_label("Borrow for"), 1, 0, Qt.AlignVCenter)
        duration_row = QHBoxLayout()
        duration_row.setSpacing(6)
        duration_row.addWidget(minus_button)
        duration_row.addWidget(self.days_spin)
        duration_row.addWidget(plus_button)
        duration_row.addSpacing(6)
        duration_row.addWidget(max_pill)
        duration_row.addStretch()
        grid.addLayout(duration_row, 1, 1)
        outer.addLayout(grid)

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

        self.pickup_edit.dateTimeChanged.connect(self._on_input_changed)
        self.days_spin.valueChanged.connect(self._on_input_changed)
        self._refresh_summary()

    # ---------- reading the student's choices ----------
    def pickup_at(self) -> datetime:
        return qdatetime_to_local_aware(self.pickup_edit.dateTime())

    def days(self) -> int:
        return self.days_spin.value()

    def validate(self, now: datetime | None = None) -> bool:
        """Check every field of this row, show any problems, return True if all fine."""
        now = now or local_now()
        pickup_error = validate_pickup(self.pickup_at(), now)
        days_error = validate_days(self.days(), self.max_days)
        availability_error = "" if self.item.is_available else (
            "This item is no longer available, so it can't be requested."
        )

        self._mark_invalid(self.pickup_edit, bool(pickup_error))
        self._mark_invalid(self.days_spin, bool(days_error))

        messages = [m for m in (availability_error, pickup_error, days_error) if m]
        self.error_label.setText("\n".join(messages))
        self.error_label.setVisible(bool(messages))
        return not messages

    def to_draft(self) -> RequestDraft:
        """Build the RequestDraft (call only after validate() returned True)."""
        return RequestDraft(
            item=self.item,
            pickup_at=self.pickup_at(),
            days=self.days(),
            max_days=self.max_days,
        )

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
        widget.setProperty("invalid", invalid)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _on_input_changed(self, _value=None):
        self._update_days_suffix(self.days_spin.value())
        # The student is fixing things: hide the old complaint until Confirm again.
        self._mark_invalid(self.pickup_edit, False)
        self._mark_invalid(self.days_spin, False)
        self.error_label.hide()
        self._refresh_summary()

    def _refresh_summary(self):
        # No due date here on purpose: the clock only starts at the confirmed handover.
        self.summary_label.setText(
            f"Request: borrow for {plural(self.days(), 'day')} · "
            f"preferred pickup {format_pickup(self.pickup_at())}"
        )


# ======================================================================
# 6. REQUEST DIALOG
# ======================================================================
class RequestPreviewDialog(QDialog):
    """'Review your requests' - the borrowing request form. Submits nothing.

    Usage (same for Catalog and My List):
        dialog = RequestPreviewDialog(items, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            drafts = dialog.drafts      # list of RequestDraft, one per item

    Confirm validates EVERYTHING again (availability, pickup time, days). If
    anything is wrong the dialog stays open and explains it. Cancel / closing
    the window never produces drafts.
    """

    def __init__(self, items, parent=None):
        super().__init__(parent)
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
        requestable = [item for item in unique if item.is_available]
        blocked = [item for item in unique if not item.is_available]

        self._rows = []        # one RequestDraftRow per requestable item
        self._drafts = []      # filled only after a successful Confirm
        self._finished = False  # stops a second accept (no duplicate confirmations)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        tag = QLabel("Preview only · Nothing is sent yet")
        tag.setObjectName("catalogTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        layout.addWidget(tag, alignment=Qt.AlignLeft)

        title = QLabel("Review your requests")
        title.setObjectName("myListDialogTitle")
        layout.addWidget(title)

        # Notes + one form per item scroll together; the buttons stay visible below.
        self.scroll = QScrollArea()
        self.scroll.setObjectName("catalogScroll")
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
            row = RequestDraftRow(item, now)
            self._rows.append(row)
            inner_layout.addWidget(row)

        footnote = QLabel(
            "Each item becomes its own separate request, and each lender or administrator "
            "approves theirs independently - one rejection won't cancel the others. "
            f"Times use your local time zone ({local_timezone_label()}). Borrowing limits "
            "shown here are sample values for this preview only."
        )
        footnote.setObjectName("myListFootnote")
        footnote.setWordWrap(True)
        inner_layout.addWidget(footnote)
        inner_layout.addStretch()
        self.scroll.setWidget(inner)
        layout.addWidget(self.scroll, 1)

        count = len(self._rows)
        self.summary_label = QLabel(
            f"{plural(count, 'separate request')} would be created"
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
        self.confirm_button = QPushButton("Confirm (Preview Only)")
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

        self._drafts = [row.to_draft() for row in self._rows]
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
            "Your preferred pickup schedule is subject to lender or administrator approval.",
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
        self.resize(660, max(height, 440))
        self.setMinimumSize(520, 420)


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
        self.setStyleSheet(CATALOG_STYLESHEET + MY_LIST_STYLESHEET)  # only this screen

        self._saved_items = []   # CatalogItem objects, in the order they were saved
        self._selected = set()   # the selected ones (always available items)
        self._rows = {}          # CatalogItem -> SavedItemRow
        self._prepared_drafts = []   # drafts from the latest successful confirmation
        self._dialog_open = False    # stops two forms from opening at once

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

    def set_saved_items(self, items):
        """Replace the whole saved list (duplicates are ignored)."""
        unique = []
        for item in items:
            if item not in unique:
                unique.append(item)
        self._saved_items = unique
        self._selected = {item for item in self._selected
                          if item in unique and item.is_available}
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
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Header, toolbar, rows and empty state all scroll together;
        # only the action bar stays fixed at the bottom.
        scroll = QScrollArea()
        scroll.setObjectName("catalogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("catalogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 8)
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
        self.rows_container.setObjectName("catalogContent")
        self._rows_layout = QVBoxLayout(self.rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(10)
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
        header.setObjectName("catalogHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(26, 18, 26, 18)
        layout.setSpacing(12)

        texts = QVBoxLayout()
        texts.setSpacing(8)
        tag = QLabel("Preview · Sample data only")
        tag.setObjectName("catalogTag")
        tag.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        texts.addWidget(tag, alignment=Qt.AlignLeft)

        title = QLabel("My List")
        title.setObjectName("catalogTitle")
        texts.addWidget(title)

        subtitle = QLabel(
            "Items you saved for later. Select the available ones and request "
            "them together."
        )
        subtitle.setObjectName("catalogSubtitle")
        subtitle.setWordWrap(True)
        texts.addWidget(subtitle)
        texts.addStretch()
        layout.addLayout(texts, 1)

        pixmap = QPixmap(str(HAPPY_MASCOT_PATH))
        if not pixmap.isNull():
            mascot = QLabel()
            mascot.setPixmap(pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(mascot, 0, Qt.AlignTop | Qt.AlignRight)
        return header

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("myListToolbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 10, 12, 10)
        layout.setSpacing(12)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("myListSummary")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label, 1)

        self.select_all_button = QPushButton("Select all eligible")
        self.select_all_button.setObjectName("myListSelectAll")
        self.select_all_button.setCursor(Qt.PointingHandCursor)
        self.select_all_button.clicked.connect(self._on_select_all_clicked)
        layout.addWidget(self.select_all_button)
        return bar

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("myListActionBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 10, 12, 10)
        layout.setSpacing(12)

        self.selected_label = QLabel("")
        self.selected_label.setObjectName("myListSelectedLabel")
        layout.addWidget(self.selected_label, 1)

        self.request_button = QPushButton("Request Selected")
        self.request_button.setObjectName("myListRequestButton")
        self.request_button.setCursor(Qt.PointingHandCursor)
        self.request_button.clicked.connect(self._on_request_clicked)
        layout.addWidget(self.request_button)
        return bar

    def _build_empty_state(self) -> QFrame:
        box = QFrame()
        box.setObjectName("catalogEmpty")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignHCenter)

        pixmap = QPixmap(str(CURIOUS_MASCOT_PATH))
        icon = QLabel()
        icon.setObjectName("catalogEmptyIcon")
        icon.setAlignment(Qt.AlignCenter)
        if not pixmap.isNull():
            icon.setPixmap(pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon.setText("🔖")  # a missing image file must never crash the app
        layout.addWidget(icon)

        title = QLabel("Your list is empty")
        title.setObjectName("catalogEmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        text = QLabel(
            "Found something you like? Save it from the catalog and it will "
            "wait for you here, ready to request whenever you are."
        )
        text.setObjectName("catalogEmptyText")
        text.setAlignment(Qt.AlignCenter)
        text.setWordWrap(True)
        layout.addWidget(text)

        button = QPushButton("Browse Catalog")
        button.setObjectName("catalogPrimaryButton")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.browse_catalog_requested.emit)
        layout.addWidget(button, alignment=Qt.AlignHCenter)
        return box

    # ---------- refreshing what is shown ----------
    def _eligible_items(self) -> list:
        return [item for item in self._saved_items if item.is_available]

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
            dialog = RequestPreviewDialog(chosen, self)
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

QDateTimeEdit#myListPickupEdit, QSpinBox#myListDaysSpin {{
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

QDateTimeEdit#myListPickupEdit:focus, QSpinBox#myListDaysSpin:focus {{
    border-color: {NAVY};
}}

QDateTimeEdit#myListPickupEdit[invalid="true"], QSpinBox#myListDaysSpin[invalid="true"] {{
    border-color: {ERROR_RED};
    background-color: #FFF0F5;
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

/* The calendar that pops open from the pickup box */
QCalendarWidget QAbstractItemView {{
    background-color: white;
    color: {NAVY};
    selection-background-color: {PERIWINKLE};
    selection-color: white;
}}

QCalendarWidget QToolButton {{
    color: {NAVY};
    font-weight: bold;
}}

QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background-color: {SOFT_LAVENDER};
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
