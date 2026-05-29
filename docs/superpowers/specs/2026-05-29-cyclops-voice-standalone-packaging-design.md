# Cyclops Voice — Standalone Distributable Packaging (Design Spec)

**Date:** 2026-05-29
**Status:** Approved (design); pending implementation plan
**Supersedes the TODO item:** "Create executable / standalone installer (e.g. PyInstaller `.exe`)"

## 1. Goal

Produce a **single, double-clickable native executable** that runs the full Cyclops Voice
app on any modern Windows machine — with **no Python install, no venv, no manual model
download** — so it can be shared with non-technical users. Mac and Linux builds are an
explicit later phase.

The original request used the word "containerize." During brainstorming this was
clarified: Docker is the **wrong** tool here. A Linux container has no access to the host's
speakers, global hotkeys, clipboard, or system tray — the entire point of the app — and an
image is not a "downloadable file you double-click." The correct technique is **freezing /
native packaging** into a self-contained binary that runs natively and therefore keeps every
feature.

### Non-goals (this phase)

- Docker / OCI images.
- Mac (`.app`) and Linux (AppImage) builds — designed for, but built in a later phase.
- A polished installer wizard (Inno Setup/NSIS), code signing, auto-update.
- Windowed (no-console) build. Phase 1 is console-enabled on purpose (see §6).

## 2. Decisions (locked during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Technique | Native freezing, **not** Docker | Container can't reach host audio/hotkey/tray; not a shareable file |
| Tool | **PyInstaller** (one-file) | Best hook ecosystem for our native deps; alternatives (Nuitka, cx_Freeze) weaker here |
| Package shape | **One-file `CyclopsVoice.exe`** | "Single file to share" is the user's explicit goal |
| Voice model | **Downloaded on first run** to a per-user data dir | Keeps the exe small; ~60 MB model not embedded |
| Default action on double-click | **Start the daemon** (tray + hotkey + HTTP API) | Only sane default for a shareable background app |
| Console | **Enabled** in Phase 1 | First-run download progress + errors must be visible |

## 3. Adversarial (GAN-style) risk evaluation

The design was stress-tested as Generator vs. Discriminator, validated against the
*actually-installed* packages in `.venv`. Findings drive the design below.

| Risk | Status | Resolution baked into design |
|---|---|---|
| **Missing espeak phonemizer data** (would crash synthesis at runtime) | **Neutralized** | piper-tts 1.4.2 bundles `piper/espeak-ng-data/`, native `espeakbridge.pyd`, and `tashkeel/` *in-package*. `--collect-all piper` collects them, preserving the package-relative layout `espeakbridge.pyd` resolves against. |
| **PortAudio / onnxruntime native DLLs not bundled** | **Neutralized** | onnxruntime ships an official PyInstaller hook; `sounddevice` carries PortAudio in `_sounddevice_data`; pedalboard is a self-contained native wheel. `--collect-all` covers them. |
| **uvicorn reload → fork bomb when frozen** | **N/A** | `daemon.py` runs `uvicorn.Server` directly in a worker thread; no reload, single process. Add `multiprocessing.freeze_support()` as insurance. |
| **Exe size blow-up** from full multi-language espeak data | **Mitigated** | Ship **English-only** espeak data (drop `ru_dict` 8.6 MB, `cmn`, etc., and the 4.8 MB Arabic `tashkeel`). See §5.3. |
| **SmartScreen / AV on unsigned one-file + first-run download** | **Accepted (documented)** | Inherent to a free unsigned shareable exe. Phase-1 mitigation: document "More info → Run anyway." Phase-2 hardening: installer and/or code signing. |

## 4. Architecture impact

The codebase already has the right seam: `SpeechEngine` takes an injectable `sink` and
`dsp_apply`, and the daemon/API/tray are cleanly separated. Packaging needs **small,
additive** changes — no rearchitecture. The only structural gap is that paths (model,
config) currently resolve **relative to the working directory**, which is unsafe for a
double-clicked exe whose CWD is unpredictable and whose own directory may be read-only.

## 5. Detailed design

### 5.1 New module: `src/cyclops_voice/paths.py`

Single source of truth for where runtime files live.

- `is_frozen() -> bool` — `getattr(sys, "frozen", False)`.
- `data_dir() -> Path` — per-user writable dir, created if missing:
  - Windows: `%APPDATA%\CyclopsVoice`
  - macOS: `~/Library/Application Support/CyclopsVoice`
  - Linux: `$XDG_DATA_HOME/CyclopsVoice` or `~/.local/share/CyclopsVoice`
- `default_model_path() -> str`:
  - If `./models/en_US-ryan-medium.onnx` exists (source checkout / dev) → return it.
    **This preserves the hermetic test suite and the acoustic golden test.**
  - Else → `data_dir()/models/en_US-ryan-medium.onnx` (frozen app).
- `default_config_path() -> Path` — `data_dir()/config.toml`.

### 5.2 `config.py` changes

- `VoiceConfig.model_path` default sources from `paths.default_model_path()`.
- `load_config(None)` auto-loads `paths.default_config_path()` when it exists, so a shared
  user can drop a `config.toml` next to their data without passing `--config`. Behavior when
  a path *is* passed is unchanged. Defaults still returned when no file exists.

### 5.3 Model bootstrap (first-run download)

- Refactor the download logic out of `scripts/install_voice_model.py` into a reusable
  function, e.g. `cyclops_voice.model_download.ensure_model(dest: Path) -> Path`:
  - Source: existing HuggingFace URL (`rhasspy/piper-voices/.../en_US/ryan/medium/`),
    both `.onnx` and `.onnx.json`.
  - Idempotent: skip files that already exist; print progress; clear error on failure.
- `daemon.build_engine()` (or `run_daemon`) calls `ensure_model(default_model_path())`
  **before** constructing `PiperTTS` when the model is missing.
- `scripts/install_voice_model.py` and the `cyclops install-model` subcommand become thin
  wrappers over `ensure_model()` (targeting the data dir), so existing flows still work.

### 5.4 Frozen entry behavior

- When `is_frozen()` **and** no CLI subcommand was given (double-click), default `argv` to
  `["daemon"]`. Running from a terminal with explicit args is unchanged
  (`CyclopsVoice.exe say "..."`, `render`, `status`, etc. all still work).
- Add `multiprocessing.freeze_support()` at the very start of the entry path.
- Implementation detail: a dedicated entry (e.g. `src/cyclops_voice/__main__.py` or a small
  `app_entry.py` used as the PyInstaller entry script) that calls `freeze_support()` then
  `cli.main()`.

### 5.5 PyInstaller configuration

- Committed spec file: **`packaging/CyclopsVoice.spec`**.
- Build helper: **`scripts/build_exe.py`** (wraps `PyInstaller.__main__.run` so the build is
  one command and CI-friendly).
- Collection strategy:
  - `--collect-all piper` for espeak data + `espeakbridge.pyd`, **then prune** the bundled
    `espeak-ng-data` to English-only and drop `tashkeel/` (custom step in the spec's
    `datas`/`Analysis`, or a post-collect filter). Keep: `en_dict`, `phondata`,
    `phondata-manifest`, `phonindex`, `phontab`, `intonations`, `lang/gmw/en*`, `voices/`.
  - Rely on official/community hooks for `onnxruntime`, `sounddevice` (PortAudio),
    `pedalboard`. Add explicit `collect_*` only if a hook proves insufficient at runtime.
  - Hidden imports as needed for `uvicorn` workers, `mcp`, `pystray`, `pynput`, `PIL`.
- Output: `dist/CyclopsVoice.exe`, one-file, **console enabled**.
- No app icon in Phase 1 (none exists in repo); optional later.

### 5.6 Packaging metadata & ignores

- New optional dependency group in `pyproject.toml`: `build = ["pyinstaller"]`.
- `.gitignore`: add `build/` and `dist/`. **Keep `packaging/CyclopsVoice.spec` tracked.**

## 6. Console vs. windowed (Phase 1 rationale)

A tray app would ideally be windowed (no console). But the first-run model download is the
single most likely thing to fail on a fresh machine (network, proxy, AV). A console makes
its progress and any error visible. Phase 1 ships **console-enabled**; Phase 2 switches to
windowed with a rotating log file in the data dir once the happy path is proven.

## 7. Testing & verification

**Automated (must stay green):**
- Existing `pytest` suite — all 28 tests, including the acoustic golden test. The
  `default_model_path()` "use `./models` if present" rule guarantees dev/test behavior is
  unchanged.
- New unit tests for `paths.py` (data-dir resolution; source-vs-frozen model path) and
  `ensure_model()` (idempotent skip; download invoked when missing — network mocked).

**Manual (Phase 1 acceptance, on this machine):**
1. Build: `python scripts/build_exe.py` → `dist/CyclopsVoice.exe` exists.
2. Simulate a clean machine (empty `%APPDATA%\CyclopsVoice`): double-click the exe →
   console shows model download → tray icon appears → `GET http://127.0.0.1:7788/health`
   returns ok.
3. `dist\CyclopsVoice.exe render "Hull integrity stable." -o out.wav` → valid stereo WAV.
4. Global hotkey `Ctrl+Alt+R` on selected text → audible Cyclops voice.
5. Confirm exe size is reasonable after English-only espeak pruning.

## 8. Scope boundary

**Phase 1 (this effort):** `paths.py`, config + model-bootstrap + frozen-entry changes, the
PyInstaller spec/build script, and a **working, verified one-file `CyclopsVoice.exe` with
first-run model download** on Windows.

**Phase 2+ (later, not now):** Mac/Linux builds (PyInstaller can't cross-compile → per-OS CI
matrix), windowed build + log file, installer wizard, code signing, optional model-embedded
variant.

## 9. Open risk accepted by stakeholder

Unsigned one-file exe triggers SmartScreen "Unknown publisher" and may draw AV attention on
first-run download. Accepted for Phase 1; revisited via installer/signing in Phase 2.
