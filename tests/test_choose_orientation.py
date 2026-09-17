import unittest

from experiments.choose_orientation import CueExperiment, ORIENT_HORIZONTAL


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


if __name__ == "__main__":
    unittest.main()
