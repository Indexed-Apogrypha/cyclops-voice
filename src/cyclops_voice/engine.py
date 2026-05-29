from __future__ import annotations
import threading
import uuid
from typing import Callable
import numpy as np
from .chunker import chunk_text
from .config import CyclopsConfig, Preset, resolve_preset
from .player import Player, AudioSink, SoundDeviceSink

DspApply = Callable[..., np.ndarray]


class SpeechEngine:
    def __init__(self, tts, config: CyclopsConfig,
                 sink: AudioSink | None = None, dsp_apply: DspApply | None = None):
        self.tts = tts
        self.config = config
        self.sample_rate = (config.audio.sample_rate or tts.sample_rate)
        if dsp_apply is None:
            from .dsp import apply_dsp as dsp_apply  # default real DSP
        self._dsp = dsp_apply
        self._sink = sink or SoundDeviceSink(self.sample_rate,
                                             config.audio.output_device or None)
        self._player = Player(self.sample_rate, self._sink)
        self._lock = threading.Lock()
        self._current_text: str | None = None
        self._gen_thread: threading.Thread | None = None

    def speak(self, text: str, preset: str | None = None,
              mode: str = "interrupt") -> str:
        preset_obj = resolve_preset(preset or self.config.voice.preset)
        chunks = chunk_text(text)
        if mode == "interrupt":
            self._player.stop()
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._current_text = text.strip()[:200]
        self._player.submit(job_id, self._generate(chunks, preset_obj))
        return job_id

    def _generate(self, chunks: list[str], preset: Preset):
        pitch = self.config.voice.pitch_semitones
        for ch in chunks:
            mono = self.tts.synth(ch)
            if mono.size == 0:
                continue
            yield np.asarray(
                self._dsp(mono, self.sample_rate, preset, pitch_semitones=pitch),
                dtype=np.float32,
            )

    def stop(self):
        self._player.stop()
        with self._lock:
            self._current_text = None

    def pause(self): self._player.pause()
    def resume(self): self._player.resume()
    def skip(self): self._player.skip()
    def wait_idle(self, timeout=None): return self._player.wait_idle(timeout)

    def status(self) -> dict:
        with self._lock:
            ct = self._current_text
        state = self._player.state
        return {
            "state": state,
            "current_text": ct if state != "idle" else None,
            "queue_len": self._player._jobs.qsize(),
            "preset": self.config.voice.preset,
        }
