import unittest
from types import SimpleNamespace
from unittest.mock import Mock

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
            buttons["Advance to ITI"].click()

            self.assertEqual(commands, ["SERVO 60", "SERVO 180", "SERVO 180"])
        finally:
            panel.close()
            panel.deleteLater()

    def test_gui_advance_to_iti_triggers_servo_and_bus_control(self):
        raw_cmds = []
        controls_pushed = []
        logs = []
        window = SimpleNamespace(
            _send_raw=raw_cmds.append,
            _running=lambda: True,
            bus=SimpleNamespace(push_control=controls_pushed.append),
            logs=SimpleNamespace(add_print=logs.append),
        )

        MainWindow._advance_to_iti(window)

        self.assertEqual(raw_cmds, ["SERVO 180"])
        self.assertEqual(controls_pushed, [{"type": "advance_to_iti"}])
        self.assertIn("[control] advance to ITI", logs)

        raw_cmds.clear()
        controls_pushed.clear()
        logs.clear()
        window._running = lambda: False

        MainWindow._advance_to_iti(window)

        self.assertEqual(raw_cmds, ["SERVO 180"])
        self.assertEqual(controls_pushed, [])
        self.assertTrue(any("no experiment running" in msg for msg in logs))

    def test_reward_wait_timeout_button_calls_control_handler(self):
        controls = SimpleNamespace(**{
            name: Mock() for name in (
                "_start_run", "_stop_run", "_manual_key", "_timeout_reward_wait",
                "_skip_trial", "_skip_stage", "_skip_loop", "_set_trial_number",
            )
        })
        panel = QtWidgets.QWidget()
        panel.setLayout(MainWindow._build_controls(controls))
        try:
            button = next(
                button for button in panel.findChildren(QtWidgets.QPushButton)
                if button.text() == "Timeout reward-port wait"
            )
            button.click()
            controls._timeout_reward_wait.assert_called_once()
        finally:
            panel.close()
            panel.deleteLater()

    def test_experiment_advance_to_iti_transitions_from_reward_to_iti(self):
        from experiments.consecutive_reward import ConsecutiveReward

        motor_cmds = []
        display_calls = []
        exp = ConsecutiveReward.__new__(ConsecutiveReward)
        exp.state = exp.REWARD_STATE
        exp._pending_iti_ms = 2500
        exp.hw = SimpleNamespace(motor=SimpleNamespace(close=lambda: motor_cmds.append("CLOSE")))
        exp.display = SimpleNamespace(black=lambda: display_calls.append("BLACK"))
        exp.clock = lambda: 100
        exp._apply_ambient = lambda state: None
        exp.log = lambda msg: None

        advanced = exp.advance_to_iti()

        self.assertTrue(advanced)
        self.assertEqual(exp.state, exp.ITI_STATE)
        self.assertEqual(display_calls, ["BLACK"])
        self.assertEqual(motor_cmds, ["CLOSE"])

        # When not in REWARD state, advance_to_iti should return False and not re-enter ITI
        advanced_again = exp.advance_to_iti()
        self.assertFalse(advanced_again)
        self.assertEqual(exp.state, exp.ITI_STATE)


if __name__ == "__main__":
    unittest.main()
