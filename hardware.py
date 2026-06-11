"""Hardware — all Arduino-attached components, sharing one serial link.

A thin bundle so an experiment can be handed a single object and reach each
peripheral by name:

    hw = Hardware(port="COM3")
    hw.connect()
    hw.motor.turn(90)        # gate servo
    hw.motor.open()
    hw.reward.deliver("LEFT")
    hw.tone.play(1000, 200)
    hw.ir_emitter.off()              # IR LEDs
    for ev in hw.ir_detector.poll_events():   # beam-break detectors
        ...
    hw.close()

Components:
    .motor        -> Motor        (choice gate servo)  — motor.turn(angle)
    .reward       -> Reward       (reward pumps)
    .ir_detector  -> IR_detector  (beam-break DETECTORS / receivers)
    .ir_emitter   -> IR_emitter   (the IR emitter LEDs)
    .tone         -> Tone         (buzzer; firmware-stubbed)
    .link         -> SerialLink   (shared transport)
"""

from config import DEFAULT_BAUD
from serial_link import SerialLink
from motor import Motor
from reward import Reward
from ir_detector import IR_detector
from ir_emitter import IR_emitter
from tone import Tone


class Hardware:
    def __init__(self, port=None, baud=DEFAULT_BAUD, verbose=True):
        self.link = SerialLink(port=port, baud=baud, verbose=verbose)
        # IR_detector registers its listener on construction, before connect()
        # starts the reader thread, so no early events are missed.
        self.ir_detector = IR_detector(self.link)
        self.ir_emitter = IR_emitter(self.link)
        self.motor = Motor(self.link)
        self.reward = Reward(self.link)
        self.tone = Tone(self.link)

    # ---- configuration / lifecycle ----------------------------------------
    def set_serial_port(self, port):
        self.link.set_serial_port(port)

    @staticmethod
    def available_ports():
        return SerialLink.available_ports()

    @staticmethod
    def auto_detect_port():
        return SerialLink.auto_detect_port()

    @property
    def connected(self):
        return self.link.connected

    def connect(self):
        return self.link.connect()

    def confirm(self, timeout=3.0):
        """True if the board responds (PING/READY) — i.e. firmware is flashed."""
        return self.link.confirm(timeout)

    def close(self):
        try:
            self.motor.close()      # leave the gate closed (safe state)
        except Exception:
            pass
        self.link.close()
