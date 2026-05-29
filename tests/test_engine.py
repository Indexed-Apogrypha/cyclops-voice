# tests/test_engine.py
import numpy as np
from cyclops_voice.engine import SpeechEngine
from cyclops_voice.config import CyclopsConfig, PRESETS

class FakeTTS:
    sample_rate = 22050
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
