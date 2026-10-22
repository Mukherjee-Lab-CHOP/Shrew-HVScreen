import unittest

from PySide6 import QtWidgets

from gui.performance_view import PerformanceView


class PerformanceViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_random_side_csv_builds_rolling_performance_for_both_tasks(self):
        view = PerformanceView()
        self.addCleanup(view.deleteLater)
        rows = [
            ["1", "100", "LEFT", "LEFT", "1", "1.0", "REWARD"],
            ["2", "200", "RIGHT", "LEFT", "0", "1.0", "NO REWARD"],
            ["3", "300", "LEFT", "TIMEOUT", "0", "1.0", ""],
            ["4", "400", "RIGHT", "SKIP", "0", "1.0", ""],
        ]

        for target_column in ("horizontal_side", "vertical_side"):
            with self.subTest(target_column=target_column):
                header = ["trial_number", "target_onset_timestamp", target_column,
                          "chosen_side", "correct", "reward_percent", "reward"]
                view.set_data(header, rows)
                self.assertEqual(view.accuracy_series.count(), 3)
                self.assertAlmostEqual(view.accuracy_series.at(2).y(), 100 / 3)
                self.assertIn("Accuracy: 33.3%", view.summary.text())
                self.assertIn("Timeouts: 1", view.summary.text())
                self.assertIn("Skips: 1", view.summary.text())