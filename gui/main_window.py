"""MainWindow — assembles the whole control panel.

Layout:
    top     : serial bar (COM/connect, stimulus screen) + run controls
    left    : pipeline builder
    middle  : live CSV table + stimulus mirror
    right   : experiment selector, variable editors, state-machine node graph
    bottom  : commands-out log | prints/events log

A ~30 ms QTimer drains the Bus (filled by the background worker) and updates the
widgets, so the GUI thread never touches the worker's internals directly.
"""

import os
import sys

from PySide6 import QtCore, QtWidgets

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import DEFAULT_PORT                      # noqa: E402
from hardware import Hardware                       # noqa: E402

from .bus import Bus                                # noqa: E402
from .experiments_registry import discover          # noqa: E402
from .serial_bar import SerialBar                    # noqa: E402
from .pipeline_panel import PipelinePanel            # noqa: E402
from .variables_panel import VariablesPanel          # noqa: E402
from .state_graph import StateGraphView              # noqa: E402
from .csv_view import CsvView                        # noqa: E402
from .logs_panel import LogsPanel                    # noqa: E402
from .stimulus import StimulusScene, MirrorView, StimulusWindow   # noqa: E402
from .display_proxy import DisplayProxy              # noqa: E402
from .worker import PipelineWorker                   # noqa: E402


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cue Experiment Control Panel")
        self.resize(1480, 920)

        self.registry = discover()
        self.bus = Bus()
        self.hw = None
        self.worker = None
        self.stim_window = None
        self.stim_scene = StimulusScene()
        self._last_csv = None
        self._last_stage = -1

        self._build_ui()

        # drain the worker->GUI bus on the main thread
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._drain_bus)
        self._timer.start()

        # once the window is up, auto-connect to the default port if present
        QtCore.QTimer.singleShot(0, self._autoconnect_default)

    def _autoconnect_default(self):
        """If the default port (COM5) is present, select and connect to it so the
        board is live without the user having to click Connect."""
        if self.hw is not None:
            return
        self.serial_bar.scan_ports()
        if self.serial_bar.select_port(DEFAULT_PORT):
            self.logs.add_print(f"[gui] auto-connecting to {DEFAULT_PORT}…")
            self._connect_hardware(DEFAULT_PORT, self.serial_bar.baud())

    # ---- UI construction ---------------------------------------------------
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)

        # top: serial bar + run controls
        self.serial_bar = SerialBar()
        self.serial_bar.connect_requested.connect(self._connect_hardware)
        self.serial_bar.disconnect_requested.connect(self._disconnect_hardware)
        outer.addWidget(self.serial_bar)
        outer.addLayout(self._build_controls())
        outer.addLayout(self._build_command_controls())

        # main vertical splitter: [panels] over [logs]
        vsplit = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        outer.addWidget(vsplit, 1)

        hsplit = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        vsplit.addWidget(hsplit)

        # left: pipeline
        self.pipeline = PipelinePanel(self.registry)
        hsplit.addWidget(self.pipeline)

        # middle: CSV + mirror
        mid = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.csv_view = CsvView()
        mid_top = QtWidgets.QWidget(); mtl = QtWidgets.QVBoxLayout(mid_top)
        mtl.setContentsMargins(0, 0, 0, 0)
        mtl.addWidget(QtWidgets.QLabel("<b>CSV (live)</b>"))
        mtl.addWidget(self.csv_view)
        mid.addWidget(mid_top)
        mirror_box = QtWidgets.QWidget(); mbl = QtWidgets.QVBoxLayout(mirror_box)
        mbl.setContentsMargins(0, 0, 0, 0)
        mbl.addWidget(QtWidgets.QLabel("<b>Secondary screen (mirror)</b>"))
        self.mirror = MirrorView(self.stim_scene.scene)
        self.mirror.setMinimumHeight(180)
        mbl.addWidget(self.mirror)
        mid.addWidget(mirror_box)
        hsplit.addWidget(mid)

        # right: experiment + variables + state graph
        hsplit.addWidget(self._build_right_panel())
        hsplit.setSizes([320, 640, 460])

        # bottom: logs
        self.logs = LogsPanel()
        vsplit.addWidget(self.logs)
        vsplit.setSizes([640, 220])

        # seed a default pipeline stage from the first experiment
        if self.registry:
            first = sorted(self.registry)[0]
            spec = self.registry[first]["spec"]
            defaults = {v["key"]: v.get("default") for v in spec.get("variables", [])}
            self.pipeline.set_default_stage(first, defaults)

    def _build_controls(self):
        row = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("▶ Start")
        self.start_btn.clicked.connect(self._start_run)
        self.stop_btn = QtWidgets.QPushButton("■ Stop")
        self.stop_btn.clicked.connect(self._stop_run)
        self.stop_btn.setEnabled(False)
        row.addWidget(self.start_btn)
        row.addWidget(self.stop_btn)

        row.addSpacing(20)
        row.addWidget(QtWidgets.QLabel("Manual:"))
        for label, key in (("Center (c)", "c"), ("Left (l)", "l"),
                           ("Right (r)", "r"), ("Timeout (t)", "t")):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(lambda _checked=False, k=key, lbl=label: self._manual_key(k, lbl))
            row.addWidget(b)

        row.addStretch(1)
        self.run_status = QtWidgets.QLabel("idle")
        self.run_status.setStyleSheet("font-weight:bold;")
        row.addWidget(self.run_status)
        return row

    def _build_command_controls(self):
        """Buttons + a free-text field to send raw commands straight to the
        Arduino (independent of any running experiment). Everything sent here
        also shows up in the 'Commands out' log."""
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Send to Arduino:"))
        for label, cmd in (("Gate open", "SERVO 60"), ("Gate close", "SERVO 180"),
                           ("Reward L", "REWARD L"), ("Reward R", "REWARD R"),
                           ("Emit on", "EMIT ON"), ("Emit off", "EMIT OFF"),
                           ("Ping", "PING")):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(lambda _checked=False, c=cmd: self._send_raw(c))
            row.addWidget(b)

        self.cmd_edit = QtWidgets.QLineEdit()
        self.cmd_edit.setPlaceholderText("custom command, e.g.  SERVO 90  or  TONE 1000 200")
        self.cmd_edit.returnPressed.connect(self._send_custom)
        row.addWidget(self.cmd_edit, 1)
        send_btn = QtWidgets.QPushButton("Send")
        send_btn.clicked.connect(self._send_custom)
        row.addWidget(send_btn)
        return row

    def _build_right_panel(self):
        # Vertical splitter so the state-machine area can be resized vs. the
        # experiment/variables area.
        split = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        top = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(top)
        layout.addWidget(QtWidgets.QLabel("<b>Experiment</b>"))
        self.exp_combo = QtWidgets.QComboBox()
        self.exp_combo.addItems(sorted(self.registry))
        self.exp_combo.currentTextChanged.connect(self._on_experiment_selected)
        layout.addWidget(self.exp_combo)

        vbox = QtWidgets.QGroupBox("Variables")
        vlay = QtWidgets.QVBoxLayout(vbox)
        self.variables = VariablesPanel()
        # scroll so every variable is reachable no matter how many there are
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.variables)
        vlay.addWidget(scroll)
        add_btn = QtWidgets.QPushButton("Add as pipeline stage →")
        add_btn.clicked.connect(self._add_current_as_stage)
        vlay.addWidget(add_btn)
        layout.addWidget(vbox, 1)
        split.addWidget(top)

        bottom = QtWidgets.QWidget()
        blay = QtWidgets.QVBoxLayout(bottom)
        blay.addWidget(QtWidgets.QLabel("<b>State machine</b> (drag to resize / move nodes)"))
        self.graph = StateGraphView()
        blay.addWidget(self.graph, 1)
        split.addWidget(bottom)

        split.setSizes([360, 420])
        if self.registry:
            self._on_experiment_selected(self.exp_combo.currentText())
        return split

    # ---- experiment selection ----------------------------------------------
    def _on_experiment_selected(self, name):
        info = self.registry.get(name)
        if not info:
            return
        spec = info["spec"]
        self.variables.load_variables(spec.get("variables", []))
        self.graph.load_spec(spec)

    def _add_current_as_stage(self):
        name = self.exp_combo.currentText()
        if not name:
            return
        trials, ok = QtWidgets.QInputDialog.getInt(
            self, "Add stage", f"How many trials of '{name}'?", 10, 1, 100000)
        if not ok:
            return
        stage = {"experiment": name, "trials": trials, "params": self.variables.values()}
        self.pipeline._stages.append(stage)      # reuse the panel's model
        self.pipeline._refresh()

    # ---- hardware ----------------------------------------------------------
    def _connect_hardware(self, port, baud):
        self.serial_bar.set_connected(False, "connecting…")
        QtWidgets.QApplication.processEvents()
        if self.hw is not None:
            self.hw.close()
        self.hw = Hardware(port=port, baud=baud, verbose=False)
        # surface every inbound firmware line in the prints pane, and mirror
        # outgoing commands (incl. manual ones) into the commands pane.
        self.hw.link.add_listener(self._inbound_line)
        self.hw.link.on_send = self.bus.push_command
        if self.hw.connect():
            # Opening the port resets the Arduino; give it time to boot and
            # answer (boot banner / READY / PONG) before deciding it's silent.
            ok = self.hw.confirm(timeout=3.0)
            self.serial_bar.set_connected(True, f"{port}" + ("" if ok else " (no reply)"))
            self.logs.add_print(f"[gui] connected to {port}"
                                + ("" if ok else " — board not responding (flash firmware?)"))
        else:
            self.serial_bar.set_connected(False, "open failed")
            self.logs.add_print(f"[gui] could not open {port}")

    def _disconnect_hardware(self):
        if self.hw is not None:
            self.hw.close()
            self.hw = None
        self.serial_bar.set_connected(False, "disconnected")

    def _inbound_line(self, line):
        # called from the serial reader thread -> queue is thread-safe
        self.bus.push_print(f"<- {line}")
        return False        # not "handled"; let other listeners (IR) see it too

    def _ensure_hw(self):
        """Return a Hardware to send through, creating a detached one (commands
        logged, not sent) if nothing is connected."""
        if self.hw is None:
            self.hw = Hardware(port=None, verbose=False)
            self.hw.link.add_listener(self._inbound_line)
            self.hw.connect()
            self.logs.add_print("[gui] no Arduino connected — commands are logged, not sent.")
        self.hw.link.on_send = self.bus.push_command
        return self.hw

    def _send_raw(self, cmd):
        """Send a raw command string to the Arduino (link adds the $…\\n framing)."""
        self._ensure_hw().link.send(cmd)

    def _send_custom(self):
        text = self.cmd_edit.text().strip()
        if text:
            self._send_raw(text)
            self.cmd_edit.clear()

    def _manual_key(self, key, label):
        """Feed a manual control key to the running experiment, echoing it so
        it's visible that the press registered."""
        self.bus.push_key(key)
        running = self.worker is not None and self.worker.isRunning()
        if running:
            self.logs.add_print(f"[manual] {label}")
        else:
            self.logs.add_print(f"[manual] {label} — ignored (press Start first)")

    # ---- run control -------------------------------------------------------
    def _start_run(self):
        if self.worker is not None and self.worker.isRunning():
            return
        pipeline = self.pipeline.get_pipeline()
        if not pipeline:
            QtWidgets.QMessageBox.warning(self, "No pipeline", "Add at least one stage.")
            return
        self._ensure_hw()                          # allow detached test runs

        # open the stimulus window on the chosen monitor
        self.stim_window = StimulusWindow(self.stim_scene.scene)
        self.stim_window.open_on_screen(self.serial_bar.screen_index())

        display = DisplayProxy(self.bus)
        self.worker = PipelineWorker(self.hw, display, self.registry, pipeline, self.bus)
        self.worker.finished.connect(self._on_worker_finished)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.serial_bar.set_busy(True)
        self.run_status.setText("running")
        self.worker.start()

    def _stop_run(self):
        if self.worker is not None:
            self.worker.request_stop()
            self.run_status.setText("stopping…")

    def _on_worker_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.serial_bar.set_busy(False)
        self.run_status.setText("idle")
        self.pipeline.highlight_stage(-1)
        self.graph.set_current_state(None)
        if self.stim_window is not None:
            self.stim_window.close()
            self.stim_window = None
        self.worker = None

    # ---- bus draining (main thread) ----------------------------------------
    def _drain_bus(self):
        for line in Bus.drain(self.bus.commands):
            self.logs.add_command(line)
        for line in Bus.drain(self.bus.prints):
            self.logs.add_print(line)
        for op in Bus.drain(self.bus.render):
            self._apply_render(op)
        for kind, payload in Bus.drain(self.bus.events):
            self._handle_event(kind, payload)

        status = self.bus.get_status()
        if status["csv_path"] and status["csv_path"] != self._last_csv:
            self._last_csv = status["csv_path"]
            self.csv_view.set_path(status["csv_path"])
        self.csv_view.refresh()
        if status["running"]:
            stage = status["stage_label"]
            target = status["stage_target"]
            done = status["trials_done"]
            left = max(0, target - done) if target else 0
            self.run_status.setText(
                f"running — stage '{stage}'  trial {done}/{target}  "
                f"({left} left)  [{status['state'] or ''}]")

    def _apply_render(self, op):
        kind = op[0]
        if kind == "show":
            self.stim_scene.show(op[1], op[2])
        elif kind == "choice":
            self.stim_scene.choice(op[1])
        elif kind == "black":
            self.stim_scene.black()

    def _handle_event(self, kind, payload):
        if kind == "state":
            self.graph.set_current_state(payload)
        elif kind == "stage":
            self._last_stage = payload
            self.pipeline.highlight_stage(payload)
            # show the running stage's experiment graph on the right
            stage = self.pipeline.get_pipeline()[payload] if \
                0 <= payload < len(self.pipeline.get_pipeline()) else None
            if stage:
                self.exp_combo.setCurrentText(stage["experiment"])
        elif kind == "done":
            pass

    # ---- shutdown ----------------------------------------------------------
    def closeEvent(self, event):
        if self.worker is not None:
            self.worker.request_stop()
            self.worker.wait(2000)
        if self.stim_window is not None:
            self.stim_window.close()
        if self.hw is not None:
            self.hw.close()
        super().closeEvent(event)
