import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config import CH_CENTER, CH_LEFT
from experiments.vertical_random_side import (
    STATE_WAIT_CENTER,
    STATE_WAIT_CHOICE,
    VerticalRandomSide,
)


class MissedClearTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.hw = SimpleNamespace(
            motor=SimpleNamespace(open=Mock(), close=Mock(), open_deg=60),
            reward=SimpleNamespace(deliver=Mock()),
            ir_detector=SimpleNamespace(poll_events=Mock(return_value=[])),
        )
        with patch("experiments._base.AMBIENT_ENABLED", False):
            self.exp = VerticalRandomSide(
                self.hw, None, os.path.join(directory.name, "t.csv"),
                params={"CORRECT_ITI_WAIT": 0, "INCORRECT_ITI_WAIT": 0},
                verbose=False,
            )
        self.addCleanup(self.exp.close)
        self.now = 0
        self.exp.clock = lambda: self.now

    def step(self, events=(), dt=0):
        self.now += dt
        self.hw.ir_detector.poll_events.return_value = list(events)
        self.exp.step([])
        self.hw.ir_detector.poll_events.return_value = []

    def test_center_poke_after_lost_clear_still_starts_trial(self):
        # first centre poke starts a trial ...
        self.step([(CH_CENTER, True, 1)])
        self.step(dt=150)
        self.assertEqual(self.exp.state, STATE_WAIT_CHOICE)
        # ... but its CLEAR is never received. Finish the trial via timeout.
        self.exp.step(["t"])
        self.step(dt=1)
        self.assertEqual(self.exp.state, STATE_WAIT_CENTER)
        # the next real poke only produces another BROKEN edge
        self.step([(CH_CENTER, True, 2)], dt=1000)
        self.step(dt=150)
        self.assertEqual(self.exp.state, STATE_WAIT_CHOICE)

    def test_side_poke_after_lost_clear_still_registers(self):
        self.exp.vertical_side = "LEFT"
        self.exp.goto(STATE_WAIT_CHOICE)
        self.step([(CH_LEFT, True, 1)])
        self.step(dt=150)                      # choice registered
        self.step(dt=1)                        # REWARD/ITI -> back to centre
        self.exp.goto(STATE_WAIT_CHOICE)
        self.exp.vertical_side = "LEFT"
        self.hw.reward.deliver.reset_mock()
        self.step([(CH_LEFT, True, 2)], dt=1000)   # LEFT CLEAR was lost
        self.step(dt=150)
        self.hw.reward.deliver.assert_called_once_with("LEFT")

    def test_hold_still_requires_poke_duration(self):
        self.step([(CH_CENTER, True, 1)])
        self.step(dt=50)
        self.assertEqual(self.exp.state, STATE_WAIT_CENTER)
        self.step([(CH_CENTER, False, 2)], dt=10)
        self.step(dt=500)
        self.assertEqual(self.exp.state, STATE_WAIT_CENTER)


if __name__ == "__main__":
    unittest.main()
