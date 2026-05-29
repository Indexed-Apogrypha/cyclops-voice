from __future__ import annotations
import numpy as np
from pedalboard import (
    Pedalboard, HighpassFilter, LowpassFilter, PeakFilter,
    Compressor, Reverb, Chorus, Distortion, Gain, PitchShift, Bitcrush,
)
from .config import Preset


def to_stereo(mono: np.ndarray) -> np.ndarray:
    mono = np.asarray(mono, dtype=np.float32).reshape(-1)
    return np.stack([mono, mono], axis=1)  # (N, 2)


def build_board(preset: Preset, pitch_semitones: float = 0.0) -> Pedalboard:
    plugins = []
    if abs(pitch_semitones) > 1e-6:
        plugins.append(PitchShift(semitones=float(pitch_semitones)))
    plugins += [
        HighpassFilter(cutoff_frequency_hz=preset.highpass_hz),
        PeakFilter(cutoff_frequency_hz=preset.lowmid_freq_hz,
                   gain_db=preset.lowmid_gain_db, q=preset.lowmid_q),
        LowpassFilter(cutoff_frequency_hz=preset.lowpass_hz),
        Compressor(threshold_db=preset.comp_threshold_db, ratio=preset.comp_ratio,
                   attack_ms=15, release_ms=200),
    ]
    if preset.drive_db > 0:
        plugins.append(Distortion(drive_db=preset.drive_db))
    if preset.bitcrush_bit_depth > 0:
        plugins.append(Bitcrush(bit_depth=preset.bitcrush_bit_depth))
    if preset.chorus_mix > 0:
        plugins.append(Chorus(rate_hz=0.6, depth=0.25, centre_delay_ms=8.0,
                              feedback=0.0, mix=preset.chorus_mix))
    plugins += [
        Reverb(room_size=preset.reverb_room_size, damping=preset.reverb_damping,
               wet_level=preset.reverb_wet, dry_level=1.0 - preset.reverb_wet * 0.5,
               width=preset.reverb_width),
        Gain(gain_db=2.0),
    ]
    return Pedalboard(plugins)


def apply_dsp(mono: np.ndarray, sample_rate: int, preset: Preset,
              pitch_semitones: float = 0.0) -> np.ndarray:
    """Mono float32 -> stereo (N,2) float32 through the Cyclops chain."""
    stereo = to_stereo(mono)                      # (N, 2)
    board = build_board(preset, pitch_semitones)
    # pedalboard expects (num_channels, num_samples): transpose in/out.
    processed = board(stereo.T, sample_rate)      # (2, N)
    out = np.ascontiguousarray(processed.T, dtype=np.float32)  # (N, 2)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 0.99:
        out = (out / peak * 0.97).astype(np.float32)  # guard against clipping
    return out
