from __future__ import annotations
from typing import Literal
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1)
    preset: str | None = None
    mode: Literal["interrupt", "enqueue"] = "interrupt"


class RenderRequest(BaseModel):
    text: str = Field(min_length=1)
    preset: str | None = None
    path: str | None = None


def create_app(engine, auth_token: str = "", version: str = "0.1.0",
               model: str = "", sample_rate: int = 0, runtime=None) -> FastAPI:
    app = FastAPI(title="Cyclops Voice")

    def _auth(token: str | None):
        if auth_token and token != auth_token:
            raise HTTPException(status_code=401, detail="invalid token")

    def _current_cfg():
        return runtime.config if runtime is not None else engine.config

    def _apply_cfg(cfg):
        (runtime.apply_config if runtime is not None else engine.apply_config)(cfg)

    @app.get("/health")
    def health():
        return {"ok": True, "version": version, "model": model, "sample_rate": sample_rate}

    @app.get("/status")
    def status():
        return engine.status()

    @app.get("/presets")
    def presets():
        from .config import all_presets
        return {"presets": sorted(all_presets()), "active": engine.status()["preset"]}

    @app.post("/speak")
    def speak(req: SpeakRequest, x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token)
        try:
            job_id = engine.speak(req.text, preset=req.preset, mode=req.mode)
        except KeyError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"job_id": job_id, **engine.status()}

    @app.post("/stop")
    def stop(x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token); engine.stop(); return engine.status()

    @app.post("/pause")
    def pause(x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token); engine.pause(); return engine.status()

    @app.post("/resume")
    def resume(x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token); engine.resume(); return engine.status()

    @app.post("/skip")
    def skip(x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token); engine.skip(); return engine.status()

    @app.post("/render")
    def render(req: RenderRequest, x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token)
        from .export import render_to_wav
        path = render_to_wav(engine, req.text, preset=req.preset, path=req.path)
        return {"path": path}

    @app.get("/config")
    def get_config():
        from .config import to_dict
        return to_dict(_current_cfg())

    @app.post("/config")
    def set_config(body: dict, x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token)
        from .config import from_dict, to_dict, save_config
        cfg = from_dict(body)
        try:
            _apply_cfg(cfg)
        except KeyError as e:
            raise HTTPException(status_code=400, detail=str(e))
        save_config(cfg)
        return to_dict(cfg)

    @app.get("/audio/devices")
    def audio_devices():
        from .player import list_output_devices
        return {"devices": list_output_devices()}

    @app.post("/autostart")
    def autostart(body: dict, x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token)
        from .autostart import set_enabled
        return {"enabled": set_enabled(bool(body.get("enabled")))}

    # Settings GUI: static page served at /ui/ (pywebview / browser points here).
    try:
        from importlib.resources import files
        from fastapi.staticfiles import StaticFiles
        web_dir = files("cyclops_voice") / "web"
        if web_dir.is_dir():
            app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="ui")
    except Exception:
        pass

    return app
