"""PipelinePanel — left side. Build an ordered pipeline of experiment stages.

Each stage = (experiment, number of trials, variable overrides). The worker runs
them top to bottom: "run this experiment N times, then switch to the next with
these variables." Stages can be added, edited, reordered, and removed.
"""

from PySide6 import QtCore, QtWidgets

from .variables_panel import VariablesPanel


class StageDialog(QtWidgets.QDialog):
    def __init__(self, registry, stage=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pipeline stage")
        self._registry = registry
        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.exp_combo = QtWidgets.QComboBox()
        self.exp_combo.addItems(sorted(registry))
        self.trials_spin = QtWidgets.QSpinBox()
        self.trials_spin.setRange(1, 100000)
        self.trials_spin.setValue(10)
        form.addRow("Experiment", self.exp_combo)
        form.addRow("Trials", self.trials_spin)
        layout.addLayout(form)

        layout.addWidget(QtWidgets.QLabel("Variable overrides:"))
        self.vars = VariablesPanel()
        layout.addWidget(self.vars)

        self.exp_combo.currentTextChanged.connect(self._reload_vars)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if stage:
            self.exp_combo.setCurrentText(stage["experiment"])
            self.trials_spin.setValue(stage["trials"])
            self._reload_vars(stage["experiment"], stage.get("params"))
        else:
            self._reload_vars(self.exp_combo.currentText())

    def _reload_vars(self, name, values=None):
        info = self._registry.get(name)
        spec = info["spec"] if info else {"variables": []}
        self.vars.load_variables(spec.get("variables", []), values)

    def stage(self):
        return {
            "experiment": self.exp_combo.currentText(),
            "trials": self.trials_spin.value(),
            "params": self.vars.values(),
        }


class PipelinePanel(QtWidgets.QWidget):
    pipeline_changed = QtCore.Signal()

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self._registry = registry
        self._stages = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("<b>Pipeline</b> (runs top → bottom)"))

        self.list = QtWidgets.QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self.edit_stage())
        layout.addWidget(self.list, 1)

        row = QtWidgets.QHBoxLayout()
        for text, slot in (("Add", self.add_stage), ("Edit", self.edit_stage),
                           ("Remove", self.remove_stage), ("↑", self.move_up),
                           ("↓", self.move_down)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        layout.addLayout(row)

        self.current_label = QtWidgets.QLabel("Stage: —")
        layout.addWidget(self.current_label)

    # ---- model -------------------------------------------------------------
    def get_pipeline(self):
        return [dict(s) for s in self._stages]

    def _refresh(self):
        self.list.clear()
        for i, s in enumerate(self._stages):
            extra = "" if not s["params"] else "  " + ", ".join(
                f"{k}={v}" for k, v in s["params"].items())
            prefix = "" if i == 0 else "↓ "
            self.list.addItem(f"{prefix}{i+1}. {s['experiment']}  ×{s['trials']}{extra}")
        self.pipeline_changed.emit()

    # ---- actions -----------------------------------------------------------
    def add_stage(self):
        if not self._registry:
            return
        dlg = StageDialog(self._registry, parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._stages.append(dlg.stage())
            self._refresh()

    def edit_stage(self):
        i = self.list.currentRow()
        if i < 0:
            return
        dlg = StageDialog(self._registry, stage=self._stages[i], parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._stages[i] = dlg.stage()
            self._refresh()

    def remove_stage(self):
        i = self.list.currentRow()
        if i >= 0:
            self._stages.pop(i)
            self._refresh()

    def move_up(self):
        i = self.list.currentRow()
        if i > 0:
            self._stages[i - 1], self._stages[i] = self._stages[i], self._stages[i - 1]
            self._refresh()
            self.list.setCurrentRow(i - 1)

    def move_down(self):
        i = self.list.currentRow()
        if 0 <= i < len(self._stages) - 1:
            self._stages[i + 1], self._stages[i] = self._stages[i], self._stages[i + 1]
            self._refresh()
            self.list.setCurrentRow(i + 1)

    def set_default_stage(self, experiment, params):
        """Seed the pipeline with a single stage (used on first load)."""
        self._stages = [{"experiment": experiment, "trials": 10, "params": dict(params)}]
        self._refresh()

    def highlight_stage(self, index):
        self.current_label.setText(
            f"Stage: {index+1}/{len(self._stages)}" if 0 <= index < len(self._stages) else "Stage: —")
        for i in range(self.list.count()):
            item = self.list.item(i)
            font = item.font()
            font.setBold(i == index)
            item.setFont(font)
