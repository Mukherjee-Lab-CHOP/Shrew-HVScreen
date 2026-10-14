import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config import CH_LEFT
from experiments.consecutive_reward import (
    ConsecutiveReward,
    SPEC,
    STATE_ITI,
    STATE_REWARD,
    STATE_WAIT_CENTER,
    STATE_WAIT_POKE,
)


class ConsecutiveRewardTimeoutTest(unittest.TestCase):
    def make_experiment(self, timeout=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        hardware = SimpleNamespace(
            motor=SimpleNamespace(open=Mock(), close=Mock(), open_deg=60),
            reward=SimpleNamespace(deliver=Mock()),
            ir_detector=SimpleNamespace(poll_events=Mock(return_value=[])),
        )
        params = {} if timeout is None else {"CHOICE_TIMEOUT_MS": timeout}
        with patch("experiments._base.AMBIENT_ENABLED", False):
            exp = ConsecutiveReward(
                hardware, None, os.path.join(directory.name, "trial.csv"),
                params=params, verbose=False,
            )
        self.addCleanup(exp.close)
        self.now = 500
        exp.clock = lambda: self.now
        exp.step(["c"])
        hardware.motor.close.reset_mock()
        self.assertEqual(exp.state, STATE_WAIT_POKE)
        return exp, hardware

    def test_unlimited_default_and_gui_spec(self):
        exp, hardware = self.make_experiment()
        self.now += 1_000_000
        exp.step([])
        self.assertEqual(exp.CHOICE_TIMEOUT_MS, 0)
        self.assertEqual(exp.state, STATE_WAIT_POKE)
        hardware.motor.close.assert_not_called()
        variable = next(v for v in SPEC["variables"] if v["key"] == "CHOICE_TIMEOUT_MS")
        self.assertEqual(variable["default"], 0)
        self.assertEqual(variable["min"], 0)

    def test_deadline_closes_once_logs_timeout_and_runs_incorrect_iti(self):
        exp, hardware = self.make_experiment(30_000)
        exp.last_side, exp.consecutive = "LEFT", 2
        self.now = 30_499
        exp.step([])
        self.assertEqual(exp.state, STATE_WAIT_POKE)
        hardware.motor.close.assert_not_called()
        self.now = 30_500
        exp.step(["l"])
        self.assertEqual(exp.state, STATE_ITI)
        hardware.motor.close.assert_called_once()
        hardware.reward.deliver.assert_not_called()
        self.assertEqual((exp.last_side, exp.consecutive), ("LEFT", 2))
        self.assertEqual((exp.trial_num, exp.completed_trials), (1, 1))
        with open(exp.csv_path) as stream:
            self.assertIn("1,30500,TIMEOUT,2,3,NO REWARD", stream.read())
        self.now += exp.INCORRECT_ITI_WAIT - 1
        exp.step([])
        self.assertEqual(exp.state, STATE_ITI)
        self.now += 1
        exp.step([])
        self.assertEqual(exp.state, STATE_WAIT_CENTER)
        hardware.motor.close.assert_called_once()

    def test_ir_poke_before_deadline_keeps_existing_reward_window(self):
        exp, hardware = self.make_experiment(30_000)
        self.now = 600
        hardware.ir_detector.poll_events.return_value = [(CH_LEFT, True, 123)]
        exp.step([])
        hardware.ir_detector.poll_events.return_value = []
        self.now = 700
        exp.step([])
        hardware.reward.deliver.assert_called_once_with("LEFT")
        self.assertEqual(exp.state, STATE_REWARD)
        self.now = 3_699
        exp.step([])
        hardware.motor.close.assert_not_called()
        self.now = 3_700
        exp.step([])
        self.assertEqual(exp.state, STATE_ITI)
        hardware.motor.close.assert_called_once()

    def test_manual_timeout_works_when_unlimited(self):
        exp, hardware = self.make_experiment()
        exp.step(["t"])
        self.assertEqual(exp.state, STATE_ITI)
        hardware.motor.close.assert_called_once()
        hardware.reward.deliver.assert_not_called()

    def test_timeout_rejects_other_states(self):
        exp, hardware = self.make_experiment()
        self.assertTrue(exp.timeout_reward_wait())
        self.assertEqual(exp.state, STATE_ITI)
        self.assertFalse(exp.timeout_reward_wait())
        hardware.motor.close.assert_called_once()
        for state in (STATE_WAIT_CENTER, STATE_REWARD):
            exp.state = state
            self.assertFalse(exp.timeout_reward_wait())


if __name__ == "__main__":
    unittest.main()
