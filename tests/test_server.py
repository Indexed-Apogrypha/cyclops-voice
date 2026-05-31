# tests/test_server.py
from fastapi.testclient import TestClient
from cyclops_voice.server import create_app
from cyclops_voice.config import CyclopsConfig

class FakeEngine:
    def __init__(self): self.calls = []; self._state = "idle"
    def speak(self, text, preset=None, mode="interrupt"):
        self.calls.append(("speak", text, preset, mode)); self._state = "speaking"; return "job123"
    def stop(self): self._state = "idle"; self.calls.append(("stop",))
    def pause(self): self.calls.append(("pause",))
    def resume(self): self.calls.append(("resume",))
    def skip(self): self.calls.append(("skip",))
    def status(self):
        return {"state": self._state, "current_text": None, "queue_len": 0, "preset": "game-accurate"}

class FakeRuntime:
    def __init__(self): self.config = CyclopsConfig(); self.applied = []
    def apply_config(self, cfg): self.applied.append(cfg); self.config = cfg

def client(token="", runtime=None):
    eng = FakeEngine()
    app = create_app(eng, auth_token=token, version="0.1.0", model="m.onnx",
                     sample_rate=22050, runtime=runtime)
    return TestClient(app), eng

def test_health():
    c, _ = client()
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True

def test_speak():
    c, eng = client()
    r = c.post("/speak", json={"text": "hello"})
    assert r.status_code == 200 and r.json()["job_id"] == "job123"
    assert eng.calls[0] == ("speak", "hello", None, "interrupt")

def test_speak_requires_text():
    c, _ = client()
    assert c.post("/speak", json={}).status_code == 422

def test_stop_status():
    c, eng = client()
    assert c.post("/stop").status_code == 200
    assert c.get("/status").json()["state"] == "idle"

def test_auth_token_enforced():
    c, _ = client(token="secret")
    assert c.post("/speak", json={"text": "x"}).status_code == 401
    assert c.post("/speak", json={"text": "x"},
                  headers={"X-Cyclops-Token": "secret"}).status_code == 200

def test_get_config_returns_runtime_config():
    rt = FakeRuntime()
    c, _ = client(runtime=rt)
    body = c.get("/config").json()
    assert body["service"]["port"] == 7788
    assert body["read"]["mode"] == "paragraph"
    assert body["voice"]["effects"]["reverb_wet"] is None

def test_post_config_applies_and_saves(tmp_path, monkeypatch):
    import cyclops_voice.config as cfgmod
    monkeypatch.setattr(cfgmod, "default_config_path", lambda: tmp_path / "config.toml")
    rt = FakeRuntime()
    c, _ = client(runtime=rt)
    payload = {"voice": {"preset": "subtle", "length_scale": 1.4},
               "read": {"mode": "paragraph"}}
    r = c.post("/config", json=payload)
    assert r.status_code == 200
    assert rt.applied and rt.applied[-1].voice.preset == "subtle"
    assert rt.applied[-1].read.mode == "paragraph"
    assert (tmp_path / "config.toml").exists()  # persisted

def test_post_config_rejects_bad_preset():
    class RaisingRuntime(FakeRuntime):
        def apply_config(self, cfg):
            from cyclops_voice.config import build_effective_preset
            build_effective_preset(cfg)  # raises KeyError on unknown preset
    c, _ = client(runtime=RaisingRuntime())
    r = c.post("/config", json={"voice": {"preset": "nope"}})
    assert r.status_code == 400

def test_audio_devices_shape(monkeypatch):
    import cyclops_voice.player as pl
    monkeypatch.setattr(pl, "list_output_devices",
                        lambda: [{"index": 0, "name": "Speakers"}])
    c, _ = client()
    assert c.get("/audio/devices").json()["devices"][0]["name"] == "Speakers"

def test_settings_ui_served():
    c, _ = client()
    r = c.get("/ui/")
    assert r.status_code == 200 and "Cyclops Voice" in r.text
    assert c.get("/ui/app.js").status_code == 200
