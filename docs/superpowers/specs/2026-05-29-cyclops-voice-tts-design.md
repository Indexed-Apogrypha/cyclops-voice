# Cyclops Voice — System-Wide TTS Service (Design Spec)

- **Date:** 2026-05-29
- **Status:** Approved design — ready for implementation planning
- **Owner:** matthew88harper@gmail.com
- **Working dir:** `X:\Projects\SubnauticaVoice`

---

## 1. Summary

A persistent, **offline, system-wide text-to-speech service for Windows** that reads arbitrary
text aloud in the voice of the **Cyclops submarine AI from Subnautica**. It behaves like a
"Read Aloud" browser extension, but OS-wide: read Obsidian notes, read Claude Desktop responses,
and be driven programmatically by tools like Open Interpreter.

The voice is produced by **neural TTS (Piper) + a measured DSP chain** — which is essentially how
the original in-game voice was made (a heavily-processed TTS voice). We are **evoking** the voice,
not cloning the actor: 100% local, no copyrighted audio shipped, no legal exposure.

### Goals
- One always-running background service that any app/script can send text to.
- Three control surfaces: **global hotkey**, **local HTTP API + CLI**, **MCP server**.
- Low-latency, sentence-streaming playback with unified play/pause/stop/skip.
- A "game-accurate" Cyclops voice, with tunable presets.

### Non-goals (YAGNI)
- **No voice cloning** of the real actor (copyright/ethics; out of scope).
- **No cloud TTS** (must be offline/local).
- **No clipboard auto-read** mode (explicitly declined).
- **No full GUI** beyond an optional system-tray icon.
- **Windows-first**; cross-platform is a non-goal for v1 (the design avoids gratuitous lock-in but is not tested elsewhere).

---

## 2. Voice target (measured)

The DSP recipe was derived by measuring two real reference clips (a clean "Welcome aboard,
Captain" line and a ~130 s multi-line compilation) with an acoustic analysis script
(numpy/scipy: pitch tracking, Welch LTAS, dynamics, Schroeder reverb decay, stereo correlation).

### 2.1 Measured numbers

| Metric | Single line | Compilation | Notes / confidence |
|---|---|---|---|
| Format | 48 kHz stereo | 48 kHz stereo | YouTube re-encode; gross traits survive |
| F0 (pitch) median | 145.5 Hz (small sample) | **110.6 Hz** (IQR 78–147, n=1866) | Male ~110 Hz. **High** |
| Spectral peak | ~146 Hz | ~146 Hz | Fundamental region |
| Centroid | 416 Hz | 528 Hz | Very dark. **High** |
| 5–95% energy band | 76–1172 Hz | 70–1682 Hz | Almost everything < ~1.7 kHz |
| Band 100–300 Hz | **52.4%** | **45.5%** | Dominant trait. **High** |
| Band 3.4–8 kHz | 1.0% | 1.8% | Treble nearly gone |
| Band >8 kHz | 0.1% | 0.2% | Treble dead |
| Crest factor | 18.8 dB | 19.9 dB | Not heavily compressed. **Low** (silence-gap caveat) |
| Reverb RT60 (est.) | ~554 ms | ~973 ms | Medium metallic room. **Med** |
| L/R correlation | 0.639 | 0.757 | Real stereo width. **High** |

### 2.2 Consolidated voice profile
- **Timbre:** dark, bass-forward. ~45–52% of energy in 100–300 Hz; centroid ~420–530 Hz; treble
  rolled off steeply above ~3 kHz, effectively nothing above 8 kHz. "Deep voice through a large
  speaker inside a metal hull."
- **Pitch:** adult male, fundamental ~110 Hz (range ~75–150 Hz). The "deep" impression is
  **EQ- and pacing-driven**, not from an unusually low pitch.
- **Pacing:** slow, deliberate, evenly spaced phrasing.
- **Space:** genuine **stereo reverb**, RT60 ≈ 0.6–1.0 s, decorrelated L/R (corr ~0.64–0.76).
- **Dynamics:** moderate/natural — not aggressively limited.
- **Modulation:** **no solid evidence of flanger/chorus on the voice** — the periodic amplitude
  detected (0.25–1 Hz) is phrasing cadence, not an effect LFO. Width is explained by the reverb.

### 2.3 Target acoustic envelope (used by the golden test in §8)
- 100–300 Hz energy fraction: **≥ 40%** (target band 45–52%)
- >8 kHz energy fraction: **< 0.5%**
- 3.4–8 kHz energy fraction: **< 3%**
- Spectral centroid: **400–550 Hz**
- Reverb RT60: **0.5–1.1 s**
- Post-reverb L/R correlation: **< 0.85** (stereo width present)

---

## 3. DSP chain (`dsp.py`)

Base voice: Piper `en_US-ryan` (calm male), `length_scale` raised slightly for deliberate pacing,
optional −1 to −2 semitone pitch shift. Then the **"game-accurate" preset** (the default):

1. **High-pass** ~60 Hz — remove rumble, keep body.
2. **Low-mid boost** — broad bell/low-shelf centered ~150–250 Hz, **+4 to +8 dB**. *(the core trait)*
3. **Low-pass** ~3.0–3.5 kHz — kill the treble (the muffled metal-speaker character).
4. **Compressor** ~2.5:1, gentle — steady "PA announcement" level, do not squash.
5. **Stereo reverb** — medium metallic room/plate, RT60 ~0.7–0.9 s, moderate wet, decorrelated width.
6. *(optional)* faint **chorus** for width and/or light **saturation** for comms grit.

Every stage maps 1:1 to a `pedalboard` plugin
(`HighpassFilter`, `PeakFilter`/`LowShelfFilter`, `LowpassFilter`, `Compressor`, `Reverb`,
`Chorus`, `Distortion`, `Gain`), so the chain is fully parameter-driven.

**Mono→stereo:** Piper output is mono; duplicate to 2 channels before the reverb so the stereo
width/decorrelation takes effect. Internal sample rate = Piper model rate (e.g. 22.05 kHz);
optionally upsample to 44.1 kHz before reverb for a smoother tail.

### Presets
- `game-accurate` — default; the measured recipe above.
- `subtle` — lighter low-mid boost, higher low-pass (~5 kHz), less reverb; for long reading sessions.
- `heavy` — more reverb + saturation + optional flanger; maximum machine character.

---

## 4. Architecture (Approach A: daemon + thin clients)

```
  Obsidian / Claude / any app        Open Interpreter / scripts      Claude Desktop
        | (select text)                       | (cyclops say)              | (MCP tool)
        v                                      v                           v
  +-------------+                       +-------------+             +--------------+
  | hotkey.py   |                       |   cli.py    |             | mcp_server.py|
  | (listener)  |                       | (HTTP client)|            | (HTTP client)|
  +------+------+                       +------+------+             +------+-------+
         \________________________  HTTP (127.0.0.1) ________________________/
                                          |
                                   +------v------+
                                   |  server.py  |  FastAPI
                                   +------+------+
                                          |
                                   +------v------+
                                   |  engine.py  |  SpeechEngine (single source of truth)
                                   +--+-------+--+
                          pipeline.py |       | player.py
                    (tts+dsp worker)  |       | (sounddevice queue)
                       tts.py  dsp.py |       |
                                      v       v
                                   speakers (gapless, streamed)
```

The **daemon** (`daemon.py`, launched via `pythonw` = no console) hosts the engine, the FastAPI
server, the hotkey listener, and an optional tray icon, all in one process. The model loads **once**
and stays warm. The CLI and MCP server are separate processes that are pure HTTP clients.

### 4.1 Components

| Module | Responsibility | Key deps |
|---|---|---|
| `config.py` | Load/validate TOML config; presets; paths | tomllib |
| `tts.py` | Piper → mono PCM (numpy float32); model loaded once | piper-tts / onnxruntime |
| `dsp.py` | Cyclops chain + presets (§3) | pedalboard, numpy |
| `chunker.py` | Text → sentence-sized chunks; length caps | stdlib `re` |
| `pipeline.py` | text → chunks → (tts→dsp) → PCM buffers; worker runs 1–2 chunks ahead | tts, dsp, chunker |
| `player.py` | Playback queue: play/pause/resume/stop/skip; owns the output stream | sounddevice |
| `engine.py` | `SpeechEngine`: job/state machine (idle/speaking/paused), interrupt vs enqueue | pipeline, player |
| `server.py` | FastAPI app exposing the engine | fastapi, uvicorn |
| `daemon.py` | Entry: start engine + uvicorn + hotkey (+ tray) | all |
| `hotkey.py` | Global hotkey → simulate Ctrl+C → read clipboard → POST `/speak`; restore clipboard | pynput, pyperclip, httpx |
| `cli.py` | `cyclops` command → HTTP client | httpx, argparse/click |
| `mcp_server.py` | MCP **stdio** server; tools call the HTTP API | mcp SDK, httpx |
| `tray.py` | Optional tray icon: status + stop/quit | pystray, Pillow |
| `export.py` | Optional offline "render to .wav" (pedalboard or your ffmpeg/sox chain) | pedalboard / ffmpeg+sox |

Design intent: every module has one purpose and a narrow interface, so each can be implemented and
tested in isolation and handed to a separate coding agent.

---

## 5. Control-surface interfaces

### 5.1 HTTP API (bind `127.0.0.1` only)
| Method | Path | Body / params | Returns |
|---|---|---|---|
| POST | `/speak` | `{text, preset?, mode?: "interrupt"\|"enqueue"}` | `{job_id, state}` |
| POST | `/stop` | — | `{state}` |
| POST | `/pause` | — | `{state}` |
| POST | `/resume` | — | `{state}` |
| POST | `/skip` | — | `{state}` (skip current utterance) |
| GET | `/status` | — | `{state, current_text, queue_len, preset}` |
| GET | `/health` | — | `{ok, version, model, sample_rate}` |
| GET | `/presets` | — | `{presets: [...], active}` |
| POST | `/render` | `{text, preset?, path?}` | `{path}` (offline export) |

`mode` default = **`interrupt`** (stop current + speak new), since the common case is "read this
selection now." `enqueue` appends.

### 5.2 CLI (`cyclops`)
```
cyclops say "All systems online."      # or:  echo "..." | cyclops say -
cyclops stop | pause | resume | skip | status
cyclops render "Hull integrity stable." -o out.wav [--preset heavy]
cyclops daemon                         # start the background service
cyclops install-model                  # download the ryan voice model
cyclops install-autostart              # add Startup-folder shortcut
```
The CLI is what Open Interpreter shells out to (it may also hit the HTTP API directly).

### 5.3 MCP server (stdio)
Tools (thin wrappers over the HTTP API):
- `speak(text: str, preset?: str) -> status`
- `stop() -> status`
- `status() -> status`

Registered in Claude Desktop's `claude_desktop_config.json`. If the daemon is not running, the
tool returns an actionable error (and may optionally auto-start it via a health-check then spawn).

---

## 6. Concurrency model
Daemon threads:
- **uvicorn / asyncio** — HTTP server.
- **generation worker** — runs tts+dsp, staying 1–2 chunks ahead of playback.
- **playback** — sounddevice stream/queue.
- **hotkey listener** — pynput listener.
- *(optional)* **tray** — pystray (note: on Windows pystray may need the main thread; the plan
  resolves the exact thread layout, e.g. tray on main thread + uvicorn in a worker thread).

Engine state guarded by a lock; `stop`/`pause` implemented as events checked by the worker and the
player. New `/speak` in `interrupt` mode signals stop, drains the queue, then starts the new job.

**Latency budget:** first audio < ~1 s. Achieved via sentence chunking (start chunk 1 immediately)
+ warm model + generate-ahead worker.

---

## 7. Configuration
Location: `%APPDATA%\CyclopsVoice\config.toml` (override via `--config`). Example:
```toml
[service]
host = "127.0.0.1"
port = 7788
auth_token = ""              # optional; if set, clients must send it (localhost hardening)

[voice]
model_path = "models/en_US-ryan-medium.onnx"
length_scale = 1.15          # >1 = slower/more deliberate
pitch_semitones = -1
preset = "game-accurate"

[hotkeys]
read_selection = "ctrl+alt+r"
stop = "ctrl+alt+s"

[audio]
output_device = ""           # empty = system default
sample_rate = 0              # 0 = use model rate
```
Presets are defined in code (`dsp.py`); config selects the active one and can override params.

---

## 8. Testing strategy
- **Unit:** `chunker` (sentence boundaries, length caps, edge cases), `engine` (state-machine
  transitions: idle→speaking→paused→idle, interrupt, skip), `config` (load/validate/defaults).
- **Acoustic golden test** (`test_dsp.py`): render a fixed phrase through the chain, run the §2.3
  measurements on the output, and assert they fall inside the **target acoustic envelope**
  (100–300 Hz ≥ 40%, >8 kHz < 0.5%, centroid 400–550 Hz, RT60 0.5–1.1 s, post-reverb L/R corr
  < 0.85). This is a regression test that the voice still "sounds like the Cyclops." Reuse the
  analysis approach from the reference-profiling script.
- **API:** FastAPI `TestClient` for every endpoint + error paths.
- **CLI / MCP:** run against a test server; assert correct HTTP calls and output.
- DSP/TTS unit tests use synthetic signals (sine/impulse/noise) so they don't depend on audio
  hardware; playback is mocked in CI.

---

## 9. Deployment
- Python project (`pyproject.toml`) in a **dedicated Python 3.12 venv** — *not* the system
  Python 3.14, because `pedalboard` / `sounddevice` / `onnxruntime` wheels are most reliably
  available on 3.12. (The implementation plan must verify wheel availability before pinning.)
- Bundled tools already present on this machine: `ffmpeg`, `ffprobe`, `sox`, `piper.exe`. The
  daemon uses the Python `piper-tts`/onnxruntime path for the warm model; `piper.exe` and
  ffmpeg/sox remain available for the optional `export.py` path.
- `scripts/install_voice_model.py` downloads `en_US-ryan` from the Piper voices repo.
- `scripts/install_autostart.py` creates a Startup-folder shortcut to `pythonw daemon.py`.
- Claude Desktop integration: add `mcp_server.py` to `claude_desktop_config.json`.

### Proposed repo layout
```
cyclops-voice/
  pyproject.toml
  README.md
  config.example.toml
  src/cyclops_voice/
    __init__.py  config.py  tts.py  dsp.py  chunker.py  pipeline.py
    player.py  engine.py  server.py  daemon.py  hotkey.py  tray.py
    cli.py  mcp_server.py  export.py
  models/                       # downloaded voice model(s)
  tests/
    test_chunker.py  test_dsp.py  test_engine.py  test_server.py  test_cli.py
  scripts/
    install_voice_model.py  install_autostart.py
```

---

## 10. Honest notes / expectation-setting
- **Claude Desktop via MCP** grants Claude the *ability* to speak; it will not auto-narrate every
  reply unless instructed (e.g. a project instruction telling it to call `speak` with its answer).
  The zero-setup path for "read Claude's answer" remains: select text → hotkey.
- **Security:** the API is localhost-only, but any local process can call it. An optional
  `auth_token` header is provided as hardening (off by default).
- **Python 3.14 caveat:** system Python is 3.14; some native wheels may lag. Pin the project venv
  to 3.12 (or whatever the plan verifies supports all native deps).

---

## 11. Defaults (all easily changed in config)
- Port: `7788`
- Hotkeys: `Ctrl+Alt+R` (read selection), `Ctrl+Alt+S` (stop)
- Preset: `game-accurate`
- `/speak` mode: `interrupt`
- Voice: `en_US-ryan-medium`, `length_scale` 1.15, pitch −1 semitone

---

## 12. Tech stack
Python 3.12 · `piper-tts`/`onnxruntime` (TTS) · `pedalboard` (DSP) · `sounddevice` (playback) ·
`fastapi` + `uvicorn` (API) · `pynput` + `pyperclip` (hotkey/clipboard) · official `mcp` SDK
(MCP server) · `httpx` (clients) · `pystray` + `Pillow` (optional tray) · `pytest` (tests) ·
`ffmpeg`/`sox`/`piper.exe` (optional export path; already installed).
