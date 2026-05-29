from __future__ import annotations
import httpx


class CyclopsClient:
    def __init__(self, base_url: str = "http://127.0.0.1:7788",
                 token: str = "", transport: httpx.BaseTransport | None = None,
                 timeout: float = 5.0):
        headers = {"X-Cyclops-Token": token} if token else {}
        self._c = httpx.Client(base_url=base_url, headers=headers,
                               transport=transport, timeout=timeout)

    def is_up(self) -> bool:
        try:
            return self._c.get("/health").json().get("ok", False)
        except httpx.HTTPError:
            return False

    def speak(self, text: str, preset: str | None = None,
              mode: str = "interrupt") -> dict:
        r = self._c.post("/speak", json={"text": text, "preset": preset, "mode": mode})
        r.raise_for_status(); return r.json()

    def _post(self, path: str) -> dict:
        r = self._c.post(path); r.raise_for_status(); return r.json()

    def stop(self): return self._post("/stop")
    def pause(self): return self._post("/pause")
    def resume(self): return self._post("/resume")
    def skip(self): return self._post("/skip")

    def status(self) -> dict:
        r = self._c.get("/status"); r.raise_for_status(); return r.json()

    def render(self, text: str, preset: str | None = None,
               path: str | None = None) -> dict:
        r = self._c.post("/render", json={"text": text, "preset": preset, "path": path})
        r.raise_for_status(); return r.json()
