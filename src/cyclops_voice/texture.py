"""
Texture stage: grain/rasp + PA/intercom coloration.

  add_rasp(mono)      -- band-limited noise GATED by the voice amplitude envelope,
                         so grain appears only during phonation. Runs on mono PCM
                         after pitch-quantize, before the DSP board.
  presence_eq(stereo) -- midrange presence peak applied post-board for the
                         PA/intercom "forward" quality.

Implemented with numpy only (no scipy): a boxcar envelope follower and an FFT
band-limited noise generator. This keeps the frozen one-file exe free of scipy,
which fails to import under PyInstaller (scipy.stats _distn_infrastructure bug).
"""
from __future__ import annotations

import numpy as np


def _envelope(x: np.ndarray, sr: int, smooth_hz: float = 50.0) -> np.ndarray:
    """Normalized amplitude envelope via a centered boxcar moving average of |x|."""
    a = np.abs(x)
    win = max(1, int(round(sr / smooth_hz)))
    if win > 1 and a.size >= win:
        c = np.cumsum(np.insert(a, 0, 0.0))
        ma = (c[win:] - c[:-win]) / win          # length = a.size - win + 1
        pad_l = win // 2
        pad_r = a.size - ma.size - pad_l
        env = np.concatenate([
            np.full(pad_l, ma[0]),
            ma,
            np.full(max(0, pad_r), ma[-1]),
        ])[:a.size]
    else:
        env = a
    peak = float(env.max()) if env.size else 0.0
    return env / peak if peak > 1e-9 else env


def _bandlimited_noise(n: int, sr: int, lo: float, hi: float,
                       taper_hz: float = 150.0, seed: int = 0) -> np.ndarray:
    """White noise band-limited to [lo, hi] via an FFT mask with cosine edges."""
    noise = np.random.default_rng(seed).standard_normal(n)
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    mask = ((freqs >= lo) & (freqs <= hi)).astype(np.float64)
    if taper_hz > 0:  # raised-cosine ramps to suppress brick-wall ringing
        for edge, rising in ((lo, True), (hi, False)):
            band = (freqs >= edge - taper_hz) & (freqs <= edge + taper_hz)
            ramp = 0.5 * (1 - np.cos(np.pi * (freqs[band] - (edge - taper_hz)) / (2 * taper_hz)))
            mask[band] = ramp if rising else (1.0 - ramp)
    out = np.fft.irfft(spec * mask, n)
    pk = float(np.max(np.abs(out)))
    return out / pk if pk > 1e-9 else out


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
    noise = _bandlimited_noise(x.size, sr, band_hz[0], band_hz[1], seed=seed)

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
