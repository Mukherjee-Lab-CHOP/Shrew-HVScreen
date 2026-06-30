"""consecutive_reward — nose-poke for reward, with a same-side streak limit.

Each trial is initiated by a CENTER hold; the shrew then pokes LEFT or RIGHT and
gets a reward, EXCEPT it may not go to the same side more than MAX_CONSECUTIVE
times in a row: once it exceeds the limit on a side, that side stops paying out
until it switches to the other side (which resets the streak).

State machine:  WAIT_CENTER_HOLD --center--> WAIT_POKE --poke L/R--> ITI
                --elapsed--> WAIT_CENTER_HOLD
"""

from config import AMBIENT_VARS
from experiments._base import Experiment, WAIT_CENTER_MSG

STATE_WAIT_CENTER = "WAIT_CENTER_HOLD"
STATE_WAIT_POKE   = "WAIT_POKE"
STATE_REWARD      = "REWARD"
STATE_ITI         = "ITI"

DEFAULT_MAX_CONSECUTIVE = 3
DEFAULT_INIT_POKE_MS = 100
DEFAULT_REWARD_POKE_MS = 100
DEFAULT_REWARD_MS = 3000
DEFAULT_CORRECT_ITI_WAIT = 2000
DEFAULT_INCORRECT_ITI_WAIT = 10000


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
        self.INIT_POKE_MS = self.param("INIT_POKE_MS", DEFAULT_INIT_POKE_MS, int)
        self.REWARD_POKE_MS = self.param("REWARD_POKE_MS", DEFAULT_REWARD_POKE_MS, int)
        self.REWARD_MS = self.param("REWARD_MS", DEFAULT_REWARD_MS, int)
        self.CORRECT_ITI_WAIT = self.param("CORRECT_ITI_WAIT", DEFAULT_CORRECT_ITI_WAIT, int)
        self.INCORRECT_ITI_WAIT = self.param("INCORRECT_ITI_WAIT", DEFAULT_INCORRECT_ITI_WAIT, int)
        self.last_side = None
        self.consecutive = 0

    def intro_lines(self):
        return [f"  Max same-side streak before reward stops: {self.MAX_CONSECUTIVE}"]

    # ---- main loop ---------------------------------------------------------
    def run_step(self, keys):
        inp = self.inputs(keys)

        if self.state == STATE_WAIT_CENTER:
            if inp["center"]:
                self.open_gate()        # centre initiation -> open gate (SERVO 60)
                self.goto(STATE_WAIT_POKE, "STATE = WAIT_POKE (poke LEFT or RIGHT)")
        elif self.state == STATE_WAIT_POKE:
            if inp["left"]:
                self._poke("LEFT")
            elif inp["right"]:
                self._poke("RIGHT")
        # REWARD and ITI states are handled centrally by the base step.
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
        # green correct-square when rewarded, blue otherwise, on the poked side
        self.display_choice(side, correct=allowed)
        self.end_trial(correct=allowed, rewarded=allowed)

    # ---- run control -------------------------------------------------------
    def skip_trial(self):
        """Count a skipped trial and begin anew, from ANY state (no reward, streak
        untouched). Returns to WAIT_CENTER ready for the next poke."""
        self.trial_num += 1
        self.log(f"TRIAL {self.trial_num} SKIPPED — beginning anew.")
        self.write_row([self.trial_num, self.clock(), "SKIP",
                        self.consecutive, self.MAX_CONSECUTIVE, ""])
        self.completed_trials += 1
        self.close_gate()
        self.goto(STATE_WAIT_CENTER, WAIT_CENTER_MSG)


SPEC = {
    "name": "consecutive_reward",
    "title": "Consecutive Reward (nose-poke, same-side streak limit)",
    "variables": [
        {"key": "MAX_CONSECUTIVE", "label": "Max same-side in a row", "type": "int",
         "default": DEFAULT_MAX_CONSECUTIVE, "min": 1, "max": 100, "step": 1},
        {"key": "INIT_POKE_MS", "label": "Init poke time (ms)", "type": "int",
         "default": DEFAULT_INIT_POKE_MS, "min": 0, "max": 10000, "step": 50},
        {"key": "REWARD_POKE_MS", "label": "Reward poke time (ms)", "type": "int",
         "default": DEFAULT_REWARD_POKE_MS, "min": 0, "max": 10000, "step": 50},
        {"key": "REWARD_MS", "label": "Reward phase (ms, gate open)", "type": "int",
         "default": DEFAULT_REWARD_MS, "min": 0, "max": 60000, "step": 250},
        {"key": "CORRECT_ITI_WAIT", "label": "ITI after correct (ms)", "type": "int",
         "default": DEFAULT_CORRECT_ITI_WAIT, "min": 0, "max": 120000, "step": 500},
        {"key": "INCORRECT_ITI_WAIT", "label": "ITI after incorrect (ms)", "type": "int",
         "default": DEFAULT_INCORRECT_ITI_WAIT, "min": 0, "max": 120000, "step": 500},
        *AMBIENT_VARS,
    ],
    "states": [
        {"id": STATE_WAIT_CENTER, "label": "Wait Center Hold", "x": 60,  "y": 60},
        {"id": STATE_WAIT_POKE,   "label": "Wait Poke", "x": 340, "y": 60},
        {"id": STATE_REWARD,      "label": "Reward (gate open)", "x": 600, "y": 60},
        {"id": STATE_ITI,         "label": "Inter-Trial Interval", "x": 340, "y": 240},
    ],
    "transitions": [
        {"from": STATE_WAIT_CENTER, "to": STATE_WAIT_POKE,   "label": "center held / 'c'"},
        {"from": STATE_WAIT_POKE,   "to": STATE_REWARD,      "label": "rewarded poke"},
        {"from": STATE_WAIT_POKE,   "to": STATE_ITI,         "label": "no-reward poke"},
        {"from": STATE_REWARD,      "to": STATE_ITI,         "label": "reward phase done"},
        {"from": STATE_ITI,         "to": STATE_WAIT_CENTER, "label": "ITI elapsed"},
    ],
}

EXPERIMENT = ConsecutiveReward
