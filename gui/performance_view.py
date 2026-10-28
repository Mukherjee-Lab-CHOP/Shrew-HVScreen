"""Session-wide outcome timeline for horizontal/vertical random-side tasks."""

import logging
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets


@dataclass
class Outcome:
    experiment: str
    trial: str
    target: str
    chosen: str
    correct: bool
    reward: str


class PerformanceView(QtWidgets.QWidget):
    TASKS = {
        "horizontal_random_side": ("Horizontal", "horizontal_side", 35),
        "vertical_random_side": ("Vertical", "vertical_side", 85),
    }
    SPACING = 28
    COLORS = {"correct": "#16803c", "incorrect": "#c62828", "timeout": "#666666"}

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        legend = QtWidgets.QLabel(
            "Filled green: correct | Filled red: incorrect\n"
            "Hollow circle: timeout | Gray X: skipped")
        legend.setWordWrap(True)
        layout.addWidget(legend)
        self.summaries = {}
        for name in self.TASKS:
            label = QtWidgets.QLabel()
            label.setWordWrap(True)
            self.summaries[name] = label
            layout.addWidget(label)

        timeline_row = QtWidgets.QWidget()
        timeline_row.setFixedHeight(155)
        row = QtWidgets.QHBoxLayout(timeline_row)
        row.setContentsMargins(0, 0, 0, 0)
        labels = QtWidgets.QWidget()
        labels.setFixedWidth(80)
        for title, _, y in self.TASKS.values():
            label = QtWidgets.QLabel(title, labels)
            label.setGeometry(0, y - 10, 80, 20)
        row.addWidget(labels)
        self.scene = QtWidgets.QGraphicsScene(self)
        self.timeline = QtWidgets.QGraphicsView(self.scene)
        self.timeline.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.timeline.setRenderHint(QtGui.QPainter.Antialiasing)
        self.timeline.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.timeline.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.timeline.setMinimumHeight(155)
        self.timeline.setFixedHeight(155)
        row.addWidget(self.timeline, 1)
        layout.addWidget(timeline_row)
        axis_label = QtWidgets.QLabel("Session trial order (equal spacing, not elapsed time)")
        layout.addWidget(axis_label)
        layout.addStretch(1)
        self.reset_session()

    def reset_session(self):
        self.outcomes = []
        self.markers = []
        self.scene.clear()
        self.scene.setSceneRect(0, 0, self.SPACING, 120)
        for name in self.TASKS:
            self._update_summary(name)

    def add_trial(self, experiment, header, row):
        if experiment not in self.TASKS:
            return
        columns = dict(zip(header, (str(value).strip() for value in row)))
        required = ("trial_number", self.TASKS[experiment][1],
                    "chosen_side", "correct", "reward")
        if len(row) != len(header) or any(key not in columns for key in required):
            logging.getLogger(__name__).warning("Invalid performance row for %s: %r",
                                              experiment, row)
            return
        chosen = columns["chosen_side"].upper()
        if chosen not in ("LEFT", "RIGHT", "TIMEOUT", "SKIP") or columns["correct"] not in (
                "0", "1"):
            logging.getLogger(__name__).warning("Invalid performance outcome for %s: %r",
                                              experiment, row)
            return
        outcome = Outcome(experiment, columns["trial_number"],
                          columns[self.TASKS[experiment][1]], chosen,
                          columns["correct"] == "1", columns["reward"])
        self.outcomes.append(outcome)
        self._add_marker(outcome)
        self._update_summary(experiment)

    def _add_marker(self, outcome):
        bar = self.timeline.horizontalScrollBar()
        follow_latest = bar.value() == bar.maximum()
        number = len(self.outcomes)
        x = number * self.SPACING
        y = self.TASKS[outcome.experiment][2]
        if outcome.chosen == "SKIP":
            path = QtGui.QPainterPath()
            path.moveTo(-5, -5)
            path.lineTo(5, 5)
            path.moveTo(-5, 5)
            path.lineTo(5, -5)
            marker = self.scene.addPath(path, QtGui.QPen(QtGui.QColor("#888888"), 2))
            result = "Skipped"
        else:
            timeout = outcome.chosen == "TIMEOUT"
            result = "Timeout" if timeout else ("Correct" if outcome.correct else "Incorrect")
            color = QtGui.QColor(self.COLORS[result.lower()])
            brush = QtGui.QBrush() if timeout else QtGui.QBrush(color)
            marker = self.scene.addEllipse(-6, -6, 12, 12, QtGui.QPen(color, 2), brush)
        marker.setPos(x, y)
        marker.setToolTip(
            f"Session trial {number} | {self.TASKS[outcome.experiment][0]}\n"
            f"Stage trial: {outcome.trial} | Target: {outcome.target}\n"
            f"{result} | Choice: {outcome.chosen} | Reward: {outcome.reward or '--'}")
        self.markers.append(marker)
        tick = self.scene.addSimpleText(str(number))
        tick.setPos(x - tick.boundingRect().width() / 2, 103)
        self.scene.setSceneRect(0, 0, x + self.SPACING, 125)
        if follow_latest:
            bar.setValue(bar.maximum())

    def _update_summary(self, experiment):
        outcomes = [item for item in self.outcomes if item.experiment == experiment]
        left = sum(item.chosen == "LEFT" for item in outcomes)
        right = sum(item.chosen == "RIGHT" for item in outcomes)
        choices = left + right
        correct = sum(item.correct for item in outcomes if item.chosen in ("LEFT", "RIGHT"))
        timeouts = sum(item.chosen == "TIMEOUT" for item in outcomes)
        skips = sum(item.chosen == "SKIP" for item in outcomes)
        left_pct = f"{100 * left / choices:.1f}%" if choices else "--"
        right_pct = f"{100 * right / choices:.1f}%" if choices else "--"
        self.summaries[experiment].setText(
            f"{self.TASKS[experiment][0]}: Left: {left} ({left_pct}) | "
            f"Right: {right} ({right_pct})\n"
            f"Correct: {correct} | Incorrect: {choices - correct} | "
            f"Timeouts: {timeouts} | Skips: {skips}")
