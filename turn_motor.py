"""turn_motor — the Python <-> Arduino transport / actuation layer.

This class is the ONLY thing that talks to the board. It sends actuation
commands (reward pumps, gate servo, IR emitters, tone) and receives IR
beam-break events from the thin firmware (firmware/cue_hw/cue_hw.ino).

It owns a background reader thread so IR edges are captured the moment they
arrive; the experiment loop pulls them with `poll_events()`.

If no serial port is set (or pyserial is not installed) the object runs in
"detached" mode: every actuation call becomes a logged no-op and no IR events
are produced. That lets the whole experiment be driven from the terminal with
no Arduino attached.

Example
-------
    link = turn_motor()
    link.set_serial_port("/dev/tty.usbmodem1101")   # or "COM3" on Windows
    link.connect()
    link.gate_open()
    link.reward_left()
    for channel, broken, arduino_ms in link.poll_events():
        ...
    link.close()
"""

import queue
import threading
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:                      # pyserial optional -> detached mode
    serial = None
    list_ports = None

from config import DEFAULT_BAUD, CH_LEFT, CH_CENTER, CH_RIGHT


class turn_motor:
    IR_CHANNELS = {CH_LEFT, CH_CENTER, CH_RIGHT}

    def __init__(self, port=None, baud=DEFAULT_BAUD, verbose=True):
        self.port = port
        self.baud = baud
        self.verbose = verbose
        self._ser = None
        self._reader = None
        self._stop = threading.Event()
        self._events = queue.Queue()      # (channel, broken: bool, arduino_ms: int|None)
        self._connected = False

    # ---- configuration -----------------------------------------------------
    def set_serial_port(self, port):
        """Set (or change) the serial port. Reconnects if already connected."""
        was_connected = self._connected
        if was_connected:
            self.close()
        self.port = port
        if was_connected:
            self.connect()

    def set_baud(self, baud):
        self.baud = baud

    @staticmethod
    def available_ports():
        """List candidate serial ports (empty if pyserial is unavailable)."""
        if list_ports is None:
            return []
        return [p.device for p in list_ports.comports()]

    @property
    def connected(self):
        return self._connected

    # ---- lifecycle ----------------------------------------------------------
    def connect(self):
        """Open the serial port and start the reader thread.

        Returns True on success, False if it falls back to detached mode.
        """
        if serial is None:
            self._log("pyserial not installed -> detached (terminal-only).")
            return False
        if not self.port:
            self._log("no serial port set -> detached (terminal-only).")
            return False
        try:
            # serial_for_url accepts real ports (COM3, /dev/tty*) and URL
            # handlers (socket://...), so a fake-Arduino harness can plug in.
            self._ser = serial.serial_for_url(self.port, baudrate=self.baud,
                                              timeout=0.05)
        except Exception as e:
            self._log(f"could not open '{self.port}': {e}")
            self._ser = None
            return False

        time.sleep(0.2)
        try:
            self._ser.reset_input_buffer()
        except Exception:
            pass

        self._stop.clear()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._connected = True
        self._log(f"connected on {self.port} @ {self.baud} baud")
        return True

    def close(self):
        self._stop.set()
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=1.0)
        if self._ser is not None:
            try:
                self.gate_close()        # leave the rig in a safe state
            except Exception:
                pass
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        self._connected = False

    # ---- outgoing commands --------------------------------------------------
    def _send(self, line):
        if self._ser is None:
            self._log(f"(detached) -> {line}")
            return
        try:
            self._ser.write((line + "\n").encode())
        except Exception as e:
            self._log(f"write failed ({line!r}): {e}")

    def reward(self, side):
        """Pulse the reward pump for 'L'/'LEFT' or 'R'/'RIGHT'."""
        s = str(side).upper()
        if s in ("L", "LEFT"):
            self.reward_left()
        elif s in ("R", "RIGHT"):
            self.reward_right()

    def reward_left(self):
        self._send("REWARD L")

    def reward_right(self):
        self._send("REWARD R")

    def gate_open(self):
        self._send("GATE OPEN")

    def gate_close(self):
        self._send("GATE CLOSE")

    def emitters(self, on=True):
        self._send("EMIT ON" if on else "EMIT OFF")

    def tone(self, freq=1000, ms=200):
        """Request a tone. NOTE: firmware currently stubs this (no buzzer wired)."""
        self._send(f"TONE {int(freq)} {int(ms)}")

    def ping(self):
        self._send("PING")

    # ---- incoming events ----------------------------------------------------
    def poll_events(self):
        """Drain and return all IR events seen since the last call.

        Each item is (channel, broken: bool, arduino_ms: int|None).
        """
        out = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                break
        return out

    def _read_loop(self):
        buf = b""
        while not self._stop.is_set():
            try:
                data = self._ser.read(64)
            except Exception:
                break
            if not data:
                continue
            buf += data
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode(errors="ignore").strip()
                if line:
                    self._handle_line(line)

    def _handle_line(self, line):
        # IR <CHANNEL> BROKEN|CLEAR [<millis>]
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "IR" and parts[1] in self.IR_CHANNELS:
            broken = parts[2].upper() == "BROKEN"
            arduino_ms = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else None
            self._events.put((parts[1], broken, arduino_ms))
            return
        # Anything else is informational firmware chatter (ACKs, banner, etc.)
        self._log(f"<- {line}")

    def _log(self, msg):
        if self.verbose:
            print(f"[arduino] {msg}", flush=True)
