# tests/test_dsp.py
import numpy as np
from cyclops_voice.config import PRESETS
from cyclops_voice.dsp import apply_dsp
from tests.acoustics import rms, lr_correlation

SR = 22050

def _tone(freq, sr=SR, secs=1.0, amp=0.3):
    t = np.arange(int(sr * secs)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)

def test_output_is_stereo_float32():
    out = apply_dsp(_tone(200), SR, PRESETS["game-accurate"])
    assert out.ndim == 2 and out.shape[1] == 2
    assert out.dtype == np.float32

def test_lowpass_kills_treble():
    lo = apply_dsp(_tone(200), SR, PRESETS["game-accurate"])
    hi = apply_dsp(_tone(10000), SR, PRESETS["game-accurate"])
    atten_db = 20 * np.log10(rms(lo) / (rms(hi) + 1e-9))
    assert atten_db > 18  # 10 kHz strongly attenuated vs 200 Hz

def test_lowmid_boosted_relative_to_mids():
    low = apply_dsp(_tone(200), SR, PRESETS["game-accurate"])
    mid = apply_dsp(_tone(1000), SR, PRESETS["game-accurate"])
    boost_db = 20 * np.log10(rms(low) / (rms(mid) + 1e-9))
    assert boost_db > 2  # low-mids hotter than 1 kHz

def test_reverb_creates_stereo_width():
    rng = np.random.default_rng(0)
    noise = (0.2 * rng.standard_normal(SR)).astype(np.float32)
    out = apply_dsp(noise, SR, PRESETS["game-accurate"])
    assert lr_correlation(out) < 0.97  # decorrelated -> width present
