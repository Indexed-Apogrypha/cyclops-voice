"""
Gemini audio judge.

Uploads a WAV to Gemini, presents the full rubric + measured reference profile,
and parses back a structured JSON score for all 7 rubric categories.

Requires: GEMINI_KEY in .env (or environment).
Model: gemini-2.5-flash (audio-native).
"""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import google.genai as genai
from google.genai import types

# ---------------------------------------------------------------------------
# Rubric prompt (full text + reference profile, so the judge has both)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are an expert audio judge evaluating AI-synthesized speech against the
official Subnautica Cyclops onboard AI voice.

REFERENCE PROFILE (measured from real Cyclops audio clips):
- Pitch (F0 median): ~110 Hz (adult male, deep; range 75-155 Hz)
- Spectral centroid: ~420-530 Hz (very dark timbre)
- Energy band 100-300 Hz: ~45-52% of total (low-mid dominant)
- Treble above 3.4 kHz: <3% of energy; above 8 kHz: <0.5% (rolled off)
- Reverb RT60: ~0.6-1.0 s (medium metallic room)
- Stereo L/R correlation: ~0.64-0.76 (clear stereo width from reverb)
- Pacing: deliberate, ~0.85-1.0x conversational speed
- Character: human-derived vehicle AI, mild roughness/grain, slight rasp,
  controlled warmth, submarine onboard command tone

RUBRIC (100 points total):

1. TIMBRE IDENTITY (20 pts)
   Target: deep/mid-low register, dense chest resonance, synthetic coloration,
   mild PA/intercom quality, mature vocal weight, calm command presence.
   Cyclops-specific: light roughness, mild vocal grain, subtle rasp, slight
   modulation artifacts, non-sterile delivery.
   Penalize: youthful/boyish, playful, cheerful, smooth corporate narrator,
   overly clean cinematic voice, exaggerated robotic monotone.

2. CADENCE (20 pts)
   Target: 0.85-1.0x conversational speed, deliberate procedural pacing,
   meaningful clause spacing, controlled warning pauses.
   Penalize: rushed, casual, overly slow dramatic pauses, audiobook cadence.

3. PROSODIC CONTOUR (15 pts)
   Target: controlled operational intonation, NOT flat, NOT emotionally
   performative. Small-to-moderate pitch movement, emphasized operational
   keywords, controlled terminal contours.
   Penalize: monotone flattening, actorly emotional performance, sing-song.

4. PROCEDURAL AUTHORITY (15 pts)
   Target: competent systems officer, operational confidence, calm authority,
   capable of managing reactor startup / hull damage / emergency procedures.
   Penalize: anxiety, uncertainty, emotional escalation, conversational informality.

5. DICTION & CLARITY (10 pts)
   Target: high operational intelligibility, broadcast-grade readability,
   sharp consonants, clear word boundaries.
   Penalize: muddy articulation, swallowed consonants, excessive effects masking speech.

6. SYNTHETIC CHARACTER (10 pts)
   Target: human core enhanced by restrained machine processing, ship PA coloration,
   believable onboard system voice. Human intelligibility must remain dominant.
   Penalize: completely natural untreated voice, cartoon robot, heavy vocoder,
   hard TTS artifacting, overprocessed cyberpunk effects.

7. EMOTIONAL CALIBRATION (10 pts)
   Target: restrained operational personality, dry confidence, controlled warmth,
   understated charisma, subtle reassurance. Emotion always subordinate to professionalism.
   Penalize: emotionally blank monotone, enthusiastic friendliness, dramatic acting,
   strong emotional expressiveness.

SCORING GUIDE:
95-100: Exceptional — near-official Cyclops quality
85-94:  Strong — clearly Cyclops-adjacent, minor deviations
70-84:  Partial — captures some traits, misses important identity components
50-69:  Weak — noticeable mismatch
<50:    Poor — fails to evoke Cyclops identity

You will receive one audio clip. Score it against the rubric above.
"""

SCORE_REQUEST = """
Listen carefully to the audio clip. Score it against the rubric.

Respond ONLY with valid JSON in this exact structure (no markdown, no commentary):
{
  "scores": {
    "timbre_identity": <int 0-20>,
    "cadence": <int 0-20>,
    "prosodic_contour": <int 0-15>,
    "procedural_authority": <int 0-15>,
    "diction_clarity": <int 0-10>,
    "synthetic_character": <int 0-10>,
    "emotional_calibration": <int 0-10>
  },
  "total": <int 0-100>,
  "defects": [<short string per notable weakness, max 5>],
  "strengths": [<short string per notable strength, max 3>],
  "model_notes": "<one sentence on base voice quality>"
}

The "total" field must equal the sum of the 7 category scores.
"""


# ---------------------------------------------------------------------------
# Judge client
# ---------------------------------------------------------------------------

PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


def _get_client() -> genai.Client:
    key = os.environ.get("GEMINI_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_KEY not set — add it to .env")
    return genai.Client(api_key=key)


def _is_transient(e: Exception) -> bool:
    s = str(e)
    return "503" in s or "429" in s or "RESOURCE_EXHAUSTED" in s or "UNAVAILABLE" in s


def _pick_model(client: genai.Client) -> str:
    """Return the first model that responds to a plain text ping without 503/429."""
    for model in PREFERRED_MODELS:
        try:
            client.models.generate_content(model=model, contents="ping")
            return model
        except Exception as e:
            if _is_transient(e):
                continue
            raise
    # All models transient — fall back to best and let the caller handle it
    return PREFERRED_MODELS[0]


def _upload_wav(client: genai.Client, wav_path: Path) -> str:
    """Upload WAV via Files API, return file URI. Retries once on transient error."""
    for attempt in range(2):
        try:
            with open(wav_path, "rb") as f:
                response = client.files.upload(
                    file=f,
                    config=types.UploadFileConfig(mime_type="audio/wav"),
                )
            # Poll until processing is complete
            file_name = response.name
            for _ in range(20):
                file_info = client.files.get(name=file_name)
                if file_info.state == types.FileState.ACTIVE:
                    return file_info.uri
                if file_info.state == types.FileState.FAILED:
                    raise RuntimeError(f"File processing failed: {file_name}")
                time.sleep(1)
            raise RuntimeError(f"File never became ACTIVE: {file_name}")
        except Exception as e:
            if attempt == 0 and "503" in str(e):
                time.sleep(3)
                continue
            raise


def _parse_scores(raw: str) -> dict:
    """Extract JSON from Gemini response, tolerating minor formatting."""
    raw = raw.strip()
    # strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def judge_wav(wav_path: str | Path, label: str = "") -> dict:
    """
    Upload wav_path to Gemini, score against the Cyclops rubric.
    Returns the parsed score dict from the model, plus wav/label metadata.
    """
    wav_path = Path(wav_path)
    client = _get_client()

    uri = _upload_wav(client, wav_path)

    contents = [
        types.Content(parts=[
            types.Part(text=SYSTEM_PROMPT + "\n\n" + SCORE_REQUEST),
            types.Part(file_data=types.FileData(file_uri=uri, mime_type="audio/wav")),
        ], role="user")
    ]

    last_err = None
    for model in PREFERRED_MODELS:
        try:
            print(f"  [judge] trying {model} ...", end=" ", flush=True)
            resp = client.models.generate_content(model=model, contents=contents)
            print("OK", flush=True)
            break
        except Exception as e:
            print(f"{'transient' if _is_transient(e) else 'error'}: {str(e)[:60]}", flush=True)
            last_err = e
            if _is_transient(e):
                time.sleep(2)
                continue
            raise
    else:
        raise RuntimeError(f"All models failed. Last error: {last_err}")

    raw = resp.text
    parsed = _parse_scores(raw)

    # recalculate total to guard against model arithmetic errors
    cats = parsed.get("scores", {})
    calc_total = sum(cats.values())
    if abs(calc_total - parsed.get("total", 0)) > 1:
        parsed["total"] = calc_total  # trust the sum, not the stated total

    return {
        "wav": str(wav_path),
        "label": label,
        **parsed,
    }


def judge_candidate(candidate_dir: str | Path, candidate_id: str = "") -> dict:
    """
    Judge the combined.wav for a candidate (as rendered by render_matrix.py).
    Falls back to judging individual lines and averaging if combined.wav is missing.
    """
    candidate_dir = Path(candidate_dir)
    combined = candidate_dir / "combined.wav"
    if combined.exists():
        return judge_wav(combined, label=candidate_id or candidate_dir.name)

    # fallback: judge each line, average scores
    line_scores = []
    for wav in sorted(candidate_dir.glob("*.wav")):
        if wav.name == "combined.wav":
            continue
        r = judge_wav(wav, label=wav.stem)
        line_scores.append(r)

    if not line_scores:
        raise FileNotFoundError(f"No WAVs found in {candidate_dir}")

    # average per-category
    cats = list(line_scores[0]["scores"].keys())
    avg_scores = {c: round(sum(r["scores"][c] for r in line_scores) / len(line_scores)) for c in cats}
    avg_total = sum(avg_scores.values())
    all_defects = list({d for r in line_scores for d in r.get("defects", [])})[:5]
    all_strengths = list({s for r in line_scores for s in r.get("strengths", [])})[:3]

    return {
        "wav": str(candidate_dir),
        "label": candidate_id or candidate_dir.name,
        "scores": avg_scores,
        "total": avg_total,
        "defects": all_defects,
        "strengths": all_strengths,
        "model_notes": line_scores[0].get("model_notes", ""),
        "averaged_from": len(line_scores),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Judge a WAV file or candidate dir against the Cyclops rubric")
    p.add_argument("path", help="Path to a .wav file or a candidate render directory")
    p.add_argument("--label", default="", help="Human-readable label for the result")
    args = p.parse_args()

    path = Path(args.path)
    if path.is_dir():
        result = judge_candidate(path, candidate_id=args.label or path.name)
    else:
        result = judge_wav(path, label=args.label or path.stem)

    print(json.dumps(result, indent=2))
