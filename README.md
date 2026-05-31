# Cyclops Voice

System-wide, offline TTS that reads text aloud in the Subnautica Cyclops submarine AI voice.
Piper neural TTS + a tuned DSP chain (matched to the original game audio via a Gemini-as-judge
loop). Works anywhere on Windows: Obsidian, Claude Desktop, Open Interpreter, any app.

---

## Quick start — standalone exe

> **No Python required.** Download `CyclopsVoice.exe`, double-click, done.

1. Download **[CyclopsVoice.exe](https://github.com/Indexed-Apogrypha/cyclops-voice/releases)** (~71 MB, one-file, no install)
2. Double-click — the console window opens, downloads the 60 MB voice model on first run, then starts the daemon
3. Select text in any app → `Ctrl+Alt+R`

The model is cached to `%APPDATA%\CyclopsVoice\models\` after the first run (~2 s cold start
thereafter). An optional `config.toml` in `%APPDATA%\CyclopsVoice\` overrides any defaults.

---

## How it works

One background daemon owns a warm Piper voice model and the Cyclops DSP chain. Several
surfaces drive it:

- **Global hotkey** — select text in any app, press `Ctrl+Alt+R`
- **Double right-click** — read the sentence (or paragraph) under the cursor, no selection
  needed (via Windows UI Automation; works in browsers and most native apps)
- **Settings GUI** — a native window (tray → **Settings…**) to tune voice, effects, hotkeys,
  the read gesture, and app behavior, applied live with no restart
- **CLI / scripts** — `cyclops say "Hull integrity stable."`
- **MCP server** — Claude Desktop calls the `speak` tool directly

The voice pipeline: Piper neural TTS → WORLD hard pitch quantization (chromatic F0 snap, -2
semitone register) → envelope-gated rasp → pedalboard DSP board (highpass, low-mid boost,
lowpass, compression, distortion, bitcrush, reverb) → PA presence peak. The DSP recipe was
reverse-engineered from actual Cyclops audio. Full spec in `docs/superpowers/specs/`.

---

## Source setup

**Requires Python 3.12.** (`pedalboard`/`sounddevice` wheels are pinned to 3.12.)

```powershell
# 1. Create venv and install
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"

# 2. Download the en_US-ryan voice model (~60 MB)
.\.venv\Scripts\python scripts\install_voice_model.py

# 3. (Optional) copy and edit config
copy config.example.toml "$env:APPDATA\CyclopsVoice\config.toml"
```

---

## Usage

```powershell
# Start the background service (hotkey + tray + API, port 7788)
cyclops daemon

# Open the settings window (also on the tray menu as "Settings…")
cyclops gui

# Speak text
cyclops say "All systems online."
echo "Multi-line text" | cyclops say -

# Playback control
cyclops stop
cyclops pause
cyclops resume
cyclops skip
cyclops status

# Render to .wav
cyclops render "Hull integrity stable." -o out.wav
cyclops render "Flank speed engaged." --preset heavy -o heavy.wav

# First-run model download (source installs only; exe does this automatically)
cyclops install-model

# Start on Windows login
cyclops install-autostart
```

**Hotkeys** (configurable in the GUI or `config.toml`):
- `Ctrl+Alt+R` — read current selection from any app
- `Ctrl+Alt+S` — stop
- `Ctrl+Alt+P` — pause / resume
- **Double right-click** — read the sentence/paragraph under the cursor (configurable;
  defaults to a context-menu auto-dismiss)

**Presets:**

| Preset | Description |
|---|---|
| `game-accurate-v2` | **Default / shipped.** WORLD pitch quantization + rasp + full DSP board + PA presence. Closest to the real Cyclops voice. |
| `game-accurate` | Original measured DSP chain, no WORLD processing. Preserved for regression testing. |
| `subtle` | Light processing, good for long reading sessions. |
| `heavy` | More reverb + saturation. |

---

## HTTP API

```python
import httpx
# Speak
httpx.post("http://127.0.0.1:7788/speak", json={"text": "Dive, dive, dive."})
# Render to file
httpx.post("http://127.0.0.1:7788/render", json={"text": "Hull integrity stable."})
```

Full API: `GET /health /status /presets /config /audio/devices` ·
`POST /speak /stop /pause /resume /skip /render /config /autostart`. The settings GUI is
served at `GET /ui/` and live-applies edits through `POST /config`.

Optional token auth: set `auth_token` in config, then send `X-Cyclops-Token: <token>`.

---

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

The daemon must be running first. Available tools: `speak(text, preset?)`, `stop()`, `status()`.

> **Note:** Claude won't auto-narrate its own replies unless you add a project instruction
> telling it to call the `speak` tool with its response. The zero-setup path for reading
> Claude's answers is: select the text → `Ctrl+Alt+R`.

---

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
# 64 passed — includes acoustic golden test that verifies the DSP output
# matches the measured Cyclops voice profile (low-mid dominance, treble rolloff, stereo width)
```

---

## Build the exe yourself

```powershell
.\.venv\Scripts\python -m pip install -e ".[build]"
.\.venv\Scripts\python scripts\build_exe.py --clean
# → dist/CyclopsVoice.exe (~71 MB)
```

---

## Config reference (`config.example.toml`)

```toml
[service]
host = "127.0.0.1"
port = 7788
auth_token = ""           # optional; clients send X-Cyclops-Token header

[voice]
# model_path auto-resolves: ./models in source, %APPDATA%\CyclopsVoice\models in exe
length_scale = 1.22       # >1 = slower / more deliberate
pitch_semitones = 0.0     # register handled by WORLD in the default preset
preset = "game-accurate-v2"

[voice.effects]            # high-level overrides layered on the preset (omit = use preset)
# reverb_wet = 0.24
# rasp_amount = 0.10
# drive_db = 4.0
# presence_gain_db = 3.0

[hotkeys]
read_selection = "ctrl+alt+r"
stop = "ctrl+alt+s"
pause_resume = "ctrl+alt+p"

[read]                     # double-right-click read-under-cursor
trigger = "double_rmb"     # double_rmb | modifier_rmb | off
modifier = "ctrl"          # used when trigger = modifier_rmb
mode = "sentence"          # sentence | paragraph
auto_dismiss_menu = true   # send Esc to close the context menu after grabbing text
max_chars = 0              # 0 = unlimited

[audio]
output_device = ""        # empty = system default
sample_rate = 0           # 0 = use model's native rate
volume = 1.0              # master output gain

[behavior]
launch_on_login = false
start_minimized = true
read_dispatch = "interrupt"  # interrupt | enqueue — for hotkey/right-click reads
```
