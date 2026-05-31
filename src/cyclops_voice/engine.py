from __future__ import annotations
import threading
import uuid
from typing import Callable
import numpy as np
from .chunker import chunk_text
from .config import CyclopsConfig, Preset, resolve_preset, build_effective_preset
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
        self._effective_preset = build_effective_preset(config)
        self._sink = sink or SoundDeviceSink(self.sample_rate,
                                             config.audio.output_device or None)
        self._player = Player(self.sample_rate, self._sink, gain=config.audio.volume)
        self._lock = threading.Lock()
        self._current_text: str | None = None

    def speak(self, text: str, preset: str | None = None,
              mode: str = "interrupt") -> str:
        preset_obj = resolve_preset(preset) if preset else self._effective_preset
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

    def apply_config(self, new_cfg: CyclopsConfig) -> None:
        """Live-apply voice/effects/volume/device changes without a restart.

        Builds (and thereby validates) the new effective preset *before* mutating
        any engine state, so an invalid config raises and leaves the engine intact."""
        new_effective = build_effective_preset(new_cfg)  # raises KeyError on bad preset
        old = self.config
        self.config = new_cfg
        if new_cfg.voice.length_scale != old.voice.length_scale:
            self.tts.set_length_scale(new_cfg.voice.length_scale)
        self._effective_preset = new_effective
        if new_cfg.audio.volume != old.audio.volume:
            self._player.set_gain(new_cfg.audio.volume)
        if (new_cfg.audio.output_device or "") != (old.audio.output_device or ""):
            self.set_output_device(new_cfg.audio.output_device or None)

    def set_output_device(self, device: str | int | None) -> None:
        new_sink = SoundDeviceSink(self.sample_rate, device or None)
        old_sink = self._sink
        self._player.set_sink(new_sink)
        self._sink = new_sink
        try:
            old_sink.close()
        except Exception:
            pass

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
