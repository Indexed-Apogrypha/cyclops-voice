from __future__ import annotations
from pathlib import Path
import numpy as np
from piper import PiperVoice
from piper.config import SynthesisConfig


class PiperTTS:
    """Loads a Piper voice once; synthesizes text to mono float32 PCM."""

    def __init__(self, model_path: str | Path, length_scale: float = 1.0):
        self.model_path = str(model_path)
        if not Path(self.model_path).exists():
            raise FileNotFoundError(
                f"Piper voice model not found: {self.model_path}. "
                "Run: python scripts/install_voice_model.py"
            )
        self._voice = PiperVoice.load(self.model_path)
        self.length_scale = length_scale
        self.sample_rate = int(getattr(self._voice.config, "sample_rate", 22050))
        self._syn_config = SynthesisConfig(length_scale=length_scale)

    def set_length_scale(self, length_scale: float) -> None:
        """Live speed change: rebuild the synthesis config (no model reload)."""
        self.length_scale = length_scale
        self._syn_config = SynthesisConfig(length_scale=length_scale)

    def synth(self, text: str) -> np.ndarray:
        """Synthesize text to mono float32 PCM in [-1, 1]."""
        text = text.strip()
        if not text:
            return np.zeros(0, dtype=np.float32)
        # synthesize() returns Iterable[AudioChunk]; each has audio_float_array
        parts = [
            chunk.audio_float_array.astype(np.float32)
            for chunk in self._voice.synthesize(text, syn_config=self._syn_config)
        ]
        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(parts).reshape(-1)
