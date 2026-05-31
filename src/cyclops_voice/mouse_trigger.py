"""Double-right-click (or modifier+right-click) to read the text under the cursor.

Two pieces:
  - GestureDetector: pure state machine deciding when a right-button press fires the
    read gesture. Clock/state are passed in, so it's fully unit-testable with no mouse.
  - MouseTriggerManager: wires the detector to a pynput mouse listener, a keyboard
    modifier tracker, the UIA text extractor, and the HTTP client. Re-bindable via apply().

On trigger: grab the sentence/paragraph at the cursor (UIA), guard length, speak it,
and (default) send Esc to dismiss the context menu that a right-click pops.
"""
from __future__ import annotations
import time

from .client import CyclopsClient
from .config import CyclopsConfig
from .text_under_cursor import make_text_under_cursor


class GestureDetector:
    """Decides, per right-button press, whether the read gesture has fired."""

    def __init__(self, cfg: CyclopsConfig, interval: float = 0.4):
        self.trigger = cfg.read.trigger        # double_rmb | modifier_rmb | off
        self.modifier = cfg.read.modifier
        self.interval = interval
        self._last_press_t: float | None = None

    def feed_right_press(self, t: float, modifier_held: bool) -> bool:
        if self.trigger == "off":
            return False
        if self.trigger == "modifier_rmb":
            return bool(modifier_held)
        # double_rmb: two presses within `interval`.
        last, self._last_press_t = self._last_press_t, t
        if last is not None and (t - last) <= self.interval:
            self._last_press_t = None  # consume so a third click doesn't re-fire
            return True
        return False


class MouseTriggerManager:
    def __init__(self, cfg: CyclopsConfig, extractor=None, client: CyclopsClient | None = None,
                 clock=None, send_esc=None, interval: float = 0.4):
        self.cfg = cfg
        self._extractor = extractor if extractor is not None else make_text_under_cursor()
        self._client = client or CyclopsClient(
            base_url=f"http://{cfg.service.host}:{cfg.service.port}",
            token=cfg.service.auth_token)
        self._clock = clock or time.monotonic
        self._send_esc = send_esc  # injectable; defaults to a pynput Esc tap
        self._interval = interval
        self._detector = GestureDetector(cfg, interval)
        self._modifier_held = False
        self._mouse_listener = None
        self._kbd_listener = None

    # --- core (unit-testable; no real mouse needed) ---------------------------
    def handle_right_press(self, x: int, y: int, t: float | None = None,
                           modifier_held: bool | None = None) -> None:
        t = self._clock() if t is None else t
        if modifier_held is None:
            mh = True if self.cfg.read.modifier == "none" else self._modifier_held
        else:
            mh = modifier_held
        if self._detector.feed_right_press(t, mh):
            self._do_read(x, y)

    def _do_read(self, x: int, y: int) -> None:
        text = None
        try:
            text = self._extractor.get_text_at(x, y, self.cfg.read.mode)
        except Exception:
            text = None
        mc = self.cfg.read.max_chars
        if text and not (mc and len(text) > mc):
            try:
                if self._client.is_up():
                    self._client.speak(text, mode=self.cfg.behavior.read_dispatch)
            except Exception:
                pass
        self._dismiss_menu()

    def _dismiss_menu(self) -> None:
        if not self.cfg.read.auto_dismiss_menu:
            return
        try:
            (self._send_esc or self._default_send_esc)()
        except Exception:
            pass

    @staticmethod
    def _default_send_esc() -> None:
        from pynput import keyboard
        kb = keyboard.Controller()
        kb.press(keyboard.Key.esc); kb.release(keyboard.Key.esc)

    # --- live listeners -------------------------------------------------------
    def start(self) -> None:
        if self.cfg.read.trigger == "off":
            return
        from pynput import mouse, keyboard

        def on_click(x, y, button, pressed):
            if pressed and button == mouse.Button.right:
                self.handle_right_press(x, y)

        mods = {"ctrl": (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl),
                "alt": (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt),
                "shift": (keyboard.Key.shift_l, keyboard.Key.shift_r, keyboard.Key.shift)}
        watch = mods.get(self.cfg.read.modifier, ())

        def on_press(key):
            if key in watch:
                self._modifier_held = True

        def on_release(key):
            if key in watch:
                self._modifier_held = False

        self._mouse_listener = mouse.Listener(on_click=on_click)
        self._mouse_listener.daemon = True
        self._mouse_listener.start()
        if self.cfg.read.trigger == "modifier_rmb" and self.cfg.read.modifier != "none":
            self._kbd_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._kbd_listener.daemon = True
            self._kbd_listener.start()

    def stop(self) -> None:
        for lst in (self._mouse_listener, self._kbd_listener):
            if lst is not None:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._mouse_listener = self._kbd_listener = None

    def apply(self, cfg: CyclopsConfig) -> None:
        self.cfg = cfg
        self._detector = GestureDetector(cfg, self._interval)
        self._modifier_held = False
        self.stop()
        self.start()
