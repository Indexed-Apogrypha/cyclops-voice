"""
Texture stage: the grain/rasp + PA/intercom coloration the Gemini judge flags as
the consistent residual gap (timbre & synthetic-character categories).

Two tools, both composable around the existing DSP chain:

  add_rasp(mono)   -- band-limited noise GATED by the voice amplitude envelope, so
                      grain appears only during phonation (authentic rasp, not hiss).
                      Runs on Piper mono PCM, after pitch-quantize, before apply_dsp.

  presence_eq(stereo) -- a midrange presence peak applied post-DSP for the
                      PA/intercom "forward" quality.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter, sosfilt
from pedalboard import Pedalboard, PeakFilter


def _envelope(x: np.ndarray, sr: int, smooth_hz: float = 50.0) -> np.ndarray:
    """Smoothed amplitude envelope, normalized to [0,1]."""
    b, a = butter(1, smooth_hz / (sr / 2), btype="low")
    env = lfilter(b, a, np.abs(x))
    peak = float(env.max())
    return env / peak if peak > 1e-9 else env


def add_rasp(
    mono: np.ndarray,
    sr: int,
    *,
    amount: float = 0.1,
    band_hz: tuple[float, float] = (1200.0, 3200.0),
    env_smooth_hz: float = 50.0,
    env_exp: float = 1.5,
    seed: int = 0,
) -> np.ndarray:
    """Add envelope-gated band-limited noise grain to mono PCM.

    amount  : grain level relative to peak (0.05-0.18 useful range).
    band_hz : where the rasp lives (upper-mid, just under the lowpass).
    env_exp : >1 concentrates grain on loud (voiced) frames, keeps gaps clean.
    """
    x = np.asarray(mono, dtype=np.float64).reshape(-1)
    if x.size == 0 or amount <= 0:
        return x.astype(np.float32)

    env = _envelope(x, sr, env_smooth_hz)
    noise = np.random.default_rng(seed).standard_normal(x.size)
    sos = butter(4, [band_hz[0] / (sr / 2), band_hz[1] / (sr / 2)],
                 btype="band", output="sos")
    noise = sosfilt(sos, noise)
    npk = float(np.max(np.abs(noise)))
    if npk > 1e-9:
        noise /= npk

    out = x + noise * np.power(env, env_exp) * amount
    pk = float(np.max(np.abs(out)))
    if pk > 0.999:
        out = out / pk * 0.97
    return out.astype(np.float32)


def presence_eq(
    stereo: np.ndarray,
    sr: int,
    *,
    freq_hz: float = 2200.0,
    gain_db: float = 4.0,
    q: float = 1.0,
) -> np.ndarray:
    """Apply a midrange presence peak to stereo (N,2) PCM for PA/intercom forwardness."""
    if abs(gain_db) < 1e-6:
        return stereo
    board = Pedalboard([PeakFilter(cutoff_frequency_hz=freq_hz, gain_db=gain_db, q=q)])
    processed = board(stereo.T, sr)  # pedalboard wants (channels, samples)
    out = np.ascontiguousarray(processed.T, dtype=np.float32)
    pk = float(np.max(np.abs(out))) if out.size else 0.0
    if pk > 0.99:
        out = (out / pk * 0.97).astype(np.float32)
    return out
