import sys

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.theme import STYLESHEET


def main():
    qt_app = QApplication(sys.argv)   # the engine that runs the GUI
    qt_app.setStyleSheet(STYLESHEET)  # apply our Pixel Pop colors

    window = MainWindow()
    window.show()

    sys.exit(qt_app.exec())           # keep the window open until closed


if __name__ == "__main__":
    main()
