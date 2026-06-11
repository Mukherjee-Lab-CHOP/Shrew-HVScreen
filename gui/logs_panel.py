"""LogsPanel — bottom. Two separate read-only panes: commands sent OUT to the
Arduino, and everything printed (experiment logs + inbound firmware lines).
"""

from PySide6 import QtGui, QtWidgets

MAX_BLOCKS = 2000


class _LogPane(QtWidgets.QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(MAX_BLOCKS)
        self.setFont(QtGui.QFont("Menlo", 10))

    def append_line(self, text):
        self.appendPlainText(text.rstrip("\n"))


class LogsPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        cmd_box = QtWidgets.QVBoxLayout()
        cmd_box.addWidget(QtWidgets.QLabel("<b>Commands out →</b>"))
        self.commands = _LogPane()
        cmd_box.addWidget(self.commands)

        print_box = QtWidgets.QVBoxLayout()
        print_box.addWidget(QtWidgets.QLabel("<b>Prints / events</b>"))
        self.prints = _LogPane()
        print_box.addWidget(self.prints)

        layout.addLayout(cmd_box, 1)
        layout.addLayout(print_box, 1)

    def add_command(self, line):
        self.commands.append_line(f"$ {line}")

    def add_print(self, line):
        self.prints.append_line(line)
