"""vertical_random_side — present the VERTICAL target on a random side; the
shrew should choose that side.

Each trial auto-starts: the vertical figure appears on a random side (left or
right). The other side shows the horizontal figure if SHOW_OTHER_ORIENTATION is
on, otherwise it stays blank. Choosing the vertical side pays out with
REWARD_PERCENT probability; the other side never pays (0%). Run it for N trials
via the pipeline (e.g. "10 vertical in a row").

State machine:  WAIT_CHOICE --choice/timeout--> ITI --elapsed--> WAIT_CHOICE
"""

import csv
import os
import random
import time
from datetime import datetime

from config import ORIENT_HORIZONTAL, ORIENT_VERTICAL, CH_LEFT, CH_CENTER, CH_RIGHT

STATE_WAIT_CENTER = "WAIT_CENTER_HOLD"
STATE_WAIT_CHOICE = "WAIT_CHOICE"
STATE_ITI         = "ITI"

DEFAULT_REWARD_PERCENT = 0.5
DEFAULT_HOLD_MS = 2000
DEFAULT_CHOICE_TIMEOUT_MS = 20000
DEFAULT_ITI_MS = 6000

BLANK = 0   # display code for "nothing on this side"


def _now_ms():
    return int(time.monotonic() * 1000)


class VerticalRandomSide:
    def __init__(self, hardware, display, csv_path=None, params=None, verbose=True):
        self.hw = hardware
        self.display = display
        self.verbose = verbose

        params = params or {}
        self.REWARD_PERCENT = float(params.get("REWARD_PERCENT", DEFAULT_REWARD_PERCENT))
        self.SHOW_OTHER_ORIENTATION = bool(params.get("SHOW_OTHER_ORIENTATION", True))
        self.HOLD_MS = int(params.get("HOLD_MS", DEFAULT_HOLD_MS))
        self.CHOICE_TIMEOUT_MS = int(params.get("CHOICE_TIMEOUT_MS", DEFAULT_CHOICE_TIMEOUT_MS))
        self.ITI_MS = int(params.get("ITI_MS", DEFAULT_ITI_MS))

        self.trial_num = 0          # trials started
        self.completed_trials = 0   # trials finished (what the pipeline counts)
        self.vertical_side = None   # "LEFT" / "RIGHT"
        self.stim_onset_ms = 0

        self._t0 = _now_ms()
        self.state = STATE_WAIT_CENTER
        self.state_start = self.clock()

        self._broken = {CH_LEFT: False, CH_CENTER: False, CH_RIGHT: False}
        self._broken_since = {CH_LEFT: 0, CH_CENTER: 0, CH_RIGHT: 0}
        self._armed = {CH_LEFT: True, CH_CENTER: True, CH_RIGHT: True}

        self.csv_path = csv_path or datetime.now().strftime("session_%Y%m%d_%H%M%S.csv")
        parent = os.path.dirname(self.csv_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._csv_file = open(self.csv_path, "w", newline="")
        self._csv = csv.writer(self._csv_file)
        self._csv.writerow([
            "trial_number", "target_onset_timestamp", "vertical_side",
            "chosen_side", "correct", "reward_percent", "reward",
        ])
        self._csv_file.flush()

        if self.display is not None:
            self.display.black()
        self._intro()

    # ---- time --------------------------------------------------------------
    def clock(self):
        return _now_ms() - self._t0

    # ---- main loop ---------------------------------------------------------
    def step(self, keys):
        if "q" in keys:
            return "QUIT"
        self._ingest_ir()
        center = self._ir_hold(CH_CENTER) or ("c" in keys)
        left = self._ir_hold(CH_LEFT) or ("l" in keys)
        right = self._ir_hold(CH_RIGHT) or ("r" in keys)
        force_to = "t" in keys
        now = self.clock()

        if self.state == STATE_WAIT_CENTER:
            if center:
                self._start_trial()
        elif self.state == STATE_WAIT_CHOICE:
            if force_to or (now - self.state_start > self.CHOICE_TIMEOUT_MS):
                self._timeout()
            elif left:
                self._choice("LEFT")
            elif right:
                self._choice("RIGHT")
        elif self.state == STATE_ITI:
            if now - self.state_start >= self.ITI_MS:
                self.state = STATE_WAIT_CENTER
                self.state_start = now
                self._log("STATE = WAIT_CENTER_HOLD (hold CENTER, or press c)")
        return None

    # ---- IR hold timing ----------------------------------------------------
    def _ingest_ir(self):
        for channel, broken, _ms in self.hw.ir_detector.poll_events():
            if channel not in self._broken:
                continue
            if broken and not self._broken[channel]:
                self._broken[channel] = True
                self._broken_since[channel] = self.clock()
            elif not broken and self._broken[channel]:
                self._broken[channel] = False
                self._armed[channel] = True

    def _ir_hold(self, channel):
        if (self._broken[channel] and self._armed[channel]
                and (self.clock() - self._broken_since[channel]) >= self.HOLD_MS):
            self._armed[channel] = False
            return True
        return False

    # ---- trial logic -------------------------------------------------------
    def _start_trial(self):
        self.trial_num += 1
        self.vertical_side = random.choice(["LEFT", "RIGHT"])
        other = ORIENT_HORIZONTAL if self.SHOW_OTHER_ORIENTATION else BLANK
        if self.vertical_side == "LEFT":
            left_code, right_code = ORIENT_VERTICAL, other
        else:
            left_code, right_code = other, ORIENT_VERTICAL
        if self.display is not None:
            self.display.show(left_code, right_code)
        self.stim_onset_ms = self.clock()
        self.state = STATE_WAIT_CHOICE
        self.state_start = self.clock()
        self._log(f"TRIAL {self.trial_num}: vertical on {self.vertical_side}"
                  f"  (show_other={self.SHOW_OTHER_ORIENTATION})")

    def _choice(self, side):
        correct = (side == self.vertical_side)
        rewarded = correct and (random.random() < self.REWARD_PERCENT)
        if rewarded:
            self.hw.reward.deliver(side)
        if self.display is not None:
            self.display.choice(side)
        reward_str = "REWARD" if rewarded else "NO REWARD"
        self._log(f"  CHOICE {side}  correct={correct}  -> {reward_str}")
        self._write_row(side, correct, reward_str)
        self._end_trial()

    def _timeout(self):
        self._log(f"  TIMEOUT (vertical was {self.vertical_side})")
        self._write_row("TIMEOUT", False, "")
        self._end_trial()

    def _end_trial(self):
        self.completed_trials += 1
        if self.display is not None:
            self.display.black()
        self.state = STATE_ITI
        self.state_start = self.clock()
        self._log(f"  STATE = ITI ({self.ITI_MS} ms)")

    def _write_row(self, chosen_side, correct, reward_str):
        self._csv.writerow([
            self.trial_num, self.stim_onset_ms, self.vertical_side,
            chosen_side, int(correct), round(self.REWARD_PERCENT, 4), reward_str,
        ])
        self._csv_file.flush()

    # ---- io ----------------------------------------------------------------
    def close(self):
        try:
            self._csv_file.close()
        except Exception:
            pass

    def _intro(self):
        print()
        print("#" * 64)
        print("  VERTICAL ON RANDOM SIDE")
        print("#" * 64)
        print(f"  Vertical-side reward chance: {self.REWARD_PERCENT * 100:.1f}%  "
              f"(other side 0%)")
        print(f"  Show other orientation: {self.SHOW_OTHER_ORIENTATION}")
        print(f"  Logging to: {self.csv_path}")
        print("  Controls: c = start trial (CENTER)   l = choose LEFT   "
              "r = choose RIGHT   t = timeout   q = quit")
        print()
        self._log("STATE = WAIT_CENTER_HOLD (hold CENTER, or press c)")

    def _log(self, msg):
        if self.verbose:
            print(f"{self.clock():>8}  {msg}", flush=True)


SPEC = {
    "name": "vertical_random_side",
    "title": "Vertical on Random Side",
    "variables": [
        {"key": "REWARD_PERCENT", "label": "Vertical-side reward chance", "type": "float",
         "default": DEFAULT_REWARD_PERCENT, "min": 0.0, "max": 1.0, "step": 0.05},
        {"key": "SHOW_OTHER_ORIENTATION", "label": "Show other orientation", "type": "bool",
         "default": True},
        {"key": "HOLD_MS", "label": "Hold time (ms)", "type": "int",
         "default": DEFAULT_HOLD_MS, "min": 0, "max": 10000, "step": 100},
        {"key": "CHOICE_TIMEOUT_MS", "label": "Choice timeout (ms)", "type": "int",
         "default": DEFAULT_CHOICE_TIMEOUT_MS, "min": 1000, "max": 120000, "step": 1000},
        {"key": "ITI_MS", "label": "Inter-trial interval (ms)", "type": "int",
         "default": DEFAULT_ITI_MS, "min": 0, "max": 60000, "step": 500},
    ],
    "states": [
        {"id": STATE_WAIT_CENTER, "label": "Wait Center Hold", "x": 60,  "y": 60},
        {"id": STATE_WAIT_CHOICE, "label": "Wait Choice", "x": 340, "y": 60},
        {"id": STATE_ITI,         "label": "Inter-Trial Interval", "x": 340, "y": 240},
    ],
    "transitions": [
        {"from": STATE_WAIT_CENTER, "to": STATE_WAIT_CHOICE, "label": "center held / 'c'"},
        {"from": STATE_WAIT_CHOICE, "to": STATE_ITI,         "label": "choice or timeout"},
        {"from": STATE_ITI,         "to": STATE_WAIT_CENTER, "label": "ITI elapsed"},
    ],
}

EXPERIMENT = VerticalRandomSide
