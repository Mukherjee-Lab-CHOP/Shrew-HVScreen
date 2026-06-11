"""VariablesPanel — editors for an experiment's tunable variables (from SPEC).

Builds a spin box per variable and exposes the current values as a params dict
to pass to the experiment.
"""

from PySide6 import QtCore, QtWidgets


class VariablesPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._form = QtWidgets.QFormLayout(self)
        self._form.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self._editors = {}     # key -> (widget, type)

    def load_variables(self, variables, values=None):
        """Rebuild editors for the given SPEC variable list, optionally seeded
        with `values` (a params dict)."""
        values = values or {}
        while self._form.rowCount():
            self._form.removeRow(0)
        self._editors = {}
        for var in variables:
            key = var["key"]
            vtype = var.get("type", "float")
            default = values.get(key, var.get("default", 0))
            if vtype == "int":
                w = QtWidgets.QSpinBox()
                w.setRange(int(var.get("min", 0)), int(var.get("max", 1_000_000)))
                w.setSingleStep(int(var.get("step", 1)))
                w.setValue(int(default))
            else:
                w = QtWidgets.QDoubleSpinBox()
                w.setDecimals(3)
                w.setRange(float(var.get("min", 0.0)), float(var.get("max", 1e9)))
                w.setSingleStep(float(var.get("step", 0.1)))
                w.setValue(float(default))
            self._editors[key] = (w, vtype)
            self._form.addRow(var.get("label", key), w)

    def values(self):
        out = {}
        for key, (w, vtype) in self._editors.items():
            out[key] = int(w.value()) if vtype == "int" else float(w.value())
        return out

    def set_enabled(self, enabled):
        for w, _ in self._editors.values():
            w.setEnabled(enabled)
