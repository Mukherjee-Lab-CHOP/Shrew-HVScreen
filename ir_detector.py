"""IR_detector — the infrared beam-break DETECTORS (receivers).

This class is ONLY the detectors. The IR emitter LEDs that shine onto them are a
separate concern, handled by IR_emitter (ir_emitter.py) — keep the two distinct
so they are never confused.

Subscribes to the serial link and surfaces edge events emitted by the firmware:

    IR <CHANNEL> BROKEN <millis>
    IR <CHANNEL> CLEAR  <millis>
        CHANNEL is one of: INNER_LEFT  CENTER  INNER_RIGHT

The experiment pulls captured events with poll_events(); hold timing (a beam
held broken for HOLD_MS) is done in the experiment, which owns its own clock.

    detector = IR_detector(link)
    for channel, broken, arduino_ms in detector.poll_events():
        ...
"""

import queue

from config import CH_LEFT, CH_CENTER, CH_RIGHT


class IR_detector:
    CHANNELS = {CH_LEFT, CH_CENTER, CH_RIGHT}

    def __init__(self, link):
        self._link = link
        self._events = queue.Queue()
        link.add_listener(self._on_line)

    def _on_line(self, line):
        # IR <CHANNEL> BROKEN|CLEAR [<millis>]
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "IR" and parts[1] in self.CHANNELS:
            broken = parts[2].upper() == "BROKEN"
            arduino_ms = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else None
            self._events.put((parts[1], broken, arduino_ms))
            return True        # handled -> suppress default log
        return False

    def poll_events(self):
        """Drain and return all detector events since the last call:
        list of (channel, broken: bool, arduino_ms: int|None)."""
        out = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                break
        return out
