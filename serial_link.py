"""SerialLink — the shared serial connection to the Arduino firmware.

Owns the serial port and a background reader thread. The hardware component
classes (Motor, Reward, IR, Tone) are built on top of one SerialLink: they send
commands through `send()` and subscribe to inbound lines via `add_listener()`.

Detached mode: with no port set (or pyserial not installed), `send()` becomes a
logged no-op and no lines arrive — so the whole rig can be driven from the
terminal with no Arduino attached.
"""

import threading
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:                      # pyserial optional -> detached mode
    serial = None
    list_ports = None

from config import DEFAULT_BAUD


class SerialLink:
    def __init__(self, port=None, baud=DEFAULT_BAUD, verbose=True):
        self.port = port
        self.baud = baud
        self.verbose = verbose
        self._ser = None
        self._reader = None
        self._stop = threading.Event()
        self._listeners = []
        self._connected = False
        self._data_event = threading.Event()   # set when any line arrives
        self.on_send = None                     # optional hook(line) for monitors/GUI

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
        """List every serial port device (empty if pyserial is unavailable)."""
        if list_ports is None:
            return []
        return [p.device for p in list_ports.comports()]

    @staticmethod
    def list_ports_detailed():
        """List ports with metadata for a UI: list of dicts with
        device, description, and is_usb (a USB VID present ~ likely Arduino)."""
        if list_ports is None:
            return []
        out = []
        for p in list_ports.comports():
            out.append({
                "device": p.device,
                "description": (p.description or "").strip(),
                "is_usb": getattr(p, "vid", None) is not None,
            })
        return out

    @staticmethod
    def auto_detect_port():
        """Best guess at the Arduino's port.

        Prefers real USB serial devices (those with a USB VID), and on macOS
        collapses the /dev/cu.* and /dev/tty.* twin nodes that point at the same
        device (preferring the cu.* node, which is what you open for I/O).

        Returns (chosen_port_or_None, candidate_devices). chosen_port is set only
        when the de-duplicated candidate list has exactly one entry.
        """
        if list_ports is None:
            return None, []
        infos = list(list_ports.comports())
        if not infos:
            return None, []

        # Prefer devices that look like real USB serial adapters (have a VID).
        usb = [p for p in infos if getattr(p, "vid", None) is not None]
        pool = usb or infos
        devices = [p.device for p in pool]

        # Collapse macOS cu./tty. twins (same suffix), preferring cu.
        order = []
        index_by_suffix = {}
        for d in devices:
            suffix = d
            for pre in ("/dev/cu.", "/dev/tty."):
                if d.startswith(pre):
                    suffix = d[len(pre):]
                    break
            if suffix in index_by_suffix:
                i = index_by_suffix[suffix]
                if d.startswith("/dev/cu."):   # prefer the cu. node
                    order[i] = d
                continue
            index_by_suffix[suffix] = len(order)
            order.append(d)

        chosen = order[0] if len(order) == 1 else None
        return chosen, order

    @property
    def connected(self):
        return self._connected

    def add_listener(self, fn):
        """Register a callable fn(line) -> bool. Returning True marks the line
        as handled and suppresses the default log of unrecognised output."""
        self._listeners.append(fn)

    # ---- lifecycle ----------------------------------------------------------
    def connect(self):
        """Open the port and start the reader thread. Returns True on success,
        False if it falls back to detached mode."""
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
        self._data_event.clear()
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
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        self._connected = False

    # ---- io -----------------------------------------------------------------
    def send(self, line):
        # Every command is framed with a leading '$' (start marker) and a
        # trailing newline (terminator), so the firmware can reliably pick
        # commands out of the serial stream.
        if self.on_send is not None:
            try:
                self.on_send(line)
            except Exception:
                pass
        if self._ser is None:
            self._log(f"(detached) -> ${line}")
            return
        try:
            self._ser.write(("$" + line + "\n").encode())
        except Exception as e:
            self._log(f"write failed ({line!r}): {e}")

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
                    self._dispatch(line)

    def _dispatch(self, line):
        self._data_event.set()        # any line proves the board is talking
        handled = False
        for fn in self._listeners:
            try:
                if fn(line):
                    handled = True
            except Exception as e:
                self._log(f"listener error: {e}")
        if not handled:
            self._log(f"<- {line}")   # informational firmware chatter

    def confirm(self, timeout=3.0):
        """Verify the board is actually responding, and wait out its boot.

        Opening the port resets the Arduino (DTR), so for ~1.5-2 s it's running
        the bootloader and drops everything sent to it. A single PING fired right
        after open is therefore usually lost. We re-ping every 0.4 s until the
        board talks back (boot banner / READY / PONG) or `timeout` elapses, so by
        the time this returns True the link is genuinely usable. Distinguishes
        'port opened but wrong/!flashed firmware' from a working link."""
        if self._ser is None:
            return False
        if self._data_event.is_set():     # already heard from it (e.g. boot READY)
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.send("PING")
            if self._data_event.wait(0.4):
                return True
        return False

    def _log(self, msg):
        if self.verbose:
            print(f"[arduino] {msg}", flush=True)
