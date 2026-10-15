#!/usr/bin/env python3
"""Test the gate servo (Motor): close, open, then sweep 0 -> 180.

    python hardware_test/test_motor.py [--port COM3]
"""

import time

from _common import run
from config import SERVO_OPEN_DEG, SERVO_CLOSE_DEG


def test_motor(hw):
    print("[MOTOR] gate servo")
    # Allow a full 180-degree move at the firmware default of 25 ms/degree.
    settle_s = 5.0
    print(f"  closing -> {SERVO_CLOSE_DEG}"); hw.motor.close(); time.sleep(settle_s)
    print(f"  opening -> {SERVO_OPEN_DEG}");  hw.motor.open();  time.sleep(settle_s)
    print("  sweeping 0 -> 180 ...")
    for angle in range(0, 181, 30):
        print(f"    SERVO {angle}"); hw.motor.turn(angle); time.sleep(settle_s)
    print(f"  closing -> {SERVO_CLOSE_DEG}"); hw.motor.close()
    time.sleep(settle_s)
    print("  [MOTOR] done — did the gate move at each step?")


if __name__ == "__main__":
    run("Test the gate servo motor.", test_motor)
