# Hardware test

One runnable script per Arduino component, so you can check each part on its
own. They drive the board through the same classes the experiment uses
(`Hardware` → `Motor` / `Reward` / `IR_detector` / `IR_emitter`), so a pass means
the real control path works, not just the wiring.

**Prerequisite:** flash `firmware/firmware.ino` to the board and close the
Arduino IDE Serial Monitor (it locks the COM port).

## Scripts

| File | Tests | What it does |
|------|-------|--------------|
| `test_motor.py` | gate servo | closes, opens, then sweeps 0 → 180 |
| `test_reward.py` | reward pumps | pulses the LEFT then RIGHT pump |
| `test_ir.py` | IR emitters + detectors | turns emitters on, then checks each beam reports BROKEN when you break it |
| `test_all.py` | all of the above | connects once and runs them in sequence |
| `_common.py` | — | shared connect/auto-detect/confirm helper (not run directly) |

## Run

```bash
python hardware_test/test_motor.py            # auto-detect port
python hardware_test/test_reward.py
python hardware_test/test_ir.py               # break each beam by hand
python hardware_test/test_all.py              # guided, all three

python hardware_test/test_motor.py --port COM3        # explicit port
python hardware_test/test_motor.py --list-ports       # list ports and exit
python hardware_test/test_ir.py --port COM3           # (IR also accepts defaults)
```

Each script auto-detects the Arduino, pings it, and prints `link OK` or warns
that the board isn't responding (firmware not flashed / wrong port / port held
open). `test_ir.py` flags any beam it never saw break — useful for catching a
misaligned or miswired sensor.
