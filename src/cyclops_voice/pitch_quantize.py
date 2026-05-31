"""
Hard pitch quantization via the WORLD vocoder (pyworld).

The "autotuned/robotic" Cyclops quality is about pitch MOVEMENT: per-frame F0
snapped to the nearest chromatic semitone with no glide/portamento and vibrato
killed. WORLD lets us do this losslessly on the mono PCM:

    harvest (F0) -> stonemask (refine) -> cheaptrick (spectral env) -> d4c (aperiodicity)
    -> snap F0 to 12-TET grid (+ optional formant warp) -> synthesize

Runs on the raw Piper mono PCM, BEFORE the Cyclops DSP chain.
"""
from __future__ import annotations

import numpy as np

A4_HZ = 440.0
FRAME_PERIOD_MS = 5.0


def snap_f0_chromatic(f0: np.ndarray, strength: float = 1.0,
                      transpose_semitones: float = 0.0,
                      a4_hz: float = A4_HZ) -> np.ndarray:
    """Snap each voiced F0 frame to the nearest 12-TET semitone.

    transpose_semitones shifts the whole contour first (e.g. -2 to drop register),
    so snapping lands on grid notes in that register.
    strength=1.0 -> full snap (hard autotune). 0.0 -> no change; in between blends
    toward the grid in MIDI space. Unvoiced frames (f0<=0) pass through untouched.
    """
    f0 = np.asarray(f0, dtype=np.float64)
    out = f0.copy()
    voiced = f0 > 0
    if not np.any(voiced):
        return out
    midi = 69.0 + 12.0 * np.log2(f0[voiced] / a4_hz) + transpose_semitones
    snapped = np.round(midi)
    target = midi + strength * (snapped - midi)
    out[voiced] = a4_hz * np.power(2.0, (target - 69.0) / 12.0)
    return out


def shift_formants(sp: np.ndarray, alpha: float) -> np.ndarray:
    """Warp the spectral envelope along frequency to shift formants by factor alpha.

    alpha>1 moves formants UP. new_sp[f] = sp[f/alpha], per frame, linear interp.
    """
    if abs(alpha - 1.0) < 1e-6:
        return sp
    n_bins = sp.shape[1]
    src_idx = np.arange(n_bins, dtype=np.float64)
    sample_at = src_idx / alpha
    out = np.empty_like(sp)
    for i in range(sp.shape[0]):
        out[i] = np.interp(sample_at, src_idx, sp[i])
    np.maximum(out, 1e-16, out=out)  # envelope must stay positive for synthesis
    return out


def quantize_pitch(
    mono: np.ndarray,
    sample_rate: int,
    *,
    snap_strength: float = 1.0,
    transpose_semitones: float = 0.0,
    formant_alpha: float = 1.0,
    f0_floor: float = 71.0,
    f0_ceil: float = 500.0,
    frame_period: float = FRAME_PERIOD_MS,
) -> np.ndarray:
    """Hard-quantize the pitch of mono float PCM, returning mono float32.

    snap_strength       : 0..1 blend toward the chromatic grid (1.0 = full autotune step).
    transpose_semitones : shift register before snapping.
    formant_alpha       : spectral-envelope warp; 1.05-1.10 = subtle upward formant shift.
    """
    import pyworld as pw  # lazy: only imported when quantization is actually used

    x = np.ascontiguousarray(np.asarray(mono, dtype=np.float64).reshape(-1))
    if x.size == 0:
        return np.zeros(0, dtype=np.float32)

    f0, t = pw.harvest(x, sample_rate, f0_floor=f0_floor, f0_ceil=f0_ceil,
                       frame_period=frame_period)
    f0 = pw.stonemask(x, f0, t, sample_rate)
    sp = pw.cheaptrick(x, f0, t, sample_rate)
    ap = pw.d4c(x, f0, t, sample_rate)

    f0q = snap_f0_chromatic(f0, strength=snap_strength,
                            transpose_semitones=transpose_semitones)
    spq = shift_formants(sp, formant_alpha)

    y = pw.synthesize(f0q, spq, ap, sample_rate, frame_period=frame_period)
    y = np.asarray(y, dtype=np.float32)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0.999:
        y = (y / peak * 0.97).astype(np.float32)
    return y
