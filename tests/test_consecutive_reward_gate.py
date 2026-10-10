import unittest

from experiments.consecutive_reward import (
    ConsecutiveReward,
    STATE_WAIT_CENTER,
    STATE_WAIT_POKE,
)
from motor import Motor
from serial_link import SerialLink


class FakeSerial:
    def __init__(self, error=None):
        self.writes = []
        self.error = error

    def write(self, data):
        if self.error:
            raise self.error
        self.writes.append(data)


class ConsecutiveRewardGateTest(unittest.TestCase):
    def _make_experiment(self, serial_port):
        link = SerialLink.__new__(SerialLink)
        link.on_send = None
        link._ser = serial_port
        link._log = lambda message: None

        exp = ConsecutiveReward.__new__(ConsecutiveReward)
        exp.state = STATE_WAIT_CENTER
        exp.hw = type("Hardware", (), {"motor": Motor(link)})()
        exp.inputs = lambda keys: {
            "center": True,
            "left": False,
            "right": False,
        }
        exp.log_messages = []
        exp.log = exp.log_messages.append

        def goto(state, msg=None):
            exp.state = state
            if msg:
                exp.log(msg)

        exp.goto = goto
        return exp

    def test_center_hold_sends_gate_open_command_and_logs_success(self):
        serial_port = FakeSerial()
        exp = self._make_experiment(serial_port)

        exp.run_step([])

        self.assertEqual(serial_port.writes, [b"$SERVO 60\n"])
        self.assertIn("Gate-open command sent (SERVO 60).", exp.log_messages)
        self.assertEqual(exp.state, STATE_WAIT_POKE)

    def test_center_hold_reports_command_not_sent_when_disconnected(self):
        exp = self._make_experiment(None)

        exp.run_step([])

        self.assertTrue(any("command was not sent" in msg for msg in exp.log_messages))
        self.assertEqual(exp.state, STATE_WAIT_POKE)

    def test_center_hold_reports_serial_write_failure(self):
        serial_port = FakeSerial(error=OSError("port unavailable"))
        exp = self._make_experiment(serial_port)

        exp.run_step([])

        self.assertTrue(any("command was not sent" in msg for msg in exp.log_messages))
        self.assertEqual(exp.state, STATE_WAIT_POKE)


if __name__ == "__main__":
    unittest.main()
