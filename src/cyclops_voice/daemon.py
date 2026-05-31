from __future__ import annotations
import socket
import threading
from pathlib import Path
import uvicorn
from . import __version__
from .config import load_config, CyclopsConfig
from .tts import PiperTTS
from .engine import SpeechEngine
from .server import create_app


def _reserve_port(host: str, port: int) -> socket.socket | None:
    """Bind host:port exclusively as a single-instance guard, before the slow
    model load. Returns the bound socket (handed to uvicorn via run(sockets=[..]))
    or None if another daemon already owns the port. No SO_REUSEADDR — a second
    bind must fail so a concurrent starter exits instead of racing."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        return None
    return sock


def build_engine(cfg: CyclopsConfig) -> SpeechEngine:
    if not Path(cfg.voice.model_path).exists():
        from .model_download import ensure_model
        print(f"Voice model not found; downloading to {cfg.voice.model_path} ...")
        ensure_model(cfg.voice.model_path)
    tts = PiperTTS(cfg.voice.model_path, length_scale=cfg.voice.length_scale)
    return SpeechEngine(tts=tts, config=cfg)


class DaemonRuntime:
    """Holds the live daemon surfaces and fans config changes out to all of them.

    The FastAPI app calls apply_config() (POST /config) to live-apply GUI edits:
    voice/effects/volume/device via the engine, hotkey combos via the hotkey
    manager, and the read gesture via the mouse-trigger manager.
    """

    def __init__(self, cfg: CyclopsConfig, engine: SpeechEngine,
                 hotkeys=None, mouse=None):
        self.config = cfg
        self.engine = engine
        self.hotkeys = hotkeys
        self.mouse = mouse

    def apply_config(self, new_cfg: CyclopsConfig) -> None:
        self.engine.apply_config(new_cfg)
        if self.hotkeys is not None:
            self.hotkeys.apply(new_cfg)
        if self.mouse is not None:
            self.mouse.apply(new_cfg)
        self.config = new_cfg


def run_daemon(config_path: str | Path | None = None,
               enable_hotkey: bool = True, enable_tray: bool = True) -> None:
    cfg = load_config(config_path)
    # Single-instance guard: reserve the port before the slow model load so a
    # concurrent/rapid second launch exits cleanly instead of spawning a duplicate.
    sock = _reserve_port(cfg.service.host, cfg.service.port)
    if sock is None:
        print(f"Cyclops daemon already running at "
              f"{cfg.service.host}:{cfg.service.port}; exiting.")
        return
    engine = build_engine(cfg)
    if Path("tuning").is_dir():
        from .config import load_tuning_candidates
        load_tuning_candidates(Path("tuning"))

    hotkeys = mouse = None
    if enable_hotkey:
        from .hotkey import HotkeyManager
        hotkeys = HotkeyManager(cfg)
        hotkeys.start()
        # Always create the mouse trigger (start() no-ops when trigger == "off") so
        # the GUI can enable/disable the read gesture live via apply().
        from .mouse_trigger import MouseTriggerManager
        mouse = MouseTriggerManager(cfg)
        mouse.start()

    runtime = DaemonRuntime(cfg, engine, hotkeys=hotkeys, mouse=mouse)
    app = create_app(
        engine, auth_token=cfg.service.auth_token, version=__version__,
        model=cfg.voice.model_path, sample_rate=engine.sample_rate, runtime=runtime,
    )

    server = uvicorn.Server(uvicorn.Config(
        app, host=cfg.service.host, port=cfg.service.port, log_level="warning"))

    # Serve on the pre-reserved socket (binding already done by _reserve_port).
    if enable_tray:
        from .tray import run_tray  # tray needs main thread; uvicorn -> worker thread
        t = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        t.start()
        run_tray(cfg)          # blocks on main thread until quit
        server.should_exit = True
    else:
        server.run(sockets=[sock])


if __name__ == "__main__":
    run_daemon()
