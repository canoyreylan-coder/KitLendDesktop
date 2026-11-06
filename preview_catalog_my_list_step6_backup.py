"""TEMPORARY runner: Browse Catalog + My List working together.

Put this file in the project root (next to main.py), then run:

    python preview_catalog_my_list.py

Use the two buttons at the top to switch screens. Save an item with the star
button on a Catalog card and it appears in My List; remove it in My List and
the star turns off in the Catalog.

Bookmarks live in memory only (they start empty every time). There is no
login, no database and no real borrowing, and this is NOT connected to the
Login, Register or Dashboard screens.
"""
import sys
from pathlib import Path

# Make `import app...` work no matter where the script is started from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QButtonGroup,
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
from app.my_list_screen import MyListScreen  # noqa: E402
from app.theme import CREAM, NAVY, PERIWINKLE, STYLESHEET  # noqa: E402

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
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.statusBar().setStyleSheet(f"QStatusBar {{ background-color: {NAVY}; color: {CREAM}; }}")

        # --- Catalog -> shared list -> My List ---
        self.catalog.bookmark_toggled.connect(self._on_catalog_bookmark_toggled)
        self.catalog.item_selected.connect(self._on_item_selected)
        # --- My List -> shared list -> Catalog ---
        self.my_list.item_removed.connect(self._on_my_list_item_removed)
        self.my_list.browse_catalog_requested.connect(self.show_catalog)
        self.my_list.request_preview_confirmed.connect(self._on_request_preview_confirmed)

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

    # ---------- placeholders for features that do not exist yet ----------
    def _on_item_selected(self, item):
        self.statusBar().showMessage(
            f"You clicked '{item.title}'. Item details are not built yet.", 5000
        )

    def _on_request_preview_confirmed(self, items):
        self.statusBar().showMessage(
            f"Preview only: {len(items)} separate request(s) would be created. Nothing was sent.", 5000
        )


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setStyleSheet(STYLESHEET)  # same Pixel Pop theme as main.py

    window = CatalogMyListPreviewWindow()
    window.show()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
