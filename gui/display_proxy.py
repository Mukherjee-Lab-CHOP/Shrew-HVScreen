"""DisplayProxy — a stand-in for the pygame Display, used in GUI mode.

It implements the same interface the experiment calls (start / show / choice /
black / update / close / enabled) but, instead of drawing, it pushes render ops
onto the Bus. The Qt main thread drains them and updates the real stimulus
window + the middle mirror. This keeps the experiment code unchanged and avoids
running pygame inside the Qt app.
"""


class DisplayProxy:
    def __init__(self, bus):
        self._bus = bus
        self.enabled = True

    def start(self):
        return True

    def show(self, left_fig, right_fig):
        self._bus.push_render(("show", int(left_fig), int(right_fig)))

    def choice(self, side, correct=True):
        self._bus.push_render(("choice", str(side), bool(correct)))

    def black(self):
        self._bus.push_render(("black",))

    def update(self):
        # ESC / window-close is handled by the Qt window + Stop button, so the
        # experiment's own loop never needs to quit on our behalf.
        return True

    def close(self):
        self._bus.push_render(("black",))
