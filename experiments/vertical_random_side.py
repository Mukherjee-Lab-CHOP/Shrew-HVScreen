"""vertical_random_side — present the VERTICAL target on a random side; the
shrew should choose that side.

Each trial is initiated by a CENTER hold, then the vertical figure appears on a
random side (left or right). The other side shows the horizontal figure if
SHOW_OTHER_ORIENTATION is on, otherwise it stays blank. Choosing the vertical
side pays out with REWARD_PERCENT probability; the other side never pays (0%).

State machine:  WAIT_CENTER_HOLD --center--> WAIT_CHOICE --choice/timeout--> ITI
                --elapsed--> WAIT_CENTER_HOLD
"""

import random

from config import ORIENT_HORIZONTAL, ORIENT_VERTICAL
from experiments._base import Experiment, WAIT_CENTER_MSG

STATE_WAIT_CENTER = "WAIT_CENTER_HOLD"
STATE_WAIT_CHOICE = "WAIT_CHOICE"
STATE_REWARD      = "REWARD"
STATE_ITI         = "ITI"

DEFAULT_REWARD_PERCENT = 1.0
DEFAULT_INIT_HOLD_MS = 2000
DEFAULT_CHOICE_TIMEOUT_MS = 20000
DEFAULT_REWARD_MS = 3000
DEFAULT_ITI_MS = 6000

BLANK = 0   # display code for "nothing on this side"


class VerticalRandomSide(Experiment):
    TITLE = "VERTICAL ON RANDOM SIDE"
    INITIAL_STATE = STATE_WAIT_CENTER
    BLANK_ON_START = True
    CONTROLS_HELP = ("c = start trial (CENTER)   l = choose LEFT   "
                     "r = choose RIGHT   t = timeout   q = quit")
    CSV_HEADER = [
        "trial_number", "target_onset_timestamp", "vertical_side",
        "chosen_side", "correct", "reward_percent", "reward",
    ]

    def setup(self):
        self.REWARD_PERCENT = self.param("REWARD_PERCENT", DEFAULT_REWARD_PERCENT, float)
        self.SHOW_OTHER_ORIENTATION = self.param("SHOW_OTHER_ORIENTATION", True, bool)
        self.INIT_HOLD_MS = self.param("INIT_HOLD_MS", DEFAULT_INIT_HOLD_MS, int)
        self.CHOICE_TIMEOUT_MS = self.param("CHOICE_TIMEOUT_MS", DEFAULT_CHOICE_TIMEOUT_MS, int)
        self.REWARD_MS = self.param("REWARD_MS", DEFAULT_REWARD_MS, int)
        self.ITI_MS = self.param("ITI_MS", DEFAULT_ITI_MS, int)

        self.vertical_side = None   # "LEFT" / "RIGHT"
        self.stim_onset_ms = 0

    def intro_lines(self):
        return [
            f"  Vertical-side reward chance: {self.REWARD_PERCENT * 100:.1f}%  (other side 0%)",
            f"  Show other orientation: {self.SHOW_OTHER_ORIENTATION}",
        ]

    # ---- main loop ---------------------------------------------------------
    def run_step(self, keys):
        inp = self.inputs(keys)
        now = self.clock()

        if self.state == STATE_WAIT_CENTER:
            if inp["center"]:
                self._start_trial()
        elif self.state == STATE_WAIT_CHOICE:
            if inp["timeout"] or (now - self.state_start > self.CHOICE_TIMEOUT_MS):
                self._timeout()
            elif inp["left"]:
                self._choice("LEFT")
            elif inp["right"]:
                self._choice("RIGHT")
        elif self.state == STATE_ITI:
            if now - self.state_start >= self.ITI_MS:
                self.goto(STATE_WAIT_CENTER, WAIT_CENTER_MSG)
        return None

    # ---- trial logic -------------------------------------------------------
    def _start_trial(self):
        self.trial_num += 1
        self.vertical_side = random.choice(["LEFT", "RIGHT"])
        other = ORIENT_HORIZONTAL if self.SHOW_OTHER_ORIENTATION else BLANK
        if self.vertical_side == "LEFT":
            left_code, right_code = ORIENT_VERTICAL, other
        else:
            left_code, right_code = other, ORIENT_VERTICAL
        self.open_gate()                # centre initiation -> open gate (SERVO 60)
        self.display_show(left_code, right_code)
        self.stim_onset_ms = self.clock()
        self.goto(STATE_WAIT_CHOICE,
                  f"TRIAL {self.trial_num}: vertical on {self.vertical_side}"
                  f"  (show_other={self.SHOW_OTHER_ORIENTATION})")

    def _choice(self, side):
        correct = (side == self.vertical_side)
        rewarded = correct and (random.random() < self.REWARD_PERCENT)
        if rewarded:
            self.hw.reward.deliver(side)
        self.display_choice(side)
        reward_str = "REWARD" if rewarded else "NO REWARD"
        self.log(f"  CHOICE {side}  correct={correct}  -> {reward_str}")
        self._write_row(side, correct, reward_str)
        self._end_trial(rewarded)

    def _timeout(self):
        self.log(f"  TIMEOUT (vertical was {self.vertical_side})")
        self._write_row("TIMEOUT", False, "")
        self._end_trial(rewarded=False)

    def _end_trial(self, rewarded=False):
        self.completed_trials += 1
        if rewarded:
            # keep the gate open + stimulus up for the reward phase, then ITI
            self.enter_reward_phase()
        else:
            self.display_black()
            self.close_gate()           # ITI -> close gate (SERVO 180)
            self.goto(STATE_ITI, f"  STATE = ITI ({self.ITI_MS} ms)")

    def _write_row(self, chosen_side, correct, reward_str):
        self.write_row([
            self.trial_num, self.stim_onset_ms, self.vertical_side,
            chosen_side, int(correct), round(self.REWARD_PERCENT, 4), reward_str,
        ])

    # ---- run control -------------------------------------------------------
    def skip_trial(self):
        """Count a skipped trial and begin anew, from ANY state. Mid-trial it
        skips the in-progress trial; at the start (or in the ITI) it still records
        a fresh skipped trial. Either way it returns to WAIT_CENTER."""
        if self.state != STATE_WAIT_CHOICE:
            self.trial_num += 1     # no trial in progress -> count a fresh one
        self.log(f"  TRIAL {self.trial_num} SKIPPED — beginning anew.")
        self._write_row("SKIP", False, "")
        self.completed_trials += 1
        self.display_black()
        self.close_gate()
        self.goto(STATE_WAIT_CENTER, WAIT_CENTER_MSG)


SPEC = {
    "name": "vertical_random_side",
    "title": "Vertical on Random Side",
    "variables": [
        {"key": "REWARD_PERCENT", "label": "Vertical-side reward chance", "type": "float",
         "default": DEFAULT_REWARD_PERCENT, "min": 0.0, "max": 1.0, "step": 0.05},
        {"key": "SHOW_OTHER_ORIENTATION", "label": "Show other orientation", "type": "bool",
         "default": True},
        {"key": "INIT_HOLD_MS", "label": "Initation Hold time (ms)", "type": "int",
         "default": DEFAULT_INIT_HOLD_MS, "min": 0, "max": 10000, "step": 100},
        {"key": "CHOICE_TIMEOUT_MS", "label": "Choice timeout (ms)", "type": "int",
         "default": DEFAULT_CHOICE_TIMEOUT_MS, "min": 1000, "max": 120000, "step": 1000},
        {"key": "REWARD_MS", "label": "Reward phase (ms, gate open)", "type": "int",
         "default": DEFAULT_REWARD_MS, "min": 0, "max": 60000, "step": 250},
        {"key": "ITI_MS", "label": "Inter-trial interval (ms)", "type": "int",
         "default": DEFAULT_ITI_MS, "min": 0, "max": 60000, "step": 500},
    ],
    "states": [
        {"id": STATE_WAIT_CENTER, "label": "Wait Center Hold", "x": 60,  "y": 60},
        {"id": STATE_WAIT_CHOICE, "label": "Wait Choice", "x": 340, "y": 60},
        {"id": STATE_REWARD,      "label": "Reward (gate open)", "x": 600, "y": 60},
        {"id": STATE_ITI,         "label": "Inter-Trial Interval", "x": 340, "y": 240},
    ],
    "transitions": [
        {"from": STATE_WAIT_CENTER, "to": STATE_WAIT_CHOICE, "label": "center held / 'c'"},
        {"from": STATE_WAIT_CHOICE, "to": STATE_REWARD,      "label": "rewarded choice"},
        {"from": STATE_WAIT_CHOICE, "to": STATE_ITI,         "label": "no reward / timeout"},
        {"from": STATE_REWARD,      "to": STATE_ITI,         "label": "reward phase done"},
        {"from": STATE_ITI,         "to": STATE_WAIT_CENTER, "label": "ITI elapsed"},
    ],
}

EXPERIMENT = VerticalRandomSide
