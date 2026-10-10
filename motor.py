"""Motor — a servo motor on the Arduino (the choice gate).

Commands the firmware to turn the servo to an absolute angle.

    motor = Motor(link)
    motor.turn(90)     # go to 90 degrees
    motor.open()       # convenience -> turn(open_deg)
    motor.close()      # convenience -> turn(close_deg)
"""

from config import SERVO_OPEN_DEG, SERVO_CLOSE_DEG


class Motor:
    def __init__(self, link, open_deg=SERVO_OPEN_DEG, close_deg=SERVO_CLOSE_DEG):
        self._link = link
        self.open_deg = open_deg
        self.close_deg = close_deg
        self.angle = None          # last commanded angle (None until first turn)

    def turn(self, angle):
        """Turn the servo to `angle` degrees (clamped to 0-180)."""
        angle = max(0, min(180, int(angle)))
        self.angle = angle
        return self._link.send(f"SERVO {angle}")

    def open(self):
        return self.turn(self.open_deg)

    def close(self):
        return self.turn(self.close_deg)
