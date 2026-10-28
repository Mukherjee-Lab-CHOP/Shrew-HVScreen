import unittest
from unittest.mock import patch

from PySide6 import QtCore, QtWidgets

from gui.main_window import MainWindow


class MainWindowLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        for name in ("_load_gui_state", "_save_gui_state", "_autoconnect_default"):
            patcher = patch.object(MainWindow, name)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)
        self.window.show()
        self.app.processEvents()

    def test_data_tabs_are_in_right_column_above_state_graph(self):
        tabs = self.window.data_tabs
        right = tabs.parentWidget()
        columns = right.parentWidget()
        self.assertIsInstance(columns, QtWidgets.QSplitter)
        self.assertEqual(columns.orientation(), QtCore.Qt.Orientation.Horizontal)
        self.assertIs(columns.widget(2), right)
        self.assertEqual(right.orientation(), QtCore.Qt.Orientation.Vertical)
        self.assertIs(right.widget(0), tabs)
        self.assertTrue(right.widget(1).isAncestorOf(self.window.graph))
        self.assertGreaterEqual(self.window.graph.height(), 240)
        self.assertIs(tabs.widget(0), self.window.csv_view)
        self.assertIs(tabs.widget(1), self.window.performance_view)
        self.assertIs(tabs.currentWidget(), self.window.performance_view)
        self.assertIs(columns.widget(1).widget(1), self.window.camera_panel)

    def test_pipeline_uses_available_height_below_minimum_editor_and_remains_resizable(self):
        pipeline = self.window.pipeline
        left = pipeline.parentWidget()
        self.assertIsInstance(left, QtWidgets.QSplitter)
        self.assertEqual(left.orientation(), QtCore.Qt.Orientation.Vertical)
        self.assertIs(left.parentWidget().widget(0), left)
        self.assertIs(left.widget(1), pipeline)
        self.assertTrue(left.widget(0).isAncestorOf(self.window.stage_editor))
        self.assertLessEqual(left.width(), 610)
        editor = left.widget(0)
        self.assertAlmostEqual(editor.height(), editor.minimumSizeHint().height(), delta=2)
        self.assertGreater(pipeline.height(), editor.height())
        self.assertGreaterEqual(pipeline.tree.height(), 150)
        sizes = left.sizes()
        left.setSizes([sizes[0] + 50, sizes[1] - 50])
        self.app.processEvents()
        self.assertGreater(editor.height(), sizes[0])
        self.assertLess(pipeline.height(), sizes[1])

    def test_pipeline_receives_extra_height_when_window_grows(self):
        pipeline = self.window.pipeline
        editor = pipeline.parentWidget().widget(0)
        editor_height = editor.height()
        pipeline_height = pipeline.height()
        self.window.resize(self.window.width(), self.window.height() + 200)
        self.app.processEvents()
        self.assertEqual(editor.height(), editor_height)
        self.assertGreater(pipeline.height(), pipeline_height)

    def test_preview_column_is_about_half_previous_640_pixel_width(self):
        self.assertLessEqual(self.window.camera_panel.width(), 360)
        self.assertLessEqual(self.window.mirror.width(), 360)
        panel = self.window.camera_panel
        self.assertGreater(panel.start_btn.y(), panel.selector.y())
        for widget in (panel.selector, panel.refresh_btn, panel.start_btn, panel.stop_btn):
            self.assertTrue(panel.rect().contains(widget.geometry()))

    def test_relocated_pipeline_selection_still_loads_stage_editor(self):
        pipeline = self.window.pipeline
        item = pipeline.tree.topLevelItem(0)
        self.assertIsNotNone(item)
        pipeline.tree.setCurrentItem(item)
        self.app.processEvents()
        node = pipeline.selected_node()
        self.assertEqual(self.window._edit_kind, "stage")
        self.assertEqual(self.window.exp_combo.currentText(), node["experiment"])
        self.assertIn("Editing stage", self.window.mode_label.text())

    def test_performance_is_session_driven_not_replaced_by_csv_refresh(self):
        view = self.window.performance_view
        header = ["trial_number", "target_onset_timestamp", "horizontal_side",
                  "chosen_side", "correct", "reward_percent", "reward"]
        row = [1, 100, "LEFT", "LEFT", 1, 1.0, "REWARD"]
        self.window._handle_event("session", None)
        self.window._handle_event("trial", ("horizontal_random_side", header, row))
        self.window.csv_view.data_changed.emit(header, [row])
        self.window.csv_view.data_changed.emit([], [])
        self.window._handle_event("done", None)
        self.window._on_worker_finished()
        self.assertEqual(len(view.outcomes), 1)
        self.window._handle_event("session", None)
        self.assertEqual(view.outcomes, [])


if __name__ == "__main__":
    unittest.main()
