"""
Phase 3 texture sweep on the pq_v3_full winner (V3 + WORLD hard pitch quantization).

Pipeline: Piper synth -> quantize_pitch (snap 1.0, transpose -2) -> add_rasp
          -> apply_dsp(variant preset) -> presence_eq -> stereo WAV

Targets the consistent Gemini gap: timbre roughness/grain/rasp + PA/intercom color.

Usage:
    python tuning/render_texture.py [--out-dir tuning/renders] [--results-file tuning/results.jsonl]
"""
from __future__ import annotations
import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cyclops_voice.tts import PiperTTS
from cyclops_voice.dsp import apply_dsp
from tuning.proxy_score import proxy_score
from tuning.pitch_quantize import quantize_pitch
from tuning.texture import add_rasp, presence_eq
from tuning.render_matrix import EVAL_LINES, EVAL_FULL, save_wav
from tuning.render_quantized import V3_PRESET, V3_MODEL, V3_LENGTH_SCALE, V3_TRANSPOSE

# Each variant: id, rasp amount, preset overrides, presence (freq, gain, q)
VARIANTS = [
    ("tx_rasp_light", 0.06, {},                                  (2200.0, 0.0, 1.0)),
    ("tx_rasp_med",   0.11, {},                                  (2200.0, 0.0, 1.0)),
    ("tx_grit",       0.08, {"drive_db": 4.0, "bitcrush_bit_depth": 11.0}, (2200.0, 0.0, 1.0)),
    ("tx_pa",         0.08, {"drive_db": 4.0, "highpass_hz": 140.0, "lowpass_hz": 3000.0},
                                                                 (2300.0, 4.0, 1.0)),
    ("tx_full",       0.10, {"drive_db": 4.0, "bitcrush_bit_depth": 11.0, "highpass_hz": 120.0},
                                                                 (2300.0, 3.0, 1.0)),
]


def render_variant(cid: str, rasp_amt: float, overrides: dict,
                   presence: tuple, out_dir: Path) -> dict:
    tts = PiperTTS(V3_MODEL, length_scale=V3_LENGTH_SCALE)
    sr = tts.sample_rate
    preset = replace(V3_PRESET, **overrides) if overrides else V3_PRESET
    pf, pg, pq = presence
    line_results, all_audio = [], []

    for line_id, text in EVAL_LINES:
        mono = tts.synth(text)
        if mono.size:
            mono = quantize_pitch(mono, sr, snap_strength=1.0,
                                  transpose_semitones=V3_TRANSPOSE, formant_alpha=1.0)
            mono = add_rasp(mono, sr, amount=rasp_amt)
            audio = apply_dsp(mono, sr, preset, pitch_semitones=0.0)
            audio = presence_eq(audio, sr, freq_hz=pf, gain_db=pg, q=pq)
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
        "pitch_quantize": {"snap_strength": 1.0, "transpose_semitones": V3_TRANSPOSE,
                           "formant_alpha": 1.0},
        "texture": {"rasp_amount": rasp_amt, "presence": presence, "overrides": overrides},
        "preset": asdict(preset),
        "mean_proxy_composite": mean_composite,
        "combined_proxy": combined_proxy,
        "lines": line_results,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 3 texture sweep on pq_v3_full")
    p.add_argument("--out-dir", default="tuning/renders")
    p.add_argument("--results-file", default="tuning/results.jsonl")
    args = p.parse_args(argv)

    out_dir = ROOT / args.out_dir
    results_file = ROOT / args.results_file
    results_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Rendering {len(VARIANTS)} texture variant(s) -> {out_dir}")
    with open(results_file, "a", encoding="utf-8") as log:
        for i, (cid, rasp_amt, overrides, presence) in enumerate(VARIANTS):
            print(f"  [{i+1}/{len(VARIANTS)}] {cid} (rasp={rasp_amt}) ...",
                  end=" ", flush=True)
            result = render_variant(cid, rasp_amt, overrides, presence, out_dir)
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            log.write(json.dumps(result) + "\n")
            log.flush()
            print(f"proxy={result['mean_proxy_composite']:.1f}")

    print(f"Results appended to {results_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
