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
               model: str = "", sample_rate: int = 0) -> FastAPI:
    app = FastAPI(title="Cyclops Voice")

    def _auth(token: str | None):
        if auth_token and token != auth_token:
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/health")
    def health():
        return {"ok": True, "version": version, "model": model, "sample_rate": sample_rate}

    @app.get("/status")
    def status():
        return engine.status()

    @app.get("/presets")
    def presets():
        from .config import PRESETS
        return {"presets": sorted(PRESETS), "active": engine.status()["preset"]}

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

    return app
