"""
Local acoustic proxy scorer.

Computes objective metrics anchored to the measured Cyclops reference profile
(from docs/superpowers/specs/2026-05-29-cyclops-voice-tts-design.md §2.2):
  - Band 100-300 Hz fraction  target >= 0.40  (ideal 0.45-0.52)
  - Centroid                  target 400-550 Hz
  - Band 3.4-8 kHz fraction   target < 0.03
  - Band >8 kHz fraction      target < 0.005
  - Reverb RT60               target 0.0 (tail unmeasurable in dense speech) OR 0.5-1.1 s
  - L/R correlation           target < 0.85
  - Words-per-second cadence  target 2.0-2.8 wps (0.85-1.0x conversational ~2.8 wps)

proxy_score() returns a dict with per-metric pass/fail and a 0-100 composite.
The composite is NOT a rubric score -- it is a cheap gate to avoid wasting Gemini calls
on candidates that already fail the measurable acoustics targets.
"""
from __future__ import annotations
import re
import numpy as np
import wave
from pathlib import Path

# ---------------------------------------------------------------------------
# low-level measurements (shared with tests/acoustics.py but duplicated here
# so tuning/ is a standalone CLI with no dependency on the tests package)
# ---------------------------------------------------------------------------

def _to_mono(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1) if x.ndim == 2 else x


def _welch(x: np.ndarray, sr: int):
    from scipy.signal import welch
    m = _to_mono(x)
    return welch(m, fs=sr, nperseg=min(8192, len(m)))


def band_fraction(x: np.ndarray, sr: int, lo: float, hi: float) -> float:
    f, p = _welch(x, sr)
    df = f[1] - f[0]
    total = float(np.sum(p) * df) + 1e-15
    sel = (f >= lo) & (f < hi)
    return float(np.sum(p[sel]) * df) / total


def spectral_centroid(x: np.ndarray, sr: int) -> float:
    f, p = _welch(x, sr)
    return float(np.sum(f * p) / (np.sum(p) + 1e-15))


def lr_correlation(stereo: np.ndarray) -> float:
    assert stereo.ndim == 2 and stereo.shape[1] == 2
    return float(np.corrcoef(stereo[:, 0], stereo[:, 1])[0, 1])


def reverb_rt60(stereo: np.ndarray, sr: int) -> float:
    m = np.abs(_to_mono(stereo))
    fl = int(0.02 * sr)
    env = np.sqrt(np.convolve(m**2, np.ones(fl) / fl, "same") + 1e-15)
    edb = 20 * np.log10(env / env.max() + 1e-12)
    end = len(edb) - 1
    start = end
    while start > 0 and edb[start] < -15:
        start -= 1
    seg = edb[start:end]
    if len(seg) < int(0.05 * sr):
        return 0.0
    t = np.arange(len(seg)) / sr
    slope = np.polyfit(t, seg, 1)[0]
    return float(-60.0 / slope) if slope < -1 else 0.0


def estimate_f0_median(x: np.ndarray, sr: int) -> float:
    """Rough F0 median via autocorrelation on voiced frames."""
    m = _to_mono(x).astype(np.float64)
    frame = int(0.025 * sr)
    hop = int(0.010 * sr)
    f0s = []
    for i in range(0, len(m) - frame, hop):
        seg = m[i:i + frame]
        seg -= seg.mean()
        if np.sqrt(np.mean(seg**2)) < 1e-4:
            continue
        # autocorrelation via FFT
        n = 2 * len(seg)
        F = np.fft.rfft(seg, n=n)
        ac = np.fft.irfft(F * F.conj()).real[:len(seg)]
        ac /= ac[0] + 1e-15
        lo, hi = int(sr / 400), int(sr / 60)  # 60-400 Hz
        if lo >= hi or hi >= len(ac):
            continue
        idx = np.argmax(ac[lo:hi]) + lo
        if ac[idx] > 0.3:
            f0s.append(sr / idx)
    return float(np.median(f0s)) if f0s else 0.0


def words_per_second(audio: np.ndarray, sr: int, text: str) -> float:
    """Estimate wps from word count and audio duration."""
    words = len(re.findall(r"\S+", text))
    duration = len(_to_mono(audio)) / sr
    return words / duration if duration > 0 else 0.0


# ---------------------------------------------------------------------------
# WAV I/O
# ---------------------------------------------------------------------------

def load_wav(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n_ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n_ch == 2:
        pcm = pcm.reshape(-1, 2)
    return pcm, sr


# ---------------------------------------------------------------------------
# composite proxy scorer
# ---------------------------------------------------------------------------

def proxy_score(wav_path: str | Path, text: str = "") -> dict:
    audio, sr = load_wav(wav_path)

    lm = band_fraction(audio, sr, 100, 300)
    hi1 = band_fraction(audio, sr, 3400, 8000)
    hi2 = band_fraction(audio, sr, 8000, sr // 2)
    cen = spectral_centroid(audio, sr)
    lr = lr_correlation(audio) if audio.ndim == 2 else 1.0
    rt = reverb_rt60(audio, sr)
    f0 = estimate_f0_median(audio, sr)
    wps = words_per_second(audio, sr, text) if text else None

    # per-metric pass/fail and partial scores (each 0-1)
    scores = {}

    # low-mid dominance (rubric: timbre identity, most measurable proxy)
    scores["lowmid_band"] = {
        "value": round(lm, 4),
        "target": ">=0.40 (ideal 0.45-0.52)",
        "pass": lm >= 0.40,
        "partial": min(1.0, lm / 0.40),
    }

    # centroid
    scores["centroid_hz"] = {
        "value": round(cen, 1),
        "target": "400-550 Hz",
        "pass": 400 <= cen <= 550,
        "partial": 1.0 if 400 <= cen <= 550 else max(0.0, 1.0 - abs(cen - 475) / 200),
    }

    # treble rolloff
    scores["treble_3k8k"] = {
        "value": round(hi1, 4),
        "target": "<0.03",
        "pass": hi1 < 0.03,
        "partial": min(1.0, max(0.0, 1.0 - (hi1 - 0.03) / 0.05)) if hi1 >= 0.03 else 1.0,
    }
    scores["treble_8k"] = {
        "value": round(hi2, 4),
        "target": "<0.005",
        "pass": hi2 < 0.005,
        "partial": 1.0 if hi2 < 0.005 else min(1.0, max(0.0, 1.0 - (hi2 - 0.005) / 0.01)),
    }

    # stereo width
    scores["lr_correlation"] = {
        "value": round(lr, 4),
        "target": "<0.85",
        "pass": lr < 0.85,
        "partial": min(1.0, max(0.0, (0.85 - lr) / 0.30 + 0.6)) if lr < 0.85 else max(0.0, 1.0 - (lr - 0.85) / 0.15),
    }

    # reverb (0.0 is "unmeasurable in dense speech" = acceptable)
    rt_pass = rt == 0.0 or 0.4 <= rt <= 1.2
    scores["reverb_rt60"] = {
        "value": round(rt, 3),
        "target": "0.0 (dense) or 0.4-1.2 s",
        "pass": rt_pass,
        "partial": 1.0 if rt_pass else max(0.0, 1.0 - abs(rt - 0.7) / 0.8),
    }

    # F0 (target ~110 Hz, adult male; penalize boyish >160 Hz)
    f0_pass = 80 <= f0 <= 155 if f0 > 0 else True
    scores["f0_median_hz"] = {
        "value": round(f0, 1),
        "target": "80-155 Hz (adult male; ideal ~110 Hz)",
        "pass": f0_pass,
        "partial": 1.0 if f0_pass else max(0.0, 1.0 - (f0 - 155) / 50) if f0 > 155 else max(0.0, 1.0 - (80 - f0) / 30),
    }

    # cadence
    if wps is not None:
        wps_pass = 2.0 <= wps <= 3.2
        scores["words_per_sec"] = {
            "value": round(wps, 2),
            "target": "2.0-3.2 wps (deliberate pacing)",
            "pass": wps_pass,
            "partial": 1.0 if wps_pass else max(0.0, 1.0 - abs(wps - 2.6) / 1.5),
        }

    # composite: simple mean of partials, 0-100
    partials = [v["partial"] for v in scores.values()]
    composite = round(100 * sum(partials) / len(partials), 1)

    return {
        "wav": str(wav_path),
        "composite_proxy": composite,
        "metrics": scores,
    }


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 2:
        print("usage: proxy_score.py <file.wav> [text]")
        sys.exit(1)
    text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
    result = proxy_score(sys.argv[1], text)
    print(json.dumps(result, indent=2))
