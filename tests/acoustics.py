# tests/acoustics.py — reusable acoustic measurements (mirrors the reference-profiling script)
import numpy as np
from scipy.signal import welch


def to_mono(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1) if x.ndim == 2 else x


def band_fraction(x: np.ndarray, sr: int, lo: float, hi: float) -> float:
    m = to_mono(x)
    f, p = welch(m, fs=sr, nperseg=min(8192, len(m)))
    df = f[1] - f[0]
    total = float(np.sum(p) * df) + 1e-15
    sel = (f >= lo) & (f < hi)
    return float(np.sum(p[sel]) * df) / total


def spectral_centroid(x: np.ndarray, sr: int) -> float:
    m = to_mono(x)
    f, p = welch(m, fs=sr, nperseg=min(8192, len(m)))
    return float(np.sum(f * p) / (np.sum(p) + 1e-15))


def lr_correlation(stereo: np.ndarray) -> float:
    assert stereo.ndim == 2 and stereo.shape[1] == 2
    return float(np.corrcoef(stereo[:, 0], stereo[:, 1])[0, 1])


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(to_mono(x))) + 1e-15))


def reverb_rt60(stereo: np.ndarray, sr: int) -> float:
    """Crude Schroeder decay estimate on the trailing tail."""
    m = np.abs(to_mono(stereo))
    fl = int(0.02 * sr)
    env = np.sqrt(np.convolve(m**2, np.ones(fl) / fl, "same") + 1e-15)
    edb = 20 * np.log10(env / env.max() + 1e-12)
    end = len(edb) - 1
    start = end
    while start > 0 and edb[start] < -15:  # walk back into the tail
        start -= 1
    seg = edb[start:end]
    if len(seg) < int(0.05 * sr):
        return 0.0
    t = np.arange(len(seg)) / sr
    slope = np.polyfit(t, seg, 1)[0]
    return float(-60.0 / slope) if slope < -1 else 0.0
