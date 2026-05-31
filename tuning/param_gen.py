"""
Phase 2 parameter grid generator.

Targets the three failing proxy metrics from the baseline:
  - F0 too high (165.8 Hz → need ~-7 additional semitones total)
  - RT60 too long (1.87 s → tighten room_size + raise damping)
  - L/R correlation too high (0.883 → add chorus for width + modulation)
Plus the perceptual timbre gap (-4 Gemini pts):
  - Too clean/smooth → add drive_db (harmonic saturation / grain)

Grid strategy: fix acoustics first, then layer grain on the best acoustic combos.
Total: ~20 focused candidates, designed to not overlap with baseline.
"""
from __future__ import annotations
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cyclops_voice.config import PRESETS, VoiceConfig

# -----------------------------------------------------------------------
# Base: game-accurate preset values (all overrides are relative to this)
# -----------------------------------------------------------------------
BASE = asdict(PRESETS["game-accurate"])
BASE_MODEL = VoiceConfig().model_path
BASE_LS = 1.15  # length_scale

def candidate(cid: str, pitch: float, room: float, damp: float, wet: float,
              drive: float = 0.0, chorus: float = 0.0,
              lm_gain: float = 8.0, lp_hz: float = 3200.0,
              length_scale: float = BASE_LS) -> dict:
    preset = {**BASE,
              "lowmid_gain_db": lm_gain,
              "lowpass_hz": lp_hz,
              "reverb_room_size": room,
              "reverb_damping": damp,
              "reverb_wet": wet,
              "reverb_width": 1.0,          # keep at max
              "drive_db": drive,
              "chorus_mix": chorus}
    return {
        "candidate_id": cid,
        "model_path": BASE_MODEL,
        "length_scale": length_scale,
        "pitch_semitones": pitch,
        "preset": preset,
    }


def build_grid() -> list[dict]:
    grid = []

    # ------------------------------------------------------------------
    # Stage A — fix acoustic fails: pitch + reverb, no grain yet
    # Reference target: pitch ~-7, room 0.42, damp 0.65, wet 0.24
    # ------------------------------------------------------------------
    grid += [
        candidate("A1_p5_rev",   pitch=-5.0, room=0.42, damp=0.65, wet=0.24),
        candidate("A2_p7_rev",   pitch=-7.0, room=0.42, damp=0.65, wet=0.24),
        candidate("A3_p8_rev",   pitch=-8.0, room=0.42, damp=0.65, wet=0.24),
        candidate("A4_p7_rev_lo",pitch=-7.0, room=0.38, damp=0.70, wet=0.22),  # tighter room
        candidate("A5_p7_rev_md",pitch=-7.0, room=0.50, damp=0.60, wet=0.26),  # looser room
    ]

    # ------------------------------------------------------------------
    # Stage B — add grain (drive_db) on best acoustic combos
    # ------------------------------------------------------------------
    grid += [
        candidate("B1_p7_d2",    pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=2.0),
        candidate("B2_p7_d4",    pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=4.0),
        candidate("B3_p8_d2",    pitch=-8.0, room=0.42, damp=0.65, wet=0.24, drive=2.0),
        candidate("B4_p8_d4",    pitch=-8.0, room=0.42, damp=0.65, wet=0.24, drive=4.0),
        candidate("B5_p7_d3",    pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=3.0),
    ]

    # ------------------------------------------------------------------
    # Stage C — add chorus (modulation artifacts + stereo width)
    # ------------------------------------------------------------------
    grid += [
        candidate("C1_p7_d2_c6", pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=2.0, chorus=0.06),
        candidate("C2_p7_d3_c8", pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=3.0, chorus=0.08),
        candidate("C3_p8_d2_c6", pitch=-8.0, room=0.42, damp=0.65, wet=0.24, drive=2.0, chorus=0.06),
        candidate("C4_p7_d2_c10",pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=2.0, chorus=0.10),
    ]

    # ------------------------------------------------------------------
    # Stage D — EQ variants (boost low-mid more for chest resonance)
    # ------------------------------------------------------------------
    grid += [
        candidate("D1_p7_d2_lm10", pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=2.0, lm_gain=10.0),
        candidate("D2_p7_d2_lm6",  pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=2.0, lm_gain=6.0),
    ]

    # ------------------------------------------------------------------
    # Stage E — pacing variants (length_scale)
    # ------------------------------------------------------------------
    grid += [
        candidate("E1_p7_d2_ls110", pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=2.0, length_scale=1.10),
        candidate("E2_p7_d2_ls120", pitch=-7.0, room=0.42, damp=0.65, wet=0.24, drive=2.0, length_scale=1.20),
    ]

    return grid


if __name__ == "__main__":
    grid = build_grid()
    out = ROOT / "tuning" / "param_sets_phase2.json"
    out.write_text(json.dumps(grid, indent=2))
    print(f"Generated {len(grid)} candidates -> {out}")
    for c in grid:
        p = c["preset"]
        print(f"  {c['candidate_id']:<22} pitch={c['pitch_semitones']:>5}  "
              f"room={p['reverb_room_size']}  damp={p['reverb_damping']}  "
              f"drive={p['drive_db']}  chorus={p['chorus_mix']}  "
              f"ls={c['length_scale']}")
