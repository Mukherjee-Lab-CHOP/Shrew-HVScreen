import unittest

from experiments.choose_orientation import (
    CueExperiment,
    ORIENT_HORIZONTAL,
    STATE_ITI,
    STATE_WAIT_CENTER,
)


class CueExperimentChoiceOverlayTest(unittest.TestCase):
    def test_wrong_choice_uses_incorrect_overlay(self):
        exp = CueExperiment.__new__(CueExperiment)
        exp.hw = type("HW", (), {"reward": type("Reward", (), {"deliver": lambda self, side: None})()})()
        exp.log = lambda *args, **kwargs: None
        exp._write_trial_row = lambda *args, **kwargs: None
        exp._end_trial = lambda choice: None
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

    def test_trial_completes_after_gate_closes_at_end_of_iti(self):
        exp = CueExperiment.__new__(CueExperiment)
        close_calls = []
        exp.hw = type(
            "HW",
            (),
            {"motor": type("Motor", (), {"close": lambda self: close_calls.append(True)})()},
        )()
        exp.completed_trials = 0
        exp.horizontal_unchosen = 0
        exp.vertical_unchosen = 0
        exp.ITI_MS = 100
        exp.display_black = lambda: None
        exp.goto = lambda state, msg=None: setattr(exp, "state", state)

        exp._end_trial(ORIENT_HORIZONTAL)

        self.assertEqual(exp.state, STATE_ITI)
        self.assertEqual(exp.completed_trials, 0)
        self.assertEqual(close_calls, [])

        exp._end_iti()

        self.assertEqual(exp.state, STATE_WAIT_CENTER)
        self.assertEqual(exp.completed_trials, 1)
        self.assertEqual(close_calls, [True])


if __name__ == "__main__":
    unittest.main()
