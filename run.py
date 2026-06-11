#!/usr/bin/env python3
"""Entry point for the behavior experiments.

Wires together the pieces and runs the main loop:

    turn_motor   <- talks to the Arduino firmware (IR in, actuation out)
    Display      <- pygame stimulus screen
    <experiment> <- the trial logic + CSV logging (chosen with --experiment)

Both control paths are always live: the experiment responds to real IR beam
breaks from the Arduino AND to terminal keystrokes, simultaneously.

Experiments are auto-discovered from the experiments/ package: any module that
defines ``EXPERIMENT = <class>`` is selectable. Add a new file there and it
shows up automatically.

Examples
--------
    python run.py --list-experiments              # see available experiments
    python run.py --list-ports                    # see available serial ports
    python run.py                                 # default experiment, terminal-only
    python run.py --experiment choose_orientation --port COM3
    python run.py --experiment choose_orientation --port /dev/tty.usbmodem1101
    python run.py --no-display                    # logic + hardware, no screen

Type in THIS terminal to drive the task by hand (Cmd/Alt-Tab back from the
fullscreen display first). The keys depend on the experiment; choose_orientation
uses:
    c = initiate trial    l = choose LEFT    r = choose RIGHT
    t = force timeout      q = quit
"""

import argparse
import importlib
import pkgutil
import sys
import threading
import time

import experiments
from config import DEFAULT_BAUD, DEFAULT_HIGHLIGHT_MS
from turn_motor import turn_motor
from display import Display

DEFAULT_EXPERIMENT = "choose_orientation"


def discover_experiments():
    """Return {module_name: experiment_class} for every experiments/ module
    that exposes a module-level EXPERIMENT class."""
    registry = {}
    for mod in pkgutil.iter_modules(experiments.__path__):
        if mod.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"experiments.{mod.name}")
        except Exception as e:
            print(f"[warn] could not import experiments.{mod.name}: {e}", flush=True)
            continue
        cls = getattr(module, "EXPERIMENT", None)
        if cls is not None:
            registry[mod.name] = cls
    return registry


def _first_doc_line(cls):
    doc = cls.__doc__
    if not doc:                                   # fall back to the module docstring
        doc = getattr(sys.modules.get(cls.__module__), "__doc__", "")
    lines = (doc or "").strip().splitlines()
    return lines[0] if lines else ""


def _start_key_thread():
    """Read the terminal in a background thread; return a thread-safe getter.

    Each line typed contributes its characters as individual (lowercased) key
    events, so 'l<Enter>' yields 'l'. EOF (Ctrl-D) yields a synthetic 'q'.
    Any non-whitespace character is forwarded, so each experiment defines its
    own key meanings.
    """
    import queue
    q = queue.Queue()

    def reader():
        while True:
            try:
                line = sys.stdin.readline()
            except Exception:
                q.put("q")
                return
            if line == "":            # EOF
                q.put("q")
                return
            for ch in line.strip().lower():
                if not ch.isspace():
                    q.put(ch)

    threading.Thread(target=reader, daemon=True).start()

    def drain():
        keys = []
        while True:
            try:
                keys.append(q.get_nowait())
            except queue.Empty:
                break
        return keys

    return drain


def main():
    registry = discover_experiments()
    choices = sorted(registry)

    p = argparse.ArgumentParser(description="Behavior experiment runner (Python controller).")
    p.add_argument("--experiment", default=DEFAULT_EXPERIMENT, choices=choices or None,
                   help=f"Which experiment to run (default: {DEFAULT_EXPERIMENT}).")
    p.add_argument("--list-experiments", action="store_true",
                   help="List available experiments and exit.")
    p.add_argument("--port", default=None,
                   help="Arduino serial port (e.g. COM3 or /dev/tty.usbmodem1101). "
                        "Omit to run terminal-only.")
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    p.add_argument("--fig1", default="fig1.png", help="Horizontal figure image.")
    p.add_argument("--fig2", default="fig2.png", help="Vertical figure image.")
    p.add_argument("--fig3", default="fig3.png", help="Choice-highlight overlay image.")
    p.add_argument("--screen", type=int, default=0, help="Monitor index for fullscreen.")
    p.add_argument("--windowed", action="store_true", help="Windowed instead of fullscreen.")
    p.add_argument("--no-display", action="store_true", help="Run without the pygame screen.")
    p.add_argument("--highlight_ms", type=int, default=DEFAULT_HIGHLIGHT_MS,
                   help="How long the choice overlay stays up.")
    p.add_argument("--csv", default=None, help="CSV output path (default: session_<timestamp>.csv).")
    p.add_argument("--list-ports", action="store_true", help="List serial ports and exit.")
    args = p.parse_args()

    if args.list_experiments:
        if registry:
            print("Available experiments:")
            for name in choices:
                desc = _first_doc_line(registry[name])
                print(f"  {name:<24} {desc}")
        else:
            print("No experiments found in the experiments/ package.")
        return

    if args.list_ports:
        ports = turn_motor.available_ports()
        if ports:
            print("Serial ports:")
            for d in ports:
                print(f"  {d}")
        else:
            print("No serial ports detected (or pyserial not installed).")
        return

    if not registry:
        print("[error] no experiments found in experiments/ (need EXPERIMENT = <class>).")
        return
    if args.experiment not in registry:
        print(f"[error] unknown experiment '{args.experiment}'. "
              f"Available: {', '.join(choices)}")
        return
    experiment_cls = registry[args.experiment]

    # ---- Arduino link ------------------------------------------------------
    link = turn_motor(port=args.port, baud=args.baud)
    link.connect()                     # falls back to detached mode if no port

    # ---- Display -----------------------------------------------------------
    display = Display(fig1=args.fig1, fig2=args.fig2, fig3=args.fig3,
                      screen_index=args.screen, windowed=args.windowed,
                      highlight_ms=args.highlight_ms, enabled=not args.no_display)
    display.start()

    # ---- Experiment --------------------------------------------------------
    print(f"[info] running experiment: {args.experiment}")
    exp = experiment_cls(link, display, csv_path=args.csv)

    get_keys = _start_key_thread()

    try:
        while True:
            keys = get_keys()
            if exp.step(keys) == "QUIT":
                break
            if not display.update():   # ESC / window closed
                break
            time.sleep(0.005)
    except KeyboardInterrupt:
        print("\n[info] interrupted")
    finally:
        exp.close()
        display.close()
        link.close()
        trials = getattr(exp, "trial_num", "?")
        csv_path = getattr(exp, "csv_path", "?")
        print(f"\n  Stopped after {trials} trial(s). CSV: {csv_path}")


if __name__ == "__main__":
    main()
