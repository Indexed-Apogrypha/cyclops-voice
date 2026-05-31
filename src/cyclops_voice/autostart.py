"""Enable/disable launching the daemon on Windows login via a Startup-folder shortcut.

Shared by the CLI (`install-autostart`) and the GUI's 'Launch on login' toggle.
Source checkouts launch `pythonw -m cyclops_voice.cli daemon`; a frozen exe relaunches
itself with the `daemon` argument.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

from .paths import is_frozen

_LNK_NAME = "CyclopsVoice.lnk"


def _startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"


def _shortcut_path() -> Path:
    return _startup_dir() / _LNK_NAME


def is_enabled() -> bool:
    return _shortcut_path().exists()


def _launch_target() -> tuple[str, str, str]:
    """Return (target_path, arguments, working_dir) for the shortcut."""
    if is_frozen():
        return str(Path(sys.executable)), "daemon", str(Path(sys.executable).parent)
    venv = Path(sys.prefix)
    pythonw = venv / "Scripts" / "pythonw.exe"
    target = pythonw if pythonw.exists() else Path(sys.executable)
    return str(target), "-m cyclops_voice.cli daemon", str(Path.cwd())


def enable() -> Path:
    startup = _startup_dir()
    startup.mkdir(parents=True, exist_ok=True)
    target, args, workdir = _launch_target()
    lnk = _shortcut_path()
    ps = f'''
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{lnk}")
$s.TargetPath = "{target}"
$s.Arguments = "{args}"
$s.WorkingDirectory = "{workdir}"
$s.WindowStyle = 7
$s.Save()
'''
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return lnk


def disable() -> None:
    lnk = _shortcut_path()
    if lnk.exists():
        lnk.unlink()


def set_enabled(enabled: bool) -> bool:
    if enabled:
        enable()
    else:
        disable()
    return is_enabled()
