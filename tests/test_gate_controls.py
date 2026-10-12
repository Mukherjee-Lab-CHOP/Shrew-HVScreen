import unittest
from types import SimpleNamespace

from PySide6 import QtWidgets

from gui.main_window import MainWindow
from motor import Motor


class GateControlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_motor_defaults_use_configured_open_and_closed_angles(self):
        commands = []
        motor = Motor(SimpleNamespace(send=commands.append))

        motor.open()
        motor.close()

        self.assertEqual(commands, ["SERVO 60", "SERVO 180"])

    def test_gui_gate_buttons_match_motor_defaults(self):
        commands = []
        controls = SimpleNamespace(
            _send_raw=commands.append,
            _send_custom=lambda: None,
        )
        panel = QtWidgets.QWidget()
        layout = MainWindow._build_command_controls(controls)
        panel.setLayout(layout)
        try:
            buttons = {
                button.text(): button
                for button in panel.findChildren(QtWidgets.QPushButton)
            }
            buttons["Gate open"].click()
            buttons["Gate close"].click()

            self.assertEqual(commands, ["SERVO 60", "SERVO 180"])
        finally:
            panel.close()
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
