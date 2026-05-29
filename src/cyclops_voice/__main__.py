"""Frozen/`python -m cyclops_voice` entry point.

`multiprocessing.freeze_support()` must run first in a frozen build. When frozen
and double-clicked with no subcommand, default to running the daemon (tray +
hotkey + HTTP API) -- the only sane default for a shareable background app.
"""
from __future__ import annotations

import multiprocessing
import sys

from .cli import main
from .paths import is_frozen


def entry() -> int:
    multiprocessing.freeze_support()
    argv = sys.argv[1:]
    if is_frozen() and not argv:
        argv = ["daemon"]
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(entry())
