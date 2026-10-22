"""Live performance plots for horizontal/vertical random-side experiments."""

from collections import deque

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis


class PerformanceView(QtWidgets.QWidget):
    WINDOW_SIZE = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.summary = QtWidgets.QLabel("Waiting for random-side experiment data")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.chart = QChart()
        self.chart.setTitle("Rolling performance (last 10 outcomes)")
        self.accuracy_series = QLineSeries()
        self.accuracy_series.setName("Correct choices")
        self.accuracy_series.setColor(QtGui.QColor("#167d6a"))
        self.reward_series = QLineSeries()
        self.reward_series.setName("Rewarded")
        self.reward_series.setColor(QtGui.QColor("#d17a22"))
        self.chart.addSeries(self.accuracy_series)
        self.chart.addSeries(self.reward_series)

        self.axis_x = QValueAxis()
        self.axis_x.setTitleText("Trial number")
        self.axis_x.setLabelFormat("%d")
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("Percent")
        self.axis_y.setRange(0, 100)
        self.axis_y.setLabelFormat("%d%%")
        self.chart.addAxis(self.axis_x, QtCore.Qt.AlignBottom)
        self.chart.addAxis(self.axis_y, QtCore.Qt.AlignLeft)
        for series in (self.accuracy_series, self.reward_series):
            series.attachAxis(self.axis_x)
            series.attachAxis(self.axis_y)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QtGui.QPainter.Antialiasing)
        layout.addWidget(self.chart_view, 1)

    def set_data(self, header, rows):
        columns = {name: index for index, name in enumerate(header)}
        if "horizontal_side" in columns:
            target_name = "Horizontal target"
        elif "vertical_side" in columns:
            target_name = "Vertical target"
        else:
            self._clear(f"Performance plot not available for this task.\n"
                        f"Showing random-side tasks only.")
            return

        required = ("trial_number", "chosen_side", "correct", "reward")
        if any(name not in columns for name in required):
            self._clear("This CSV does not contain the fields needed for a performance plot.")
            return

        outcomes = []
        timeouts = 0
        skips = 0
        left_choices = 0
        right_choices = 0
        for row in rows:
            if len(row) < len(header):
                continue
            chosen = row[columns["chosen_side"]].strip().upper()
            if chosen == "SKIP":
                skips += 1
                continue
            try:
                trial_number = int(float(row[columns["trial_number"]]))
                correct = int(row[columns["correct"]]) == 1
            except ValueError:
                continue
            if chosen == "TIMEOUT":
                timeouts += 1
            elif chosen == "LEFT":
                left_choices += 1
            elif chosen == "RIGHT":
                right_choices += 1
            rewarded = row[columns["reward"]].strip().upper() == "REWARD"
            outcomes.append((trial_number, correct, rewarded))

        self.accuracy_series.clear()
        self.reward_series.clear()
        recent = deque(maxlen=self.WINDOW_SIZE)
        for trial_number, correct, rewarded in outcomes:
            recent.append((correct, rewarded))
            count = len(recent)
            accuracy = 100 * sum(item[0] for item in recent) / count
            reward_rate = 100 * sum(item[1] for item in recent) / count
            self.accuracy_series.append(trial_number, accuracy)
            self.reward_series.append(trial_number, reward_rate)

        if outcomes:
            first_trial = outcomes[0][0]
            last_trial = outcomes[-1][0]
            self.axis_x.setRange(max(0, first_trial - 1), max(first_trial + 1, last_trial + 1))
            accuracy_total = 100 * sum(item[1] for item in outcomes) / len(outcomes)
            reward_total = sum(item[2] for item in outcomes)
            accuracy_text = f"{accuracy_total:.1f}%"
            reward_text = f"{reward_total}/{len(outcomes)}"
        else:
            self.axis_x.setRange(0, 1)
            accuracy_text = "--"
            reward_text = "0/0"

        self.chart.setTitle(f"{target_name}: rolling performance (last 10 outcomes)")
        self.summary.setText(
            f"Outcomes: {len(outcomes)} | Accuracy: {accuracy_text} | "
            f"Rewards: {reward_text} | Left: {left_choices} | Right: {right_choices} | "
            f"Timeouts: {timeouts} | Skips: {skips}"
        )

    def _clear(self, message):
        self.accuracy_series.clear()
        self.reward_series.clear()
        self.axis_x.setRange(0, 1)
        self.chart.setTitle("Task performance")
        self.summary.setText(message)