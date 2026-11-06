"""Preview the My Requests screen on its own:   python preview_my_requests.py

Run it from the project folder (the one that contains `app/`). It shows only
the My Requests screen with sample requests - no login, no dashboard, no
database. Cancelling is simulated in memory and nothing is ever sent.
The pink strip at the top is a preview tool, not part of the real screen.

Checks (no window needed to read the results):
    python preview_my_requests.py --selftest
runs the borrowing/pickup checks and exits. The same checks run when you click
"Run checks" in the pink strip. The due-date formula is checked on its own,
separately from the interface.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make `import app...` work no matter where the script is started from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import app.my_requests_screen as requests_module  # noqa: E402
from app.catalog_screen import SAMPLE_ITEMS  # noqa: E402
from app.my_requests_screen import (  # noqa: E402
    BORROWING_RULE_TEXT,
    STATUS_INFO,
    BorrowRequest,
    CancelRequestDialog,
    MyRequestsScreen,
    RequestStatus,
    build_sample_requests,
    compute_due_at,
    format_dt,
    request_facts,
)
from app.theme import NAVY, PINK, STYLESHEET  # noqa: E402


# ======================================================================
# CHECKS - plain Python, read top to bottom
# ======================================================================
class CheckRunner:
    """Counts passed checks and remembers the failed ones."""

    def __init__(self):
        self.passed = 0
        self.failures = []

    def check(self, condition, label):
        if condition:
            self.passed += 1
        else:
            self.failures.append(label)

    def expect_error(self, label, function, *args, **kwargs):
        """The call must raise ValueError (that is how the model refuses bad input)."""
        try:
            function(*args, **kwargs)
        except ValueError:
            self.passed += 1
        else:
            self.failures.append(f"{label} (expected a ValueError)")

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        if self.ok:
            return f"All {self.passed} checks passed."
        return f"{len(self.failures)} check(s) FAILED, {self.passed} passed."


# Fixed, timezone-aware times (UTC+8) so the checks give the same answer anywhere.
CHECK_TZ = timezone(timedelta(hours=8))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """October `day`, 2026 at hour:minute (UTC+8)."""
    return datetime(2026, 10, day, hour, minute, tzinfo=CHECK_TZ)


CHECK_NOW = at(17, 12)  # "now" for the sample-data checks: Oct 17, 2026, 12:00 PM
ARDUINO = next(item for item in SAMPLE_ITEMS if item.title == "Arduino Uno Starter Kit")


def example_request(status, **overrides) -> BorrowRequest:
    """The Arduino example: max 5 days, student chose 4, submitted Oct 17,
    preferred pickup Oct 20 at 3:00 PM, approved Oct 18, deadline Oct 20 at 5:00 PM."""
    values = dict(
        request_id="CHECK-1", item=ARDUINO, max_days=5, requested_days=4,
        submitted_at=at(17, 10), status=status, preferred_pickup_at=at(20, 15),
    )
    if status not in (RequestStatus.PENDING, RequestStatus.REJECTED):
        values.update(approved_at=at(18, 9), scheduled_pickup_at=at(20, 15),
                      pickup_deadline=at(20, 17))
    if status in (RequestStatus.BORROWED, RequestStatus.RETURN_PENDING, RequestStatus.RETURNED):
        values.update(picked_up_at=at(20, 15))
    if status in (RequestStatus.RETURN_PENDING, RequestStatus.RETURNED):
        values.update(status_changed_at=at(24, 10))
    values.update(overrides)
    return BorrowRequest(**values)


def snapshot(request):
    """Everything about a request that cancelling ANOTHER request must not change."""
    return (request.status, request.approved_at, request.scheduled_pickup_at,
            request.pickup_deadline, request.picked_up_at, request.status_changed_at,
            request.due_at, len(request.status_history))


def run_model_checks() -> CheckRunner:
    """Checks for the rules, the model and the sample data. No windows involved."""
    r = CheckRunner()

    # --- 1. The due-date formula on its own ---
    r.check(compute_due_at(at(20, 15), 4) == at(24, 15),
            "formula: Oct 20 3:00 PM + 4 days = Oct 24 3:00 PM")
    r.check(compute_due_at(at(20, 15), 1) - at(20, 15) == timedelta(hours=24),
            "formula: 1 day is exactly 24 hours")
    r.check(compute_due_at(at(20, 15), 30) - at(20, 15) == timedelta(hours=720),
            "formula: 30 days is exactly 720 hours")
    r.check(compute_due_at(at(20, 15).astimezone(timezone.utc), 4) == at(24, 15),
            "formula: same moment in another timezone gives the same due moment")
    r.check(compute_due_at(None, 4) is None, "formula: no pickup -> no due date")
    r.expect_error("formula: naive pickup time", compute_due_at, datetime(2026, 10, 20, 15), 4)
    r.expect_error("formula: zero days", compute_due_at, at(20, 15), 0)

    # --- 2. The example from the policy ---
    borrowed = example_request(RequestStatus.BORROWED)
    r.check(borrowed.due_at == at(24, 15), "example: due Oct 24, 2026 at 3:00 PM")
    r.check(borrowed.due_at != at(18, 9) + timedelta(days=4),
            "example: due date is NOT approval time + days")
    r.check(borrowed.countdown_started, "example: borrowed -> countdown started")

    # --- 3. Approval alone does not start the countdown ---
    awaiting = example_request(RequestStatus.APPROVED)
    r.check(awaiting.due_at is None, "approved: no due date")
    r.check(awaiting.picked_up_at is None and not awaiting.countdown_started,
            "approved: no actual pickup, countdown not started")
    r.check(("Borrowing period", "Borrowing period not started", False)
            in request_facts(awaiting, at(19, 12)),
            "approved: card says 'Borrowing period not started'")
    r.expect_error("approved with an actual pickup time",
                   example_request, RequestStatus.APPROVED, picked_up_at=at(20, 15))

    # --- 4. Late but still valid pickup: the due date counts from the ACTUAL handover ---
    late = example_request(RequestStatus.APPROVED)
    late.confirm_pickup(at(20, 16, 30))
    r.check(late.status is RequestStatus.BORROWED and late.picked_up_at == at(20, 16, 30),
            "late pickup: becomes Borrowed with the actual time recorded")
    r.check(late.due_at == at(24, 16, 30), "late pickup: due Oct 24 4:30 PM (from actual pickup)")
    r.check(late.due_at != at(24, 15), "late pickup: NOT counted from the scheduled 3:00 PM")
    r.check(late.status_history[-1].status is RequestStatus.BORROWED,
            "late pickup: history ends with Borrowed")

    # --- 5. Missed pickup: no handover without a new valid arrangement ---
    too_late = example_request(RequestStatus.APPROVED)
    r.expect_error("pickup after the deadline", too_late.confirm_pickup, at(20, 17, 1))
    r.check(too_late.status is RequestStatus.APPROVED and too_late.picked_up_at is None,
            "too late: request unchanged after the refused pickup")
    r.expect_error("pickup of an expired reservation",
                   example_request(RequestStatus.EXPIRED).confirm_pickup, at(20, 16))
    r.expect_error("pickup of a pending request",
                   example_request(RequestStatus.PENDING).confirm_pickup, at(20, 16))
    r.expect_error("pickup before the approval",
                   example_request(RequestStatus.APPROVED).confirm_pickup, at(18, 8))

    # --- 6. The model refuses impossible requests ---
    r.expect_error("borrowed without an actual pickup", example_request,
                   RequestStatus.BORROWED, picked_up_at=None)
    r.expect_error("returned without an actual pickup", example_request,
                   RequestStatus.RETURNED, picked_up_at=None)
    r.expect_error("cancelled with an actual pickup", example_request,
                   RequestStatus.CANCELLED, picked_up_at=at(20, 15), status_changed_at=at(21, 9))
    r.expect_error("more days than the maximum", example_request,
                   RequestStatus.PENDING, requested_days=6)
    r.expect_error("naive timestamp", example_request,
                   RequestStatus.PENDING, preferred_pickup_at=datetime(2026, 10, 20, 15))
    r.expect_error("pickup before approval", example_request,
                   RequestStatus.BORROWED, picked_up_at=at(18, 8))
    r.expect_error("pickup after the pickup deadline", example_request,
                   RequestStatus.BORROWED, picked_up_at=at(20, 18))
    r.expect_error("pending with a pickup arrangement", example_request,
                   RequestStatus.PENDING, scheduled_pickup_at=at(20, 15))
    r.expect_error("approved without a pickup deadline", example_request,
                   RequestStatus.APPROVED, pickup_deadline=None)

    # --- 7. The sample requests tell the right story ---
    samples = build_sample_requests(CHECK_NOW)
    by_status = {request.status: request for request in samples}
    r.check(len(samples) == 8 and len(by_status) == 8, "samples: one request per status")
    r.check(len({request.request_id for request in samples}) == 8, "samples: unique IDs")

    pending = by_status[RequestStatus.PENDING]
    r.check(pending.preferred_pickup_at is not None and pending.approved_at is None
            and pending.picked_up_at is None and pending.due_at is None,
            "sample Pending: preferred pickup shown, no approval, no pickup, no due date")

    approved = by_status[RequestStatus.APPROVED]
    r.check(approved.approved_at is not None and approved.scheduled_pickup_at is not None
            and approved.pickup_deadline is not None
            and approved.picked_up_at is None and approved.due_at is None,
            "sample Approved: reserved with a pickup arrangement, no pickup, no due date")

    sample_borrowed = by_status[RequestStatus.BORROWED]
    r.check(sample_borrowed.due_at == sample_borrowed.picked_up_at
            + timedelta(days=sample_borrowed.requested_days),
            "sample Borrowed: due date = actual pickup + days")
    r.check(sample_borrowed.picked_up_at > sample_borrowed.scheduled_pickup_at,
            "sample Borrowed: collected after the scheduled time, due date still from actual pickup")

    waiting_return = by_status[RequestStatus.RETURN_PENDING]
    r.check(waiting_return.due_at == waiting_return.picked_up_at
            + timedelta(days=waiting_return.requested_days)
            and waiting_return.status_changed_at is not None,
            "sample Return Pending: original pickup and due dates kept")

    returned = by_status[RequestStatus.RETURNED]
    r.check(returned.picked_up_at is not None and returned.due_at is not None
            and returned.status_changed_at is not None,
            "sample Returned: pickup, due date and return time kept")

    cancelled = by_status[RequestStatus.CANCELLED]
    r.check(cancelled.approved_at is not None and cancelled.scheduled_pickup_at is not None
            and cancelled.picked_up_at is None and cancelled.due_at is None,
            "sample Cancelled reservation: approval kept, no pickup, no due date")

    expired = by_status[RequestStatus.EXPIRED]
    r.check(expired.picked_up_at is None and expired.due_at is None
            and expired.pickup_deadline is not None,
            "sample Expired: no pickup, no due date")

    rejected = by_status[RequestStatus.REJECTED]
    r.check(rejected.approved_at is None and rejected.due_at is None,
            "sample Rejected: no approval, no due date")

    r.check(all(request.submitted_at <= CHECK_NOW for request in samples)
            and all(request.approved_at is None or request.approved_at <= CHECK_NOW for request in samples)
            and all(request.picked_up_at is None or request.picked_up_at <= CHECK_NOW for request in samples),
            "samples: submission, approval and pickup are never in the future")
    r.check(all(request.status_history[-1].status is request.status for request in samples),
            "samples: each history ends with the current status")

    # --- 8. What the cards say ---
    for request in samples:
        facts = {label: value for label, value, _muted in request_facts(request, CHECK_NOW)}
        label = request.status.info.label
        r.check("Preferred pickup" in facts, f"card {label}: shows the preferred pickup")
        if request.due_at is not None:
            r.check(facts.get("Due date") == format_dt(request.due_at),
                    f"card {label}: due date matches the formula")
        else:
            r.check(facts.get("Due date", "").startswith(("Not set", "None")),
                    f"card {label}: no due date is shown")
    old_phrases = ("approval time +", "counts from the approval", "starts once the request is approved",
                   "has already started")
    texts = [info.description for info in STATUS_INFO.values()] + [BORROWING_RULE_TEXT]
    r.check(not any(phrase in text for text in texts for phrase in old_phrases),
            "wording: nothing says approval starts the borrowing countdown")
    r.check("Approval does not start the countdown" in BORROWING_RULE_TEXT,
            "wording: the rule box says approval does not start the countdown")
    r.check(STATUS_INFO[RequestStatus.APPROVED].label == "Approved — Awaiting Pickup",
            "wording: student-facing name for the approved status")

    # --- 9. Cancellation rules (model) ---
    expected_cancellable = {RequestStatus.PENDING, RequestStatus.APPROVED}
    for status, request in by_status.items():
        r.check(request.can_cancel == (status in expected_cancellable),
                f"cancel rule: {status.info.label}")
        if status not in expected_cancellable:
            r.expect_error(f"cancelling {status.info.label}", request.cancel, CHECK_NOW)

    fresh = {request.request_id: request for request in build_sample_requests(CHECK_NOW)}
    before = {rid: snapshot(request) for rid, request in fresh.items()}
    fresh["REQ-1001"].cancel(CHECK_NOW)  # Pending
    r.check(fresh["REQ-1001"].status is RequestStatus.CANCELLED
            and fresh["REQ-1001"].picked_up_at is None and fresh["REQ-1001"].due_at is None,
            "cancel Pending: becomes Cancelled, no pickup, no due date")
    r.check(all(snapshot(fresh[rid]) == before[rid] for rid in fresh if rid != "REQ-1001"),
            "cancel Pending: every other request is unchanged")

    fresh = {request.request_id: request for request in build_sample_requests(CHECK_NOW)}
    before = {rid: snapshot(request) for rid, request in fresh.items()}
    reservation = fresh["REQ-1002"]
    approved_at, scheduled, deadline = (reservation.approved_at, reservation.scheduled_pickup_at,
                                        reservation.pickup_deadline)
    reservation.cancel(CHECK_NOW)  # Approved — Awaiting Pickup
    r.check(reservation.status is RequestStatus.CANCELLED and reservation.picked_up_at is None
            and reservation.due_at is None, "cancel Approved: becomes Cancelled, no pickup, no due date")
    r.check((reservation.approved_at, reservation.scheduled_pickup_at, reservation.pickup_deadline)
            == (approved_at, scheduled, deadline), "cancel Approved: approval history is preserved")
    r.check(all(snapshot(fresh[rid]) == before[rid] for rid in fresh if rid != "REQ-1002"),
            "cancel Approved: every other request is unchanged")
    return r


def run_screen_checks() -> CheckRunner:
    """Checks that use the real screen and dialog. Needs a QApplication to exist.

    The confirmation dialog is replaced by an automatic 'Yes' / 'No' only for these
    checks, so nothing waits for a click. Nothing is shown on screen.
    """
    r = CheckRunner()
    original_dialog = CancelRequestDialog

    class AlwaysYes(original_dialog):
        def exec(self):
            return QDialog.DialogCode.Accepted

    class AlwaysNo(original_dialog):
        def exec(self):
            return QDialog.DialogCode.Rejected

    try:
        screen = MyRequestsScreen(build_sample_requests(CHECK_NOW), clock=lambda: CHECK_NOW)
        cancelled_events = []
        screen.request_cancelled.connect(cancelled_events.append)
        by_id = {request.request_id: request for request in screen.requests}
        before = {rid: snapshot(request) for rid, request in by_id.items()}

        # Pending: "No" changes nothing, "Yes" cancels only that request.
        requests_module.CancelRequestDialog = AlwaysNo
        screen._on_cancel_clicked(by_id["REQ-1001"])
        r.check(by_id["REQ-1001"].status is RequestStatus.PENDING and not cancelled_events,
                "screen: declining the confirmation keeps the Pending request")
        requests_module.CancelRequestDialog = AlwaysYes
        screen._on_cancel_clicked(by_id["REQ-1001"])
        r.check(by_id["REQ-1001"].status is RequestStatus.CANCELLED
                and cancelled_events == [by_id["REQ-1001"]],
                "screen: confirming cancels the Pending request and emits request_cancelled once")
        r.check(all(snapshot(by_id[rid]) == before[rid] for rid in by_id if rid != "REQ-1001"),
                "screen: other requests unchanged after cancelling the Pending one")
        r.check("Your other requests were not changed" in screen.banner.text(),
                "screen: banner says other requests were not changed")

        # Approved — Awaiting Pickup: confirmed, reservation released, history kept.
        screen._on_cancel_clicked(by_id["REQ-1002"])
        reservation = by_id["REQ-1002"]
        r.check(reservation.status is RequestStatus.CANCELLED and reservation.picked_up_at is None
                and reservation.due_at is None and reservation.approved_at is not None,
                "screen: cancelling the reservation keeps approval history, no pickup or due date")
        r.check("reservation was released" in screen.banner.text(),
                "screen: banner says the reservation was released")
        r.check(cancelled_events == [by_id["REQ-1001"], reservation],
                "screen: one signal per cancelled request")
        r.check(all(snapshot(by_id[rid]) == before[rid]
                    for rid in by_id if rid not in ("REQ-1001", "REQ-1002")),
                "screen: the remaining requests are still unchanged")

        # Borrowed / Return Verification Pending cannot be cancelled from the screen.
        for rid in ("REQ-1003", "REQ-1004"):
            event_count = len(cancelled_events)
            screen._on_cancel_clicked(by_id[rid])
            r.check(by_id[rid].status in (RequestStatus.BORROWED, RequestStatus.RETURN_PENDING)
                    and len(cancelled_events) == event_count,
                    f"screen: {rid} cannot be cancelled")

        # The dialogs: the reservation one asks for an extra tick before the red button works.
        requests_module.CancelRequestDialog = original_dialog
        fresh = {request.request_id: request for request in build_sample_requests(CHECK_NOW)}
        pending_dialog = original_dialog(fresh["REQ-1001"])
        r.check(pending_dialog.acknowledge is None and pending_dialog.confirm_button.isEnabled(),
                "dialog: Pending needs only the confirmation button")
        reserved_dialog = original_dialog(fresh["REQ-1002"])
        r.check(reserved_dialog.acknowledge is not None
                and not reserved_dialog.confirm_button.isEnabled(),
                "dialog: reservation cancel is locked until acknowledged")
        reserved_dialog.acknowledge.setChecked(True)
        r.check(reserved_dialog.confirm_button.isEnabled(),
                "dialog: reservation cancel unlocks after acknowledging")
        pending_dialog.deleteLater()
        reserved_dialog.deleteLater()

        # Reset and empty state still work.
        screen.set_requests(build_sample_requests(CHECK_NOW))
        r.check(len(screen.visible_requests) == 8
                and all(request.status is not RequestStatus.CANCELLED
                        or request.request_id == "REQ-1007" for request in screen.visible_requests),
                "screen: reset restores the original sample requests")
        screen.set_requests([])
        r.check(screen.visible_requests == [], "screen: empty state shows no cards")
    finally:
        requests_module.CancelRequestDialog = original_dialog
    return r


def run_all_checks() -> CheckRunner:
    """Model checks, then screen checks (the second needs a running QApplication)."""
    combined = run_model_checks()
    if QApplication.instance() is not None:
        screen_results = run_screen_checks()
        combined.passed += screen_results.passed
        combined.failures += screen_results.failures
    return combined


# ======================================================================
# PREVIEW WINDOW
# ======================================================================
class MyRequestsPreviewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KitLend Desktop - My Requests (Preview, sample data)")
        self.resize(1000, 700)
        self.setMinimumSize(800, 500)

        central = QWidget()
        central.setObjectName("previewCentral")
        central.setStyleSheet(f"QWidget#previewCentral {{ background-color: {NAVY}; }}")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central)

        self.requests_screen = MyRequestsScreen(build_sample_requests())
        layout.addWidget(self._build_tool_strip())
        layout.addWidget(self.requests_screen, 1)

        # Show what the screen reports (the real app will connect these later)
        self.requests_screen.request_cancelled.connect(
            lambda request: self._say(f"request_cancelled → {request.request_id} only"))
        self.requests_screen.browse_catalog_requested.connect(
            lambda: self._say("browse_catalog_requested → (Catalog is not connected in this preview)"))

    def _build_tool_strip(self) -> QFrame:
        strip = QFrame()
        strip.setObjectName("previewStrip")
        strip.setStyleSheet(
            f"QFrame#previewStrip {{ background-color: {PINK}; border-bottom: 3px solid {NAVY}; }}"
            f"QLabel {{ color: {NAVY}; font-size: 12px; font-weight: bold; background: transparent; }}"
        )
        row = QHBoxLayout(strip)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(10)
        row.addWidget(QLabel("PREVIEW TOOLS"))

        reset = QPushButton("Reset sample requests")
        reset.setObjectName("mintButton")
        reset.clicked.connect(self._reset_sample)
        row.addWidget(reset)

        empty = QPushButton("Show empty state")
        empty.setObjectName("mintButton")
        empty.clicked.connect(self._show_empty)
        row.addWidget(empty)

        checks = QPushButton("Run checks")
        checks.setObjectName("mintButton")
        checks.clicked.connect(self._run_checks)
        row.addWidget(checks)

        self.event_label = QLabel("Events from the screen appear here.")
        row.addWidget(self.event_label, 1)
        return strip

    def _reset_sample(self):
        # Fresh timestamps, relative to right now, so everything stays consistent.
        self.requests_screen.set_requests(build_sample_requests())
        self._say("Sample requests restored.")

    def _show_empty(self):
        self.requests_screen.set_requests([])
        self._say("No requests - friendly empty state shown.")

    def _run_checks(self):
        results = run_all_checks()  # uses its own copies; the screen above is not touched
        for failure in results.failures:
            print("CHECK FAILED:", failure)
        self._say(results.summary() + ("" if results.ok else " See the terminal for details."))

    def _say(self, text: str):
        self.event_label.setText(text)


def selftest_main() -> int:
    """Run every check without opening a window. Exit code 0 = all passed."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no display needed
    qt_app = QApplication(sys.argv)
    qt_app.setStyleSheet(STYLESHEET)
    results = run_all_checks()
    for failure in results.failures:
        print("CHECK FAILED:", failure)
    print(results.summary())
    return 0 if results.ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest_main())

    qt_app = QApplication(sys.argv)
    qt_app.setStyleSheet(STYLESHEET)
    window = MyRequestsPreviewWindow()
    window.show()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
