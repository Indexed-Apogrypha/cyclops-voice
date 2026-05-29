"""Build the one-file CyclopsVoice.exe via PyInstaller.

Usage (from repo root, in the venv):
    python scripts/build_exe.py [--clean]

Wraps PyInstaller so the build is a single, CI-friendly command. Output:
dist/CyclopsVoice.exe (one-file, console-enabled). The voice model is downloaded
on first run, not embedded.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "CyclopsVoice.spec"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        print("PyInstaller not installed. Run: pip install -e \".[build]\"",
              file=sys.stderr)
        return 1

    if not SPEC.exists():
        print(f"Spec not found: {SPEC}", file=sys.stderr)
        return 1

    args = [str(SPEC), "--noconfirm"]
    if "--clean" in argv:
        args.append("--clean")

    print(f"Building from {SPEC} ...")
    pyi.run(args)
    exe = ROOT / "dist" / ("CyclopsVoice.exe" if sys.platform == "win32" else "CyclopsVoice")
    print(f"\nDone. Expected output: {exe}")
    print(f"  exists: {exe.exists()}"
          + (f"  ({exe.stat().st_size // (1024*1024)} MB)" if exe.exists() else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
