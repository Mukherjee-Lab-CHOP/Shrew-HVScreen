"""PipelineWorker — runs the experiment pipeline on a background thread.

For each stage it builds the chosen experiment with its variable overrides,
runs it until the requested number of trials complete (or Stop is pressed), then
advances to the next stage. All output flows through the Bus:
  * outgoing serial commands  (via hw.link.on_send hook)
  * stdout / log lines        (via a redirected stream)
  * display ops               (the experiment calls our DisplayProxy)
  * state / trial / stage / csv status updates
"""

import os
import sys
import threading
import time
from datetime import datetime

from PySide6 import QtCore

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _SkipLoop(Exception):
    """Raised to unwind out of the innermost running loop (Skip loop control)."""


class _StreamToBus:
    """File-like object: forwards writes to the Bus prints queue (and the real
    stream, so a launching console still shows output)."""

    def __init__(self, bus, real):
        self._bus = bus
        self._real = real
        self._buf = ""

    def write(self, text):
        try:
            self._real.write(text)
        except Exception:
            pass
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._bus.push_print(line)

    def flush(self):
        try:
            self._real.flush()
        except Exception:
            pass


class PipelineWorker(QtCore.QThread):
    def __init__(self, hardware, display_proxy, registry, pipeline, bus, parent=None):
        super().__init__(parent)
        self._hw = hardware
        self._display = display_proxy
        self._registry = registry
        self._pipeline = pipeline
        self._bus = bus
        self._stop = threading.Event()
        self._skip_stage = threading.Event()
        self._skip_loop = threading.Event()

    def request_stop(self):
        self._stop.set()

    # ---- thread body -------------------------------------------------------
    def run(self):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        tee = _StreamToBus(self._bus, old_stdout)
        sys.stdout = tee
        sys.stderr = tee
        # mirror outgoing serial commands into the commands pane
        prev_hook = getattr(self._hw.link, "on_send", None)
        self._hw.link.on_send = self._bus.push_command

        self._bus.set_status(running=True)
        try:
            self._run_pipeline()
        except Exception as e:        # never let the worker die silently
            self._bus.push_print(f"[worker error] {e!r}")
        finally:
            self._hw.link.on_send = prev_hook
            sys.stdout, sys.stderr = old_stdout, old_stderr
            self._bus.set_status(running=False, state=None)
            self._bus.push_event("done")

    def _run_pipeline(self):
        """Walk the node tree top to bottom, repeating each loop's children."""
        try:
            self._run_nodes(self._pipeline)
        except _SkipLoop:
            pass        # "skip loop" pressed outside any loop -> nothing to unwind

    def _run_nodes(self, nodes):
        for node in nodes:
            if self._stop.is_set():
                return
            if node.get("type") == "loop":
                self._run_loop(node)
            else:
                self._run_stage(node)
                self._check_skip()      # may raise _SkipLoop to unwind a loop

    def _run_loop(self, node):
        count = int(node.get("count", 1) or 0)      # 0 == infinite
        label = f"×{count}" if count else "(∞)"
        self._bus.push_print(f"\n=== LOOP start {label} ===")
        iteration = 0
        while not self._stop.is_set():
            if count and iteration >= count:
                break
            try:
                self._run_nodes(node.get("children", []))
            except _SkipLoop:
                self._bus.push_print("=== LOOP skipped ===")
                break
            iteration += 1
        self._bus.push_print(f"=== LOOP done ({iteration} iteration(s)) ===")

    def _check_skip(self):
        if self._skip_loop.is_set():
            self._skip_loop.clear()
            raise _SkipLoop()

    def _run_stage(self, node):
        name = node["experiment"]
        info = self._registry.get(name)
        if info is None:
            self._bus.push_print(f"[worker] unknown experiment '{name}', skipping.")
            return
        target = int(node.get("trials", 1))
        params = node.get("params") or {}

        data_dir = os.path.join(_ROOT, "data", name)
        os.makedirs(data_dir, exist_ok=True)
        csv_path = self._unique_csv(data_dir)

        self._bus.set_status(stage_label=name, csv_path=csv_path)
        self._bus.push_event("node", node.get("id"))
        self._bus.push_print(f"\n=== STAGE {name}  (target {target} trials) ===")

        self._skip_stage.clear()
        exp = self._build_experiment(info["class"], csv_path, params)
        if exp is None:
            return

        def completed(e):
            # uniform "trials finished" count; fall back to trial_num
            return int(getattr(e, "completed_trials", getattr(e, "trial_num", 0)))

        self._bus.set_status(stage_target=target, trials_done=completed(exp),
                             trial_num=getattr(exp, "trial_num", 0))
        last_state = None
        last_done = -1
        last_trial = -1
        try:
            while not self._stop.is_set():
                for ctrl in self._bus.drain_controls():
                    self._apply_control(exp, ctrl)
                # "skip loop" also stops the current stage (then _check_skip
                # unwinds the enclosing loop); leave the flag set for it.
                if self._skip_loop.is_set():
                    self._bus.push_print(f"=== STAGE {name} cut by skip-loop ===")
                    break
                if self._skip_stage.is_set():
                    self._skip_stage.clear()
                    self._bus.push_print(
                        f"=== STAGE {name} skipped ({completed(exp)} trials) ===")
                    break
                keys = self._bus.drain_keys()
                result = exp.step(keys)

                if exp.state != last_state:
                    last_state = exp.state
                    self._bus.set_status(state=exp.state)
                    self._bus.push_event("state", exp.state)
                done = completed(exp)
                trial = int(getattr(exp, "trial_num", done))
                if done != last_done or trial != last_trial:
                    last_done = done
                    last_trial = trial
                    self._bus.set_status(trials_done=done, trial_num=trial)

                # stage complete: requested number of trials finished
                if target > 0 and done >= target:
                    self._bus.push_print(f"=== STAGE {name} complete: {done} trials ===")
                    break
                if result == "QUIT":
                    self._stop.set()
                    break
                time.sleep(0.005)
        finally:
            try:
                exp.close()
            except Exception:
                pass

    def _apply_control(self, exp, ctrl):
        """Apply a structured run control to the live experiment."""
        kind = ctrl.get("type")
        if kind == "set_trial":
            n = max(0, int(ctrl.get("value", 0)))
            # all experiments share these counters; keep them consistent so the
            # CSV numbering and the pipeline progress both reflect the new value.
            if hasattr(exp, "trial_num"):
                exp.trial_num = n
            if hasattr(exp, "completed_trials"):
                exp.completed_trials = n
            self._bus.push_print(f"[control] trial number set to {n}")
        elif kind == "skip_trial":
            fn = getattr(exp, "skip_trial", None)
            if callable(fn):
                try:
                    fn()
                except Exception as e:
                    self._bus.push_print(f"[control] skip failed: {e!r}")
            else:
                self._bus.push_print("[control] this experiment can't skip trials")
        elif kind == "skip_stage":
            self._skip_stage.set()
        elif kind == "skip_loop":
            self._skip_loop.set()

    def _unique_csv(self, data_dir):
        """A session CSV path that won't collide when a stage is run repeatedly
        (the same-second timestamp would otherwise overwrite the previous run)."""
        base = datetime.now().strftime("session_%Y%m%d_%H%M%S")
        path = os.path.join(data_dir, base + ".csv")
        n = 2
        while os.path.exists(path):
            path = os.path.join(data_dir, f"{base}_{n}.csv")
            n += 1
        return path

    def _build_experiment(self, cls, csv_path, params):
        try:
            return cls(self._hw, self._display, csv_path=csv_path, params=params)
        except TypeError:
            # experiment that doesn't accept params yet
            return cls(self._hw, self._display, csv_path=csv_path)
        except Exception as e:
            self._bus.push_print(f"[worker] could not start experiment: {e!r}")
            return None
