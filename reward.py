"""Reward — the reward pumps.

The firmware pulses the selected pump for its configured duration (REWARD_MS).

    reward = Reward(link)
    reward.left()
    reward.right()
    reward.deliver("LEFT")     # side-agnostic helper
"""


class Reward:
    def __init__(self, link):
        self._link = link

    def left(self):
        self._link.send("REWARD L")

    def right(self):
        self._link.send("REWARD R")

    def deliver(self, side):
        """Pulse the pump for 'L'/'LEFT' or 'R'/'RIGHT'."""
        s = str(side).upper()
        if s in ("L", "LEFT"):
            self.left()
        elif s in ("R", "RIGHT"):
            self.right()
