"""PipelinePanel — left side. Manage one or more named pipelines and choose which
one is active.

A pipeline is an ordered tree of NODES:

  * stage node : {"type":"stage", "id", "experiment", "trials", "params"}
                 trials == 0 means "run forever".
  * loop  node : {"type":"loop", "id", "count", "children":[node, ...]}
                 count == 0 means "repeat forever"; loops may nest.

The worker walks the tree top to bottom, repeating each loop's children `count`
times. Nesting (and the tree's indentation) is the visual structure; a running
"Skip loop" control breaks out of the innermost active loop.
"""

import copy
import uuid

from PySide6 import QtCore, QtGui, QtWidgets

from .variables_panel import VariablesPanel


def _new_id():
    return uuid.uuid4().hex[:8]


def stage_node(experiment, trials, params, nid=None):
    return {"type": "stage", "id": nid or _new_id(),
            "experiment": experiment, "trials": trials, "params": params or {}}


def loop_node(count=1, children=None, nid=None):
    return {"type": "loop", "id": nid or _new_id(),
            "count": count, "children": children or []}


def _fmt_trials(n):
    return "∞" if not n else str(n)


def _fmt_count(n):
    return "∞" if not n else f"{n}×"


def _spec_vars(registry, name):
    info = registry.get(name)
    spec = info["spec"] if info else {"variables": []}
    return spec.get("variables", [])


def _reassign_ids(node):
    """Give a (copied) node and all descendants fresh ids."""
    node["id"] = _new_id()
    for child in node.get("children", []):
        _reassign_ids(child)
    return node


class _PipeTree(QtWidgets.QTreeWidget):
    """Tree of stage/loop items with internal drag-drop reordering + reparenting.
    Stage items reject drops (they can't contain children); loops accept them."""

    reordered = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.setIndentation(22)
        self.setExpandsOnDoubleClick(False)

    def mousePressEvent(self, event):
        if self.itemAt(event.pos()) is None:
            self.clearSelection()
            self.setCurrentItem(None)
        super().mousePressEvent(event)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit()


class StageDialog(QtWidgets.QDialog):
    """Pop-up for creating/editing a stage: experiment, trials (∞ option), vars."""

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
        return stage_node(self.exp_combo.currentText(), trials, self.variables.values())


class LoopDialog(QtWidgets.QDialog):
    """Pop-up to set a loop's repeat count (0 / ∞ = forever)."""

    def __init__(self, count=1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Loop")
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        box = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        self.count_spin = QtWidgets.QSpinBox()
        self.count_spin.setRange(1, 1000000)
        self.count_spin.setValue(count if count else 1)
        self.infinite_chk = QtWidgets.QCheckBox("∞ (forever)")
        self.infinite_chk.setChecked(not count)
        self.infinite_chk.toggled.connect(lambda on: self.count_spin.setEnabled(not on))
        self.count_spin.setEnabled(bool(count))
        row.addWidget(self.count_spin)
        row.addWidget(self.infinite_chk)
        row.addStretch(1)
        form.addRow("Repeat", box)
        layout.addLayout(form)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def count(self):
        return 0 if self.infinite_chk.isChecked() else self.count_spin.value()


class PipelinePanel(QtWidgets.QWidget):
    pipeline_changed = QtCore.Signal()      # tree or pipeline set changed -> persist
    node_selected = QtCore.Signal(str)      # selected node id ("" when none)
    add_requested = QtCore.Signal()         # create a new stage via the side editor

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self._registry = registry
        self._pipelines = {"Default": []}   # name -> list[node]  (tree roots)
        self._active = "Default"
        self._loading = False
        self._clipboard = None
        self._busy = False
        self._node_by_id = {}               # id -> node (rebuilt on every refresh)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("<b>Pipelines</b>"))

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
            "Stages & loops (drag to reorder / nest). Click to edit on the right."))
        self.tree = _PipeTree()
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        self.tree.reordered.connect(self._on_reordered)
        layout.addWidget(self.tree, 1)

        row = QtWidgets.QHBoxLayout()
        for text, slot in (("＋ Stage", self.new_stage_dialog),
                           ("🔁 Loop", self.new_loop),
                           ("Remove", self.remove_selected),
                           ("↑", self.move_up), ("↓", self.move_down)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
            self._mgmt_btns.append(b)
        layout.addLayout(row)

        crow = QtWidgets.QHBoxLayout()
        for text, slot in (("Duplicate", self.duplicate_selected),
                           ("Copy", self.copy_selected), ("Paste", self.paste_clipboard)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(slot)
            crow.addWidget(b)
            self._mgmt_btns.append(b)
            if text == "Paste":
                self._paste_btn = b
        layout.addLayout(crow)

        for seq, slot in (("Ctrl+D", self.duplicate_selected), ("Ctrl+C", self.copy_selected),
                          ("Ctrl+V", self.paste_clipboard)):
            sc = QtGui.QShortcut(QtGui.QKeySequence(seq), self.tree)
            sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        self.current_label = QtWidgets.QLabel("—")
        layout.addWidget(self.current_label)

        self._sync_combo()
        self._refresh()
        self._update_paste_enabled()

    # ---- active pipeline model --------------------------------------------
    @property
    def _nodes(self):
        return self._pipelines.setdefault(self._active, [])

    def active_name(self):
        return self._active

    def get_nodes(self):
        """Deep copy of the active pipeline's node tree (for the worker)."""
        return copy.deepcopy(self._nodes)

    # ---- node lookup -------------------------------------------------------
    def _index(self):
        """Rebuild id -> node map over the whole pipeline set."""
        self._node_by_id = {}

        def walk(nodes):
            for nd in nodes:
                self._node_by_id[nd["id"]] = nd
                if nd["type"] == "loop":
                    walk(nd["children"])
        for stages in self._pipelines.values():
            walk(stages)

    def _locate(self, nid, nodes=None):
        """Return (parent_list, index, node) for nid in the active tree, or None."""
        nodes = self._nodes if nodes is None else nodes
        for i, nd in enumerate(nodes):
            if nd["id"] == nid:
                return nodes, i, nd
            if nd["type"] == "loop":
                hit = self._locate(nid, nd["children"])
                if hit:
                    return hit
        return None

    def selected_id(self):
        item = self.tree.currentItem()
        return item.data(0, QtCore.Qt.UserRole) if item is not None else None

    def selected_node(self):
        nid = self.selected_id()
        if nid is None:
            return None
        hit = self._locate(nid)
        return copy.deepcopy(hit[2]) if hit else None

    def selected_is_loop(self):
        nd = self.selected_node()
        return bool(nd and nd["type"] == "loop")

    # ---- insertion point ---------------------------------------------------
    def _insert_target(self):
        """Where a new node should go: (list, index). Into a selected loop, or
        right after the selected node in its parent, else end of top level."""
        nid = self.selected_id()
        if nid is not None:
            hit = self._locate(nid)
            if hit:
                parent, idx, nd = hit
                if nd["type"] == "loop":
                    return nd["children"], len(nd["children"])
                return parent, idx + 1
        return self._nodes, len(self._nodes)

    # ---- create stage / loop ----------------------------------------------
    def new_stage_dialog(self):
        if not self._registry:
            return
        dlg = StageDialog(self._registry, parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._insert_node(dlg.stage())

    def new_loop(self):
        dlg = LoopDialog(count=1, parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._insert_node(loop_node(count=dlg.count()))

    def add_stage_data(self, stage):
        """Add a stage built by the side editor (top level / into selected loop)."""
        if stage.get("type") != "stage":
            stage = stage_node(stage.get("experiment", ""), stage.get("trials", 1),
                               stage.get("params"))
        self._insert_node(stage)

    def _insert_node(self, node):
        node.setdefault("id", _new_id())
        target, idx = self._insert_target()
        target.insert(idx, node)
        self._refresh(select_id=node["id"])

    # ---- edit --------------------------------------------------------------
    def update_selected_stage(self, data):
        """Apply experiment/trials/params from the side editor to the selected
        stage (keeping its id)."""
        hit = self._locate(self.selected_id() or "")
        if not hit or hit[2]["type"] != "stage":
            return
        nd = hit[2]
        nd["experiment"] = data.get("experiment", nd["experiment"])
        nd["trials"] = data.get("trials", nd.get("trials", 1))
        nd["params"] = data.get("params", nd.get("params", {}))
        self._refresh(select_id=nd["id"])

    def update_selected_loop(self, count):
        hit = self._locate(self.selected_id() or "")
        if hit and hit[2]["type"] == "loop":
            hit[2]["count"] = count
            self._refresh(select_id=hit[2]["id"])

    def _on_double_clicked(self, item, _col):
        nid = item.data(0, QtCore.Qt.UserRole)
        hit = self._locate(nid)
        if not hit:
            return
        nd = hit[2]
        if nd["type"] == "loop":
            dlg = LoopDialog(count=nd.get("count", 1), parent=self)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                nd["count"] = dlg.count()
                self._refresh(select_id=nid)
        else:
            dlg = StageDialog(self._registry, stage=nd, parent=self)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                new = dlg.stage()
                new["id"] = nid
                hit[0][hit[1]] = new
                self._refresh(select_id=nid)

    # ---- remove / move / clipboard ----------------------------------------
    def remove_selected(self):
        hit = self._locate(self.selected_id() or "")
        if hit:
            hit[0].pop(hit[1])
            self._refresh()

    def move_up(self):
        hit = self._locate(self.selected_id() or "")
        if hit and hit[1] > 0:
            lst, i = hit[0], hit[1]
            lst[i - 1], lst[i] = lst[i], lst[i - 1]
            self._refresh(select_id=hit[2]["id"])

    def move_down(self):
        hit = self._locate(self.selected_id() or "")
        if hit and hit[1] < len(hit[0]) - 1:
            lst, i = hit[0], hit[1]
            lst[i + 1], lst[i] = lst[i], lst[i + 1]
            self._refresh(select_id=hit[2]["id"])

    def duplicate_selected(self):
        hit = self._locate(self.selected_id() or "")
        if hit:
            dup = _reassign_ids(copy.deepcopy(hit[2]))
            hit[0].insert(hit[1] + 1, dup)
            self._refresh(select_id=dup["id"])

    def copy_selected(self):
        nd = self.selected_node()
        if nd:
            self._clipboard = nd
            self._update_paste_enabled()

    def paste_clipboard(self):
        if self._clipboard is None:
            return
        node = _reassign_ids(copy.deepcopy(self._clipboard))
        self._insert_node(node)

    def clear_selection(self):
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)

    # ---- drag-drop reorder/reparent ---------------------------------------
    def _on_reordered(self):
        self._pipelines[self._active] = self._tree_to_nodes(self.tree.invisibleRootItem())
        self._index()
        if not self._loading:
            self.pipeline_changed.emit()
        self._relabel()

    def _tree_to_nodes(self, parent_item):
        out = []
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            nid = item.data(0, QtCore.Qt.UserRole)
            base = self._node_by_id.get(nid, {})
            if base.get("type") == "loop":
                out.append({"type": "loop", "id": nid, "count": base.get("count", 1),
                            "children": self._tree_to_nodes(item)})
            else:
                out.append(dict(base))
        return out

    # ---- selection signal --------------------------------------------------
    def _on_current_changed(self, *_):
        self.node_selected.emit(self.selected_id() or "")
        nd = self.selected_node()
        self.current_label.setText(
            "Loop" if nd and nd["type"] == "loop"
            else (nd["experiment"] if nd else "—"))

    # ---- pipeline management ----------------------------------------------
    def new_pipeline(self):
        suggested = self._unique_name("Pipeline")
        name, ok = QtWidgets.QInputDialog.getText(self, "New pipeline", "Name:", text=suggested)
        if not ok:
            return
        name = name.strip() or suggested
        if name in self._pipelines:
            QtWidgets.QMessageBox.warning(self, "Exists", f"'{name}' already exists.")
            return
        self._pipelines[name] = []
        self._active = name
        self._sync_combo()
        self._refresh()

    def rename_pipeline(self):
        old = self._active
        name, ok = QtWidgets.QInputDialog.getText(self, "Rename pipeline", "Name:", text=old)
        if not ok:
            return
        name = name.strip()
        if not name or name == old:
            return
        if name in self._pipelines:
            QtWidgets.QMessageBox.warning(self, "Exists", f"'{name}' already exists.")
            return
        self._pipelines = {(name if k == old else k): v for k, v in self._pipelines.items()}
        self._active = name
        self._sync_combo()
        self._refresh()

    def duplicate_pipeline(self):
        name = self._unique_name(f"{self._active} copy")
        clone = copy.deepcopy(self._nodes)
        for nd in clone:
            _reassign_ids(nd)
        self._pipelines[name] = clone
        self._active = name
        self._sync_combo()
        self._refresh()

    def delete_pipeline(self):
        if len(self._pipelines) <= 1:
            QtWidgets.QMessageBox.information(self, "Keep one", "At least one pipeline must remain.")
            return
        if QtWidgets.QMessageBox.question(
                self, "Delete pipeline", f"Delete pipeline '{self._active}'?") \
                != QtWidgets.QMessageBox.Yes:
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
            self._refresh()
            self.clear_selection()

    # ---- persistence -------------------------------------------------------
    def to_dict(self):
        return {"pipelines": copy.deepcopy(self._pipelines), "active": self._active}

    def load_dict(self, data):
        self._loading = True
        try:
            pls = data.get("pipelines") or {}
            self._pipelines = {k: [dict(s) for s in v] for k, v in pls.items()} or {"Default": []}
            active = data.get("active")
            self._active = active if active in self._pipelines else next(iter(self._pipelines))
            self._migrate()
        finally:
            self._loading = False
        self._sync_combo()
        self._refresh()

    def _migrate(self):
        """Back-compat: tag legacy flat stages as type=stage, drop old flow keys,
        and ensure every node has an id."""
        seen = set()

        def fix(nodes):
            for nd in nodes:
                nd.setdefault("type", "stage")
                for legacy in ("next", "repeat", "routes"):
                    nd.pop(legacy, None)
                nid = nd.get("id")
                if not nid or nid in seen:
                    nid = _new_id()
                    nd["id"] = nid
                seen.add(nid)
                if nd["type"] == "loop":
                    nd.setdefault("count", 1)
                    nd.setdefault("children", [])
                    fix(nd["children"])
        for stages in self._pipelines.values():
            fix(stages)

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

    def _item_text(self, nd):
        if nd["type"] == "loop":
            return f"🔁 Loop  {_fmt_count(nd.get('count', 1))}"
        extra = ""
        if nd.get("params"):
            extra = "  " + ", ".join(f"{k}={v}" for k, v in nd["params"].items())
        return f"{nd['experiment']}  ×{_fmt_trials(nd.get('trials'))}{extra}"

    def _build_items(self, parent_item, nodes):
        for nd in nodes:
            item = QtWidgets.QTreeWidgetItem([self._item_text(nd)])
            item.setData(0, QtCore.Qt.UserRole, nd["id"])
            flags = (QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                     | QtCore.Qt.ItemIsDragEnabled)
            if nd["type"] == "loop":
                flags |= QtCore.Qt.ItemIsDropEnabled
                f = item.font(0); f.setBold(True); item.setFont(0, f)
                item.setForeground(0, QtGui.QColor(120, 170, 255))
            item.setFlags(flags)
            parent_item.addChild(item)
            if nd["type"] == "loop":
                self._build_items(item, nd["children"])

    def _refresh(self, select_id=None):
        self._index()
        self.tree.blockSignals(True)
        self.tree.clear()
        self._build_items(self.tree.invisibleRootItem(), self._nodes)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        if select_id:
            self._select(select_id)
        elif not self._loading:
            self.node_selected.emit("")     # nothing selected -> editor to 'create'
        if not self._loading:
            self.pipeline_changed.emit()

    def _relabel(self):
        """Refresh item texts in place (after a drag) without rebuilding."""
        def walk(parent):
            for i in range(parent.childCount()):
                item = parent.child(i)
                nd = self._node_by_id.get(item.data(0, QtCore.Qt.UserRole))
                if nd:
                    item.setText(0, self._item_text(nd))
                walk(item)
        walk(self.tree.invisibleRootItem())

    def _select(self, nid):
        def walk(parent):
            for i in range(parent.childCount()):
                item = parent.child(i)
                if item.data(0, QtCore.Qt.UserRole) == nid:
                    self.tree.setCurrentItem(item)
                    return True
                if walk(item):
                    return True
            return False
        walk(self.tree.invisibleRootItem())

    def set_default_stage(self, experiment, params):
        self._pipelines = {"Default": [stage_node(experiment, 10, dict(params))]}
        self._active = "Default"
        self._sync_combo()
        self._refresh()

    def highlight_running(self, node_id):
        """Bold the running stage's tree item (clears others)."""
        def walk(parent):
            for i in range(parent.childCount()):
                item = parent.child(i)
                nd = self._node_by_id.get(item.data(0, QtCore.Qt.UserRole))
                is_run = (item.data(0, QtCore.Qt.UserRole) == node_id)
                if nd and nd["type"] == "stage":
                    f = item.font(0); f.setBold(is_run); item.setFont(0, f)
                    item.setForeground(0, QtGui.QColor(120, 220, 130) if is_run
                                       else QtGui.QColor(220, 220, 220))
                walk(item)
        walk(self.tree.invisibleRootItem())

    def _update_paste_enabled(self):
        if hasattr(self, "_paste_btn"):
            self._paste_btn.setEnabled(self._clipboard is not None and not self._busy)

    def set_busy(self, busy):
        self._busy = busy
        self.pipe_combo.setEnabled(not busy)
        for b in self._mgmt_btns:
            b.setEnabled(not busy)
        self.tree.setDragDropMode(
            QtWidgets.QAbstractItemView.NoDragDrop if busy
            else QtWidgets.QAbstractItemView.InternalMove)
        self._update_paste_enabled()
