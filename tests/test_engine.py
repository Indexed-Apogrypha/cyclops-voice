# tests/test_engine.py
import numpy as np
from cyclops_voice.engine import SpeechEngine
from cyclops_voice.config import CyclopsConfig, PRESETS

class FakeTTS:
    sample_rate = 22050
    def __init__(self): self.length_scale = 1.22
    def set_length_scale(self, v): self.length_scale = v
    def synth(self, text):
        return (np.ones(2205, dtype=np.float32) * 0.01)

class RecordingSink:
    def __init__(self): self.frames = []
    def write(self, block): self.frames.append(block.copy())
    def close(self): pass

def make_engine():
    cfg = CyclopsConfig()
    sink = RecordingSink()
    eng = SpeechEngine(tts=FakeTTS(), config=cfg, sink=sink,
                       dsp_apply=lambda mono, sr, preset, pitch_semitones=0.0:
                           np.stack([mono, mono], axis=1))
    return eng, sink

def test_speak_returns_job_and_plays():
    eng, sink = make_engine()
    job = eng.speak("One sentence. Two sentence.")
    assert isinstance(job, str) and job
    eng.wait_idle(timeout=5)
    assert sum(len(f) for f in sink.frames) > 0
    assert eng.status()["state"] == "idle"

def test_status_shape():
    eng, _ = make_engine()
    s = eng.status()
    assert set(s) == {"state", "current_text", "queue_len", "preset"}

def test_unknown_preset_raises():
    eng, _ = make_engine()
    try:
        eng.speak("hi", preset="nope")
        assert False, "expected KeyError"
    except KeyError:
        pass

def _recording_engine():
    cfg = CyclopsConfig()
    sink = RecordingSink()
    seen = []
    def dsp(mono, sr, preset, pitch_semitones=0.0):
        seen.append(preset)
        return np.stack([mono, mono], axis=1)
    eng = SpeechEngine(tts=FakeTTS(), config=cfg, sink=sink, dsp_apply=dsp)
    return eng, sink, seen

def test_apply_config_updates_speed_and_effects():
    eng, sink, seen = _recording_engine()
    cfg = CyclopsConfig()
    cfg.voice.length_scale = 1.5
    cfg.voice.effects.reverb_wet = 0.5
    eng.apply_config(cfg)
    assert eng.tts.length_scale == 1.5
    eng.speak("Hello there."); eng.wait_idle(timeout=5)
    assert seen and seen[-1].reverb_wet == 0.5  # override reached the DSP

def test_apply_config_volume_changes_gain():
    eng, sink, _ = _recording_engine()
    cfg = CyclopsConfig(); cfg.audio.volume = 0.25
    eng.apply_config(cfg)
    eng.speak("Hi."); eng.wait_idle(timeout=5)
    assert sink.frames and np.allclose(sink.frames[0], 0.01 * 0.25)

def test_apply_config_bad_preset_is_atomic():
    eng, _, _ = _recording_engine()
    before_preset = eng.config.voice.preset
    bad = CyclopsConfig(); bad.voice.preset = "nope"; bad.voice.length_scale = 9.9
    try:
        eng.apply_config(bad)
        assert False, "expected KeyError"
    except KeyError:
        pass
    # nothing partially applied
    assert eng.config.voice.preset == before_preset
    assert eng.tts.length_scale != 9.9

def test_set_output_device_swaps_sink(monkeypatch):
    import cyclops_voice.engine as engmod
    class FakeDevSink:
        def __init__(self, sr, dev=None): self.dev = dev; self.frames = []; self.closed = False
        def write(self, b): self.frames.append(b.copy())
        def close(self): self.closed = True
    monkeypatch.setattr(engmod, "SoundDeviceSink", FakeDevSink)
    eng, sink, _ = _recording_engine()
    old = eng._sink
    eng.set_output_device("Speakers")
    assert isinstance(eng._sink, FakeDevSink) and eng._sink.dev == "Speakers"
    eng.speak("Hi."); eng.wait_idle(timeout=5)
    assert sum(len(f) for f in eng._sink.frames) > 0
