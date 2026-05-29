# tests/test_client.py
import json
import httpx
from cyclops_voice.client import CyclopsClient


def test_speak_posts_text():
    def handler(request):
        assert request.url.path == "/speak"
        body = json.loads(request.content)
        assert body["text"] == "hello"
        return httpx.Response(200, json={"job_id": "j1", "state": "speaking",
                                         "current_text": "hello", "queue_len": 0,
                                         "preset": "game-accurate"})
    transport = httpx.MockTransport(handler)
    c = CyclopsClient(base_url="http://127.0.0.1:7788", transport=transport)
    out = c.speak("hello")
    assert out["job_id"] == "j1"


def test_health_false_when_unreachable():
    def handler(request):
        raise httpx.ConnectError("no daemon")
    transport = httpx.MockTransport(handler)
    c = CyclopsClient(base_url="http://127.0.0.1:7788", transport=transport)
    assert c.is_up() is False
