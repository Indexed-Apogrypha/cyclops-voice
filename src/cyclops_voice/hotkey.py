from __future__ import annotations
import time
from .client import CyclopsClient
from .config import CyclopsConfig


def capture_selection(copy_fn, get_clip, set_clip, settle: float = 0.12) -> str:
    """Copy the current selection and return it, restoring prior clipboard."""
    prev = ""
    try:
        prev = get_clip()
    except Exception:
        prev = ""
    set_clip("")          # sentinel so we can tell if copy produced nothing
    copy_fn()             # simulate Ctrl+C
    time.sleep(settle)
    try:
        text = get_clip()
    except Exception:
        text = ""
    try:
        set_clip(prev)    # restore
    except Exception:
        pass
    return text.strip()


def _hk(combo: str) -> str:
    """Translate 'ctrl+alt+r' into pynput's '<ctrl>+<alt>+r' GlobalHotKeys syntax."""
    return "+".join("<" + p + ">" if p in ("ctrl", "alt", "shift", "cmd") else p
                    for p in combo.lower().split("+"))


class HotkeyManager:
    """Owns the global-hotkey listener and can re-bind it live when config changes.

    read_selection -> copy the current selection and speak it (existing behavior).
    stop           -> stop playback.
    pause_resume   -> toggle pause/resume based on the daemon's current state.
    """

    def __init__(self, cfg: CyclopsConfig, client: CyclopsClient | None = None):
        self.cfg = cfg
        self._client = client or CyclopsClient(
            base_url=f"http://{cfg.service.host}:{cfg.service.port}",
            token=cfg.service.auth_token)
        self._listener = None

    def _copy(self):
        from pynput import keyboard
        kb = keyboard.Controller()
        kb.press(keyboard.Key.ctrl); kb.press('c')
        kb.release('c'); kb.release(keyboard.Key.ctrl)

    def _on_read(self):
        import pyperclip
        text = capture_selection(self._copy, pyperclip.paste, pyperclip.copy)
        if text and self._client.is_up():
            try:
                self._client.speak(text, mode=self.cfg.behavior.read_dispatch)
            except Exception:
                pass

    def _on_stop(self):
        try:
            if self._client.is_up():
                self._client.stop()
        except Exception:
            pass

    def _on_pause_resume(self):
        try:
            if not self._client.is_up():
                return
            state = self._client.status().get("state")
            (self._client.resume if state == "paused" else self._client.pause)()
        except Exception:
            pass

    def start(self) -> None:
        from pynput import keyboard
        self._listener = keyboard.GlobalHotKeys({
            _hk(self.cfg.hotkeys.read_selection): self._on_read,
            _hk(self.cfg.hotkeys.stop): self._on_stop,
            _hk(self.cfg.hotkeys.pause_resume): self._on_pause_resume,
        })
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def apply(self, cfg: CyclopsConfig) -> None:
        self.cfg = cfg
        self.stop()
        self.start()


def start_hotkeys(cfg: CyclopsConfig) -> HotkeyManager:
    """Backwards-compatible helper: build, start, and return a HotkeyManager."""
    mgr = HotkeyManager(cfg)
    mgr.start()
    return mgr
