"""Experiment — shared base class for the cue experiments.

Every experiment is a non-blocking state machine driven by ``step(keys)``, fed by
two parallel input sources: real IR beam breaks (with HOLD_MS hold timing done
here, in Python) and terminal/GUI keystrokes ('c','l','r','t','q'). This base
factors out the machinery they all share — construction, timing, IR hold
detection, None-safe display helpers, CSV logging, the intro banner, and state
transitions — so each concrete experiment only declares its parameters, CSV
columns, and ``run_step()`` logic.

Subclass contract
-----------------
class attrs : TITLE, CSV_HEADER, INITIAL_STATE, INITIAL_STATE_MSG, CONTROLS_HELP,
              BLANK_ON_START
setup()       : read params (via ``self.param``) into attributes; init extra
                state. Typically sets INIT_POKE_MS / REWARD_POKE_MS, REWARD_MS,
                and CORRECT_ITI_WAIT / INCORRECT_ITI_WAIT.
intro_lines() : optional list of banner lines describing the configuration.
run_step(keys): the state-machine body (called after the quit/IR preamble).
                Call end_trial(correct, rewarded) to finish a trial; the base
                runs the REWARD (gate-open) and ITI states for you.

Provided helpers: clock(), inputs(), ir_hold(), display_show/choice/black(),
open_gate/close_gate(), write_row(), goto(), end_trial(), log(), close().
"""

import csv
import os
import time
from datetime import datetime

from config import (CH_LEFT, CH_CENTER, CH_RIGHT, AMBIENT_ENABLED,
                    AMBIENT_SOUND, AMBIENT_PITCH, AMBIENT_SPEED, AMBIENT_VOLUME)
from audio import Ambient

# Logged whenever an experiment returns to the trial-start state.
WAIT_CENTER_MSG = "STATE = WAIT_CENTER_HOLD (hold CENTER, or press c)"


def now_ms():
    return int(time.monotonic() * 1000)


class Experiment:
    # ---- subclass-overridable declarations --------------------------------
    TITLE = "EXPERIMENT"
    CSV_HEADER = []
    CHANNELS = (CH_LEFT, CH_CENTER, CH_RIGHT)
    INITIAL_STATE = None
    INITIAL_STATE_MSG = WAIT_CENTER_MSG
    CONTROLS_HELP = ("c = start (CENTER)   l = LEFT   r = RIGHT   "
                     "t = timeout   q = quit")
    BLANK_ON_START = False
    # Poke recognition: how long a beam must stay broken to count as a poke. The
    # centre/initiation port and the side/reward ports have independent windows.
    INIT_POKE_MS = 100      # centre (initiation) hold, overridden in setup()
    REWARD_POKE_MS = 100    # side (choice/reward) hold, overridden in setup()
    # Reward phase: after a rewarded response the gate stays OPEN for REWARD_MS so
    # the animal can collect, THEN the ITI begins (which closes the gate). The ITI
    # length depends on whether the trial was correct. The base manages both timed
    # states; experiments call end_trial(correct, rewarded).
    REWARD_STATE = "REWARD"
    ITI_STATE = "ITI"
    REWARD_MS = 0               # overridden in setup() (0 = no wait)
    CORRECT_ITI_WAIT = 2000     # ITI after a correct trial, overridden in setup()
    INCORRECT_ITI_WAIT = 10000  # ITI after an incorrect trial, overridden in setup()

    def __init__(self, hardware, display, csv_path=None, params=None, verbose=True):
        self.hw = hardware
        self.display = display
        self.verbose = verbose
        self.params = params or {}

        self.trial_num = 0          # trials started
        self.completed_trials = 0   # trials finished (what the pipeline counts)

        self._t0 = now_ms()
        self.state = self.INITIAL_STATE
        self.state_start = self.clock()
        self._pending_iti_ms = 0    # ITI duration for the upcoming ITI (set per trial)

        # IR beam tracking for hold timing; a hold fires once per continuous
        # break and re-arms on release.
        self._broken = {ch: False for ch in self.CHANNELS}
        self._broken_since = {ch: 0 for ch in self.CHANNELS}
        self._armed = {ch: True for ch in self.CHANNELS}

        self._open_csv(csv_path)

        # ambient background sound while waiting for centre initiation
        # (waveform / pitch / speed / volume are GUI-tunable per experiment)
        if AMBIENT_ENABLED:
            self.ambient = Ambient(
                kind=self.param("AMBIENT_SOUND", AMBIENT_SOUND, str),
                pitch=self.param("AMBIENT_PITCH", AMBIENT_PITCH, float),
                speed=self.param("AMBIENT_SPEED", AMBIENT_SPEED, float),
                volume=self.param("AMBIENT_VOLUME", AMBIENT_VOLUME, float),
            )
        else:
            self.ambient = None

        self.setup()
        if self.BLANK_ON_START:
            self.display_black()
        self.close_gate()                   # safe state: gate closed at the start
        self._apply_ambient(self.state)     # start the hiss if we begin in WAIT_CENTER
        self.intro()

    # ---- params ------------------------------------------------------------
    def param(self, key, default, cast=None):
        """Fetch a tunable param with a default, optionally cast (int/float/bool)."""
        value = self.params.get(key, default)
        return cast(value) if cast is not None else value

    # ---- time --------------------------------------------------------------
    def clock(self):
        """Milliseconds since the experiment started (analogous to millis())."""
        return now_ms() - self._t0

    # ---- CSV ---------------------------------------------------------------
    def _open_csv(self, csv_path):
        self.csv_path = csv_path or datetime.now().strftime("session_%Y%m%d_%H%M%S.csv")
        parent = os.path.dirname(self.csv_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._csv_file = open(self.csv_path, "w", newline="")
        self._csv = csv.writer(self._csv_file)
        if self.CSV_HEADER:
            self.write_row(self.CSV_HEADER)

    def write_row(self, values):
        self._csv.writerow(values)
        self._csv_file.flush()

    def close(self):
        if self.ambient is not None:
            self.ambient.close()
        try:
            self._csv_file.close()
        except Exception:
            pass

    # ---- ambient sound -----------------------------------------------------
    def _apply_ambient(self, state):
        """Play the ambient hiss only while waiting for centre initiation."""
        if self.ambient is None:
            return
        if state == self.INITIAL_STATE:
            self.ambient.start()
        else:
            self.ambient.stop()

    # ---- IR beam hold timing ----------------------------------------------
    def ingest_ir(self):
        for channel, broken, _arduino_ms in self.hw.ir_detector.poll_events():
            if channel not in self._broken:
                continue
            if broken and not self._broken[channel]:
                self._broken[channel] = True
                self._broken_since[channel] = self.clock()
            elif not broken and self._broken[channel]:
                self._broken[channel] = False
                self._armed[channel] = True      # re-arm for the next break

    def ir_hold(self, channel):
        """True once when a beam has been held broken continuously long enough to
        count as a poke. The centre port uses INIT_POKE_MS; the side ports use
        REWARD_POKE_MS."""
        threshold = self.INIT_POKE_MS if channel == CH_CENTER else self.REWARD_POKE_MS
        if (self._broken[channel] and self._armed[channel]
                and (self.clock() - self._broken_since[channel]) >= threshold):
            self._armed[channel] = False
            return True
        return False

    def inputs(self, keys):
        """High-level triggers from EITHER input source. Each IR hold is sampled
        exactly once per step (the hold has a one-shot side effect), so call this
        once per ``run_step``."""
        return {
            "center":  self.ir_hold(CH_CENTER) or ("c" in keys),
            "left":    self.ir_hold(CH_LEFT)   or ("l" in keys),
            "right":   self.ir_hold(CH_RIGHT)  or ("r" in keys),
            "timeout": "t" in keys,
        }

    # ---- display (None-safe so it also runs head-less) --------------------
    def display_show(self, left, right):
        if self.display is not None:
            self.display.show(left, right)

    def display_choice(self, side, correct=True):
        if self.display is not None:
            self.display.choice(side, correct)

    def display_black(self):
        if self.display is not None:
            self.display.black()

    # ---- choice gate (servo) ----------------------------------------------
    def open_gate(self):
        """Open the choice gate (after the centre-initiation hold)."""
        try:
            self.hw.motor.open()
        except Exception:
            pass

    def close_gate(self):
        """Close the choice gate (during the ITI / between trials)."""
        try:
            self.hw.motor.close()
        except Exception:
            pass

    # ---- state transitions -------------------------------------------------
    def goto(self, state, msg=None):
        self.state = state
        self.state_start = self.clock()
        self._apply_ambient(state)      # hiss on while waiting for centre, off otherwise
        if msg:
            self.log(msg)

    def end_trial(self, correct, rewarded):
        """Finish the current trial. The experiment has already shown its
        correct/incorrect flash; this counts the trial, picks the ITI length by
        correctness, and (if rewarded) holds the gate open for the reward phase
        first. The base step then runs the timed REWARD/ITI states and returns to
        the centre-initiation state."""
        self.completed_trials += 1
        self._pending_iti_ms = (self.CORRECT_ITI_WAIT if correct
                                else self.INCORRECT_ITI_WAIT)
        if rewarded:
            # gate stays OPEN + stimulus up through the reward-collection window
            self.goto(self.REWARD_STATE, f"STATE = REWARD ({self.REWARD_MS} ms)")
        else:
            self.display_black()
            self.close_gate()
            self.goto(self.ITI_STATE, f"STATE = ITI ({self._pending_iti_ms} ms)")

    # ---- main loop ---------------------------------------------------------
    def step(self, keys):
        """Advance the state machine one tick. Returns "QUIT" or None."""
        if "q" in keys:
            return "QUIT"
        self.ingest_ir()
        if self.state == self.REWARD_STATE:
            # reward-collection window: gate stays open until REWARD_MS elapses,
            # then close the gate and begin the (correctness-dependent) ITI.
            if self.clock() - self.state_start >= self.REWARD_MS:
                self.display_black()
                self.close_gate()
                self.goto(self.ITI_STATE, f"STATE = ITI ({self._pending_iti_ms} ms)")
            return None
        if self.state == self.ITI_STATE:
            if self.clock() - self.state_start >= self._pending_iti_ms:
                self.goto(self.INITIAL_STATE, WAIT_CENTER_MSG)
            return None
        return self.run_step(keys)

    # ---- subclass hooks ----------------------------------------------------
    def setup(self):
        """Initialize parameters / experiment-specific state."""

    def intro_lines(self):
        return []

    def run_step(self, keys):
        raise NotImplementedError

    # ---- console -----------------------------------------------------------
    def intro(self):
        print()
        print("#" * 64)
        print(f"  {self.TITLE}")
        print("#" * 64)
        for line in self.intro_lines():
            print(line)
        print(f"  Logging to: {self.csv_path}")
        print(f"  Controls: {self.CONTROLS_HELP}")
        print()
        self.log(self.INITIAL_STATE_MSG)

    def log(self, msg):
        if self.verbose:
            print(f"{self.clock():>8}  {msg}", flush=True)
