#!/usr/bin/env python3
"""Guided run-through of every component test: motor, reward, IR.

Connects once, then walks through each test with an Enter prompt between them.

    python hardware_test/test_all.py [--port COM3]
"""

from _common import open_hardware
from test_motor import test_motor
from test_reward import test_reward
from test_ir import test_ir


def main():
    hw = open_hardware("Run all hardware tests (motor, reward, IR).")
    if hw is None:
        return
    try:
        print("=== GUIDED HARDWARE TEST ===")
        input("Press Enter to test the MOTOR (gate servo)... ")
        test_motor(hw)
        input("\nPress Enter to test the REWARD pumps... ")
        test_reward(hw)
        input("\nPress Enter to test the IR detectors... ")
        test_ir(hw)
        print("\n=== ALL TESTS COMPLETE ===")
    except KeyboardInterrupt:
        print("\n[info] interrupted")
    finally:
        hw.close()
        print("[info] closed.")


if __name__ == "__main__":
    main()
