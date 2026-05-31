from cyclops_voice.config import CyclopsConfig
from cyclops_voice.mouse_trigger import GestureDetector, MouseTriggerManager


def _cfg(**read):
    c = CyclopsConfig()
    for k, v in read.items():
        setattr(c.read, k, v)
    return c


# --- GestureDetector (pure) --------------------------------------------------

def test_double_rmb_within_interval_fires():
    d = GestureDetector(_cfg(trigger="double_rmb"), interval=0.4)
    assert d.feed_right_press(t=1.00, modifier_held=False) is False
    assert d.feed_right_press(t=1.30, modifier_held=False) is True

def test_double_rmb_outside_interval_does_not_fire():
    d = GestureDetector(_cfg(trigger="double_rmb"), interval=0.4)
    assert d.feed_right_press(t=1.00, modifier_held=False) is False
    assert d.feed_right_press(t=1.80, modifier_held=False) is False

def test_double_rmb_consumes_so_triple_does_not_refire():
    d = GestureDetector(_cfg(trigger="double_rmb"), interval=0.4)
    d.feed_right_press(t=1.0, modifier_held=False)
    assert d.feed_right_press(t=1.2, modifier_held=False) is True
    assert d.feed_right_press(t=1.3, modifier_held=False) is False  # third click

def test_modifier_rmb_requires_modifier():
    d = GestureDetector(_cfg(trigger="modifier_rmb"), interval=0.4)
    assert d.feed_right_press(t=1.0, modifier_held=False) is False
    assert d.feed_right_press(t=2.0, modifier_held=True) is True

def test_off_never_fires():
    d = GestureDetector(_cfg(trigger="off"), interval=0.4)
    assert d.feed_right_press(t=1.0, modifier_held=True) is False
    assert d.feed_right_press(t=1.1, modifier_held=True) is False


# --- MouseTriggerManager read pipeline (injected fakes) ----------------------

class FakeExtractor:
    def __init__(self, text): self.text = text; self.calls = []
    def get_text_at(self, x, y, mode): self.calls.append((x, y, mode)); return self.text

class FakeClient:
    def __init__(self, up=True): self.up = up; self.spoken = []
    def is_up(self): return self.up
    def speak(self, text, mode="interrupt"): self.spoken.append((text, mode))

def _mgr(text, cfg=None, esc=None):
    cfg = cfg or _cfg(trigger="double_rmb")
    client = FakeClient()
    mgr = MouseTriggerManager(cfg, extractor=FakeExtractor(text), client=client,
                              clock=lambda: 0.0, send_esc=esc, interval=0.4)
    return mgr, client

def test_read_speaks_extracted_text_with_dispatch_mode():
    cfg = _cfg(trigger="double_rmb")
    cfg.behavior.read_dispatch = "enqueue"
    mgr, client = _mgr("Hello there.", cfg=cfg)
    mgr._do_read(10, 20)
    assert mgr._extractor.calls == [(10, 20, "paragraph")]
    assert client.spoken == [("Hello there.", "enqueue")]

def test_read_respects_max_chars_guard():
    cfg = _cfg(trigger="double_rmb", max_chars=5)
    mgr, client = _mgr("way too long to read", cfg=cfg)
    mgr._do_read(0, 0)
    assert client.spoken == []  # over the cap -> ignored

def test_read_no_text_does_not_speak():
    mgr, client = _mgr(None)
    mgr._do_read(0, 0)
    assert client.spoken == []

def test_auto_dismiss_sends_esc():
    sent = []
    cfg = _cfg(trigger="double_rmb", auto_dismiss_menu=True)
    mgr, client = _mgr("Hi.", cfg=cfg, esc=lambda: sent.append(True))
    mgr._do_read(0, 0)
    assert sent == [True] and client.spoken == [("Hi.", "interrupt")]

def test_no_dismiss_when_disabled():
    sent = []
    cfg = _cfg(trigger="double_rmb", auto_dismiss_menu=False)
    mgr, client = _mgr("Hi.", cfg=cfg, esc=lambda: sent.append(True))
    mgr._do_read(0, 0)
    assert sent == []

def test_start_is_noop_when_off():
    # trigger "off" returns before touching pynput, so it's safe to always construct.
    mgr, _ = _mgr("Hi.", cfg=_cfg(trigger="off"))
    mgr.start()  # must not raise / not create a listener
    assert mgr._mouse_listener is None

def test_modifier_none_fires_without_any_modifier_held():
    # trigger=modifier_rmb + modifier=none → any right-click fires (no key required)
    cfg = _cfg(trigger="modifier_rmb", modifier="none")
    mgr, client = _mgr("Hi.", cfg=cfg)
    mgr.handle_right_press(1, 1, t=1.0)  # no modifier_held passed
    assert client.spoken == [("Hi.", "interrupt")]

def test_handle_right_press_only_reads_on_second_click():
    sent = []
    cfg = _cfg(trigger="double_rmb")
    mgr, client = _mgr("Hi.", cfg=cfg, esc=lambda: sent.append(True))
    mgr.handle_right_press(1, 1, t=1.0)
    assert client.spoken == []          # first click: no read
    mgr.handle_right_press(1, 1, t=1.2)
    assert client.spoken == [("Hi.", "interrupt")]  # second within interval
