#!/usr/bin/env python3
"""Test the IR system: turn the emitters on, then verify each detector reports
its beam being broken.

Break each beam (INNER_LEFT, CENTER, INNER_RIGHT) with your hand. The test
live-prints BROKEN/CLEAR edges and, at the end, flags any beam it never saw
break (a sign of a misaligned or miswired sensor / dead emitter).

    python hardware_test/test_ir.py [--port COM3] [--seconds 30]
"""

import sys
import threading
import time

from _common import run, CHANNEL_LABEL

MONITOR_SECONDS = 30


def test_ir(hw, seconds=MONITOR_SECONDS):
    print("[IR] turning emitters ON")
    hw.ir_emitter.on()
    time.sleep(0.3)

    print(f"[IR] break each beam: {', '.join(CHANNEL_LABEL.values())}")
    print(f"     monitoring up to {seconds}s — press Enter to stop early.\n")

    hw.ir_detector.poll_events()        # drop anything already queued
    stop = threading.Event()
    threading.Thread(target=lambda: (sys.stdin.readline(), stop.set()),
                     daemon=True).start()

    seen = set()
    end = time.time() + seconds
    while time.time() < end and not stop.is_set():
        for ch, broken, ms in hw.ir_detector.poll_events():
            label = CHANNEL_LABEL.get(ch, ch)
            print(f"    {label:<12} {'BROKEN' if broken else 'CLEAR '}  (arduino {ms} ms)")
            if broken:
                seen.add(label)
        time.sleep(0.02)

    print()
    if seen:
        print(f"  detected breaks on: {', '.join(sorted(seen))}")
    missing = [v for v in CHANNEL_LABEL.values() if v not in seen]
    if missing:
        print(f"  NEVER triggered:    {', '.join(missing)}  (check alignment/wiring)")
    else:
        print("  all three beams detected a break — IR OK.")
    print("  [IR] done.")


if __name__ == "__main__":
    run("Test the IR emitters + detectors (beam-break detection).", test_ir)
