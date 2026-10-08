import unittest

from experiments.choose_orientation import (
    CueExperiment,
    ORIENT_HORIZONTAL,
    ORIENT_VERTICAL,
    STATE_REWARD,
    STATE_ITI,
    STATE_WAIT_CENTER,
)


class CueExperimentChoiceOverlayTest(unittest.TestCase):
    def test_wrong_choice_uses_incorrect_overlay(self):
        exp = CueExperiment.__new__(CueExperiment)
        exp.hw = type("HW", (), {"reward": type("Reward", (), {"deliver": lambda self, side: None})()})()
        exp.log = lambda *args, **kwargs: None
        exp._write_trial_row = lambda *args, **kwargs: None
        exp._end_trial = lambda choice, rewarded=False: None
        exp.clock = lambda: 100
        exp.horizontal_rewarded = False
        exp.vertical_rewarded = True
        exp.left_fig = ORIENT_HORIZONTAL
        exp.right_fig = 2
        exp.stim_onset_ms = 0
        calls = []
        exp.display_choice = lambda side, correct=True: calls.append((side, correct))

        exp._handle_choice("LEFT", ORIENT_HORIZONTAL)

        self.assertEqual(calls, [("LEFT", False)])

    def _make_experiment(self, now):
        exp = CueExperiment.__new__(CueExperiment)
        close_calls = []
        motor = type("Motor", (), {"close": lambda self: close_calls.append(True)})()
        exp.hw = type(
            "HW",
            (),
            {
                "motor": motor,
                "reward": type("Reward", (), {"deliver": lambda self, side: None})(),
            },
        )()
        exp.completed_trials = 0
        exp.horizontal_unchosen = 0
        exp.vertical_unchosen = 0
        exp.horizontal_rewarded = False
        exp.vertical_rewarded = False
        exp.left_fig = ORIENT_HORIZONTAL
        exp.right_fig = ORIENT_VERTICAL
        exp.stim_onset_ms = 0
        exp.REWARD_MS = 2000
        exp.ITI_MS = 100
        exp.display_black = lambda: None
        exp.display_choice = lambda side, correct=True: None
        exp._write_trial_row = lambda *args, **kwargs: None
        exp.log = lambda *args, **kwargs: None
        exp.inputs = lambda keys: {
            "center": False,
            "left": False,
            "right": False,
            "timeout": False,
        }
        exp.ingest_ir = lambda: None
        exp.clock = lambda: now[0]

        def goto(state, msg=None):
            exp.state = state
            exp.state_start = exp.clock()

        exp.goto = goto
        exp.state = STATE_WAIT_CENTER
        exp.state_start = now[0]
        return exp, close_calls

    def test_rewarded_trial_closes_after_reward_phase_then_finishes_iti(self):
        now = [100]
        exp, close_calls = self._make_experiment(now)
        exp.horizontal_rewarded = True

        exp._handle_choice("LEFT", ORIENT_HORIZONTAL)

        self.assertEqual(exp.state, STATE_REWARD)
        self.assertEqual(exp.completed_trials, 0)
        self.assertEqual(close_calls, [])

        now[0] = 2099
        exp.step([])
        self.assertEqual(exp.state, STATE_REWARD)
        self.assertEqual(close_calls, [])

        now[0] = 2100
        exp.step([])
        self.assertEqual(exp.state, STATE_ITI)
        self.assertEqual(close_calls, [True])
        self.assertEqual(exp.completed_trials, 0)

        now[0] = 2199
        exp.step([])
        self.assertEqual(exp.state, STATE_ITI)

        now[0] = 2200
        exp.step([])
        self.assertEqual(exp.state, STATE_WAIT_CENTER)
        self.assertEqual(exp.completed_trials, 1)

    def test_unrewarded_trial_closes_gate_before_iti(self):
        now = [100]
        exp, close_calls = self._make_experiment(now)

        exp._handle_choice("LEFT", ORIENT_HORIZONTAL)

        self.assertEqual(exp.state, STATE_ITI)
        self.assertEqual(close_calls, [True])
        self.assertEqual(exp.completed_trials, 0)

        now[0] = 199
        exp.step([])
        self.assertEqual(exp.state, STATE_ITI)

        now[0] = 200
        exp.step([])
        self.assertEqual(exp.state, STATE_WAIT_CENTER)
        self.assertEqual(exp.completed_trials, 1)


if __name__ == "__main__":
    unittest.main()
