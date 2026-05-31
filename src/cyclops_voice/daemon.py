from __future__ import annotations
import threading
from pathlib import Path
import uvicorn
from . import __version__
from .config import load_config, CyclopsConfig
from .tts import PiperTTS
from .engine import SpeechEngine
from .server import create_app


def build_engine(cfg: CyclopsConfig) -> SpeechEngine:
    if not Path(cfg.voice.model_path).exists():
        from .model_download import ensure_model
        print(f"Voice model not found; downloading to {cfg.voice.model_path} ...")
        ensure_model(cfg.voice.model_path)
    tts = PiperTTS(cfg.voice.model_path, length_scale=cfg.voice.length_scale)
    return SpeechEngine(tts=tts, config=cfg)


def run_daemon(config_path: str | Path | None = None,
               enable_hotkey: bool = True, enable_tray: bool = True) -> None:
    cfg = load_config(config_path)
    engine = build_engine(cfg)
    app = create_app(
        engine, auth_token=cfg.service.auth_token, version=__version__,
        model=cfg.voice.model_path, sample_rate=engine.sample_rate,
    )

    if enable_hotkey:
        from .hotkey import start_hotkeys
        start_hotkeys(cfg)  # runs its own listener thread

    server = uvicorn.Server(uvicorn.Config(
        app, host=cfg.service.host, port=cfg.service.port, log_level="warning"))

    if enable_tray:
        from .tray import run_tray  # tray needs main thread; uvicorn -> worker thread
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        run_tray(cfg)          # blocks on main thread until quit
        server.should_exit = True
    else:
        server.run()


if __name__ == "__main__":
    run_daemon()
