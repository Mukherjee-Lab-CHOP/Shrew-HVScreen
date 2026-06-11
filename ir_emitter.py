"""IR_emitter — the infrared EMITTER LEDs.

This class is ONLY the emitters (the IR light that shines onto the detectors).
The detectors themselves are a separate concern, handled by IR (ir.py) — keep
the two distinct so they are never confused.

The firmware turns the emitters on at boot; use this to toggle them.

    ir_emitter = IR_emitter(link)
    ir_emitter.off()
    ir_emitter.on()
"""


class IR_emitter:
    def __init__(self, link):
        self._link = link
        self.is_on = True          # firmware starts with emitters on

    def set(self, on):
        self.is_on = bool(on)
        self._link.send("EMIT ON" if on else "EMIT OFF")

    def on(self):
        self.set(True)

    def off(self):
        self.set(False)
