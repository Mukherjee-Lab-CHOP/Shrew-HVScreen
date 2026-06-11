#!/usr/bin/env python3
"""Launch the cue experiment control-panel GUI.

    python run_gui.py
"""

import sys

from PySide6 import QtWidgets

from gui.main_window import MainWindow


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
