"""Create a Startup-folder shortcut that launches the daemon with pythonw (no console)."""
from __future__ import annotations
import os
import sys
from pathlib import Path


def main() -> int:
    startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
    startup.mkdir(parents=True, exist_ok=True)
    venv = Path(sys.prefix)
    pythonw = venv / "Scripts" / "pythonw.exe"
    target = pythonw if pythonw.exists() else Path(sys.executable)
    workdir = Path.cwd()
    lnk = startup / "CyclopsVoice.lnk"

    ps = f'''
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{lnk}")
$s.TargetPath = "{target}"
$s.Arguments = "-m cyclops_voice.cli daemon"
$s.WorkingDirectory = "{workdir}"
$s.WindowStyle = 7
$s.Save()
'''
    import subprocess
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print(f"created {lnk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
