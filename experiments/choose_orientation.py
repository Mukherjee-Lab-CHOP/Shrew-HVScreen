"""CueExperiment — the full cue task, ported from cue.ino into Python.

The Arduino no longer runs the trial logic; this class does. It is a
non-blocking state machine driven by ``step(keys)``. A CENTER hold initiates a
trial; the horizontal and vertical figures appear on random sides; holding LEFT
or RIGHT registers a choice, which is rewarded if that orientation was armed.

States mirror cue.ino: WAIT_CENTER_HOLD -> WAIT_CHOICE_HOLD -> ITI.

Shared machinery (timing, IR hold detection, display, CSV, intro) lives in the
Experiment base class; this module holds only the cue-task logic.
"""

import random

from config import (
    ORIENT_NONE, ORIENT_HORIZONTAL, ORIENT_VERTICAL, ORIENT_NAME,
    HOLD_MS, CHOICE_TIMEOUT_MS, ITI_MS,
    P_STIM_HORIZONTAL, P_STIM_VERTICAL,
)
from experiments._base import Experiment, WAIT_CENTER_MSG

STATE_WAIT_CENTER = "WAIT_CENTER_HOLD"
STATE_WAIT_CHOICE = "WAIT_CHOICE_HOLD"
STATE_ITI         = "ITI"


class CueExperiment(Experiment):
    TITLE = "CUE EXPERIMENT (Python controller)"
    INITIAL_STATE = STATE_WAIT_CENTER
    CONTROLS_HELP = ("c = initiate trial (CENTER)   l = choose LEFT   "
                     "r = choose RIGHT   t = force timeout   q = quit")
    CSV_HEADER = [
        "trial_number",
        "init_time_stamp",
        "horizontal_reward_probability",
        "vertical_reward_probability",
        "horizontal_side",
        "vertical_side",
        "left_orientation",
        "right_orientation",
        "target_onset_timestamp",
        "chosen_orientation",
        "chosen_side",
        "choice_timestamp",
        "reaction_time_ms",
        "reward",
    ]

    def setup(self):
        # ---- tunable parameters (GUI-editable; fall back to config defaults) -
        self.P_STIM_HORIZONTAL = self.param("P_STIM_HORIZONTAL", P_STIM_HORIZONTAL, float)
        self.P_STIM_VERTICAL   = self.param("P_STIM_VERTICAL", P_STIM_VERTICAL, float)
        self.HOLD_MS           = self.param("HOLD_MS", HOLD_MS, int)
        self.CHOICE_TIMEOUT_MS = self.param("CHOICE_TIMEOUT_MS", CHOICE_TIMEOUT_MS, int)
        self.ITI_MS            = self.param("ITI_MS", ITI_MS, int)

        # ---- reward / stimulus state (mirrors cue.ino globals) -------------
        self.horizontal_rewarded = False
        self.vertical_rewarded = False
        self.left_fig = ORIENT_NONE
        self.right_fig = ORIENT_NONE
        self.horizontal_unchosen = 0
        self.vertical_unchosen = 0
        self.last_h_chance = 0.0
        self.last_v_chance = 0.0
        self.stim_onset_ms = 0
        self.trial_start_ms = 0

    def intro_lines(self):
        return [
            f"  P_STIM_HORIZONTAL base = {self.P_STIM_HORIZONTAL * 100:.1f}%",
            f"  P_STIM_VERTICAL   base = {self.P_STIM_VERTICAL * 100:.1f}%",
            "  (effective chance = 1 - (1 - base)^(n+1) where n = unchosen trials)",
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
                self._handle_timeout()
            elif inp["left"]:
                self._handle_choice("LEFT", self.left_fig)
            elif inp["right"]:
                self._handle_choice("RIGHT", self.right_fig)
        elif self.state == STATE_ITI:
            if now - self.state_start >= self.ITI_MS:
                self._end_iti()
        return None

    # ---- trial logic (ported from cue.ino) ---------------------------------
    def _randomize_rewards(self):
        # Effective chance = 1 - (1 - base)^(n+1) where n = unchosen trials.
        if not self.horizontal_rewarded:
            self.last_h_chance = 1.0 - ((1.0 - self.P_STIM_HORIZONTAL) ** (self.horizontal_unchosen + 1))
            self.horizontal_rewarded = random.random() < self.last_h_chance
        else:
            self.last_h_chance = 1.0
        if not self.vertical_rewarded:
            self.last_v_chance = 1.0 - ((1.0 - self.P_STIM_VERTICAL) ** (self.vertical_unchosen + 1))
            self.vertical_rewarded = random.random() < self.last_v_chance
        else:
            self.last_v_chance = 1.0

    def _randomize_sides(self):
        if random.randint(0, 1) == 0:
            self.left_fig, self.right_fig = ORIENT_HORIZONTAL, ORIENT_VERTICAL
        else:
            self.left_fig, self.right_fig = ORIENT_VERTICAL, ORIENT_HORIZONTAL

    def _is_fig_rewarded(self, fig):
        if fig == ORIENT_HORIZONTAL:
            return self.horizontal_rewarded
        if fig == ORIENT_VERTICAL:
            return self.vertical_rewarded
        return False

    def _correct_side(self):
        left_r = self._is_fig_rewarded(self.left_fig)
        right_r = self._is_fig_rewarded(self.right_fig)
        if left_r and right_r:
            return "BOTH"
        if left_r:
            return "LEFT"
        if right_r:
            return "RIGHT"
        return "NEITHER"

    def _start_trial(self):
        self.trial_num += 1
        self.trial_start_ms = self.clock()
        self._randomize_rewards()
        self._randomize_sides()

        self._print_banner()

        # Gate opens at stimulus onset and stays open through the ITI.
        self.hw.motor.open()
        self.display_show(self.left_fig, self.right_fig)
        self.stim_onset_ms = self.clock()
        self.goto(STATE_WAIT_CHOICE,
                  "STATE = WAIT_CHOICE_HOLD (hold LEFT or RIGHT, or press l/r/t)")

    def _handle_choice(self, side, chosen_fig):
        choice_timestamp = self.clock()
        reaction_time_ms = choice_timestamp - self.stim_onset_ms
        rewarded = self._is_fig_rewarded(chosen_fig)

        suffix = f" ({ORIENT_NAME[chosen_fig]})" if chosen_fig != ORIENT_NONE else ""
        self.log(f"CHOICE {side}{suffix}  reaction_time={reaction_time_ms} ms")

        if rewarded:
            self.hw.reward.deliver(side)
            # Consume the armed reward for the chosen orientation.
            if chosen_fig == ORIENT_HORIZONTAL:
                self.horizontal_rewarded = False
            elif chosen_fig == ORIENT_VERTICAL:
                self.vertical_rewarded = False
            self.log("RESULT: *** REWARD ***")
        else:
            self.log("RESULT: no reward.")

        self.display_choice(side)
        self._write_trial_row(side, chosen_fig, choice_timestamp, reaction_time_ms,
                              "REWARD" if rewarded else "NO REWARD")
        self._end_trial(chosen_fig)

    def _handle_timeout(self):
        self.log(f"TRIAL {self.trial_num} TIMEOUT — no choice made.")
        # Probabilities/sides/onset are still known for a timed-out trial; only
        # the choice-specific fields are blank.
        self._write_trial_row("TIMEOUT", ORIENT_NONE, "", "", "")
        self._end_trial(ORIENT_NONE)

    def _end_trial(self, choice):
        # Clear the screen (deferred behind any active choice overlay) and
        # enter the ITI. Gate stays open until the ITI ends.
        self.completed_trials += 1
        self.display_black()
        self.goto(STATE_ITI, f"STATE = ITI ({self.ITI_MS} ms)")

        if choice == ORIENT_HORIZONTAL:
            self.horizontal_unchosen = 0
            self.vertical_unchosen += 1
        elif choice == ORIENT_VERTICAL:
            self.vertical_unchosen = 0
            self.horizontal_unchosen += 1
        # timeout: counters unchanged (matches endTrial(ORIENT_NONE))

    def _end_iti(self):
        self.hw.motor.close()
        self.goto(STATE_WAIT_CENTER, WAIT_CENTER_MSG)

    # ---- run control -------------------------------------------------------
    def skip_trial(self):
        """Abort the current trial and move on. From WAIT_CHOICE it records a
        SKIP row and enters the ITI; from the ITI it cuts the ITI short and
        returns to WAIT_CENTER; from WAIT_CENTER there's nothing to skip."""
        if self.state == STATE_WAIT_CHOICE:
            self.log(f"TRIAL {self.trial_num} SKIPPED — moving to next trial.")
            self._write_trial_row("SKIP", ORIENT_NONE, "", "", "")
            self._end_trial(ORIENT_NONE)
        elif self.state == STATE_ITI:
            self.log("ITI skipped — ready for next trial.")
            self._end_iti()
        else:
            self.log("Already waiting to start the next trial (nothing to skip).")

    # ---- CSV ---------------------------------------------------------------
    def _write_trial_row(self, chosen_side, chosen_fig, choice_timestamp,
                         reaction_time_ms, reward_str):
        # Which physical side each orientation occupies this trial. Exactly one
        # side is horizontal and the other vertical (see _randomize_sides).
        horizontal_side = "LEFT" if self.left_fig == ORIENT_HORIZONTAL else "RIGHT"
        vertical_side   = "LEFT" if self.left_fig == ORIENT_VERTICAL else "RIGHT"

        self.write_row([
            self.trial_num,                       # trial_number
            self.trial_start_ms,                  # init_time_stamp
            round(self.last_h_chance, 4),         # horizontal_reward_probability
            round(self.last_v_chance, 4),         # vertical_reward_probability
            horizontal_side,                      # horizontal_side
            vertical_side,                        # vertical_side
            ORIENT_NAME[self.left_fig],           # left_orientation
            ORIENT_NAME[self.right_fig],          # right_orientation
            self.stim_onset_ms,                   # target_onset_timestamp
            ORIENT_NAME[chosen_fig],              # chosen_orientation (NONE on timeout)
            chosen_side,                          # chosen_side (TIMEOUT on timeout)
            choice_timestamp,                     # choice_timestamp ("" on timeout)
            reaction_time_ms,                     # reaction_time_ms ("" on timeout)
            reward_str,                           # reward ("" on timeout)
        ])

    # ---- console -----------------------------------------------------------
    def _print_banner(self):
        print()
        print("=" * 64)
        print(f"  TRIAL {self.trial_num}")
        print("=" * 64)
        print(f"  LEFT  SCREEN: {ORIENT_NAME[self.left_fig]}")
        print(f"  RIGHT SCREEN: {ORIENT_NAME[self.right_fig]}")
        print()
        print("  --- DEBUG (the rat wouldn't know this) ---")
        print(f"  HORIZONTAL armed? {'YES' if self.horizontal_rewarded else 'no '}"
              f"   chance: {self.last_h_chance * 100:5.1f}%"
              f"   (unchosen streak: {self.horizontal_unchosen})")
        print(f"  VERTICAL   armed? {'YES' if self.vertical_rewarded else 'no '}"
              f"   chance: {self.last_v_chance * 100:5.1f}%"
              f"   (unchosen streak: {self.vertical_unchosen})")
        print(f"  >> Reward on: {self._correct_side()}")
        print()


# SPEC — machine-readable description of this experiment for the GUI:
#   * variables: GUI-editable knobs (passed to CueExperiment(params=...))
#   * states / transitions: the state machine, for the node-graph view.
# self.state matches a state id, so the GUI can highlight the current node.
SPEC = {
    "name": "choose_orientation",
    "title": "Choose Orientation (H/V cue task)",
    "variables": [
        {"key": "P_STIM_HORIZONTAL", "label": "P(horizontal reward)", "type": "float",
         "default": P_STIM_HORIZONTAL, "min": 0.0, "max": 1.0, "step": 0.05},
        {"key": "P_STIM_VERTICAL", "label": "P(vertical reward)", "type": "float",
         "default": P_STIM_VERTICAL, "min": 0.0, "max": 1.0, "step": 0.05},
        {"key": "HOLD_MS", "label": "Hold time (ms)", "type": "int",
         "default": HOLD_MS, "min": 0, "max": 10000, "step": 100},
        {"key": "CHOICE_TIMEOUT_MS", "label": "Choice timeout (ms)", "type": "int",
         "default": CHOICE_TIMEOUT_MS, "min": 1000, "max": 120000, "step": 1000},
        {"key": "ITI_MS", "label": "Inter-trial interval (ms)", "type": "int",
         "default": ITI_MS, "min": 0, "max": 60000, "step": 500},
    ],
    "states": [
        {"id": STATE_WAIT_CENTER, "label": "Wait Center Hold", "x": 60,  "y": 60},
        {"id": STATE_WAIT_CHOICE, "label": "Wait Choice Hold", "x": 340, "y": 60},
        {"id": STATE_ITI,         "label": "Inter-Trial Interval", "x": 340, "y": 260},
    ],
    "transitions": [
        {"from": STATE_WAIT_CENTER, "to": STATE_WAIT_CHOICE, "label": "center held / 'c'"},
        {"from": STATE_WAIT_CHOICE, "to": STATE_ITI,         "label": "choice or timeout"},
        {"from": STATE_ITI,         "to": STATE_WAIT_CENTER, "label": "ITI elapsed"},
    ],
}


# Exposed to run.py's experiment registry. To add a selectable experiment, drop
# a new module in experiments/ that likewise defines EXPERIMENT = <YourClass>.
EXPERIMENT = CueExperiment
