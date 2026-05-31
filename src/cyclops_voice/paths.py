"""Single source of truth for where runtime files live.

Source checkouts keep using ./models and ./<config> relative to the working dir
(so the hermetic tests and the acoustic golden test are unchanged). A frozen,
double-clicked exe instead uses a per-user writable data dir, because its CWD is
unpredictable and its own directory may be read-only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "CyclopsVoice"
MODEL_FILENAME = "en_US-ryan-medium.onnx"


def is_frozen() -> bool:
    """True when running inside a PyInstaller (or similar) frozen bundle."""
    return bool(getattr(sys, "frozen", False))


def data_dir() -> Path:
    """Per-user writable data directory, created if missing."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        d = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _source_model() -> Path:
    return Path("models") / MODEL_FILENAME


def default_model_path() -> str:
    """Model path: prefer ./models (dev/source/tests), else the per-user data dir."""
    src = _source_model()
    if src.exists():
        return str(src)
    return str(data_dir() / "models" / MODEL_FILENAME)


def default_config_path() -> Path:
    """Per-user config file location (may not exist)."""
    return data_dir() / "config.toml"
