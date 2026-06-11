#!/usr/bin/env python3
"""Test the reward pumps (Reward): pulse LEFT then RIGHT.

    python hardware_test/test_reward.py [--port COM3]
"""

import time

from _common import run


def test_reward(hw):
    print("[REWARD] pumps")
    print("  LEFT pump pulse ...");  hw.reward.left();  time.sleep(1.0)
    print("  RIGHT pump pulse ..."); hw.reward.right(); time.sleep(1.0)
    print("  [REWARD] done — did each pump click / dispense?")


if __name__ == "__main__":
    run("Test the reward pumps.", test_reward)
