# Cyclops Voice TTS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, system-wide Windows TTS service that reads arbitrary text aloud in the Subnautica Cyclops AI voice (Piper neural TTS + a measured DSP chain), driven by a global hotkey, a CLI, an HTTP API, and an MCP server.

**Architecture:** One background daemon owns the warm Piper model, the DSP chain, and a single streaming playback queue, exposing a localhost HTTP API. The hotkey listener, CLI, and MCP server are thin HTTP clients. Text is split into sentences and synthesized+processed chunk-by-chunk so playback starts in <~1s. See the design spec: `docs/superpowers/specs/2026-05-29-cyclops-voice-tts-design.md`.

**Tech Stack:** Python 3.12 · `piper-tts`/`onnxruntime` · `pedalboard` · `sounddevice` · `numpy`/`scipy` · `fastapi`+`uvicorn` · `httpx` · `pynput`+`pyperclip` · official `mcp` SDK · `pystray`+`Pillow` · `pytest`.

---

## Reference: the build environment

Already installed on this machine (verified): `ffmpeg`, `ffprobe`, `sox`, `piper.exe` (108 KB, no model yet), Python 3.14 (system). **Create a separate Python 3.12 venv for this project** — `pedalboard`/`sounddevice`/`onnxruntime` wheels are most reliable on 3.12. Verify wheel availability in Task 1.

## File Structure (interfaces locked here — keep names/types consistent across tasks)

```
cyclops-voice/                     (repo root = X:\Projects\SubnauticaVoice)
  pyproject.toml                   # project metadata + deps (Task 1)
  config.example.toml              # sample config (Task 2)
  src/cyclops_voice/
    __init__.py                    # version (Task 1)
    config.py                      # Preset, PRESETS, *Config dataclasses, load_config (Task 2)
    chunker.py                     # chunk_text(text, max_chars) -> list[str] (Task 3)
    dsp.py                         # to_stereo, build_board, apply_dsp (Task 4)
    tts.py                         # PiperTTS.synth(text) -> np.ndarray mono float32 (Task 5)
    player.py                      # AudioSink, SoundDeviceSink, Player (Task 6)
    engine.py                      # SpeechEngine (Task 7)
    server.py                      # FastAPI app factory create_app(engine) (Task 8)
    daemon.py                      # run_daemon(): engine + uvicorn + hotkey + tray (Task 9)
    client.py                      # CyclopsClient HTTP helper (shared by cli/mcp/hotkey) (Task 10)
    cli.py                         # `cyclops` entry point (Task 11)
    mcp_server.py                  # MCP stdio server (Task 12)
    hotkey.py                      # global hotkey -> capture selection -> speak (Task 13)
    tray.py                        # optional system tray (Task 14)
    export.py                      # offline render to .wav (Task 15)
  scripts/
    install_voice_model.py         # download en_US-ryan model (Task 16)
    install_autostart.py           # Startup-folder shortcut (Task 16)
  tests/
    acoustics.py                   # shared measurement helpers (Task 4)
    test_config.py  test_chunker.py  test_dsp.py  test_player.py
    test_engine.py  test_server.py  test_client.py  test_mcp.py
    test_acoustic_profile.py       # integration, skips without model (Task 5)
  README.md                        # (Task 17)
```

### Canonical internal interfaces (referenced by many tasks)
- Audio convention: **mono** = `np.ndarray` shape `(N,)` float32 in [-1, 1]; **stereo** = shape `(N, 2)` float32 (sounddevice frame-major).
- `chunk_text(text: str, max_chars: int = 240) -> list[str]`
- `apply_dsp(mono: np.ndarray, sample_rate: int, preset: Preset, pitch_semitones: float = 0.0) -> np.ndarray`  (returns stereo `(N,2)`)
- `PiperTTS(model_path: str, length_scale: float = 1.0)`; `.sample_rate -> int`; `.synth(text: str) -> np.ndarray` (mono)
- `Player(sample_rate: int, sink: AudioSink)`; `.submit(job_id: str, buffers: Iterator[np.ndarray])`, `.stop()`, `.pause()`, `.resume()`, `.skip()`, `.state -> str`
- `SpeechEngine(tts, preset_resolver, config)`; `.speak(text, preset=None, mode="interrupt") -> str`, `.stop()`, `.pause()`, `.resume()`, `.skip()`, `.status() -> dict`
- HTTP status object (returned by `/status`, `/stop`, etc.): `{"state": str, "current_text": str|null, "queue_len": int, "preset": str}`

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `src/cyclops_voice/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "cyclops-voice"
version = "0.1.0"
description = "System-wide Subnautica Cyclops voice TTS service"
requires-python = ">=3.12,<3.13"
dependencies = [
  "numpy>=1.26",
  "scipy>=1.11",
  "pedalboard>=0.9",
  "sounddevice>=0.4.6",
  "piper-tts>=1.2",
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "httpx>=0.27",
  "pynput>=1.7",
  "pyperclip>=1.8",
  "pystray>=0.19",
  "Pillow>=10",
  "mcp>=1.2",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[project.scripts]
cyclops = "cyclops_voice.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `src/cyclops_voice/__init__.py`**

```python
"""Cyclops Voice — system-wide Subnautica Cyclops TTS service."""
__version__ = "0.1.0"
```

- [ ] **Step 3: Create empty `tests/__init__.py`**

```python
```

- [ ] **Step 4: Create the venv and install (verifies wheels exist on 3.12)**

Run (PowerShell, from repo root):
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```
Expected: all deps install with no "no matching distribution" errors. If `py -3.12` is missing, install Python 3.12 first (`winget install Python.Python.3.12`). If any wheel fails on 3.12, STOP and report which one before continuing.

- [ ] **Step 5: Verify pytest runs**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: "no tests ran" (exit 0/5) — confirms the package is importable and pytest is wired.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml src/cyclops_voice/__init__.py tests/__init__.py
git commit -m "chore: scaffold cyclops-voice package"
```

> **Note for all later tasks:** run python/pytest via `.\.venv\Scripts\python`. Examples below write `python` for brevity — use the venv interpreter.

---

### Task 2: Config + presets

**Files:**
- Create: `src/cyclops_voice/config.py`, `config.example.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path
from cyclops_voice.config import load_config, PRESETS, Preset

def test_presets_exist():
    assert {"game-accurate", "subtle", "heavy"} <= set(PRESETS)
    assert isinstance(PRESETS["game-accurate"], Preset)

def test_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg.service.port == 7788
    assert cfg.voice.preset == "game-accurate"
    assert cfg.hotkeys.read_selection == "ctrl+alt+r"

def test_load_overrides(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        "[service]\nport = 9000\n\n[voice]\npreset = 'heavy'\nlength_scale = 1.3\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.service.port == 9000
    assert cfg.voice.preset == "heavy"
    assert cfg.voice.length_scale == 1.3
    assert cfg.service.host == "127.0.0.1"  # untouched default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: cyclops_voice.config`.

- [ ] **Step 3: Write `src/cyclops_voice/config.py`**

```python
from __future__ import annotations
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class Preset:
    name: str
    highpass_hz: float
    lowmid_freq_hz: float
    lowmid_gain_db: float
    lowmid_q: float
    lowpass_hz: float
    comp_threshold_db: float
    comp_ratio: float
    reverb_room_size: float
    reverb_damping: float
    reverb_wet: float
    reverb_width: float
    chorus_mix: float = 0.0
    drive_db: float = 0.0


PRESETS: dict[str, Preset] = {
    # Derived from the measured reference profile (see design spec §2-3).
    "game-accurate": Preset(
        name="game-accurate", highpass_hz=60, lowmid_freq_hz=200, lowmid_gain_db=6.0,
        lowmid_q=0.7, lowpass_hz=3200, comp_threshold_db=-18, comp_ratio=2.5,
        reverb_room_size=0.55, reverb_damping=0.5, reverb_wet=0.28, reverb_width=1.0,
    ),
    "subtle": Preset(
        name="subtle", highpass_hz=70, lowmid_freq_hz=180, lowmid_gain_db=3.0,
        lowmid_q=0.7, lowpass_hz=5000, comp_threshold_db=-16, comp_ratio=2.0,
        reverb_room_size=0.40, reverb_damping=0.6, reverb_wet=0.15, reverb_width=0.8,
    ),
    "heavy": Preset(
        name="heavy", highpass_hz=70, lowmid_freq_hz=220, lowmid_gain_db=8.0,
        lowmid_q=0.8, lowpass_hz=2800, comp_threshold_db=-20, comp_ratio=3.5,
        reverb_room_size=0.70, reverb_damping=0.4, reverb_wet=0.40, reverb_width=1.0,
        chorus_mix=0.2, drive_db=6.0,
    ),
}


@dataclass
class ServiceConfig:
    host: str = "127.0.0.1"
    port: int = 7788
    auth_token: str = ""


@dataclass
class VoiceConfig:
    model_path: str = "models/en_US-ryan-medium.onnx"
    length_scale: float = 1.15
    pitch_semitones: float = -1.0
    preset: str = "game-accurate"


@dataclass
class HotkeyConfig:
    read_selection: str = "ctrl+alt+r"
    stop: str = "ctrl+alt+s"


@dataclass
class AudioConfig:
    output_device: str = ""
    sample_rate: int = 0  # 0 = use model rate


@dataclass
class CyclopsConfig:
    service: ServiceConfig = field(default_factory=ServiceConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)


def _apply(section: dict, obj):
    for k, v in section.items():
        if hasattr(obj, k):
            setattr(obj, k, v)


def load_config(path: Path | str | None = None) -> CyclopsConfig:
    cfg = CyclopsConfig()
    if path is None:
        return cfg
    path = Path(path)
    if not path.exists():
        return cfg
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    _apply(data.get("service", {}), cfg.service)
    _apply(data.get("voice", {}), cfg.voice)
    _apply(data.get("hotkeys", {}), cfg.hotkeys)
    _apply(data.get("audio", {}), cfg.audio)
    return cfg


def resolve_preset(name: str) -> Preset:
    if name not in PRESETS:
        raise KeyError(f"unknown preset {name!r}; choices: {sorted(PRESETS)}")
    return PRESETS[name]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Write `config.example.toml`**

```toml
[service]
host = "127.0.0.1"
port = 7788
auth_token = ""           # optional shared token; if set, clients must send X-Cyclops-Token

[voice]
model_path = "models/en_US-ryan-medium.onnx"
length_scale = 1.15       # >1 = slower / more deliberate
pitch_semitones = -1
preset = "game-accurate"  # game-accurate | subtle | heavy

[hotkeys]
read_selection = "ctrl+alt+r"
stop = "ctrl+alt+s"

[audio]
output_device = ""        # empty = system default
sample_rate = 0           # 0 = use model rate
```

- [ ] **Step 6: Commit**

```powershell
git add src/cyclops_voice/config.py tests/test_config.py config.example.toml
git commit -m "feat: config loading and DSP presets"
```

---

### Task 3: Sentence chunker

**Files:**
- Create: `src/cyclops_voice/chunker.py`
- Test: `tests/test_chunker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chunker.py
from cyclops_voice.chunker import chunk_text

def test_splits_on_sentences():
    out = chunk_text("Hello there. All systems online! Status?")
    assert out == ["Hello there.", "All systems online!", "Status?"]

def test_blank_input():
    assert chunk_text("   \n  ") == []

def test_long_sentence_is_split_by_length():
    long = "word " * 100  # 500 chars, no sentence punctuation
    out = chunk_text(long, max_chars=240)
    assert len(out) >= 2
    assert all(len(c) <= 240 for c in out)
    assert "".join(out).replace(" ", "") == long.replace(" ", "")

def test_newlines_break_chunks():
    out = chunk_text("Line one\nLine two")
    assert out == ["Line one", "Line two"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chunker.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/cyclops_voice/chunker.py`**

```python
from __future__ import annotations
import re

_SENTENCE = re.compile(r"[^.!?\n]*[.!?]+|\S[^\n]*", re.UNICODE)


def _split_long(piece: str, max_chars: int) -> list[str]:
    words = piece.split(" ")
    out, cur = [], ""
    for w in words:
        cand = w if not cur else cur + " " + w
        if len(cand) > max_chars and cur:
            out.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out


def chunk_text(text: str, max_chars: int = 240) -> list[str]:
    """Split text into sentence-sized chunks for streaming synthesis."""
    chunks: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for m in _SENTENCE.finditer(line):
            s = m.group().strip()
            if not s:
                continue
            if len(s) <= max_chars:
                chunks.append(s)
            else:
                chunks.extend(_split_long(s, max_chars))
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_chunker.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```powershell
git add src/cyclops_voice/chunker.py tests/test_chunker.py
git commit -m "feat: sentence chunker for streaming"
```

---

### Task 4: DSP chain + acoustic measurement helpers

**Files:**
- Create: `src/cyclops_voice/dsp.py`, `tests/acoustics.py`
- Test: `tests/test_dsp.py`

- [ ] **Step 1: Write shared measurement helpers `tests/acoustics.py`**

```python
# tests/acoustics.py — reusable acoustic measurements (mirrors the reference-profiling script)
import numpy as np
from scipy.signal import welch


def to_mono(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1) if x.ndim == 2 else x


def band_fraction(x: np.ndarray, sr: int, lo: float, hi: float) -> float:
    m = to_mono(x)
    f, p = welch(m, fs=sr, nperseg=min(8192, len(m)))
    df = f[1] - f[0]
    total = float(np.sum(p) * df) + 1e-15
    sel = (f >= lo) & (f < hi)
    return float(np.sum(p[sel]) * df) / total


def spectral_centroid(x: np.ndarray, sr: int) -> float:
    m = to_mono(x)
    f, p = welch(m, fs=sr, nperseg=min(8192, len(m)))
    return float(np.sum(f * p) / (np.sum(p) + 1e-15))


def lr_correlation(stereo: np.ndarray) -> float:
    assert stereo.ndim == 2 and stereo.shape[1] == 2
    return float(np.corrcoef(stereo[:, 0], stereo[:, 1])[0, 1])


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(to_mono(x))) + 1e-15))


def reverb_rt60(stereo: np.ndarray, sr: int) -> float:
    """Crude Schroeder decay estimate on the trailing tail."""
    m = np.abs(to_mono(stereo))
    fl = int(0.02 * sr)
    env = np.sqrt(np.convolve(m**2, np.ones(fl) / fl, "same") + 1e-15)
    edb = 20 * np.log10(env / env.max() + 1e-12)
    end = len(edb) - 1
    start = end
    while start > 0 and edb[start] < -15:  # walk back into the tail
        start -= 1
    seg = edb[start:end]
    if len(seg) < int(0.05 * sr):
        return 0.0
    t = np.arange(len(seg)) / sr
    slope = np.polyfit(t, seg, 1)[0]
    return float(-60.0 / slope) if slope < -1 else 0.0
```

- [ ] **Step 2: Write the failing test `tests/test_dsp.py`**

```python
# tests/test_dsp.py
import numpy as np
from cyclops_voice.config import PRESETS
from cyclops_voice.dsp import apply_dsp
from tests.acoustics import rms, lr_correlation

SR = 22050

def _tone(freq, sr=SR, secs=1.0, amp=0.3):
    t = np.arange(int(sr * secs)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)

def test_output_is_stereo_float32():
    out = apply_dsp(_tone(200), SR, PRESETS["game-accurate"])
    assert out.ndim == 2 and out.shape[1] == 2
    assert out.dtype == np.float32

def test_lowpass_kills_treble():
    lo = apply_dsp(_tone(200), SR, PRESETS["game-accurate"])
    hi = apply_dsp(_tone(10000), SR, PRESETS["game-accurate"])
    atten_db = 20 * np.log10(rms(lo) / (rms(hi) + 1e-9))
    assert atten_db > 18  # 10 kHz strongly attenuated vs 200 Hz

def test_lowmid_boosted_relative_to_mids():
    low = apply_dsp(_tone(200), SR, PRESETS["game-accurate"])
    mid = apply_dsp(_tone(1000), SR, PRESETS["game-accurate"])
    boost_db = 20 * np.log10(rms(low) / (rms(mid) + 1e-9))
    assert boost_db > 2  # low-mids hotter than 1 kHz

def test_reverb_creates_stereo_width():
    rng = np.random.default_rng(0)
    noise = (0.2 * rng.standard_normal(SR)).astype(np.float32)
    out = apply_dsp(noise, SR, PRESETS["game-accurate"])
    assert lr_correlation(out) < 0.97  # decorrelated -> width present
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_dsp.py -q`
Expected: FAIL — `ModuleNotFoundError: cyclops_voice.dsp`.

- [ ] **Step 4: Write `src/cyclops_voice/dsp.py`**

```python
from __future__ import annotations
import numpy as np
from pedalboard import (
    Pedalboard, HighpassFilter, LowpassFilter, PeakFilter,
    Compressor, Reverb, Chorus, Distortion, Gain, PitchShift,
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
```

> **Note:** if your `pedalboard` version expects `(num_samples, num_channels)` instead, the tests in Step 2 will fail on shape/attenuation — flip the `.T` calls. The test is the source of truth.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_dsp.py -q`
Expected: PASS (4 tests). If `test_lowpass_kills_treble` is borderline, the chain is wired; do not loosen the threshold without checking `apply_dsp` orientation.

- [ ] **Step 6: Commit**

```powershell
git add src/cyclops_voice/dsp.py tests/acoustics.py tests/test_dsp.py
git commit -m "feat: Cyclops DSP chain with presets + acoustic helpers"
```

---

### Task 5: Piper TTS wrapper + acoustic golden test

**Files:**
- Create: `src/cyclops_voice/tts.py`
- Test: `tests/test_acoustic_profile.py`

- [ ] **Step 1: Probe the installed piper-tts API**

Run:
```powershell
.\.venv\Scripts\python -c "import piper, inspect; from piper import PiperVoice; print([m for m in dir(PiperVoice) if not m.startswith('__')])"
```
Expected: a list including `load` and a synthesize method (`synthesize`, `synthesize_stream_raw`, or `synthesize_wav`). Note which exist — the wrapper below targets `synthesize_stream_raw` (yields int16 PCM bytes) with a `wave` fallback. If the names differ on your version, adapt `PiperTTS.synth` accordingly; the public interface (`synth(text)->mono float32`) must not change.

- [ ] **Step 2: Write `src/cyclops_voice/tts.py`**

```python
from __future__ import annotations
import io
import wave
from pathlib import Path
import numpy as np
from piper import PiperVoice


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

    def synth(self, text: str) -> np.ndarray:
        text = text.strip()
        if not text:
            return np.zeros(0, dtype=np.float32)
        pcm = self._synth_int16(text)
        return (pcm.astype(np.float32) / 32768.0)

    def _synth_int16(self, text: str) -> np.ndarray:
        # Preferred path: streaming raw int16 PCM.
        if hasattr(self._voice, "synthesize_stream_raw"):
            try:
                chunks = list(self._voice.synthesize_stream_raw(
                    text, length_scale=self.length_scale))
            except TypeError:
                chunks = list(self._voice.synthesize_stream_raw(text))
            return np.frombuffer(b"".join(chunks), dtype=np.int16).copy()
        # Fallback: synthesize to an in-memory WAV, then read PCM.
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            self._voice.synthesize(text, wf)
        buf.seek(0)
        with wave.open(buf, "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        return np.frombuffer(raw, dtype=np.int16).copy()
```

- [ ] **Step 3: Write the integration golden test `tests/test_acoustic_profile.py`**

```python
# tests/test_acoustic_profile.py
import os
import numpy as np
import pytest
from cyclops_voice.config import VoiceConfig, PRESETS
from cyclops_voice.dsp import apply_dsp
from tests.acoustics import band_fraction, spectral_centroid, lr_correlation, reverb_rt60

MODEL = VoiceConfig().model_path

pytestmark = pytest.mark.skipif(
    not os.path.exists(MODEL),
    reason="voice model not installed; run scripts/install_voice_model.py",
)

def test_rendered_voice_matches_cyclops_envelope():
    from cyclops_voice.tts import PiperTTS
    tts = PiperTTS(MODEL, length_scale=1.15)
    mono = tts.synth("Welcome aboard, Captain. All systems online. Hull integrity stable.")
    out = apply_dsp(mono, tts.sample_rate, PRESETS["game-accurate"], pitch_semitones=-1.0)
    sr = tts.sample_rate

    assert band_fraction(out, sr, 100, 300) >= 0.30      # low-mid dominant (target 0.45-0.52)
    assert band_fraction(out, sr, 3400, 8000) < 0.05     # treble nearly gone
    assert band_fraction(out, sr, 8000, sr // 2) < 0.01  # treble dead
    assert 350 <= spectral_centroid(out, sr) <= 700      # dark timbre
    assert lr_correlation(out) < 0.9                     # stereo width
    rt = reverb_rt60(out, sr)
    assert 0.3 <= rt <= 1.5                              # medium room
```

> The envelope bounds are slightly wider than the raw measured values (spec §2.3) to allow for the synthetic voice differing from the original actor while still landing in Cyclops territory. Tighten toward 0.45 / 400-550 Hz once you hear it and are happy.

- [ ] **Step 4: Install the model, then run the golden test**

Run:
```powershell
.\.venv\Scripts\python scripts\install_voice_model.py   # implemented in Task 16; or download manually
.\.venv\Scripts\python -m pytest tests/test_acoustic_profile.py -q
```
Expected: PASS once the model exists. If the model isn't installed yet, the test SKIPS — that's acceptable; revisit after Task 16. Listen to a render to sanity-check (`cyclops render ...` after Task 11/15).

- [ ] **Step 5: Commit**

```powershell
git add src/cyclops_voice/tts.py tests/test_acoustic_profile.py
git commit -m "feat: Piper TTS wrapper + acoustic golden test"
```

---

### Task 6: Audio player (queue with pause/stop/skip)

**Files:**
- Create: `src/cyclops_voice/player.py`
- Test: `tests/test_player.py`

Design: `Player` runs a worker thread that pulls PCM buffers for the current job and writes them to an injected `AudioSink` in small blocks, honoring pause/stop/skip events. Tests inject a `FakeSink` (records frames, no hardware). Production uses `SoundDeviceSink`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_player.py
import time
import threading
import numpy as np
from cyclops_voice.player import Player, AudioSink

class FakeSink(AudioSink):
    def __init__(self):
        self.frames = []
        self.closed = False
    def write(self, block: np.ndarray) -> None:
        self.frames.append(block.copy())
    def close(self) -> None:
        self.closed = True

def _buffers(n_buffers=3, n=2205):
    for i in range(n_buffers):
        yield (np.ones((n, 2), dtype=np.float32) * (i + 1) * 0.01)

def test_plays_all_buffers():
    sink = FakeSink()
    p = Player(sample_rate=22050, sink=sink)
    p.submit("job1", _buffers())
    p.wait_idle(timeout=5)
    total = sum(len(f) for f in sink.frames)
    assert total == 3 * 2205
    assert p.state == "idle"

def test_stop_halts_playback():
    sink = FakeSink()
    p = Player(sample_rate=22050, sink=sink)
    def slow():
        for i in range(50):
            time.sleep(0.01)
            yield np.ones((2205, 2), dtype=np.float32) * 0.01
    p.submit("job2", slow())
    time.sleep(0.05)
    p.stop()
    p.wait_idle(timeout=5)
    assert p.state == "idle"
    assert sum(len(f) for f in sink.frames) < 50 * 2205  # didn't play everything

def test_skip_moves_to_idle_when_queue_empty():
    sink = FakeSink()
    p = Player(sample_rate=22050, sink=sink)
    p.submit("job3", _buffers(n_buffers=10))
    p.skip()
    p.wait_idle(timeout=5)
    assert p.state == "idle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_player.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/cyclops_voice/player.py`**

```python
from __future__ import annotations
import queue
import threading
from typing import Iterator, Protocol
import numpy as np


class AudioSink(Protocol):
    def write(self, block: np.ndarray) -> None: ...
    def close(self) -> None: ...


class SoundDeviceSink:
    def __init__(self, sample_rate: int, device: str | int | None = None):
        import sounddevice as sd
        self._stream = sd.OutputStream(
            samplerate=sample_rate, channels=2, dtype="float32",
            device=device or None,
        )
        self._stream.start()

    def write(self, block: np.ndarray) -> None:
        self._stream.write(block)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


class Player:
    """Streams PCM buffers for one job at a time with pause/stop/skip control."""
    BLOCK = 1024  # frames per sink write

    def __init__(self, sample_rate: int, sink: AudioSink):
        self.sample_rate = sample_rate
        self._sink = sink
        self._jobs: "queue.Queue[tuple[str, Iterator[np.ndarray]]]" = queue.Queue()
        self._state = "idle"
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._skip = threading.Event()
        self._pause = threading.Event()
        self._idle = threading.Event(); self._idle.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def _set(self, s: str) -> None:
        with self._lock:
            self._state = s

    def submit(self, job_id: str, buffers: Iterator[np.ndarray]) -> None:
        self._idle.clear()
        self._jobs.put((job_id, buffers))

    def stop(self) -> None:
        self._stop.set()
        try:
            while True:
                self._jobs.get_nowait()
        except queue.Empty:
            pass

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def skip(self) -> None:
        self._skip.set()

    def wait_idle(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def _run(self) -> None:
        while True:
            try:
                job_id, buffers = self._jobs.get(timeout=0.1)
            except queue.Empty:
                if self._jobs.empty():
                    self._set("idle"); self._idle.set()
                continue
            self._stop.clear(); self._skip.clear()
            self._set("speaking")
            self._play_job(buffers)
            if self._jobs.empty():
                self._set("idle"); self._idle.set()

    def _play_job(self, buffers: Iterator[np.ndarray]) -> None:
        for buf in buffers:
            if self._stop.is_set() or self._skip.is_set():
                break
            buf = np.asarray(buf, dtype=np.float32)
            for i in range(0, len(buf), self.BLOCK):
                if self._stop.is_set() or self._skip.is_set():
                    return
                while self._pause.is_set() and not self._stop.is_set():
                    self._set("paused")
                    threading.Event().wait(0.05)
                self._set("speaking")
                self._sink.write(buf[i:i + self.BLOCK])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_player.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Manual hardware smoke (optional but recommended)**

Run:
```powershell
.\.venv\Scripts\python -c "import numpy as np; from cyclops_voice.player import Player, SoundDeviceSink; sr=22050; p=Player(sr, SoundDeviceSink(sr)); t=np.arange(sr)/sr; tone=(0.2*np.sin(2*np.pi*220*t)).astype('float32'); st=np.stack([tone,tone],1); p.submit('x', iter([st])); p.wait_idle(5)"
```
Expected: a 1-second 220 Hz tone from your speakers.

- [ ] **Step 6: Commit**

```powershell
git add src/cyclops_voice/player.py tests/test_player.py
git commit -m "feat: streaming audio player with pause/stop/skip"
```

---

### Task 7: SpeechEngine (orchestration + state)

**Files:**
- Create: `src/cyclops_voice/engine.py`
- Test: `tests/test_engine.py`

Design: `SpeechEngine` owns a `Player` and a generation worker. `speak()` chunks text, then a background thread synthesizes+DSPs each chunk and hands a generator of buffers to the player. `mode="interrupt"` stops current playback and clears the queue first.

- [ ] **Step 1: Write the failing test (uses fakes, no audio/model)**

```python
# tests/test_engine.py
import numpy as np
from cyclops_voice.engine import SpeechEngine
from cyclops_voice.config import CyclopsConfig, PRESETS

class FakeTTS:
    sample_rate = 22050
    def synth(self, text):
        return (np.ones(2205, dtype=np.float32) * 0.01)

class RecordingSink:
    def __init__(self): self.frames = []
    def write(self, block): self.frames.append(block.copy())
    def close(self): pass

def make_engine():
    cfg = CyclopsConfig()
    sink = RecordingSink()
    eng = SpeechEngine(tts=FakeTTS(), config=cfg, sink=sink,
                       dsp_apply=lambda mono, sr, preset, pitch_semitones=0.0:
                           np.stack([mono, mono], axis=1))
    return eng, sink

def test_speak_returns_job_and_plays():
    eng, sink = make_engine()
    job = eng.speak("One sentence. Two sentence.")
    assert isinstance(job, str) and job
    eng.wait_idle(timeout=5)
    assert sum(len(f) for f in sink.frames) > 0
    assert eng.status()["state"] == "idle"

def test_status_shape():
    eng, _ = make_engine()
    s = eng.status()
    assert set(s) == {"state", "current_text", "queue_len", "preset"}

def test_unknown_preset_raises():
    eng, _ = make_engine()
    try:
        eng.speak("hi", preset="nope")
        assert False, "expected KeyError"
    except KeyError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/cyclops_voice/engine.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```powershell
git add src/cyclops_voice/engine.py tests/test_engine.py
git commit -m "feat: SpeechEngine orchestration and state"
```

---

### Task 8: HTTP API (FastAPI)

**Files:**
- Create: `src/cyclops_voice/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server.py
from fastapi.testclient import TestClient
from cyclops_voice.server import create_app

class FakeEngine:
    def __init__(self): self.calls = []; self._state = "idle"
    def speak(self, text, preset=None, mode="interrupt"):
        self.calls.append(("speak", text, preset, mode)); self._state = "speaking"; return "job123"
    def stop(self): self._state = "idle"; self.calls.append(("stop",))
    def pause(self): self.calls.append(("pause",))
    def resume(self): self.calls.append(("resume",))
    def skip(self): self.calls.append(("skip",))
    def status(self):
        return {"state": self._state, "current_text": None, "queue_len": 0, "preset": "game-accurate"}

def client(token=""):
    eng = FakeEngine()
    app = create_app(eng, auth_token=token, version="0.1.0", model="m.onnx", sample_rate=22050)
    return TestClient(app), eng

def test_health():
    c, _ = client()
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True

def test_speak():
    c, eng = client()
    r = c.post("/speak", json={"text": "hello"})
    assert r.status_code == 200 and r.json()["job_id"] == "job123"
    assert eng.calls[0] == ("speak", "hello", None, "interrupt")

def test_speak_requires_text():
    c, _ = client()
    assert c.post("/speak", json={}).status_code == 422

def test_stop_status():
    c, eng = client()
    assert c.post("/stop").status_code == 200
    assert c.get("/status").json()["state"] == "idle"

def test_auth_token_enforced():
    c, _ = client(token="secret")
    assert c.post("/speak", json={"text": "x"}).status_code == 401
    assert c.post("/speak", json={"text": "x"},
                  headers={"X-Cyclops-Token": "secret"}).status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/cyclops_voice/server.py`**

```python
from __future__ import annotations
from typing import Literal
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1)
    preset: str | None = None
    mode: Literal["interrupt", "enqueue"] = "interrupt"


class RenderRequest(BaseModel):
    text: str = Field(min_length=1)
    preset: str | None = None
    path: str | None = None


def create_app(engine, auth_token: str = "", version: str = "0.1.0",
               model: str = "", sample_rate: int = 0) -> FastAPI:
    app = FastAPI(title="Cyclops Voice")

    def _auth(token: str | None):
        if auth_token and token != auth_token:
            raise HTTPException(status_code=401, detail="invalid token")

    @app.get("/health")
    def health():
        return {"ok": True, "version": version, "model": model, "sample_rate": sample_rate}

    @app.get("/status")
    def status():
        return engine.status()

    @app.get("/presets")
    def presets():
        from .config import PRESETS
        return {"presets": sorted(PRESETS), "active": engine.status()["preset"]}

    @app.post("/speak")
    def speak(req: SpeakRequest, x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token)
        try:
            job_id = engine.speak(req.text, preset=req.preset, mode=req.mode)
        except KeyError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"job_id": job_id, **engine.status()}

    @app.post("/stop")
    def stop(x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token); engine.stop(); return engine.status()

    @app.post("/pause")
    def pause(x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token); engine.pause(); return engine.status()

    @app.post("/resume")
    def resume(x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token); engine.resume(); return engine.status()

    @app.post("/skip")
    def skip(x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token); engine.skip(); return engine.status()

    @app.post("/render")
    def render(req: RenderRequest, x_cyclops_token: str | None = Header(default=None)):
        _auth(x_cyclops_token)
        from .export import render_to_wav
        path = render_to_wav(engine, req.text, preset=req.preset, path=req.path)
        return {"path": path}

    return app
```

> `/render` imports `export.render_to_wav` (Task 15). If you implement the API before export, the endpoint will only fail when called — tests above don't exercise it. Implement Task 15 before relying on `/render`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_server.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```powershell
git add src/cyclops_voice/server.py tests/test_server.py
git commit -m "feat: FastAPI HTTP API over the engine"
```

---

### Task 9: Daemon entry point

**Files:**
- Create: `src/cyclops_voice/daemon.py`

Wires config → PiperTTS → SpeechEngine → FastAPI → uvicorn, and starts the hotkey listener (Task 13) and optional tray (Task 14). Hardware/process-bound: verified by smoke run.

- [ ] **Step 1: Write `src/cyclops_voice/daemon.py`**

```python
from __future__ import annotations
import threading
from pathlib import Path
import uvicorn
from . import __version__
from .config import load_config, CyclopsConfig
from .tts import PiperTTS
from .engine import SpeechEngine
from .server import create_app


def build_engine(cfg: CyclopsConfig) -> SpeechEngine:
    tts = PiperTTS(cfg.voice.model_path, length_scale=cfg.voice.length_scale)
    return SpeechEngine(tts=tts, config=cfg)


def run_daemon(config_path: str | Path | None = None,
               enable_hotkey: bool = True, enable_tray: bool = True) -> None:
    cfg = load_config(config_path)
    engine = build_engine(cfg)
    app = create_app(
        engine, auth_token=cfg.service.auth_token, version=__version__,
        model=cfg.voice.model_path, sample_rate=engine.sample_rate,
    )

    if enable_hotkey:
        from .hotkey import start_hotkeys
        start_hotkeys(cfg)  # runs its own listener thread

    server = uvicorn.Server(uvicorn.Config(
        app, host=cfg.service.host, port=cfg.service.port, log_level="warning"))

    if enable_tray:
        from .tray import run_tray  # tray needs main thread; uvicorn -> worker thread
        t = threading.Thread(target=server.run, daemon=True)
        t.start()
        run_tray(cfg)          # blocks on main thread until quit
        server.should_exit = True
    else:
        server.run()


if __name__ == "__main__":
    run_daemon()
```

- [ ] **Step 2: Smoke test (after Tasks 13–14 exist; or run with flags off)**

Run (model must be installed; hotkey/tray off to isolate the API):
```powershell
.\.venv\Scripts\python -c "import threading,time,httpx; from cyclops_voice.daemon import run_daemon; threading.Thread(target=lambda: run_daemon(enable_hotkey=False, enable_tray=False), daemon=True).start(); time.sleep(3); print(httpx.get('http://127.0.0.1:7788/health').json())"
```
Expected: `{'ok': True, 'version': '0.1.0', ...}` printed.

- [ ] **Step 3: Commit**

```powershell
git add src/cyclops_voice/daemon.py
git commit -m "feat: daemon entry point wiring engine + API"
```

---

### Task 10: Shared HTTP client

**Files:**
- Create: `src/cyclops_voice/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client.py
import respx, httpx, pytest
from cyclops_voice.client import CyclopsClient

# respx is optional; if unavailable, use httpx.MockTransport (shown below).
def test_speak_posts_text():
    def handler(request):
        assert request.url.path == "/speak"
        import json; body = json.loads(request.content)
        assert body["text"] == "hello"
        return httpx.Response(200, json={"job_id": "j1", "state": "speaking",
                                         "current_text": "hello", "queue_len": 0,
                                         "preset": "game-accurate"})
    transport = httpx.MockTransport(handler)
    c = CyclopsClient(base_url="http://127.0.0.1:7788", transport=transport)
    out = c.speak("hello")
    assert out["job_id"] == "j1"

def test_health_false_when_unreachable():
    def handler(request): raise httpx.ConnectError("no daemon")
    transport = httpx.MockTransport(handler)
    c = CyclopsClient(base_url="http://127.0.0.1:7788", transport=transport)
    assert c.is_up() is False
```

> Remove the unused `respx`/`pytest` imports if you don't add respx; `httpx.MockTransport` is sufficient and ships with httpx.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/cyclops_voice/client.py`**

```python
from __future__ import annotations
import httpx


class CyclopsClient:
    def __init__(self, base_url: str = "http://127.0.0.1:7788",
                 token: str = "", transport: httpx.BaseTransport | None = None,
                 timeout: float = 5.0):
        headers = {"X-Cyclops-Token": token} if token else {}
        self._c = httpx.Client(base_url=base_url, headers=headers,
                               transport=transport, timeout=timeout)

    def is_up(self) -> bool:
        try:
            return self._c.get("/health").json().get("ok", False)
        except httpx.HTTPError:
            return False

    def speak(self, text: str, preset: str | None = None,
              mode: str = "interrupt") -> dict:
        r = self._c.post("/speak", json={"text": text, "preset": preset, "mode": mode})
        r.raise_for_status(); return r.json()

    def _post(self, path: str) -> dict:
        r = self._c.post(path); r.raise_for_status(); return r.json()

    def stop(self): return self._post("/stop")
    def pause(self): return self._post("/pause")
    def resume(self): return self._post("/resume")
    def skip(self): return self._post("/skip")

    def status(self) -> dict:
        r = self._c.get("/status"); r.raise_for_status(); return r.json()

    def render(self, text: str, preset: str | None = None,
               path: str | None = None) -> dict:
        r = self._c.post("/render", json={"text": text, "preset": preset, "path": path})
        r.raise_for_status(); return r.json()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_client.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```powershell
git add src/cyclops_voice/client.py tests/test_client.py
git commit -m "feat: shared HTTP client"
```

---

### Task 11: CLI

**Files:**
- Create: `src/cyclops_voice/cli.py`

`cyclops` entry (registered in `pyproject.toml` Task 1). Thin wrapper over `CyclopsClient`, plus `daemon`/`install-*` subcommands.

- [ ] **Step 1: Write `src/cyclops_voice/cli.py`**

```python
from __future__ import annotations
import argparse
import sys
from .client import CyclopsClient
from .config import load_config


def _client(args) -> CyclopsClient:
    cfg = load_config(args.config)
    base = f"http://{cfg.service.host}:{cfg.service.port}"
    return CyclopsClient(base_url=base, token=cfg.service.auth_token)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cyclops", description="Cyclops voice TTS")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("say", help="speak text (use - to read stdin)")
    s.add_argument("text")
    s.add_argument("--preset", default=None)
    s.add_argument("--enqueue", action="store_true")

    for name in ("stop", "pause", "resume", "skip", "status"):
        sub.add_parser(name)

    r = sub.add_parser("render", help="render text to a .wav file")
    r.add_argument("text"); r.add_argument("-o", "--out", default=None)
    r.add_argument("--preset", default=None)

    d = sub.add_parser("daemon", help="run the background service")
    d.add_argument("--no-hotkey", action="store_true")
    d.add_argument("--no-tray", action="store_true")

    sub.add_parser("install-model", help="download the en_US-ryan voice model")
    sub.add_parser("install-autostart", help="add a Startup-folder shortcut")

    args = p.parse_args(argv)

    if args.cmd == "daemon":
        from .daemon import run_daemon
        run_daemon(args.config, enable_hotkey=not args.no_hotkey,
                   enable_tray=not args.no_tray)
        return 0
    if args.cmd == "install-model":
        from scripts.install_voice_model import main as m; return m()
    if args.cmd == "install-autostart":
        from scripts.install_autostart import main as m; return m()

    c = _client(args)
    if args.cmd != "status" and not c.is_up():
        print("Cyclops daemon not running. Start it with: cyclops daemon", file=sys.stderr)
        return 1

    if args.cmd == "say":
        text = sys.stdin.read() if args.text == "-" else args.text
        out = c.speak(text, preset=args.preset,
                      mode="enqueue" if args.enqueue else "interrupt")
        print(out["job_id"]); return 0
    if args.cmd == "render":
        out = c.render(args.text, preset=args.preset, path=args.out)
        print(out["path"]); return 0
    if args.cmd in ("stop", "pause", "resume", "skip"):
        print(getattr(c, args.cmd)()["state"]); return 0
    if args.cmd == "status":
        import json; print(json.dumps(c.status(), indent=2)); return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke test the parser (no daemon needed)**

Run: `.\.venv\Scripts\python -m cyclops_voice.cli status`
Expected: prints a JSON status if the daemon is up, or exits cleanly attempting to reach it. `cyclops say --help` should show usage. (After `pip install -e .`, `cyclops --help` works directly.)

- [ ] **Step 3: Commit**

```powershell
git add src/cyclops_voice/cli.py
git commit -m "feat: cyclops CLI"
```

---

### Task 12: MCP server

**Files:**
- Create: `src/cyclops_voice/mcp_server.py`
- Test: `tests/test_mcp.py`

Exposes `speak`/`stop`/`status` tools over stdio; each calls the daemon's HTTP API via `CyclopsClient`. Test the underlying tool functions directly (transport-independent).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp.py
from cyclops_voice import mcp_server

class FakeClient:
    def __init__(self): self.calls = []
    def is_up(self): return True
    def speak(self, text, preset=None, mode="interrupt"):
        self.calls.append(("speak", text, preset)); return {"job_id": "j", "state": "speaking"}
    def stop(self): self.calls.append(("stop",)); return {"state": "idle"}
    def status(self): return {"state": "idle", "current_text": None, "queue_len": 0, "preset": "game-accurate"}

def test_speak_tool():
    fc = FakeClient()
    out = mcp_server.do_speak(fc, "Hull breach detected.", None)
    assert "speaking" in out.lower() or "j" in out
    assert fc.calls[0] == ("speak", "Hull breach detected.", None)

def test_speak_tool_daemon_down():
    class Down(FakeClient):
        def is_up(self): return False
    out = mcp_server.do_speak(Down(), "hi", None)
    assert "not running" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mcp.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/cyclops_voice/mcp_server.py`**

```python
from __future__ import annotations
from .client import CyclopsClient
from .config import load_config


def _client() -> CyclopsClient:
    cfg = load_config(None)
    return CyclopsClient(base_url=f"http://{cfg.service.host}:{cfg.service.port}",
                         token=cfg.service.auth_token)


def do_speak(client: CyclopsClient, text: str, preset: str | None) -> str:
    if not client.is_up():
        return "Cyclops daemon is not running. Start it with: cyclops daemon"
    out = client.speak(text, preset=preset)
    return f"Speaking ({out.get('state')}), job {out.get('job_id')}."


def do_stop(client: CyclopsClient) -> str:
    if not client.is_up():
        return "Cyclops daemon is not running."
    return f"Stopped. State: {client.stop().get('state')}."


def do_status(client: CyclopsClient) -> str:
    if not client.is_up():
        return "Cyclops daemon is not running."
    return str(client.status())


def main() -> None:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("cyclops-voice")
    client = _client()

    @mcp.tool()
    def speak(text: str, preset: str | None = None) -> str:
        """Read the given text aloud in the Cyclops submarine voice."""
        return do_speak(client, text, preset)

    @mcp.tool()
    def stop() -> str:
        """Stop any current Cyclops speech immediately."""
        return do_stop(client)

    @mcp.tool()
    def status() -> str:
        """Report the Cyclops voice service status."""
        return do_status(client)

    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
```

> If your installed `mcp` SDK exposes a different high-level API than `mcp.server.fastmcp.FastMCP`, keep `do_speak/do_stop/do_status` (tested) unchanged and adapt only `main()` to the SDK's server/stdio entry point.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_mcp.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```powershell
git add src/cyclops_voice/mcp_server.py tests/test_mcp.py
git commit -m "feat: MCP stdio server"
```

---

### Task 13: Global hotkey listener

**Files:**
- Create: `src/cyclops_voice/hotkey.py`

Captures the current selection (simulate Ctrl+C → read clipboard → restore clipboard) and POSTs it to the daemon. Hardware-bound; the testable core is `capture_selection()` with injected clipboard/keyboard fakes.

- [ ] **Step 1: Write `src/cyclops_voice/hotkey.py`**

```python
from __future__ import annotations
import time
from .client import CyclopsClient
from .config import CyclopsConfig


def capture_selection(copy_fn, get_clip, set_clip, settle: float = 0.12) -> str:
    """Copy the current selection and return it, restoring prior clipboard."""
    prev = ""
    try:
        prev = get_clip()
    except Exception:
        prev = ""
    set_clip("")          # sentinel so we can tell if copy produced nothing
    copy_fn()             # simulate Ctrl+C
    time.sleep(settle)
    try:
        text = get_clip()
    except Exception:
        text = ""
    try:
        set_clip(prev)    # restore
    except Exception:
        pass
    return text.strip()


def start_hotkeys(cfg: CyclopsConfig) -> None:
    import pyperclip
    from pynput import keyboard

    client = CyclopsClient(base_url=f"http://{cfg.service.host}:{cfg.service.port}",
                           token=cfg.service.auth_token)
    kb = keyboard.Controller()

    def _copy():
        kb.press(keyboard.Key.ctrl); kb.press('c')
        kb.release('c'); kb.release(keyboard.Key.ctrl)

    def on_read():
        text = capture_selection(_copy, pyperclip.paste, pyperclip.copy)
        if text and client.is_up():
            try:
                client.speak(text)
            except Exception:
                pass

    def on_stop():
        if client.is_up():
            try:
                client.stop()
            except Exception:
                pass

    def hk(combo: str) -> str:
        return "+".join("<" + p + ">" if p in ("ctrl", "alt", "shift", "cmd") else p
                        for p in combo.lower().split("+"))

    listener = keyboard.GlobalHotKeys({
        hk(cfg.hotkeys.read_selection): on_read,
        hk(cfg.hotkeys.stop): on_stop,
    })
    listener.daemon = True
    listener.start()
```

- [ ] **Step 2: Manual verification**

Start the daemon (`cyclops daemon`), select text in any app (Notepad/Obsidian/Claude), press `Ctrl+Alt+R`. Expected: the selection is read aloud in the Cyclops voice. Press `Ctrl+Alt+S` to stop. Confirm your clipboard contents are unchanged afterward.

- [ ] **Step 3: Commit**

```powershell
git add src/cyclops_voice/hotkey.py
git commit -m "feat: global hotkey selection reader"
```

---

### Task 14: System tray (optional)

**Files:**
- Create: `src/cyclops_voice/tray.py`

- [ ] **Step 1: Write `src/cyclops_voice/tray.py`**

```python
from __future__ import annotations
from .client import CyclopsClient
from .config import CyclopsConfig


def _icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), (10, 30, 40))
    d = ImageDraw.Draw(img)
    d.ellipse((12, 12, 52, 52), outline=(0, 200, 255), width=4)
    d.ellipse((26, 26, 38, 38), fill=(0, 200, 255))  # "cyclops eye"
    return img


def run_tray(cfg: CyclopsConfig) -> None:
    import pystray
    client = CyclopsClient(base_url=f"http://{cfg.service.host}:{cfg.service.port}",
                           token=cfg.service.auth_token)

    def _safe(fn):
        def w(icon, item):
            try: fn()
            except Exception: pass
        return w

    icon = pystray.Icon(
        "cyclops", _icon_image(), "Cyclops Voice",
        menu=pystray.Menu(
            pystray.MenuItem("Stop", _safe(client.stop)),
            pystray.MenuItem("Pause", _safe(client.pause)),
            pystray.MenuItem("Resume", _safe(client.resume)),
            pystray.MenuItem("Quit", lambda icon, item: icon.stop()),
        ),
    )
    icon.run()  # blocks until Quit
```

- [ ] **Step 2: Manual verification**

Run `cyclops daemon`. Expected: a tray icon appears; "Stop" halts speech; "Quit" exits the daemon.

- [ ] **Step 3: Commit**

```powershell
git add src/cyclops_voice/tray.py
git commit -m "feat: optional system tray"
```

---

### Task 15: Offline render-to-WAV export

**Files:**
- Create: `src/cyclops_voice/export.py`

- [ ] **Step 1: Write `src/cyclops_voice/export.py`**

```python
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
```

- [ ] **Step 2: Manual verification (model required)**

Run:
```powershell
.\.venv\Scripts\python -c "from cyclops_voice.config import load_config; from cyclops_voice.daemon import build_engine; e=build_engine(load_config(None)); from cyclops_voice.export import render_to_wav; print(render_to_wav(e, 'Welcome aboard, Captain.', path='test.wav'))"
```
Expected: prints the path to `test.wav`; play it to confirm the Cyclops voice.

- [ ] **Step 3: Commit**

```powershell
git add src/cyclops_voice/export.py
git commit -m "feat: offline render-to-wav export"
```

---

### Task 16: Setup scripts (model download + autostart)

**Files:**
- Create: `scripts/__init__.py`, `scripts/install_voice_model.py`, `scripts/install_autostart.py`

- [ ] **Step 1: Create `scripts/__init__.py`**

```python
```

- [ ] **Step 2: Write `scripts/install_voice_model.py`**

```python
"""Download the en_US-ryan Piper voice model into ./models."""
from __future__ import annotations
import sys
from pathlib import Path
import urllib.request

BASE = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "en/en_US/ryan/medium/")
FILES = ["en_US-ryan-medium.onnx", "en_US-ryan-medium.onnx.json"]


def main() -> int:
    models = Path("models"); models.mkdir(exist_ok=True)
    for name in FILES:
        dest = models / name
        if dest.exists():
            print(f"exists: {dest}"); continue
        url = BASE + name + "?download=true"
        print(f"downloading {url}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            print(f"FAILED: {e}\nManually download {BASE+name} -> {dest}", file=sys.stderr)
            return 1
        print(f"saved: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Verify the model downloads**

Run: `.\.venv\Scripts\python scripts\install_voice_model.py`
Expected: `models\en_US-ryan-medium.onnx` (~60 MB) and its `.json` exist. Then re-run the golden test from Task 5 — it should now PASS, not skip.

- [ ] **Step 4: Write `scripts/install_autostart.py`**

```python
"""Create a Startup-folder shortcut that launches the daemon with pythonw (no console)."""
from __future__ import annotations
import os
import sys
from pathlib import Path


def main() -> int:
    startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
    startup.mkdir(parents=True, exist_ok=True)
    venv = Path(sys.prefix)
    pythonw = venv / "Scripts" / "pythonw.exe"
    target = pythonw if pythonw.exists() else Path(sys.executable)
    workdir = Path.cwd()
    lnk = startup / "CyclopsVoice.lnk"

    ps = f'''
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{lnk}")
$s.TargetPath = "{target}"
$s.Arguments = "-m cyclops_voice.cli daemon"
$s.WorkingDirectory = "{workdir}"
$s.WindowStyle = 7
$s.Save()
'''
    import subprocess
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print(f"created {lnk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Verify the shortcut is created**

Run: `.\.venv\Scripts\python scripts\install_autostart.py`
Expected: prints `created ...CyclopsVoice.lnk`; the shortcut exists in the Startup folder. (Log out/in later to confirm autostart.)

- [ ] **Step 6: Commit**

```powershell
git add scripts/__init__.py scripts/install_voice_model.py scripts/install_autostart.py
git commit -m "feat: model download and autostart setup scripts"
```

---

### Task 17: README + Claude Desktop integration + full test run

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# Cyclops Voice

System-wide, offline TTS that reads text aloud in the Subnautica Cyclops submarine voice
(Piper neural TTS + a measured DSP chain). Drive it from a global hotkey, a CLI, an HTTP
API, or an MCP server (Claude Desktop).

## Setup (Windows, Python 3.12)
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python scripts\install_voice_model.py
copy config.example.toml "$env:APPDATA\CyclopsVoice\config.toml"   # optional
```

## Run
```powershell
cyclops daemon                 # background service (hotkey + tray + API)
cyclops say "All systems online."
cyclops stop | pause | resume | skip | status
cyclops render "Hull integrity stable." -o out.wav --preset heavy
cyclops install-autostart      # start on login
```
Hotkeys: `Ctrl+Alt+R` read selection, `Ctrl+Alt+S` stop. Presets: `game-accurate`, `subtle`, `heavy`.

## Open Interpreter / scripts
Shell out to `cyclops say "..."`, or POST to `http://127.0.0.1:7788/speak` with `{"text": "..."}`.

## Claude Desktop (MCP)
Add to `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "cyclops-voice": {
      "command": "X:\\Projects\\SubnauticaVoice\\.venv\\Scripts\\python.exe",
      "args": ["-m", "cyclops_voice.mcp_server"]
    }
  }
}
```
The daemon must be running. Claude won't auto-narrate replies unless you instruct it to call
the `speak` tool — otherwise use the select-text + hotkey path.

## How the voice was tuned
The DSP preset was derived by measuring real Cyclops audio (spectrum, pitch, reverb, stereo
width). See `docs/superpowers/specs/2026-05-29-cyclops-voice-tts-design.md` §2.
````

- [ ] **Step 2: Run the full test suite**

Run: `.\.venv\Scripts\python -m pytest -q`
Expected: all unit tests PASS; `test_acoustic_profile.py` PASSES if the model is installed (else SKIPS).

- [ ] **Step 3: End-to-end manual check**

Start `cyclops daemon`; select text in Obsidian and press `Ctrl+Alt+R`; run `cyclops say "Flank speed engaged."`; configure Claude Desktop and have Claude call the `speak` tool. Confirm all three surfaces produce Cyclops-voiced audio and share one stop (`Ctrl+Alt+S` / tray / `cyclops stop`).

- [ ] **Step 4: Commit**

```powershell
git add README.md
git commit -m "docs: README and Claude Desktop integration"
```

---

## Self-Review (completed during planning)

**1. Spec coverage:**
- §1 use case (read anywhere, programmatic) → Tasks 9–13 ✓
- §2 measured voice profile → encoded in presets (Task 2) + golden test (Task 5) ✓
- §3 DSP chain (HPF, low-mid boost, low-pass, comp, stereo reverb, optional chorus/drive, pitch) → Task 4 ✓
- §4 architecture (daemon + thin clients) → Tasks 7–13 ✓
- §5 interfaces (HTTP/CLI/MCP) → Tasks 8, 11, 12 ✓
- §6 concurrency (worker + player threads, interrupt) → Tasks 6, 7 ✓
- §7 config schema → Task 2 ✓
- §8 error handling (missing model, daemon-down, empty selection, clipboard restore) → Tasks 5, 11, 13 ✓
- §9 testing incl. acoustic golden test → Tasks 4, 5 + per-task tests ✓
- §10 deployment/autostart/repo layout → Tasks 1, 16 ✓
- §10 honest notes (MCP narration, localhost+token) → Tasks 8 (auth), 17 (README) ✓

**2. Placeholder scan:** No "TBD"/"implement later". Every code step shows complete code; library-version adaptation points (piper-tts, mcp, pedalboard channel order) are guarded by tests that are the source of truth, not placeholders.

**3. Type/name consistency:** `apply_dsp(mono, sr, preset, pitch_semitones=)` consistent across dsp/engine/export. `Player.submit/stop/pause/resume/skip/state/wait_idle` consistent across player/engine. `SpeechEngine.speak/stop/pause/resume/skip/status/wait_idle/sample_rate/config/tts` consistent across engine/server/export/daemon. Status object keys `{state,current_text,queue_len,preset}` consistent across engine/server/client. `CyclopsClient` methods consistent across cli/mcp/hotkey/tray.

**Known sequencing note:** `/render` (Task 8) imports `export` (Task 15); the daemon (Task 9) imports `hotkey` (Task 13) and `tray` (Task 14). Implement in task order or run the daemon with `--no-hotkey --no-tray` until those exist. This is intentional dependency direction, not a gap.
