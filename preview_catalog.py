"""TEMPORARY runner for previewing the Browse Catalog screen on its own.

Put this file in the project root (next to main.py), then run:

    python preview_catalog.py

The Catalog is NOT connected to the Login or Dashboard screens, there is no
login, and all items are sample data. Delete this file once the Catalog is
wired into the real app.
"""
import sys

from PySide6.QtWidgets import QApplication, QMainWindow

from app.catalog_screen import CatalogScreen
from app.theme import STYLESHEET


class CatalogPreviewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KitLend Catalog Preview (sample data - not connected to the app)")
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)

        self.catalog = CatalogScreen()
        self.setCentralWidget(self.catalog)
        self.catalog.item_selected.connect(self._on_item_selected)

    def _on_item_selected(self, item):
        # Item details and borrowing do not exist yet, so just say so.
        self.statusBar().showMessage(
            f"You clicked '{item.title}'. Item details are not built yet.", 5000
        )


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setStyleSheet(STYLESHEET)  # same Pixel Pop theme as main.py

    window = CatalogPreviewWindow()
    window.show()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
