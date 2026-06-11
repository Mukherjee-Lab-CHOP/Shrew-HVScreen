# Cue Experiment (Python-driven)

A re-architecture of the original `cue.ino` task. **All experiment logic now
lives in Python**; the Arduino is reduced to a thin hardware I/O layer.

```
┌────────────────────┐        serial         ┌──────────────────────────────────┐
│  Arduino firmware  │  ◀── commands ──────   │  Python controller                │
│  firmware.ino      │   ── detector ev. ─▶    │  run.py                           │
│                    │                         │   ├─ Hardware (one SerialLink):   │
│  • detects IR      │                         │   │    Motor / Reward / Tone /     │
│  • drives pumps,   │                         │   │    IR_detector / IR_emitter   │
│    servo, (tone)   │                         │   ├─ Display       (pygame)        │
│                    │                         │   ├─ <experiment>  (logic + CSV)   │
│                    │                         │   └─ terminal keyboard input       │
└────────────────────┘                         └──────────────────────────────────┘
```

The task can be driven by **real IR beam breaks and terminal keystrokes at the
same time** — both feed the same state machine. It runs with or without an
Arduino attached.

## Files

| File | Role |
|------|------|
| `firmware/firmware.ino` | Thin firmware: reports IR detector edges, actuates pumps / gate servo / IR emitters / tone (tone is **stubbed** — no buzzer wired yet). No trial logic. |
| `serial_link.py` | `SerialLink` — owns the serial port + reader thread. Shared by all hardware classes. Runs *detached* (terminal-only) if no port. |
| `motor.py` | `Motor` — the gate servo. `motor.turn(angle)`, plus `open()`/`close()` helpers. |
| `reward.py` | `Reward` — the reward pumps. `left()`, `right()`, `deliver(side)`. |
| `ir_detector.py` | `IR_detector` — the beam-break **detectors** (receivers). `poll_events()`. |
| `ir_emitter.py` | `IR_emitter` — the IR **emitter LEDs**. `on()`, `off()`. Kept separate from the detectors. |
| `tone.py` | `Tone` — buzzer. `play(freq, ms)` (firmware-stubbed). |
| `hardware.py` | `Hardware` — bundles the above over one `SerialLink`: `hw.motor`, `hw.reward`, `hw.ir_detector`, `hw.ir_emitter`, `hw.tone`. |
| `display.py` | `Display` — the pygame stimulus screen (ported from the old `screen.py`): two figures, fig3 choice overlay, fullscreen/multi-monitor, ESC to quit. |
| `experiments/` | One module per experiment, each exposing `EXPERIMENT = <class>`. `choose_orientation.py` holds `CueExperiment` (the full task ported from `cue.ino`). |
| `config.py` | All tunable settings (timing, probabilities, servo angles). |
| `run.py` | Entry point — auto-discovers experiments, wires everything together, runs the loop. |

## Install

```bash
pip install -r requirements.txt
```

`pyserial`/`pygame` are optional for the CLI (it degrades to detached/headless);
`PySide6` is needed only for the GUI.

## GUI control panel

```bash
python run_gui.py
```

A PySide6 control panel that wires the whole system together:

- **Top** — pick/scan the **COM port** (likely Arduinos are flagged), connect,
  choose the **stimulus monitor**, and Start/Stop the run with manual
  `c`/`l`/`r`/`t` controls.
- **Left** — build a **pipeline** of stages: *run experiment X for N trials with
  these variable overrides, then switch to the next stage.*
- **Right** — pick an experiment, edit its **variables**, and see its
  **state-machine node graph** (drag nodes; the live current state highlights
  during a run). "Add as pipeline stage →" pushes the current setup left.
- **Middle** — the **live CSV** being written and a **mirror** of the secondary
  (stimulus) screen.
- **Bottom** — two logs: **commands sent out** to the Arduino, and **prints /
  events** (experiment logs + inbound firmware lines).

The GUI renders the stimulus itself (Qt), so it doesn't need pygame. It can run
detached (no Arduino) for dry runs — commands are logged but not sent. The
state-machine playground *tunes* the existing coded experiments (in
`experiments/`); each experiment exposes a `SPEC` describing its variables and
state graph.

## Run (command line)

```bash
python run.py --list-experiments            # see available experiments
python run.py --list-ports                  # find your Arduino's port
python run.py                               # default experiment, terminal-only
python run.py --experiment choose_orientation --port /dev/tty.usbmodem1101
python run.py --experiment choose_orientation --port COM3 --windowed
python run.py --no-display                   # logic + hardware, no screen
```

`--experiment` selects which experiment to run (default `choose_orientation`).

### Adding another experiment

Create a new module in `experiments/`, e.g. `experiments/my_task.py`, defining a
class with this interface and exposing it as `EXPERIMENT`:

```python
class MyTask:
    def __init__(self, link, display, csv_path=None, verbose=True): ...
    def step(self, keys): ...        # advance one tick; return "QUIT" to stop
    def close(self): ...             # flush/close CSV
    # attributes: trial_num, csv_path

EXPERIMENT = MyTask
```

It is then auto-discovered and selectable with `--experiment my_task`. Each
experiment defines its own terminal keys (any non-whitespace char is forwarded).

### Terminal controls for `choose_orientation` (always live, in parallel with the Arduino IR)

| Key | Action |
|-----|--------|
| `c` | Initiate a trial (= CENTER hold) |
| `l` | Choose LEFT (= INNER_LEFT hold) |
| `r` | Choose RIGHT (= INNER_RIGHT hold) |
| `t` | Force a timeout |
| `q` | Quit |

Type in the terminal and press Enter. If the display is fullscreen, Cmd-Tab
(macOS) / Alt-Tab (Windows/Linux) back to the terminal to type. With a real
Arduino, a beam held broken for `HOLD_MS` (2 s) produces the same effect.

## Display assets

The display loads its images from `figures/` next to `run.py`:

| FIG | File | Shown for |
|-----|------|-----------|
| FIG1 | `figures/orientation_horizontal.png` | horizontal target |
| FIG2 | `figures/orientation_vertical.png`   | vertical target |
| FIG3 | `figures/correct_square.png`         | choice highlight overlay |

Override any of them with `--fig1/--fig2/--fig3`. If an image is missing the
display prints a warning, disables itself, and the task keeps running from the
terminal.

## Output

One CSV row per completed trial, saved to
`data/<experiment>/session_<timestamp>.csv` (override the full path with
`--csv PATH`). The `data/` folder is git-ignored.

```
trial_number, init_time_stamp, horizontal_reward_probability,
vertical_reward_probability, horizontal_side, vertical_side,
left_orientation, right_orientation, target_onset_timestamp,
chosen_orientation, chosen_side, choice_timestamp,
reaction_time_ms, reward
```

## Firmware serial protocol

Commands **in** are framed as `$<COMMAND><newline>` — a leading `$` marks the
start of a command, newline ends it, and bytes outside a `$…command` are
ignored. Case-insensitive:
`$PING`, `$REWARD L`, `$REWARD R`, `$SERVO <angle>`, `$EMIT ON`,
`$EMIT OFF`, `$TONE <hz> <ms>` (stubbed), `$?`.

Events **out**: `READY`, `IR <INNER_LEFT|CENTER|INNER_RIGHT> <BROKEN|CLEAR> <millis>`,
plus human-readable ACK lines. Wiring is unchanged from `cue.ino`.

> **Tone is stubbed.** `TONE` is parsed and logged but drives no hardware yet.
> When a buzzer is wired to `BUZZER_PIN` (pin 9), enable the `tone()` line in
> `toneStub()`.

## Hardware not responding? (motors / reward pumps)

The display is driven by Python directly, so it works even with no Arduino — a
working screen does **not** mean the serial link is up. On startup `run.py`
auto-detects the Arduino (it filters to the USB device, so extra COM ports /
Bluetooth don't confuse it) and then pings the board:

- `[info] Arduino responded — hardware link OK.` → the link is good.
- `[warn] opened COMx but the board never replied …` → the port opened but the
  board isn't talking. Almost always one of:
  1. **Firmware not flashed.** Upload `firmware/firmware.ino` to *this* board.
     An old `cue.ino` does **not** understand `SERVO`/`REWARD` and won't respond.
  2. **Port is held open** by the Arduino IDE Serial Monitor — close it.
  3. **Wrong port** — run `python run.py --list-ports` and pass `--port COMx`.

Quick bench check after flashing: open the Arduino Serial Monitor at 115200
(set the line ending to **Newline**), type `$PING` → it should reply `PONG`;
type `$REWARD L` → the left pump pulses; `$SERVO 60` / `$SERVO 180` → the gate
moves.
