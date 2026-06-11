"""Bus — thread-safe channel between the background experiment worker and the
Qt main thread.

The worker (a background thread) pushes events here; a QTimer on the main thread
drains them and updates the widgets. Using queues + a poll timer avoids the
pitfalls of touching Qt widgets from a non-GUI thread.
"""

import queue
import threading


class Bus:
    def __init__(self):
        self.commands = queue.Queue()   # outgoing serial command strings
        self.prints = queue.Queue()     # captured stdout / log lines
        self.render = queue.Queue()     # display ops: ("show", l, r) / ("choice", side) / ("black",)
        self.events = queue.Queue()     # structured events: (kind, payload)
        self.keys = queue.Queue()       # manual control keys from the GUI -> worker

        self._lock = threading.Lock()
        self._status = {
            "state": None,
            "trial_num": 0,
            "stage_index": -1,
            "stage_label": "",
            "csv_path": None,
            "running": False,
        }

    # ---- status (latest-value, lock-protected) -----------------------------
    def set_status(self, **kw):
        with self._lock:
            self._status.update(kw)

    def get_status(self):
        with self._lock:
            return dict(self._status)

    # ---- producer helpers (called from the worker thread) ------------------
    def push_command(self, line):
        self.commands.put(line)

    def push_print(self, text):
        self.prints.put(text)

    def push_render(self, op):
        self.render.put(op)

    def push_event(self, kind, payload=None):
        self.events.put((kind, payload))

    # ---- manual keys (GUI -> worker) ---------------------------------------
    def push_key(self, ch):
        self.keys.put(ch)

    def drain_keys(self):
        out = []
        while True:
            try:
                out.append(self.keys.get_nowait())
            except queue.Empty:
                break
        return out

    @staticmethod
    def drain(q, limit=500):
        out = []
        for _ in range(limit):
            try:
                out.append(q.get_nowait())
            except queue.Empty:
                break
        return out
