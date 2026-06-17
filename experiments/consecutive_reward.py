"""consecutive_reward — nose-poke for reward, with a same-side streak limit.

Each trial is initiated by a CENTER hold; the shrew then pokes LEFT or RIGHT and
gets a reward, EXCEPT it may not go to the same side more than MAX_CONSECUTIVE
times in a row: once it exceeds the limit on a side, that side stops paying out
until it switches to the other side (which resets the streak).

State machine:  WAIT_CENTER_HOLD --center--> WAIT_POKE --poke L/R--> ITI
                --elapsed--> WAIT_CENTER_HOLD
"""

from experiments._base import Experiment, WAIT_CENTER_MSG

STATE_WAIT_CENTER = "WAIT_CENTER_HOLD"
STATE_WAIT_POKE   = "WAIT_POKE"
STATE_ITI         = "ITI"

DEFAULT_MAX_CONSECUTIVE = 3
DEFAULT_HOLD_MS = 2000
DEFAULT_ITI_MS  = 3000


class ConsecutiveReward(Experiment):
    TITLE = "CONSECUTIVE REWARD (nose-poke)"
    INITIAL_STATE = STATE_WAIT_CENTER
    BLANK_ON_START = True
    CONTROLS_HELP = ("c = start trial (CENTER)   l = poke LEFT   "
                     "r = poke RIGHT   q = quit")
    CSV_HEADER = [
        "trial_number", "timestamp_ms", "chosen_side",
        "consecutive_count", "max_consecutive", "reward",
    ]

    def setup(self):
        self.MAX_CONSECUTIVE = self.param("MAX_CONSECUTIVE", DEFAULT_MAX_CONSECUTIVE, int)
        self.HOLD_MS = self.param("HOLD_MS", DEFAULT_HOLD_MS, int)
        self.ITI_MS = self.param("ITI_MS", DEFAULT_ITI_MS, int)
        self.last_side = None
        self.consecutive = 0

    def intro_lines(self):
        return [f"  Max same-side streak before reward stops: {self.MAX_CONSECUTIVE}"]

    # ---- main loop ---------------------------------------------------------
    def run_step(self, keys):
        inp = self.inputs(keys)
        now = self.clock()

        if self.state == STATE_WAIT_CENTER:
            if inp["center"]:
                self.goto(STATE_WAIT_POKE, "STATE = WAIT_POKE (poke LEFT or RIGHT)")
        elif self.state == STATE_WAIT_POKE:
            if inp["left"]:
                self._poke("LEFT")
            elif inp["right"]:
                self._poke("RIGHT")
        elif self.state == STATE_ITI:
            if now - self.state_start >= self.ITI_MS:
                self.goto(STATE_WAIT_CENTER, WAIT_CENTER_MSG)
        return None

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
            self.log(f"POKE {side}  streak={self.consecutive}  -> REWARD")
        else:
            reward_str = "NO REWARD"
            self.log(f"POKE {side}  streak={self.consecutive} > "
                     f"{self.MAX_CONSECUTIVE}  -> NO REWARD (switch sides)")

        self.write_row([self.trial_num, self.clock(), side,
                        self.consecutive, self.MAX_CONSECUTIVE, reward_str])
        self.completed_trials += 1
        self.goto(STATE_ITI, f"STATE = ITI ({self.ITI_MS} ms)")

    # ---- run control -------------------------------------------------------
    def skip_trial(self):
        """Count a skipped trial and begin anew, from ANY state (no reward, streak
        untouched). Returns to WAIT_CENTER ready for the next poke."""
        self.trial_num += 1
        self.log(f"TRIAL {self.trial_num} SKIPPED — beginning anew.")
        self.write_row([self.trial_num, self.clock(), "SKIP",
                        self.consecutive, self.MAX_CONSECUTIVE, ""])
        self.completed_trials += 1
        self.goto(STATE_WAIT_CENTER, WAIT_CENTER_MSG)


SPEC = {
    "name": "consecutive_reward",
    "title": "Consecutive Reward (nose-poke, same-side streak limit)",
    "variables": [
        {"key": "MAX_CONSECUTIVE", "label": "Max same-side in a row", "type": "int",
         "default": DEFAULT_MAX_CONSECUTIVE, "min": 1, "max": 100, "step": 1},
        {"key": "HOLD_MS", "label": "Initiation Hold time (ms)", "type": "int",
         "default": DEFAULT_HOLD_MS, "min": 0, "max": 10000, "step": 100},
        {"key": "ITI_MS", "label": "Inter-trial interval (ms)", "type": "int",
         "default": DEFAULT_ITI_MS, "min": 0, "max": 60000, "step": 500},
    ],
    "states": [
        {"id": STATE_WAIT_CENTER, "label": "Wait Center Hold", "x": 60,  "y": 60},
        {"id": STATE_WAIT_POKE,   "label": "Wait Poke", "x": 340, "y": 60},
        {"id": STATE_ITI,         "label": "Inter-Trial Interval", "x": 340, "y": 240},
    ],
    "transitions": [
        {"from": STATE_WAIT_CENTER, "to": STATE_WAIT_POKE,   "label": "center held / 'c'"},
        {"from": STATE_WAIT_POKE,   "to": STATE_ITI,         "label": "poke L/R"},
        {"from": STATE_ITI,         "to": STATE_WAIT_CENTER, "label": "ITI elapsed"},
    ],
}

EXPERIMENT = ConsecutiveReward
