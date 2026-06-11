#!/usr/bin/env python3
"""Test the gate servo (Motor): close, open, then sweep 0 -> 180.

    python hardware_test/test_motor.py [--port COM3]
"""

import time

from _common import run
from config import SERVO_OPEN_DEG, SERVO_CLOSE_DEG


def test_motor(hw):
    print("[MOTOR] gate servo")
    print(f"  closing -> {SERVO_CLOSE_DEG}"); hw.motor.close(); time.sleep(1.0)
    print(f"  opening -> {SERVO_OPEN_DEG}");  hw.motor.open();  time.sleep(1.0)
    print("  sweeping 0 -> 180 ...")
    for angle in range(0, 181, 30):
        print(f"    SERVO {angle}"); hw.motor.turn(angle); time.sleep(0.5)
    print(f"  closing -> {SERVO_CLOSE_DEG}"); hw.motor.close()
    print("  [MOTOR] done — did the gate move at each step?")


if __name__ == "__main__":
    run("Test the gate servo motor.", test_motor)
