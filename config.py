"""Shared constants for the cue experiment.

Everything the original cue.ino hard-coded as `const` settings lives here so the
firmware stays a dumb I/O layer and all behaviour is tunable from one place.
"""

# ---- Ambient sound ---------------------------------------------------------
# Looping background sound played from the COMPUTER (or attached speaker) while
# an experiment waits for the shrew to initiate at the centre port. The waveform
# is synthesised on the fly so pitch / speed are fully adjustable.
AMBIENT_ENABLED = True
# selectable waveforms (value, GUI label)
AMBIENT_SOUNDS = ["noise", "sine", "rising", "pulse"]
AMBIENT_SOUND   = "noise"    # default waveform
AMBIENT_VOLUME  = 0.3        # 0.0 .. 1.0
AMBIENT_PITCH   = 220.0      # base tone frequency (Hz) for tonal waveforms
AMBIENT_SPEED   = 1.0        # pattern rate multiplier (sweeps/pulses per second, etc.)

# GUI-editable ambient knobs, spliced into every experiment's SPEC variables.
AMBIENT_VARS = [
    {"key": "AMBIENT_SOUND", "label": "Ambient sound", "type": "choice",
     "options": AMBIENT_SOUNDS, "default": AMBIENT_SOUND},
    {"key": "AMBIENT_PITCH", "label": "Ambient pitch (Hz)", "type": "float",
     "default": AMBIENT_PITCH, "min": 40.0, "max": 4000.0, "step": 10.0},
    {"key": "AMBIENT_SPEED", "label": "Ambient speed (x)", "type": "float",
     "default": AMBIENT_SPEED, "min": 0.1, "max": 10.0, "step": 0.1},
    {"key": "AMBIENT_VOLUME", "label": "Ambient volume", "type": "float",
     "default": AMBIENT_VOLUME, "min": 0.0, "max": 1.0, "step": 0.05},
]

# ---- Serial ----------------------------------------------------------------
DEFAULT_BAUD = 115200
DEFAULT_PORT = "COM5"    # pre-selected / auto-connected in the GUI when present

# ---- Trial timing (milliseconds) -------------------------------------------
HOLD_MS           = 2000     # how long a beam must stay broken to count as a hold
CHOICE_TIMEOUT_MS = 20000    # max time to make a choice before the trial times out
ITI_MS            = 6000     # inter-trial interval

# ---- Reward probabilities --------------------------------------------------
# Independent Bernoulli roll per orientation each trial. Effective chance grows
# the longer an orientation goes unchosen: 1 - (1-P)^(unchosen+1).
P_STIM_HORIZONTAL = 0.8
P_STIM_VERTICAL   = 0.2

# ---- Gate servo (Motor) ----------------------------------------------------
SERVO_OPEN_DEG  = 60    # angle that opens the choice gate
SERVO_CLOSE_DEG = 180   # angle that closes it

# ---- Display ---------------------------------------------------------------
DEFAULT_HIGHLIGHT_MS = 1500  # how long the fig3 overlay stays after a choice

# ---- Orientation codes -----------------------------------------------------
# These double as the FIGn numbers the display understands (1 = horizontal img,
# 2 = vertical img), matching the original SHOW L=FIGx R=FIGy protocol.
ORIENT_NONE       = 0
ORIENT_HORIZONTAL = 1
ORIENT_VERTICAL   = 2

ORIENT_NAME = {0: "NONE", 1: "HORIZONTAL", 2: "VERTICAL"}
FIG_LABEL   = {1: "horizontal", 2: "vertical"}

# ---- IR channel names (as emitted by the firmware) -------------------------
CH_LEFT   = "INNER_LEFT"
CH_CENTER = "CENTER"
CH_RIGHT  = "INNER_RIGHT"
