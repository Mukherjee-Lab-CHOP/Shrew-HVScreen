"""CueExperiment — the full cue task, ported from cue.ino into Python.

The Arduino no longer runs the trial logic; this class does. It is a
non-blocking state machine driven by `step(keys)`, called repeatedly from the
main loop. Two input sources feed it in parallel:

  * Real IR beam breaks, delivered by hardware.ir_detector.poll_events(). Hold
    timing (a beam must stay broken for HOLD_MS) is done here, in Python.
  * Terminal keystrokes ('c', 'l', 'r', 't', 'q'), which act as instant holds
    so the task can be driven by hand with or without an Arduino attached.

States mirror cue.ino: WAIT_CENTER_HOLD -> WAIT_CHOICE_HOLD -> ITI.

Outputs:
  * Actuation via hardware (motor.open/close gate servo, reward pumps).
  * Stimulus via Display (show / choice overlay / black).
  * One CSV row per completed trial (same columns as the original screen.py).
"""

import csv
import os
import random
import time
from datetime import datetime

from config import (
    ORIENT_NONE, ORIENT_HORIZONTAL, ORIENT_VERTICAL, ORIENT_NAME,
    CH_LEFT, CH_CENTER, CH_RIGHT,
    HOLD_MS, CHOICE_TIMEOUT_MS, ITI_MS,
    P_STIM_HORIZONTAL, P_STIM_VERTICAL,
)

STATE_WAIT_CENTER = "WAIT_CENTER_HOLD"
STATE_WAIT_CHOICE = "WAIT_CHOICE_HOLD"
STATE_ITI         = "ITI"


def _now_ms():
    return int(time.monotonic() * 1000)


class CueExperiment:
    def __init__(self, hardware, display, csv_path=None, params=None, verbose=True):
        self.hw = hardware
        self.display = display
        self.verbose = verbose

        # ---- tunable parameters (GUI-editable; fall back to config defaults) -
        params = params or {}
        self.P_STIM_HORIZONTAL = float(params.get("P_STIM_HORIZONTAL", P_STIM_HORIZONTAL))
        self.P_STIM_VERTICAL   = float(params.get("P_STIM_VERTICAL", P_STIM_VERTICAL))
        self.HOLD_MS           = int(params.get("HOLD_MS", HOLD_MS))
        self.CHOICE_TIMEOUT_MS = int(params.get("CHOICE_TIMEOUT_MS", CHOICE_TIMEOUT_MS))
        self.ITI_MS            = int(params.get("ITI_MS", ITI_MS))

        # ---- reward / stimulus state (mirrors cue.ino globals) -------------
        self.trial_num = 0
        self.horizontal_rewarded = False
        self.vertical_rewarded = False
        self.left_fig = ORIENT_NONE
        self.right_fig = ORIENT_NONE
        self.horizontal_unchosen = 0
        self.vertical_unchosen = 0
        self.last_h_chance = 0.0
        self.last_v_chance = 0.0

        # ---- timing --------------------------------------------------------
        self._t0 = _now_ms()
        self.stim_onset_ms = 0
        self.trial_start_ms = 0
        self.state = STATE_WAIT_CENTER
        self.state_start = self.clock()

        # ---- IR beam tracking for hold timing ------------------------------
        self._broken = {CH_LEFT: False, CH_CENTER: False, CH_RIGHT: False}
        self._broken_since = {CH_LEFT: 0, CH_CENTER: 0, CH_RIGHT: 0}
        # A hold can only fire once per continuous break; re-arms on release.
        self._armed = {CH_LEFT: True, CH_CENTER: True, CH_RIGHT: True}

        # ---- CSV -----------------------------------------------------------
        self.csv_path = csv_path or datetime.now().strftime("session_%Y%m%d_%H%M%S.csv")
        parent = os.path.dirname(self.csv_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._csv_file = open(self.csv_path, "w", newline="")
        self._csv = csv.writer(self._csv_file)
        self._csv.writerow([
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
        ])
        self._csv_file.flush()

        self._print_intro()

    # ---- time helper -------------------------------------------------------
    def clock(self):
        """Milliseconds since the experiment started (analogous to millis())."""
        return _now_ms() - self._t0

    # ---- main entry point --------------------------------------------------
    def step(self, keys):
        """Advance the state machine one tick.

        `keys` is a list of single-char terminal inputs received since the last
        call. Returns the string "QUIT" if the user asked to stop, else None.
        """
        if "q" in keys:
            return "QUIT"

        self._ingest_ir_events()

        # Derive high-level triggers from EITHER input source.
        center_hold = self._ir_hold(CH_CENTER) or ("c" in keys)
        left_hold   = self._ir_hold(CH_LEFT)   or ("l" in keys)
        right_hold  = self._ir_hold(CH_RIGHT)  or ("r" in keys)
        force_to    = ("t" in keys)

        now = self.clock()

        if self.state == STATE_WAIT_CENTER:
            if center_hold:
                self._start_trial()

        elif self.state == STATE_WAIT_CHOICE:
            if force_to or (now - self.state_start > self.CHOICE_TIMEOUT_MS):
                self._handle_timeout()
            elif left_hold:
                self._handle_choice("LEFT", self.left_fig)
            elif right_hold:
                self._handle_choice("RIGHT", self.right_fig)

        elif self.state == STATE_ITI:
            if now - self.state_start >= self.ITI_MS:
                self._end_iti()

        return None

    # ---- IR event handling -------------------------------------------------
    def _ingest_ir_events(self):
        for channel, broken, _arduino_ms in self.hw.ir_detector.poll_events():
            if channel not in self._broken:
                continue
            if broken and not self._broken[channel]:
                self._broken[channel] = True
                self._broken_since[channel] = self.clock()
            elif not broken and self._broken[channel]:
                self._broken[channel] = False
                self._armed[channel] = True      # re-arm for the next break

    def _ir_hold(self, channel):
        """True once when a beam has been held broken continuously for HOLD_MS."""
        if (self._broken[channel] and self._armed[channel]
                and (self.clock() - self._broken_since[channel]) >= self.HOLD_MS):
            self._armed[channel] = False
            return True
        return False

    # ---- trial logic (ported from cue.ino) ---------------------------------
    def _randomize_rewards(self):
        if not self.horizontal_rewarded:
            self.last_h_chance = 1 - (1 - self.P_STIM_HORIZONTAL) ** (self.horizontal_unchosen + 1)
            self.horizontal_rewarded = random.random() < self.last_h_chance
        else:
            self.last_h_chance = 1.0
        if not self.vertical_rewarded:
            self.last_v_chance = 1 - (1 - self.P_STIM_VERTICAL) ** (self.vertical_unchosen + 1)
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
        self.display.show(self.left_fig, self.right_fig)
        self.stim_onset_ms = self.clock()

        self.state = STATE_WAIT_CHOICE
        self.state_start = self.clock()
        self._log("STATE = WAIT_CHOICE_HOLD (hold LEFT or RIGHT, or press l/r/t)")

    def _handle_choice(self, side, chosen_fig):
        choice_timestamp = self.clock()
        reaction_time_ms = choice_timestamp - self.stim_onset_ms
        rewarded = self._is_fig_rewarded(chosen_fig)

        suffix = f" ({ORIENT_NAME[chosen_fig]})" if chosen_fig != ORIENT_NONE else ""
        self._log(f"CHOICE {side}{suffix}  reaction_time={reaction_time_ms} ms")

        if rewarded:
            self.hw.reward.deliver(side)
            # Consume the armed reward for the chosen orientation.
            if chosen_fig == ORIENT_HORIZONTAL:
                self.horizontal_rewarded = False
            elif chosen_fig == ORIENT_VERTICAL:
                self.vertical_rewarded = False
            self._log("RESULT: *** REWARD ***")
        else:
            self._log("RESULT: no reward.")

        self.display.choice(side)
        self._write_trial_row(side, chosen_fig, choice_timestamp, reaction_time_ms,
                              "REWARD" if rewarded else "NO REWARD")
        self._end_trial(chosen_fig)

    def _handle_timeout(self):
        self._log(f"TRIAL {self.trial_num} TIMEOUT — no choice made.")
        # Probabilities/sides/onset are still known for a timed-out trial; only
        # the choice-specific fields are blank.
        self._write_trial_row("TIMEOUT", ORIENT_NONE, "", "", "")
        self._end_trial(ORIENT_NONE)

    def _end_trial(self, choice):
        # Clear the screen (deferred behind any active choice overlay) and
        # enter the ITI. Gate stays open until the ITI ends.
        self.display.black()
        self.state = STATE_ITI
        self.state_start = self.clock()
        self._log(f"STATE = ITI ({self.ITI_MS} ms)")

        if choice == ORIENT_HORIZONTAL:
            self.horizontal_unchosen = 0
            self.vertical_unchosen += 1
        elif choice == ORIENT_VERTICAL:
            self.vertical_unchosen = 0
            self.horizontal_unchosen += 1
        # timeout: counters unchanged (matches endTrial(ORIENT_NONE))

    def _end_iti(self):
        self.hw.motor.close()
        self.state = STATE_WAIT_CENTER
        self.state_start = self.clock()
        self._log("STATE = WAIT_CENTER_HOLD (hold CENTER, or press c)")

    # ---- CSV ---------------------------------------------------------------
    def _write_trial_row(self, chosen_side, chosen_fig, choice_timestamp,
                         reaction_time_ms, reward_str):
        # Which physical side each orientation occupies this trial. Exactly one
        # side is horizontal and the other vertical (see _randomize_sides).
        horizontal_side = "LEFT" if self.left_fig == ORIENT_HORIZONTAL else "RIGHT"
        vertical_side   = "LEFT" if self.left_fig == ORIENT_VERTICAL else "RIGHT"

        self._csv.writerow([
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
        self._csv_file.flush()

    def close(self):
        try:
            self._csv_file.close()
        except Exception:
            pass

    # ---- console output ----------------------------------------------------
    def _print_intro(self):
        print()
        print("#" * 64)
        print("  CUE EXPERIMENT (Python controller)")
        print("#" * 64)
        print(f"  P_STIM_HORIZONTAL base = {self.P_STIM_HORIZONTAL * 100:.1f}%")
        print(f"  P_STIM_VERTICAL   base = {self.P_STIM_VERTICAL * 100:.1f}%")
        print("  (effective chance = 1 - (1-P)^(unchosen+1))")
        print(f"  Logging trials to: {self.csv_path}")
        print()
        print("  Terminal controls (always live, alongside the Arduino IR):")
        print("    c = initiate trial (CENTER hold)")
        print("    l = choose LEFT     r = choose RIGHT")
        print("    t = force timeout   q = quit")
        print()
        self._log("STATE = WAIT_CENTER_HOLD (hold CENTER, or press c)")

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

    def _log(self, msg):
        if self.verbose:
            print(f"{self.clock():>8}  {msg}", flush=True)


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
