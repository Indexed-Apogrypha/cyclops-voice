from __future__ import annotations
import wave
from pathlib import Path
import numpy as np
from .chunker import chunk_text
from .config import resolve_preset
from .dsp import apply_dsp


def render_to_wav(engine, text: str, preset: str | None = None,
                  path: str | None = None) -> str:
    """Render text through TTS+DSP to a 16-bit stereo WAV file. Returns the path."""
    preset_obj = resolve_preset(preset or engine.config.voice.preset)
    sr = engine.sample_rate
    pitch = engine.config.voice.pitch_semitones
    parts = []
    for ch in chunk_text(text):
        mono = engine.tts.synth(ch)
        if mono.size:
            parts.append(apply_dsp(mono, sr, preset_obj, pitch_semitones=pitch))
    audio = (np.concatenate(parts, axis=0) if parts
             else np.zeros((0, 2), dtype=np.float32))
    out_path = Path(path) if path else Path("cyclops_output.wav")
    pcm16 = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm16 * 32767).astype(np.int16)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())
    return str(out_path.resolve())
