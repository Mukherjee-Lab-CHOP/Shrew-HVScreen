"""Discover experiments and their SPECs for the GUI.

Mirrors run.py's discovery, but also pulls each module's SPEC (variables +
state graph) so the GUI can build the variable editors and the node graph.
"""

import importlib
import os
import pkgutil
import sys

# Make the project root importable when the GUI is launched from anywhere.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import experiments  # noqa: E402


def discover():
    """Return {name: {"class": cls, "spec": dict, "module": module}}."""
    found = {}
    for mod in pkgutil.iter_modules(experiments.__path__):
        if mod.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"experiments.{mod.name}")
        except Exception as e:
            print(f"[gui] could not import experiments.{mod.name}: {e}", flush=True)
            continue
        cls = getattr(module, "EXPERIMENT", None)
        if cls is None:
            continue
        spec = getattr(module, "SPEC", None) or _fallback_spec(mod.name)
        found[mod.name] = {"class": cls, "spec": spec, "module": module}
    return found


def _fallback_spec(name):
    """Minimal SPEC for an experiment that doesn't define one."""
    return {"name": name, "title": name, "variables": [], "states": [], "transitions": []}
