"""Create a Startup-folder shortcut that launches the daemon on login.

Thin CLI wrapper around cyclops_voice.autostart (the single source of truth, also
used by the GUI's 'Launch on login' toggle)."""
from __future__ import annotations

from cyclops_voice.autostart import enable


def main() -> int:
    lnk = enable()
    print(f"created {lnk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
