# tests/test_server.py
from fastapi.testclient import TestClient
from cyclops_voice.server import create_app

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

def client(token=""):
    eng = FakeEngine()
    app = create_app(eng, auth_token=token, version="0.1.0", model="m.onnx", sample_rate=22050)
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
