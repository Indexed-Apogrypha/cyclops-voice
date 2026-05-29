# Cyclops Voice

System-wide, offline TTS that reads text aloud in the Subnautica Cyclops submarine AI voice.
Piper neural TTS + a measured DSP chain (matched to the original game audio). Works anywhere
on Windows: Obsidian, Claude Desktop, Open Interpreter, any app.

## How it works

One background daemon owns a warm Piper voice model and the Cyclops DSP chain. Three surfaces
drive it:

- **Global hotkey** — select text in any app, press `Ctrl+Alt+R`
- **CLI / scripts** — `cyclops say "Hull integrity stable."`
- **MCP server** — Claude Desktop calls the `speak` tool directly

The DSP recipe was reverse-engineered from actual Cyclops audio: heavy low-mid boost (~200 Hz),
steep low-pass at ~3.2 kHz, medium metallic reverb with stereo width. See the design spec in
`docs/superpowers/specs/` for the full acoustic analysis.

## Setup

**Requires Python 3.12.** (Not 3.14 — `pedalboard`/`sounddevice` wheels are pinned to 3.12.)

```powershell
# 1. Create venv and install
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"

# 2. Download the en_US-ryan voice model (~60 MB)
.\.venv\Scripts\python scripts\install_voice_model.py

# 3. (Optional) copy and edit config
copy config.example.toml "$env:APPDATA\CyclopsVoice\config.toml"
```

## Usage

```powershell
# Start the background service (hotkey + tray + API, port 7788)
cyclops daemon

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

# Start on Windows login
cyclops install-autostart
```

**Hotkeys** (configurable in `config.toml`):
- `Ctrl+Alt+R` — read current selection from any app
- `Ctrl+Alt+S` — stop

**Presets:** `game-accurate` (default), `subtle` (light processing, good for long reading),
`heavy` (more reverb + saturation).

## Open Interpreter / scripts

Shell out to `cyclops say "..."`, or POST directly to the HTTP API:

```python
import httpx
httpx.post("http://127.0.0.1:7788/speak", json={"text": "Dive, dive, dive."})
```

Full API: `GET /health /status /presets` · `POST /speak /stop /pause /resume /skip /render`

Optional token auth: set `auth_token` in config, then send `X-Cyclops-Token: <token>`.

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

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
# 28 passed — includes acoustic golden test that verifies the DSP output
# matches the measured Cyclops voice profile (low-mid dominance, treble rolloff, stereo width)
```

## Config reference (`config.example.toml`)

```toml
[service]
host = "127.0.0.1"
port = 7788
auth_token = ""           # optional; clients send X-Cyclops-Token header

[voice]
model_path = "models/en_US-ryan-medium.onnx"
length_scale = 1.15       # >1 = slower / more deliberate
pitch_semitones = -1
preset = "game-accurate"

[hotkeys]
read_selection = "ctrl+alt+r"
stop = "ctrl+alt+s"

[audio]
output_device = ""        # empty = system default
sample_rate = 0           # 0 = use model's native rate
```
