# tests/test_mcp.py
from cyclops_voice import mcp_server

class FakeClient:
    def __init__(self): self.calls = []
    def is_up(self): return True
    def speak(self, text, preset=None, mode="interrupt"):
        self.calls.append(("speak", text, preset)); return {"job_id": "j", "state": "speaking"}
    def stop(self): self.calls.append(("stop",)); return {"state": "idle"}
    def status(self): return {"state": "idle", "current_text": None, "queue_len": 0, "preset": "game-accurate"}

def test_speak_tool():
    fc = FakeClient()
    out = mcp_server.do_speak(fc, "Hull breach detected.", None)
    assert "speaking" in out.lower() or "j" in out
    assert fc.calls[0] == ("speak", "Hull breach detected.", None)

def test_speak_tool_daemon_down():
    class Down(FakeClient):
        def is_up(self): return False
    out = mcp_server.do_speak(Down(), "hi", None)
    assert "not running" in out.lower()
