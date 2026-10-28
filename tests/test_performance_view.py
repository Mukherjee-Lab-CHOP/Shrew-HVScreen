import csv
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6 import QtCore, QtGui, QtWidgets

from experiments.horizontal_random_side import HorizontalRandomSide
from experiments.vertical_random_side import VerticalRandomSide
from gui.bus import Bus
from gui.performance_view import PerformanceView
from gui.worker import PipelineWorker


HORIZONTAL = "horizontal_random_side"
VERTICAL = "vertical_random_side"


class PerformanceViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.view = PerformanceView()
        self.addCleanup(self.view.deleteLater)

    def add(self, task, chosen="LEFT", correct=1, trial=1, reward="REWARD"):
        cls = HorizontalRandomSide if task == HORIZONTAL else VerticalRandomSide
        self.view.add_trial(task, cls.CSV_HEADER,
                            [trial, 100, "LEFT", chosen, correct, 1.0, reward])

    def test_repeated_blocks_share_session_axis_despite_stage_trial_resets(self):
        for task in (HORIZONTAL, VERTICAL, HORIZONTAL):
            for trial in range(1, 7):
                self.add(task, trial=trial)
        self.assertEqual(len(self.view.outcomes), 18)
        markers = self.view.markers
        self.assertEqual(markers[0].y(), markers[12].y())
        self.assertNotEqual(markers[0].y(), markers[6].y())
        self.assertEqual([item.x() for item in markers],
                         [self.view.SPACING * n for n in range(1, 19)])
        self.assertIn("Session trial 13", markers[12].toolTip())
        self.assertIn("Stage trial: 1", markers[12].toolTip())

    def test_colors_timeout_skip_and_per_task_choice_percentages(self):
        self.add(HORIZONTAL, reward="NO REWARD")
        self.add(HORIZONTAL, "RIGHT", 0)
        self.add(HORIZONTAL, "TIMEOUT", 0, reward="")
        self.add(HORIZONTAL, "SKIP", 0, reward="")
        self.add(VERTICAL, "RIGHT")
        correct, incorrect, timeout, skipped, _ = self.view.markers
        self.assertEqual(correct.brush().color(), QtGui.QColor("#16803c"))
        self.assertEqual(incorrect.brush().color(), QtGui.QColor("#c62828"))
        self.assertEqual(timeout.brush().style(), QtCore.Qt.NoBrush)
        self.assertIsInstance(skipped, QtWidgets.QGraphicsPathItem)
        horizontal = self.view.summaries[HORIZONTAL].text()
        vertical = self.view.summaries[VERTICAL].text()
        for text in ("Left: 1 (50.0%)", "Right: 1 (50.0%)", "Correct: 1",
                     "Incorrect: 1", "Timeouts: 1", "Skips: 1"):
            self.assertIn(text, horizontal)
        self.assertIn("Right: 1 (100.0%)", vertical)

    def test_new_session_clears_all_markers_and_summaries(self):
        self.add(HORIZONTAL)
        self.add(VERTICAL)
        self.view.reset_session()
        self.assertEqual(self.view.outcomes, [])
        self.assertEqual(self.view.markers, [])
        self.assertEqual(self.view.scene.items(), [])
        self.assertIn("Left: 0 (--)", self.view.summaries[HORIZONTAL].text())
        self.add(VERTICAL)
        self.assertEqual(self.view.markers[0].x(), self.view.SPACING)

    def test_invalid_rows_are_reported_and_other_tasks_do_not_clear_history(self):
        self.add(HORIZONTAL)
        with self.assertLogs("gui.performance_view", level="WARNING"):
            self.view.add_trial(HORIZONTAL, HorizontalRandomSide.CSV_HEADER, [1])
        self.view.add_trial("consecutive_reward", [], [])
        self.assertEqual(len(self.view.outcomes), 1)

    def test_long_session_can_scroll_back_to_earlier_trials(self):
        self.view.resize(500, 300)
        self.view.show()
        self.addCleanup(self.view.close)
        for trial in range(1, 101):
            self.add(HORIZONTAL, trial=trial)
        self.app.processEvents()
        bar = self.view.timeline.horizontalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        self.assertEqual(bar.value(), bar.maximum())
        bar.setValue(0)
        self.assertEqual(bar.value(), 0)
        self.assertEqual(len(self.view.markers), 100)
        self.add(VERTICAL)
        self.assertEqual(bar.value(), 0)

    def test_timeline_and_footer_do_not_overlap_at_minimum_height(self):
        self.view.resize(1030, self.view.minimumSizeHint().height())
        self.view.show()
        self.addCleanup(self.view.close)
        self.app.processEvents()
        layout = self.view.layout()
        timeline_row = layout.itemAt(3).widget()
        footer = layout.itemAt(4).widget()
        self.assertLess(timeline_row.geometry().bottom(), footer.geometry().top())
        self.assertLessEqual(footer.geometry().bottom(), self.view.height())

    def test_worker_emits_every_final_trial_across_fast_loop_transitions(self):
        class Horizontal(HorizontalRandomSide):
            def step(self, keys):
                return super().step(["c"] if self.trial_num == 0 else ["l"])

        class Vertical(VerticalRandomSide):
            def step(self, keys):
                return super().step(["c"] if self.trial_num == 0 else ["r"])

        bus = Bus()
        hw = MagicMock()
        hw.ir_detector.poll_events.return_value = []
        registry = {HORIZONTAL: {"class": Horizontal}, VERTICAL: {"class": Vertical}}
        stages = [{"type": "stage", "experiment": name, "trials": 1}
                  for name in (HORIZONTAL, VERTICAL)]
        pipeline = [{"type": "loop", "count": 3, "children": stages}]
        with tempfile.TemporaryDirectory() as root:
            worker = PipelineWorker(hw, None, registry, pipeline, bus)
            with patch("gui.worker._ROOT", root), \
                    patch("experiments._base.AMBIENT_ENABLED", False), \
                    patch("builtins.print"):
                worker.run()
            events = Bus.drain(bus.events)
            self.assertEqual(events[0], ("session", None))
            self.assertEqual(events[-1], ("done", None))
            trials = [payload for kind, payload in events if kind == "trial"]
            self.assertEqual([payload[0] for payload in trials],
                             [HORIZONTAL, VERTICAL] * 3)
            for payload in trials:
                self.view.add_trial(*payload)
            self.assertEqual(len(self.view.outcomes), 6)
            # CSV remains per-stage, with one header and one outcome in every file.
            files = [os.path.join(directory, name)
                     for directory, _, names in os.walk(root) for name in names]
            self.assertEqual(len(files), 6)
            for path in files:
                with open(path, newline="") as stream:
                    self.assertEqual(len(list(csv.reader(stream))), 2)
