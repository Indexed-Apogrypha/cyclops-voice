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


def start_hotkeys(cfg: CyclopsConfig) -> None:
    import pyperclip
    from pynput import keyboard

    client = CyclopsClient(base_url=f"http://{cfg.service.host}:{cfg.service.port}",
                           token=cfg.service.auth_token)
    kb = keyboard.Controller()

    def _copy():
        kb.press(keyboard.Key.ctrl); kb.press('c')
        kb.release('c'); kb.release(keyboard.Key.ctrl)

    def on_read():
        text = capture_selection(_copy, pyperclip.paste, pyperclip.copy)
        if text and client.is_up():
            try:
                client.speak(text)
            except Exception:
                pass

    def on_stop():
        if client.is_up():
            try:
                client.stop()
            except Exception:
                pass

    def hk(combo: str) -> str:
        return "+".join("<" + p + ">" if p in ("ctrl", "alt", "shift", "cmd") else p
                        for p in combo.lower().split("+"))

    listener = keyboard.GlobalHotKeys({
        hk(cfg.hotkeys.read_selection): on_read,
        hk(cfg.hotkeys.stop): on_stop,
    })
    listener.daemon = True
    listener.start()
