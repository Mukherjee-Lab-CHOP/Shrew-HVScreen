"""Experiment package.

Each module here that defines a module-level ``EXPERIMENT = <class>`` becomes
selectable from run.py via ``--experiment <module_name>``. The class must accept
``(link, display, csv_path=None, verbose=True)`` and provide:

    step(keys: list[str]) -> "QUIT" | None     # advance one tick
    close()                                     # flush/close CSV etc.
    trial_num: int                              # completed-trial counter
    csv_path: str                               # where data was logged
"""
