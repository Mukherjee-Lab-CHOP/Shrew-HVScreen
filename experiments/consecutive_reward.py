"""consecutive_reward — nose-poke for reward, with a same-side streak limit.

The shrew pokes LEFT or RIGHT and gets a reward on each poke, EXCEPT it may not
go to the same side more than MAX_CONSECUTIVE times in a row: once it exceeds the
limit on a side, that side stops paying out until it switches to the other side
(which resets the streak).

No center initiation and no stimulus — it just waits for a poke, delivers (or
withholds) reward, runs a short ITI, and repeats.

State machine:  WAIT_POKE --poke L/R--> ITI --elapsed--> WAIT_POKE
"""

import csv
import os
import time
from datetime import datetime

from config import CH_LEFT, CH_RIGHT

STATE_WAIT_POKE = "WAIT_POKE"
STATE_ITI       = "ITI"

DEFAULT_MAX_CONSECUTIVE = 3
DEFAULT_HOLD_MS = 2000
DEFAULT_ITI_MS  = 3000


def _now_ms():
    return int(time.monotonic() * 1000)


class ConsecutiveReward:
    def __init__(self, hardware, display, csv_path=None, params=None, verbose=True):
        self.hw = hardware
        self.display = display
        self.verbose = verbose

        params = params or {}
        self.MAX_CONSECUTIVE = int(params.get("MAX_CONSECUTIVE", DEFAULT_MAX_CONSECUTIVE))
        self.HOLD_MS = int(params.get("HOLD_MS", DEFAULT_HOLD_MS))
        self.ITI_MS = int(params.get("ITI_MS", DEFAULT_ITI_MS))

        self.trial_num = 0
        self.completed_trials = 0   # trials finished (what the pipeline counts)
        self.last_side = None
        self.consecutive = 0

        self._t0 = _now_ms()
        self.state = STATE_WAIT_POKE
        self.state_start = self.clock()

        self._broken = {CH_LEFT: False, CH_RIGHT: False}
        self._broken_since = {CH_LEFT: 0, CH_RIGHT: 0}
        self._armed = {CH_LEFT: True, CH_RIGHT: True}

        self.csv_path = csv_path or datetime.now().strftime("session_%Y%m%d_%H%M%S.csv")
        parent = os.path.dirname(self.csv_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._csv_file = open(self.csv_path, "w", newline="")
        self._csv = csv.writer(self._csv_file)
        self._csv.writerow([
            "trial_number", "timestamp_ms", "chosen_side",
            "consecutive_count", "max_consecutive", "reward",
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
        left = self._ir_hold(CH_LEFT) or ("l" in keys)
        right = self._ir_hold(CH_RIGHT) or ("r" in keys)
        now = self.clock()

        if self.state == STATE_WAIT_POKE:
            if left:
                self._poke("LEFT")
            elif right:
                self._poke("RIGHT")
        elif self.state == STATE_ITI:
            if now - self.state_start >= self.ITI_MS:
                self.state = STATE_WAIT_POKE
                self.state_start = now
                self._log("STATE = WAIT_POKE")
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

    # ---- poke handling -----------------------------------------------------
    def _poke(self, side):
        self.trial_num += 1
        if side == self.last_side:
            self.consecutive += 1
        else:
            self.consecutive = 1
            self.last_side = side

        allowed = self.consecutive <= self.MAX_CONSECUTIVE
        if allowed:
            self.hw.reward.deliver(side)
            reward_str = "REWARD"
            self._log(f"POKE {side}  streak={self.consecutive}  -> REWARD")
        else:
            reward_str = "NO REWARD"
            self._log(f"POKE {side}  streak={self.consecutive} > "
                      f"{self.MAX_CONSECUTIVE}  -> NO REWARD (switch sides)")

        self._csv.writerow([self.trial_num, self.clock(), side,
                            self.consecutive, self.MAX_CONSECUTIVE, reward_str])
        self._csv_file.flush()

        self.completed_trials += 1
        self.state = STATE_ITI
        self.state_start = self.clock()
        self._log(f"STATE = ITI ({self.ITI_MS} ms)")

    # ---- io ----------------------------------------------------------------
    def close(self):
        try:
            self._csv_file.close()
        except Exception:
            pass

    def _intro(self):
        print()
        print("#" * 64)
        print("  CONSECUTIVE REWARD (nose-poke)")
        print("#" * 64)
        print(f"  Max same-side streak before reward stops: {self.MAX_CONSECUTIVE}")
        print(f"  Logging to: {self.csv_path}")
        print("  Controls: l = poke LEFT   r = poke RIGHT   q = quit")
        print()
        self._log("STATE = WAIT_POKE")

    def _log(self, msg):
        if self.verbose:
            print(f"{self.clock():>8}  {msg}", flush=True)


SPEC = {
    "name": "consecutive_reward",
    "title": "Consecutive Reward (nose-poke, same-side streak limit)",
    "variables": [
        {"key": "MAX_CONSECUTIVE", "label": "Max same-side in a row", "type": "int",
         "default": DEFAULT_MAX_CONSECUTIVE, "min": 1, "max": 100, "step": 1},
        {"key": "HOLD_MS", "label": "Hold time (ms)", "type": "int",
         "default": DEFAULT_HOLD_MS, "min": 0, "max": 10000, "step": 100},
        {"key": "ITI_MS", "label": "Inter-trial interval (ms)", "type": "int",
         "default": DEFAULT_ITI_MS, "min": 0, "max": 60000, "step": 500},
    ],
    "states": [
        {"id": STATE_WAIT_POKE, "label": "Wait Poke", "x": 80, "y": 80},
        {"id": STATE_ITI,       "label": "Inter-Trial Interval", "x": 360, "y": 80},
    ],
    "transitions": [
        {"from": STATE_WAIT_POKE, "to": STATE_ITI,       "label": "poke L/R"},
        {"from": STATE_ITI,       "to": STATE_WAIT_POKE, "label": "ITI elapsed"},
    ],
}

EXPERIMENT = ConsecutiveReward
