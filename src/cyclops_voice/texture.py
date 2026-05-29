"""
Texture stage: grain/rasp + PA/intercom coloration.

  add_rasp(mono)      -- band-limited noise GATED by the voice amplitude envelope,
                         so grain appears only during phonation. Runs on mono PCM
                         after pitch-quantize, before the DSP board.
  presence_eq(stereo) -- midrange presence peak applied post-board for the
                         PA/intercom "forward" quality.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter, sosfilt


def _envelope(x: np.ndarray, sr: int, smooth_hz: float = 50.0) -> np.ndarray:
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
    """Add envelope-gated band-limited noise grain to mono PCM (returns float32)."""
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
    """Apply a midrange presence peak to stereo (N,2) PCM (returns float32)."""
    if abs(gain_db) < 1e-6:
        return np.asarray(stereo, dtype=np.float32)
    from pedalboard import Pedalboard, PeakFilter  # local: keeps module import light
    board = Pedalboard([PeakFilter(cutoff_frequency_hz=freq_hz, gain_db=gain_db, q=q)])
    processed = board(np.asarray(stereo, dtype=np.float32).T, sr)
    out = np.ascontiguousarray(processed.T, dtype=np.float32)
    pk = float(np.max(np.abs(out))) if out.size else 0.0
    if pk > 0.99:
        out = (out / pk * 0.97).astype(np.float32)
    return out
