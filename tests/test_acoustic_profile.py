# tests/test_acoustic_profile.py
import os
import numpy as np
import pytest
from cyclops_voice.config import VoiceConfig, PRESETS
from cyclops_voice.dsp import apply_dsp
from tests.acoustics import band_fraction, spectral_centroid, lr_correlation, reverb_rt60

MODEL = VoiceConfig().model_path

pytestmark = pytest.mark.skipif(
    not os.path.exists(MODEL),
    reason="voice model not installed; run scripts/install_voice_model.py",
)

def test_rendered_voice_matches_cyclops_envelope():
    from cyclops_voice.tts import PiperTTS
    tts = PiperTTS(MODEL, length_scale=1.15)
    mono = tts.synth("Welcome aboard, Captain. All systems online. Hull integrity stable.")
    out = apply_dsp(mono, tts.sample_rate, PRESETS["game-accurate"], pitch_semitones=-1.0)
    sr = tts.sample_rate

    assert band_fraction(out, sr, 100, 300) >= 0.30      # low-mid dominant (target 0.45-0.52)
    assert band_fraction(out, sr, 3400, 8000) < 0.05     # treble nearly gone
    assert band_fraction(out, sr, 8000, sr // 2) < 0.01  # treble dead
    assert 350 <= spectral_centroid(out, sr) <= 700      # dark timbre
    assert lr_correlation(out) < 0.9                     # stereo width
    rt = reverb_rt60(out, sr)
    assert 0.3 <= rt <= 1.5                              # medium room
