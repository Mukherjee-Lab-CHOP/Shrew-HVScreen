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
            for index, stage in enumerate(self._pipeline):
                if self._stop.is_set():
                    break
                self._run_stage(index, stage)
        except Exception as e:        # never let the worker die silently
            self._bus.push_print(f"[worker error] {e!r}")
        finally:
            self._hw.link.on_send = prev_hook
            sys.stdout, sys.stderr = old_stdout, old_stderr
            self._bus.set_status(running=False, state=None)
            self._bus.push_event("done")

    def _run_stage(self, index, stage):
        name = stage["experiment"]
        info = self._registry.get(name)
        if info is None:
            self._bus.push_print(f"[worker] unknown experiment '{name}', skipping.")
            return
        target = int(stage.get("trials", 1))
        params = stage.get("params") or {}

        data_dir = os.path.join(_ROOT, "data", name)
        os.makedirs(data_dir, exist_ok=True)
        csv_path = os.path.join(
            data_dir, datetime.now().strftime("session_%Y%m%d_%H%M%S.csv"))

        self._bus.set_status(stage_index=index, stage_label=name, csv_path=csv_path)
        self._bus.push_event("stage", index)
        self._bus.push_print(f"\n=== STAGE {index+1}: {name}  (target {target} trials) ===")

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
                    self._bus.push_print(
                        f"=== STAGE {index+1} complete: {done} trials ===")
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

    def _build_experiment(self, cls, csv_path, params):
        try:
            return cls(self._hw, self._display, csv_path=csv_path, params=params)
        except TypeError:
            # experiment that doesn't accept params yet
            return cls(self._hw, self._display, csv_path=csv_path)
        except Exception as e:
            self._bus.push_print(f"[worker] could not start experiment: {e!r}")
            return None
