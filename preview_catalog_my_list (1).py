"""TEMPORARY runner: Browse Catalog + My List working together.

Put this file in the project root (next to main.py), then run:

    python preview_catalog_my_list.py

Use the two buttons at the top to switch screens. Save an item with the star
button on a Catalog card and it appears in My List; remove it in My List and
the star turns off in the Catalog.

Two independent ways to request (both are PREVIEW ONLY, nothing is created):
  A) Catalog card -> Request Now -> request form for ONE item
  B) Star items -> My List -> select items -> Request Selected -> request form
     for one or many items
Both open the SAME request form (RequestPreviewDialog). For each item the
student picks a preferred pickup DATE (calendar button) and TIME (dropdown of
30-minute slots), plus how many days to borrow it. Request Now never bookmarks
the item and never touches My List.

Pickup availability (Step 7C.1) is SAMPLE data, set per lender/administrator:
  - School pickup locations have their own schedules, e.g. "Main Library" is
    Mon-Fri 9:00 AM-4:00 PM, "Electronics Lab" is Mon-Thu 1:00-5:00 PM.
  - Student lenders have their own too, e.g. Ana M. offers weekends, Paolo R.
    offers Tue/Thu evenings and Saturday mornings.
  The form opens on the next valid slot, only offered dates/times can be chosen,
  and everything is re-checked when Confirm is pressed. Borrowing days are a
  separate setting. The countdown never starts here: it starts only when the
  lender/admin confirms the real handover.

When the student confirms, the validated RequestDrafts are kept in
`self.prepared_drafts` (in memory only), ready for a later step that will turn
them into real requests. Nothing is submitted, saved or sent.

Bookmarks live in memory only (they start empty every time). There is no
login, no database and no real borrowing, and this is NOT connected to the
Login, Register or Dashboard screens.
"""
import sys
from pathlib import Path

# Make `import app...` work no matter where the script is started from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.catalog_screen import CatalogScreen  # noqa: E402
from app.my_list_screen import MyListScreen, RequestPreviewDialog  # noqa: E402
from app.theme import CREAM, MINT, NAVY, PERIWINKLE, STYLESHEET  # noqa: E402

SIDEBAR_NAVY = "#1F2140"  # same darker navy the dashboard sidebar uses


class CatalogMyListPreviewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KitLend Preview - Catalog + My List (sample data, not connected to the app)")
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)

        # ONE shared collection of bookmarked CatalogItems (oldest first, no duplicates).
        # Both screens are kept in sync with it.
        self._bookmarks = []
        self._request_dialog_open = False  # stops a second dialog from opening

        # The RequestDrafts from the latest successful confirmation, from EITHER
        # request path. In memory only: a later step will turn them into real requests.
        self.prepared_drafts = []

        # Both screens are created once and only shown/hidden, so their state
        # (search text, filters, scroll position, selections) is never lost.
        self.catalog = CatalogScreen()
        self.my_list = MyListScreen([])  # starts empty

        self.stack = QStackedWidget()
        self.stack.addWidget(self.catalog)
        self.stack.addWidget(self.my_list)

        central = QWidget()
        central.setObjectName("previewCentral")
        central.setStyleSheet(f"QWidget#previewCentral {{ background-color: {NAVY}; }}")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_nav_bar())
        layout.addWidget(self._build_banner())
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.statusBar().setStyleSheet(f"QStatusBar {{ background-color: {NAVY}; color: {CREAM}; }}")

        # --- Catalog -> shared list -> My List ---
        self.catalog.bookmark_toggled.connect(self._on_catalog_bookmark_toggled)
        self.catalog.item_selected.connect(self._on_item_selected)
        # --- Catalog -> direct (single-item) request form ---
        self.catalog.direct_request_requested.connect(self._on_direct_request)
        # --- My List -> shared list -> Catalog ---
        self.my_list.item_removed.connect(self._on_my_list_item_removed)
        self.my_list.browse_catalog_requested.connect(self.show_catalog)
        self.my_list.request_preview_confirmed.connect(self._on_request_preview_confirmed)
        self.my_list.request_drafts_prepared.connect(self._on_request_drafts_prepared)

        self._update_nav_labels()

    # ---------- navigation ----------
    def _build_nav_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("previewNav")
        bar.setStyleSheet(
            f"QFrame#previewNav {{ background-color: {SIDEBAR_NAVY}; border-bottom: 3px solid {PERIWINKLE}; }}"
            f"QLabel#previewNote {{ color: {CREAM}; font-size: 12px; background: transparent; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(10)

        # "navButton" is the checkable sidebar button style from theme.py
        self.catalog_button = QPushButton("Browse Catalog")
        self.my_list_button = QPushButton("My List")
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for button in (self.catalog_button, self.my_list_button):
            button.setObjectName("navButton")
            button.setCheckable(True)
            self._nav_group.addButton(button)
            row.addWidget(button)
        self.catalog_button.setChecked(True)
        self.catalog_button.clicked.connect(self.show_catalog)
        self.my_list_button.clicked.connect(self.show_my_list)

        row.addStretch()
        note = QLabel("Preview · sample data · bookmarks kept in memory only")
        note.setObjectName("previewNote")
        row.addWidget(note)
        return bar

    def _build_banner(self) -> QLabel:
        """A short message under the nav bar; hides itself after a few seconds."""
        self.banner = QLabel("")
        self.banner.setObjectName("previewBanner")
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            f"QLabel#previewBanner {{ background-color: {MINT}; color: {NAVY}; "
            f"border: 2px solid {NAVY}; border-radius: 14px; padding: 10px 16px; "
            f"margin: 10px 20px 0px 20px; font-size: 13px; font-weight: bold; }}"
        )
        self.banner.hide()
        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(5000)
        self._banner_timer.timeout.connect(self.banner.hide)
        return self.banner

    def _show_banner(self, text: str):
        self.banner.setText(text)
        self.banner.show()
        self._banner_timer.start()

    def show_catalog(self):
        self.stack.setCurrentWidget(self.catalog)
        self.catalog_button.setChecked(True)

    def show_my_list(self):
        self.stack.setCurrentWidget(self.my_list)
        self.my_list_button.setChecked(True)

    def _update_nav_labels(self):
        self.my_list_button.setText(f"My List ({len(self._bookmarks)})")

    # ---------- keeping both screens in sync ----------
    def _on_catalog_bookmark_toggled(self, item, is_bookmarked: bool):
        if is_bookmarked and item not in self._bookmarks:
            self._bookmarks.append(item)
        elif not is_bookmarked and item in self._bookmarks:
            self._bookmarks.remove(item)
        # The star the student just clicked is already right; update My List.
        self.my_list.set_saved_items(self._bookmarks)
        self._update_nav_labels()
        verb = "Saved" if is_bookmarked else "Removed"
        self.statusBar().showMessage(f"{verb} '{item.title}' - {len(self._bookmarks)} in My List.", 4000)

    def _on_my_list_item_removed(self, item):
        # My List already dropped the row; turn the Catalog star off too.
        if item in self._bookmarks:
            self._bookmarks.remove(item)
        self.catalog.set_bookmarked_items(self._bookmarks)
        self._update_nav_labels()

    @staticmethod
    def _describe_drafts(drafts) -> str:
        """'Title - Mon, Oct 19, 2026 at 9:00 AM, 2 days; Title 2 - ...' for the banners."""
        return "; ".join(
            f"'{draft.item.title}' - preferred pickup {draft.pickup_text}, {draft.days_text}"
            for draft in drafts
        )

    # ---------- placeholders for features that do not exist yet ----------
    def _on_item_selected(self, item):
        self.statusBar().showMessage(
            f"You clicked '{item.title}'. Item details are not built yet.", 5000
        )

    def _on_direct_request(self, item):
        """Request Now on a Catalog card: open the SAME request form My List uses."""
        if self._request_dialog_open or not item.is_available:
            return
        self._request_dialog_open = True
        try:
            dialog = RequestPreviewDialog([item], self)  # single-item list
            confirmed = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._request_dialog_open = False

        # Cancel / closing the form: nothing happens. Bookmarks are never touched.
        if not confirmed:
            return
        drafts = dialog.drafts  # the validated RequestDrafts (one per item)
        if not drafts:
            return
        self.prepared_drafts = drafts
        draft = drafts[0]
        self._show_banner(
            f"Preview only: a request draft for '{draft.item.title}' was prepared "
            f"({draft.days_text}, preferred pickup {draft.pickup_text}). "
            "NOTHING was actually sent, saved or bookmarked. "
            "The borrowing period would only start once the lender/admin confirms the handover."
        )

    def _on_request_preview_confirmed(self, items):
        # Old signal (payload = the selected CatalogItems). Still fires exactly once.
        self.statusBar().showMessage(
            f"Preview only: {len(items)} separate request(s) would be created. Nothing was sent.", 5000
        )

    def _on_request_drafts_prepared(self, drafts):
        # New signal from My List (payload = the validated RequestDrafts).
        self.prepared_drafts = list(drafts)
        self.statusBar().showMessage(
            f"Preview only: {len(drafts)} request draft(s) prepared and kept in memory. "
            "Nothing was sent.", 5000
        )
        self._show_banner(
            f"Preview only: {len(drafts)} request draft(s) prepared - "
            f"{self._describe_drafts(drafts)}. NOTHING was actually sent or saved."
        )


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setStyleSheet(STYLESHEET)  # same Pixel Pop theme as main.py

    window = CatalogMyListPreviewWindow()
    window.show()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
