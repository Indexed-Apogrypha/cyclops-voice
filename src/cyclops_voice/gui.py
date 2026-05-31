"""Native settings window (pywebview) that loads the daemon-served settings page.

Runs as its own process (`cyclops gui`, or the tray's "Settings…" item) because both
pywebview and the system tray want the main thread. The window just points at the
daemon's /ui/ page and live-applies edits through the HTTP API; if the daemon isn't
running yet, we start it and wait for /health.
"""
from __future__ import annotations
import subprocess
import sys
import time

from .client import CyclopsClient
from .config import CyclopsConfig, load_config


def _client(cfg: CyclopsConfig) -> CyclopsClient:
    return CyclopsClient(base_url=f"http://{cfg.service.host}:{cfg.service.port}",
                         token=cfg.service.auth_token)


def ensure_daemon(cfg: CyclopsConfig, timeout: float = 25.0) -> bool:
    """Return True once the daemon answers /health, starting it if needed."""
    client = _client(cfg)
    if client.is_up():
        return True
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "daemon"]
    else:
        cmd = [sys.executable, "-m", "cyclops_voice.cli", "daemon"]
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(cmd, creationflags=flags)
    except Exception:
        return client.is_up()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.is_up():
            return True
        time.sleep(0.5)
    return client.is_up()


def run_gui(cfg: CyclopsConfig | None = None) -> int:
    cfg = cfg or load_config()
    import webview
    if not ensure_daemon(cfg):
        print("Cyclops daemon did not start; cannot open settings.", file=sys.stderr)
        return 1
    url = f"http://{cfg.service.host}:{cfg.service.port}/ui/"
    webview.create_window("Cyclops Voice — Settings", url=url, width=720, height=760,
                          min_size=(560, 560))
    webview.start()
    return 0
