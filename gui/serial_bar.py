"""SerialBar — top bar. Pick/scan the COM port (flagging likely Arduinos),
connect/disconnect, choose the stimulus monitor, and see link status.
"""

from PySide6 import QtCore, QtWidgets

from serial_link import SerialLink


class SerialBar(QtWidgets.QWidget):
    connect_requested = QtCore.Signal(str, int)   # (port, baud)
    disconnect_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("COM:"))
        self.port_combo = QtWidgets.QComboBox()
        self.port_combo.setMinimumWidth(280)
        layout.addWidget(self.port_combo)

        self.refresh_btn = QtWidgets.QPushButton("Scan")
        self.refresh_btn.clicked.connect(self.scan_ports)
        layout.addWidget(self.refresh_btn)

        layout.addWidget(QtWidgets.QLabel("Baud:"))
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.addItems(["115200", "9600", "57600", "250000"])
        layout.addWidget(self.baud_combo)

        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connect)
        layout.addWidget(self.connect_btn)

        layout.addSpacing(16)
        layout.addWidget(QtWidgets.QLabel("Stimulus screen:"))
        self.screen_spin = QtWidgets.QSpinBox()
        self.screen_spin.setRange(0, 8)
        self.screen_spin.setValue(1)
        layout.addWidget(self.screen_spin)

        layout.addStretch(1)
        self.status = QtWidgets.QLabel("● disconnected")
        self.status.setStyleSheet("color:#c0392b; font-weight:bold;")
        layout.addWidget(self.status)

        self._connected = False
        self.scan_ports()

    # ---- ports -------------------------------------------------------------
    def scan_ports(self):
        current = self.current_port()
        self.port_combo.clear()
        ports = SerialLink.list_ports_detailed()
        if not ports:
            self.port_combo.addItem("(no ports found)", userData=None)
        for p in ports:
            tag = "  [Arduino?]" if p["is_usb"] else ""
            label = f"{p['device']} — {p['description']}{tag}" if p["description"] else \
                    f"{p['device']}{tag}"
            self.port_combo.addItem(label, userData=p["device"])
        # re-select previous if still present
        if current:
            idx = self.port_combo.findData(current)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)

    def current_port(self):
        return self.port_combo.currentData()

    def baud(self):
        return int(self.baud_combo.currentText())

    def screen_index(self):
        return self.screen_spin.value()

    # ---- connection state --------------------------------------------------
    def _toggle_connect(self):
        if self._connected:
            self.disconnect_requested.emit()
        else:
            port = self.current_port()
            if port:
                self.connect_requested.emit(port, self.baud())

    def set_connected(self, ok, detail=""):
        self._connected = ok
        if ok:
            self.connect_btn.setText("Disconnect")
            self.status.setText(f"● connected{(' — ' + detail) if detail else ''}")
            self.status.setStyleSheet("color:#27ae60; font-weight:bold;")
        else:
            self.connect_btn.setText("Connect")
            self.status.setText(f"● {detail or 'disconnected'}")
            self.status.setStyleSheet("color:#c0392b; font-weight:bold;")

    def set_busy(self, busy):
        """Lock port selection while a run is in progress."""
        self.port_combo.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.baud_combo.setEnabled(not busy)
        self.connect_btn.setEnabled(not busy)
        self.screen_spin.setEnabled(not busy)
