"""Preview the My List screen on its own:   python preview_my_list.py

Run it from the project folder (the one that contains `app/`). It opens only
the My List screen with sample items - no login, no dashboard, no database.
The strip at the top is a preview tool, not part of the real screen.
"""
import sys
from pathlib import Path

# Make `import app...` work no matter where the script is started from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.my_list_screen import MyListScreen, sample_saved_items  # noqa: E402
from app.theme import NAVY, PINK, STYLESHEET  # noqa: E402


class MyListPreviewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KitLend Desktop - My List (Preview)")
        self.resize(1000, 700)
        self.setMinimumSize(800, 500)

        central = QWidget()
        central.setObjectName("previewCentral")
        central.setStyleSheet(f"QWidget#previewCentral {{ background-color: {NAVY}; }}")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central)

        self.my_list = MyListScreen(sample_saved_items())
        layout.addWidget(self._build_tool_strip())
        layout.addWidget(self.my_list, 1)

        # Show what the screen reports (the real app will connect these later)
        self.my_list.item_removed.connect(
            lambda item: self._say(f"item_removed → {item.title}"))
        self.my_list.request_preview_confirmed.connect(
            lambda items: self._say(f"request_preview_confirmed → {len(items)} item(s), nothing sent"))
        self.my_list.browse_catalog_requested.connect(
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

        reset = QPushButton("Reset sample list")
        reset.setObjectName("mintButton")
        reset.clicked.connect(self._reset_sample)
        row.addWidget(reset)

        empty = QPushButton("Empty the list")
        empty.setObjectName("mintButton")
        empty.clicked.connect(self._empty_list)
        row.addWidget(empty)

        self.event_label = QLabel("Events from the screen appear here.")
        row.addWidget(self.event_label, 1)
        return strip

    def _reset_sample(self):
        self.my_list.set_saved_items(sample_saved_items())
        self._say("Sample list restored.")

    def _empty_list(self):
        self.my_list.set_saved_items([])
        self._say("List emptied - friendly empty state shown.")

    def _say(self, text: str):
        self.event_label.setText(text)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = MyListPreviewWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
