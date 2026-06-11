"""CsvView — middle panel. Live table of the CSV the active experiment is
writing. Tails the file: re-reads when its modification time changes.
"""

import csv
import os

from PySide6 import QtCore, QtWidgets


class CsvView(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._path_label = QtWidgets.QLabel("CSV: —")
        self._path_label.setWordWrap(True)
        layout.addWidget(self._path_label)
        self.table = QtWidgets.QTableWidget(0, 0)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self._path = None
        self._mtime = None

    def set_path(self, path):
        self._path = path
        self._mtime = None
        self._path_label.setText(f"CSV: {path or '—'}")
        self.refresh(force=True)

    def refresh(self, force=False):
        if not self._path or not os.path.exists(self._path):
            return
        try:
            mtime = os.path.getmtime(self._path)
        except OSError:
            return
        if not force and mtime == self._mtime:
            return
        self._mtime = mtime
        try:
            with open(self._path, newline="") as f:
                rows = list(csv.reader(f))
        except OSError:
            return
        if not rows:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return
        header, data = rows[0], rows[1:]
        self.table.setColumnCount(len(header))
        self.table.setHorizontalHeaderLabels(header)
        self.table.setRowCount(len(data))
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                if c < len(header):
                    self.table.setItem(r, c, QtWidgets.QTableWidgetItem(val))
        self.table.scrollToBottom()
