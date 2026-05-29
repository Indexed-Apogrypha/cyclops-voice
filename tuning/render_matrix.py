"""
Render matrix runner.

Renders the canonical evaluation script through one or more param sets, saves WAVs,
runs the local proxy scorer, and writes a JSON results log.

Usage:
    python tuning/render_matrix.py [--param-file tuning/param_sets.json] [--out-dir tuning/renders]

The canonical evaluation script covers every rubric context:
  - Captain address     "Welcome aboard, Captain."
  - System status       "All systems online. Hull integrity nominal."
  - Warning             "Warning. Hull breach detected. Sealing affected compartments."
  - Command             "Reactor power at maximum. Flank speed engaged."
  - Emergency           "Abandon ship. Abandon ship."
"""
from __future__ import annotations
import argparse
import json
import sys
import wave
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Make src/ and repo root importable when run from repo root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cyclops_voice.config import CyclopsConfig, Preset, VoiceConfig, ServiceConfig, AudioConfig, HotkeyConfig
from cyclops_voice.tts import PiperTTS
from cyclops_voice.dsp import apply_dsp
from tuning.proxy_score import proxy_score

EVAL_LINES = [
    ("captain_address",  "Welcome aboard, Captain."),
    ("system_status",    "All systems online. Hull integrity nominal."),
    ("warning",          "Warning. Hull breach detected. Sealing affected compartments."),
    ("command",          "Reactor power at maximum. Flank speed engaged."),
    ("emergency",        "Abandon ship. Abandon ship."),
]

# Combined text for cadence measurement
EVAL_FULL = " ".join(t for _, t in EVAL_LINES)


def load_tts(model_path: str, length_scale: float) -> PiperTTS:
    return PiperTTS(model_path, length_scale=length_scale)


def render_line(tts: PiperTTS, text: str, preset: Preset,
                pitch_semitones: float) -> np.ndarray:
    mono = tts.synth(text)
    if mono.size == 0:
        return np.zeros((0, 2), dtype=np.float32)
    return apply_dsp(mono, tts.sample_rate, preset, pitch_semitones=pitch_semitones)


def save_wav(audio: np.ndarray, sr: int, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(int16.tobytes())


def render_candidate(
    candidate_id: str,
    model_path: str,
    length_scale: float,
    pitch_semitones: float,
    preset: Preset,
    out_dir: Path,
) -> dict:
    """Render all eval lines for one candidate, compute proxy, return result dict."""
    tts = load_tts(model_path, length_scale)
    sr = tts.sample_rate

    line_results = []
    all_audio = []

    for line_id, text in EVAL_LINES:
        audio = render_line(tts, text, preset, pitch_semitones)
        wav_path = out_dir / candidate_id / f"{line_id}.wav"
        save_wav(audio, sr, wav_path)
        proxy = proxy_score(wav_path, text)
        line_results.append({
            "line": line_id,
            "text": text,
            "wav": str(wav_path),
            "proxy": proxy,
        })
        if audio.size > 0:
            all_audio.append(audio)

    # combined WAV for full-script proxy (cadence)
    combined_path = out_dir / candidate_id / "combined.wav"
    if all_audio:
        combined = np.concatenate(all_audio, axis=0)
        save_wav(combined, sr, combined_path)
        combined_proxy = proxy_score(combined_path, EVAL_FULL)
    else:
        combined_proxy = {}

    # mean composite across lines
    composites = [r["proxy"]["composite_proxy"] for r in line_results if "composite_proxy" in r.get("proxy", {})]
    mean_composite = round(sum(composites) / len(composites), 1) if composites else 0.0

    return {
        "candidate_id": candidate_id,
        "model_path": model_path,
        "length_scale": length_scale,
        "pitch_semitones": pitch_semitones,
        "preset": asdict(preset),
        "mean_proxy_composite": mean_composite,
        "combined_proxy": combined_proxy,
        "lines": line_results,
    }


def default_param_sets() -> list[dict]:
    """Return a minimal default set: current game-accurate preset, as-is."""
    from cyclops_voice.config import PRESETS, VoiceConfig
    vc = VoiceConfig()
    preset = PRESETS["game-accurate"]
    return [
        {
            "candidate_id": "baseline_game-accurate",
            "model_path": vc.model_path,
            "length_scale": vc.length_scale,
            "pitch_semitones": vc.pitch_semitones,
            "preset": asdict(preset),
        }
    ]


def preset_from_dict(d: dict) -> Preset:
    return Preset(**d)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render candidates and proxy-score them")
    p.add_argument("--param-file", default=None,
                   help="JSON file with list of candidate param dicts (default: baseline only)")
    p.add_argument("--out-dir", default="tuning/renders",
                   help="Directory for rendered WAVs (default: tuning/renders)")
    p.add_argument("--results-file", default="tuning/results.jsonl",
                   help="Append results to this JSONL file")
    args = p.parse_args(argv)

    out_dir = ROOT / args.out_dir
    results_file = ROOT / args.results_file
    results_file.parent.mkdir(parents=True, exist_ok=True)

    if args.param_file:
        param_sets = json.loads(Path(args.param_file).read_text())
    else:
        param_sets = default_param_sets()

    print(f"Rendering {len(param_sets)} candidate(s) -> {out_dir}")

    with open(results_file, "a", encoding="utf-8") as log:
        for i, params in enumerate(param_sets):
            cid = params.get("candidate_id", f"candidate_{i:03d}")
            print(f"  [{i+1}/{len(param_sets)}] {cid} ...", end=" ", flush=True)
            preset = preset_from_dict(params["preset"])
            result = render_candidate(
                candidate_id=cid,
                model_path=params["model_path"],
                length_scale=params["length_scale"],
                pitch_semitones=params["pitch_semitones"],
                preset=preset,
                out_dir=out_dir,
            )
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            log.write(json.dumps(result) + "\n")
            log.flush()
            print(f"proxy={result['mean_proxy_composite']:.1f}")

    print(f"Results appended to {results_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
