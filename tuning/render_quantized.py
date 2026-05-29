"""
Render the E1_tuned_v3 candidate with a WORLD hard-pitch-quantize stage inserted
between Piper synthesis and the Cyclops DSP chain.

    Piper synth (mono) -> quantize_pitch (WORLD) -> apply_dsp -> stereo WAV

Produces several variants (snap strength x formant shift) so the Gemini judge can
pick the most convincingly "autotuned" one without losing intelligibility.

Usage:
    python tuning/render_quantized.py [--out-dir tuning/renders] [--results-file tuning/results.jsonl]
"""
from __future__ import annotations
import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cyclops_voice.config import Preset
from cyclops_voice.tts import PiperTTS
from cyclops_voice.dsp import apply_dsp
from tuning.proxy_score import proxy_score
from tuning.pitch_quantize import quantize_pitch
from tuning.render_matrix import EVAL_LINES, EVAL_FULL, save_wav

# E1_tuned_v3 base (current best, Gemini 99) — pitch handled by WORLD now, so the
# DSP PitchShift is dropped (pitch_semitones=0) to avoid double-shifting.
V3_PRESET = Preset(
    name="game-accurate", highpass_hz=60, lowmid_freq_hz=200, lowmid_gain_db=8.0,
    lowmid_q=1.2, lowpass_hz=3200, comp_threshold_db=-18, comp_ratio=2.5,
    reverb_room_size=0.42, reverb_damping=0.65, reverb_wet=0.24, reverb_width=1.0,
    chorus_mix=0.0, drive_db=2.0, bitcrush_bit_depth=12.0,
)
V3_MODEL = "models/en_US-ryan-medium.onnx"
V3_LENGTH_SCALE = 1.22

# V3's -2 semitone register is folded into the WORLD F0 contour (transpose before
# snapping), so DSP PitchShift stays off (pitch_semitones=0) to avoid double-shift.
V3_TRANSPOSE = -2.0

# (id, snap_strength, formant_alpha)
VARIANTS = [
    ("pq_v3_full",     1.0,  1.00),   # full chromatic snap, no formant shift
    ("pq_v3_formant",  1.0,  1.07),   # full snap + subtle upward formants
    ("pq_v3_soft",     0.7,  1.05),   # softer snap (less robotic, safer diction)
]


def render_variant(cid: str, snap: float, alpha: float, out_dir: Path) -> dict:
    tts = PiperTTS(V3_MODEL, length_scale=V3_LENGTH_SCALE)
    sr = tts.sample_rate
    line_results, all_audio = [], []

    for line_id, text in EVAL_LINES:
        mono = tts.synth(text)
        if mono.size:
            mono = quantize_pitch(mono, sr, snap_strength=snap,
                                  transpose_semitones=V3_TRANSPOSE, formant_alpha=alpha)
            audio = apply_dsp(mono, sr, V3_PRESET, pitch_semitones=0.0)
        else:
            audio = np.zeros((0, 2), dtype=np.float32)
        wav_path = out_dir / cid / f"{line_id}.wav"
        save_wav(audio, sr, wav_path)
        line_results.append({"line": line_id, "text": text, "wav": str(wav_path),
                             "proxy": proxy_score(wav_path, text)})
        if audio.size:
            all_audio.append(audio)

    combined_path = out_dir / cid / "combined.wav"
    if all_audio:
        save_wav(np.concatenate(all_audio, axis=0), sr, combined_path)
        combined_proxy = proxy_score(combined_path, EVAL_FULL)
    else:
        combined_proxy = {}

    composites = [r["proxy"]["composite_proxy"] for r in line_results
                  if "composite_proxy" in r.get("proxy", {})]
    mean_composite = round(sum(composites) / len(composites), 1) if composites else 0.0

    return {
        "candidate_id": cid,
        "model_path": V3_MODEL,
        "length_scale": V3_LENGTH_SCALE,
        "pitch_semitones": 0.0,
        "pitch_quantize": {"snap_strength": snap, "formant_alpha": alpha},
        "preset": asdict(V3_PRESET),
        "mean_proxy_composite": mean_composite,
        "combined_proxy": combined_proxy,
        "lines": line_results,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render V3 + WORLD pitch quantization")
    p.add_argument("--out-dir", default="tuning/renders")
    p.add_argument("--results-file", default="tuning/results.jsonl")
    args = p.parse_args(argv)

    out_dir = ROOT / args.out_dir
    results_file = ROOT / args.results_file
    results_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Rendering {len(VARIANTS)} quantized variant(s) -> {out_dir}")
    with open(results_file, "a", encoding="utf-8") as log:
        for i, (cid, snap, alpha) in enumerate(VARIANTS):
            print(f"  [{i+1}/{len(VARIANTS)}] {cid} (snap={snap}, formant={alpha}) ...",
                  end=" ", flush=True)
            result = render_variant(cid, snap, alpha, out_dir)
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            log.write(json.dumps(result) + "\n")
            log.flush()
            print(f"proxy={result['mean_proxy_composite']:.1f}")

    print(f"Results appended to {results_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
