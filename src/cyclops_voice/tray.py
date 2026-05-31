from __future__ import annotations
import subprocess
import sys
from .client import CyclopsClient
from .config import CyclopsConfig


def _icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), (10, 30, 40))
    d = ImageDraw.Draw(img)
    d.ellipse((12, 12, 52, 52), outline=(0, 200, 255), width=4)
    d.ellipse((26, 26, 38, 38), fill=(0, 200, 255))  # "cyclops eye"
    return img


def run_tray(cfg: CyclopsConfig) -> None:
    import pystray
    client = CyclopsClient(base_url=f"http://{cfg.service.host}:{cfg.service.port}",
                           token=cfg.service.auth_token)

    def _safe(fn):
        def w(icon, item):
            try: fn()
            except Exception: pass
        return w

    def _open_settings():
        # GUI runs in its own process (pywebview wants the main thread, which the tray owns).
        cmd = [sys.executable, "gui"] if getattr(sys, "frozen", False) \
            else [sys.executable, "-m", "cyclops_voice.cli", "gui"]
        try:
            subprocess.Popen(cmd, creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        except Exception:
            pass

    icon = pystray.Icon(
        "cyclops", _icon_image(), "Cyclops Voice",
        menu=pystray.Menu(
            pystray.MenuItem("Settings…", _safe(_open_settings), default=True),
            pystray.MenuItem("Stop", _safe(client.stop)),
            pystray.MenuItem("Pause", _safe(client.pause)),
            pystray.MenuItem("Resume", _safe(client.resume)),
            pystray.MenuItem("Quit", lambda icon, item: icon.stop()),
        ),
    )
    icon.run()  # blocks until Quit
