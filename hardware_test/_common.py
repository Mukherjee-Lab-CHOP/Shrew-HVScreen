"""Shared setup for the per-component hardware tests.

Each test_*.py in this folder is independently runnable. They all use
open_hardware() to parse the common CLI args, connect to the board, and confirm
the firmware is responding before running their checks.
"""

import argparse
import os
import sys

# Make the project root importable when run from the hardware_test/ subfolder.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware import Hardware                       # noqa: E402
from config import CH_LEFT, CH_CENTER, CH_RIGHT     # noqa: E402

CHANNEL_LABEL = {CH_LEFT: "INNER_LEFT", CH_CENTER: "CENTER", CH_RIGHT: "INNER_RIGHT"}


def open_hardware(description):
    """Parse --port/--baud/--list-ports, connect, and confirm the link.

    Returns a connected Hardware, or None if the caller should just exit
    (used --list-ports, or the port could not be opened).
    """
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--port", default=None,
                   help="Serial port (e.g. COM3). Omit to auto-detect.")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--list-ports", action="store_true",
                   help="List serial ports and exit.")
    args = p.parse_args()

    if args.list_ports:
        ports = Hardware.available_ports()
        print("Serial ports:" if ports else "No serial ports detected.")
        for d in ports:
            print(f"  {d}")
        return None

    port = args.port
    if port is None:
        port, candidates = Hardware.auto_detect_port()
        if port:
            print(f"[info] auto-detected Arduino port: {port}")
        elif candidates:
            print(f"[info] multiple candidate ports {candidates}; pass --port.")
        else:
            print("[info] no serial port found.")

    hw = Hardware(port=port, baud=args.baud)
    if not hw.connect():
        print("[error] could not open the serial port. Pass --port COMx and make "
              "sure the Arduino IDE Serial Monitor is closed.")
        return None

    if hw.confirm(timeout=3.0):
        print("[info] Arduino responded — link OK.\n")
    else:
        print("[warn] opened the port but the board never replied. Flash "
              "firmware/firmware.ino and close any Serial Monitor, then retry.\n")
    return hw


def run(description, test_fn):
    """Boilerplate for a single-component test script: connect, run, clean up."""
    hw = open_hardware(description)
    if hw is None:
        return
    try:
        test_fn(hw)
    except KeyboardInterrupt:
        print("\n[info] interrupted")
    finally:
        hw.close()
        print("[info] closed.")
