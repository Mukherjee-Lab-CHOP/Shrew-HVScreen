# Cue Experiment (Python-driven)

A re-architecture of the original `cue.ino` task. **All experiment logic now
lives in Python**; the Arduino is reduced to a thin hardware I/O layer.

```
┌────────────────────┐        serial         ┌──────────────────────────────┐
│  Arduino firmware  │  ◀── commands ──────   │  Python controller            │
│  cue_hw.ino        │   ─── IR events ──▶     │  run.py                       │
│                    │                         │   ├─ turn_motor   (serial)    │
│  • detects IR      │                         │   ├─ Display      (pygame)    │
│  • drives pumps,   │                         │   ├─ CueExperiment(logic+CSV) │
│    servo, (tone)   │                         │   └─ terminal keyboard input  │
└────────────────────┘                         └──────────────────────────────┘
```

The task can be driven by **real IR beam breaks and terminal keystrokes at the
same time** — both feed the same state machine. It runs with or without an
Arduino attached.

## Files

| File | Role |
|------|------|
| `cue_hw/cue_hw.ino` | Thin firmware: reports IR edges, actuates pumps / gate servo / IR emitters / tone (tone is **stubbed** — no buzzer wired yet). No trial logic. |
| `turn_motor.py` | `turn_motor` class — the only thing that talks to the board. Sends actuation, surfaces IR events. Runs *detached* (terminal-only) if no port. |
| `display.py` | `Display` class — the pygame stimulus screen (ported from the old `screen.py`): two figures, fig3 choice overlay, fullscreen/multi-monitor, ESC to quit. |
| `experiments/` | One module per experiment, each exposing `EXPERIMENT = <class>`. `choose_orientation.py` holds `CueExperiment` (the full task ported from `cue.ino`). |
| `config.py` | All tunable settings (timing, probabilities, pins-as-names). |
| `run.py` | Entry point — auto-discovers experiments, wires everything together, runs the loop. |

## Install

```bash
pip install pyserial pygame
```

Both are optional: without `pyserial` the link runs detached; without `pygame`
(or with `--no-display`) the task runs headless. Either way the terminal
controls still work.

## Run

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

The display expects `fig1.png` (horizontal), `fig2.png` (vertical), and
`fig3.png` (choice overlay) next to `run.py`, or pass `--fig1/--fig2/--fig3`.
If they're missing the display disables itself and the task keeps running from
the terminal.

## Output

One CSV row per completed trial — `session_<timestamp>.csv` (or `--csv PATH`):

```
trial_number, init_time_stamp, horizontal_reward_probability,
vertical_reward_probability, horizontal_side, vertical_side,
left_orientation, right_orientation, target_onset_timestamp,
chosen_orientation, chosen_side, choice_timestamp,
reaction_time_ms, reward
```

## Firmware serial protocol

Commands **in** (one per line, case-insensitive):
`PING`, `REWARD L`, `REWARD R`, `GATE OPEN`, `GATE CLOSE`, `EMIT ON`,
`EMIT OFF`, `TONE <hz> <ms>` (stubbed), `?`.

Events **out**: `READY`, `IR <INNER_LEFT|CENTER|INNER_RIGHT> <BROKEN|CLEAR> <millis>`,
plus human-readable ACK lines. Wiring is unchanged from `cue.ino`.

> **Tone is stubbed.** `TONE` is parsed and logged but drives no hardware yet.
> When a buzzer is wired to `BUZZER_PIN` (pin 9), enable the `tone()` line in
> `toneStub()`.
