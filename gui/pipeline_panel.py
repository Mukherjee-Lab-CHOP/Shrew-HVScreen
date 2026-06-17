"""PipelinePanel — left side. Manage one or more named pipelines of experiment
stages and choose which one is active.

Each stage = {experiment, trials, params}. trials == 0 means "run forever" (until
the stage/experiment is skipped or the run is stopped). The worker runs the
ACTIVE pipeline's stages top to bottom. Several pipelines can be created and
switched between; the whole set (plus per-stage variable overrides) is persisted
by the main window across restarts.

Stages are created/edited on the right-side experiment panel (which carries the
variable editors); this panel handles ordering, removal, and pipeline switching.
"""

import copy

from PySide6 import QtCore, QtGui, QtWidgets

from .variables_panel import VariablesPanel


class _StageList(QtWidgets.QListWidget):
    """A list that supports drag-and-drop reordering and clears its selection
    when you click empty space (returning the editor to 'creating' mode)."""

    reordered = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)

    def mousePressEvent(self, event):
        if self.itemAt(event.pos()) is None:
            self.clearSelection()
            self.setCurrentRow(-1)
        super().mousePressEvent(event)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit()


def _fmt_trials(n):
    return "∞" if not n else str(n)


def _spec_vars(registry, name):
    info = registry.get(name)
    spec = info["spec"] if info else {"variables": []}
    return spec.get("variables", [])


class StageDialog(QtWidgets.QDialog):
    """Pop-up for creating (or editing) a stage: experiment, trial count (with an
    ∞ option), and the experiment's variables."""

    def __init__(self, registry, stage=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New stage" if stage is None else "Edit stage")
        self._registry = registry
        self.resize(380, 460)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.exp_combo = QtWidgets.QComboBox()
        self.exp_combo.addItems(sorted(registry))
        form.addRow("Experiment", self.exp_combo)

        trials_box = QtWidgets.QWidget()
        trow = QtWidgets.QHBoxLayout(trials_box)
        trow.setContentsMargins(0, 0, 0, 0)
        self.trials_spin = QtWidgets.QSpinBox()
        self.trials_spin.setRange(1, 1000000)
        self.trials_spin.setValue(10)
        self.infinite_chk = QtWidgets.QCheckBox("∞")
        self.infinite_chk.toggled.connect(lambda on: self.trials_spin.setEnabled(not on))
        trow.addWidget(self.trials_spin)
        trow.addWidget(self.infinite_chk)
        trow.addStretch(1)
        form.addRow("Trials", trials_box)
        layout.addLayout(form)

        gb = QtWidgets.QGroupBox("Variables")
        gbl = QtWidgets.QVBoxLayout(gb)
        self.variables = VariablesPanel()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.variables)
        gbl.addWidget(scroll)
        layout.addWidget(gb, 1)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # reload variable editors whenever the experiment changes
        self.exp_combo.currentTextChanged.connect(self._reload_vars)

        if stage:
            self.exp_combo.setCurrentText(stage["experiment"])
            self._reload_vars(stage["experiment"])
            trials = int(stage.get("trials", 10) or 0)
            self.infinite_chk.setChecked(trials == 0)
            if trials > 0:
                self.trials_spin.setValue(trials)
            self.variables.set_values(stage.get("params") or {})
        else:
            self._reload_vars(self.exp_combo.currentText())

    def _reload_vars(self, name):
        self.variables.load_variables(_spec_vars(self._registry, name))

    def stage(self):
        trials = 0 if self.infinite_chk.isChecked() else self.trials_spin.value()
        return {
            "experiment": self.exp_combo.currentText(),
            "trials": trials,
            "params": self.variables.values(),
        }


class PipelinePanel(QtWidgets.QWidget):
    pipeline_changed = QtCore.Signal()      # stages or the pipeline set changed -> persist
    stage_selected = QtCore.Signal(int)     # row (-1 when nothing is selected)
    add_requested = QtCore.Signal()         # user wants to create a new stage in the editor

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self._registry = registry
        self._pipelines = {"Default": []}   # name -> list[stage]
        self._active = "Default"
        self._loading = False               # suppress change signals during bulk loads
        self._clipboard = None              # copied stage (deep-copied on copy/paste)
        self._busy = False                  # True while a run is in progress

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("<b>Pipelines</b>"))

        # pipeline selector + management
        prow = QtWidgets.QHBoxLayout()
        self.pipe_combo = QtWidgets.QComboBox()
        self.pipe_combo.currentTextChanged.connect(self._on_pipe_combo)
        prow.addWidget(self.pipe_combo, 1)
        self._mgmt_btns = []
        for text, slot in (("New", self.new_pipeline), ("Rename", self.rename_pipeline),
                           ("Dup", self.duplicate_pipeline), ("Del", self.delete_pipeline)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(slot)
            prow.addWidget(b)
            self._mgmt_btns.append(b)
        layout.addLayout(prow)

        layout.addWidget(QtWidgets.QLabel(
            "Stages (top → bottom). Click one to edit it on the right; "
            "click empty space to deselect."))
        self.list = _StageList()
        self.list.currentRowChanged.connect(self.stage_selected.emit)
        self.list.itemDoubleClicked.connect(lambda _i: self.edit_stage_dialog())
        self.list.reordered.connect(self._on_reordered)
        layout.addWidget(self.list, 1)

        row = QtWidgets.QHBoxLayout()
        for text, slot in (("＋ New stage", self.new_stage_dialog),
                           ("Remove", self.remove_stage),
                           ("Move ↑", self.move_up), ("Move ↓", self.move_down)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
            self._mgmt_btns.append(b)
        layout.addLayout(row)

        # clipboard ops (also bound to Ctrl+D / Ctrl+C / Ctrl+V on the list)
        crow = QtWidgets.QHBoxLayout()
        for text, slot in (("Duplicate", self.duplicate_stage),
                           ("Copy", self.copy_stage), ("Paste", self.paste_stage)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(slot)
            crow.addWidget(b)
            self._mgmt_btns.append(b)
            if text == "Paste":
                self._paste_btn = b
        layout.addLayout(crow)

        for seq, slot in (("Ctrl+D", self.duplicate_stage), ("Ctrl+C", self.copy_stage),
                          ("Ctrl+V", self.paste_stage)):
            sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self.list)
            sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        self.current_label = QtWidgets.QLabel("Stage: —")
        layout.addWidget(self.current_label)

        self._sync_combo()
        self._update_paste_enabled()        # nothing copied yet -> Paste disabled

    # ---- active pipeline ---------------------------------------------------
    @property
    def _stages(self):
        return self._pipelines.setdefault(self._active, [])

    def active_name(self):
        return self._active

    # ---- model -------------------------------------------------------------
    def get_pipeline(self):
        return [dict(s) for s in self._stages]

    def selected_index(self):
        return self.list.currentRow()

    def get_stage(self, index):
        if 0 <= index < len(self._stages):
            return dict(self._stages[index])
        return None

    def add_stage_data(self, stage):
        """Append a stage from the right-side editor and select it."""
        self._stages.append(dict(stage))
        self._refresh()
        self.list.setCurrentRow(len(self._stages) - 1)

    def update_stage(self, index, stage):
        """Replace an existing stage in place (kept selected)."""
        if 0 <= index < len(self._stages):
            self._stages[index] = dict(stage)
            self._refresh()
            self.list.setCurrentRow(index)

    def insert_stage(self, index, stage):
        """Insert a stage at `index` (clamped) and select it."""
        index = max(0, min(index, len(self._stages)))
        self._stages.insert(index, dict(stage))
        self._refresh()
        self.list.setCurrentRow(index)

    def clear_selection(self):
        self.list.clearSelection()
        self.list.setCurrentRow(-1)

    # ---- duplicate / copy / paste ------------------------------------------
    def duplicate_stage(self):
        """Insert a copy of the selected stage right below it."""
        i = self.list.currentRow()
        if 0 <= i < len(self._stages):
            self.insert_stage(i + 1, copy.deepcopy(self._stages[i]))

    def copy_stage(self):
        """Copy the selected stage to the clipboard (usable across pipelines)."""
        i = self.list.currentRow()
        if 0 <= i < len(self._stages):
            self._clipboard = copy.deepcopy(self._stages[i])
            self._update_paste_enabled()

    def paste_stage(self):
        """Paste the clipboard stage below the selection (or at the end)."""
        if self._clipboard is None:
            return
        i = self.list.currentRow()
        at = i + 1 if i >= 0 else len(self._stages)
        self.insert_stage(at, copy.deepcopy(self._clipboard))

    # ---- create / edit via pop-up dialog -----------------------------------
    def new_stage_dialog(self):
        if not self._registry:
            return
        dlg = StageDialog(self._registry, parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.add_stage_data(dlg.stage())

    def edit_stage_dialog(self):
        i = self.list.currentRow()
        stage = self.get_stage(i)
        if stage is None:
            return
        dlg = StageDialog(self._registry, stage=stage, parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.update_stage(i, dlg.stage())

    def remove_stage(self):
        i = self.list.currentRow()
        if 0 <= i < len(self._stages):
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

    def _on_reordered(self):
        """A drag-and-drop reorder finished: rebuild the stage list to match the
        list widget's new visual order (each item carries its old index)."""
        n = len(self._stages)
        order = [self.list.item(r).data(QtCore.Qt.UserRole) for r in range(self.list.count())]
        if len(order) != n or set(order) != set(range(n)):
            self._refresh()                 # inconsistent drop -> restore from model
            return
        self._pipelines[self._active] = [self._stages[o] for o in order]
        self._refresh()

    # ---- pipeline management ----------------------------------------------
    def new_pipeline(self):
        suggested = self._unique_name("Pipeline")
        name, ok = QtWidgets.QInputDialog.getText(
            self, "New pipeline", "Name:", text=suggested)
        if not ok:
            return
        name = name.strip() or suggested
        if name in self._pipelines:
            QtWidgets.QMessageBox.warning(self, "Exists",
                                          f"A pipeline named '{name}' already exists.")
            return
        self._pipelines[name] = []
        self._active = name
        self._sync_combo()
        self._refresh()

    def rename_pipeline(self):
        old = self._active
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename pipeline", "Name:", text=old)
        if not ok:
            return
        name = name.strip()
        if not name or name == old:
            return
        if name in self._pipelines:
            QtWidgets.QMessageBox.warning(self, "Exists",
                                          f"A pipeline named '{name}' already exists.")
            return
        # preserve insertion order while renaming the active key
        self._pipelines = {(name if k == old else k): v
                           for k, v in self._pipelines.items()}
        self._active = name
        self._sync_combo()
        self._refresh()

    def duplicate_pipeline(self):
        name = self._unique_name(f"{self._active} copy")
        self._pipelines[name] = copy.deepcopy(self._stages)
        self._active = name
        self._sync_combo()
        self._refresh()

    def delete_pipeline(self):
        if len(self._pipelines) <= 1:
            QtWidgets.QMessageBox.information(
                self, "Keep one", "At least one pipeline must remain.")
            return
        if QtWidgets.QMessageBox.question(
                self, "Delete pipeline",
                f"Delete pipeline '{self._active}'?") != QtWidgets.QMessageBox.Yes:
            return
        self._pipelines.pop(self._active, None)
        self._active = next(iter(self._pipelines))
        self._sync_combo()
        self._refresh()

    def _on_pipe_combo(self, name):
        if self._loading or not name or name == self._active:
            return
        if name in self._pipelines:
            self._active = name
            self._refresh()                 # emits pipeline_changed -> persist active
            self.clear_selection()

    # ---- persistence -------------------------------------------------------
    def to_dict(self):
        return {"pipelines": copy.deepcopy(self._pipelines), "active": self._active}

    def load_dict(self, data):
        self._loading = True
        try:
            pls = data.get("pipelines") or {}
            self._pipelines = {k: [dict(s) for s in v] for k, v in pls.items()} or \
                {"Default": []}
            active = data.get("active")
            self._active = active if active in self._pipelines else next(iter(self._pipelines))
        finally:
            self._loading = False
        self._sync_combo()
        self._refresh()

    # ---- helpers -----------------------------------------------------------
    def _unique_name(self, base):
        if base not in self._pipelines:
            return base
        i = 2
        while f"{base} {i}" in self._pipelines:
            i += 1
        return f"{base} {i}"

    def _sync_combo(self):
        self._loading = True
        self.pipe_combo.clear()
        self.pipe_combo.addItems(list(self._pipelines.keys()))
        idx = self.pipe_combo.findText(self._active)
        if idx >= 0:
            self.pipe_combo.setCurrentIndex(idx)
        self._loading = False

    def _refresh(self):
        self.list.clear()
        for i, s in enumerate(self._stages):
            extra = "" if not s.get("params") else "  " + ", ".join(
                f"{k}={v}" for k, v in s["params"].items())
            prefix = "" if i == 0 else "↓ "
            item = QtWidgets.QListWidgetItem(
                f"{prefix}{i+1}. {s['experiment']}  ×{_fmt_trials(s.get('trials'))}{extra}")
            item.setData(QtCore.Qt.UserRole, i)     # track index across drag-reorders
            self.list.addItem(item)
        if not self._loading:
            self.pipeline_changed.emit()

    def set_default_stage(self, experiment, params):
        """Seed a single 'Default' pipeline with one stage (first-run only)."""
        self._pipelines = {"Default": [
            {"experiment": experiment, "trials": 10, "params": dict(params)}]}
        self._active = "Default"
        self._sync_combo()
        self._refresh()

    def highlight_stage(self, index):
        self.current_label.setText(
            f"Stage: {index+1}/{len(self._stages)}"
            if 0 <= index < len(self._stages) else "Stage: —")
        for i in range(self.list.count()):
            item = self.list.item(i)
            font = item.font()
            font.setBold(i == index)
            item.setFont(font)

    def _update_paste_enabled(self):
        if hasattr(self, "_paste_btn"):
            self._paste_btn.setEnabled(self._clipboard is not None and not self._busy)

    def set_busy(self, busy):
        """Lock pipeline switching / management while a run is in progress."""
        self._busy = busy
        self.pipe_combo.setEnabled(not busy)
        for b in self._mgmt_btns:
            b.setEnabled(not busy)
        self.list.setDragDropMode(
            QtWidgets.QAbstractItemView.NoDragDrop if busy
            else QtWidgets.QAbstractItemView.InternalMove)
        self._update_paste_enabled()
