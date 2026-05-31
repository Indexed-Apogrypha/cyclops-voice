from __future__ import annotations
import tomllib
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from pathlib import Path

from .paths import default_model_path, default_config_path


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
    bitcrush_bit_depth: float = 0.0  # 0 = disabled; 8-16 = subtle digital grain
    # --- WORLD hard pitch quantization (the "autotuned" Cyclops movement) ---
    pitch_quantize: bool = False     # when True, F0 is snapped in apply_dsp (DSP PitchShift skipped)
    quant_snap: float = 1.0          # 0..1 blend toward the 12-TET grid (1.0 = full)
    quant_transpose: float = 0.0     # semitones to drop/raise register before snapping
    formant_alpha: float = 1.0       # spectral-envelope warp; >1 = upward formant shift
    # --- texture: envelope-gated rasp grain + PA presence peak ---
    rasp_amount: float = 0.0         # 0 = off; 0.05-0.18 = grain level
    presence_freq_hz: float = 2200.0
    presence_gain_db: float = 0.0    # 0 = off
    presence_q: float = 1.0


PRESETS: dict[str, Preset] = {
    # Derived from the measured reference profile (see design spec §2-3).
    "game-accurate": Preset(
        name="game-accurate", highpass_hz=60, lowmid_freq_hz=200, lowmid_gain_db=8.0,
        lowmid_q=1.2, lowpass_hz=3200, comp_threshold_db=-18, comp_ratio=2.5,
        reverb_room_size=0.55, reverb_damping=0.5, reverb_wet=0.28, reverb_width=1.0,
    ),
    # Winning tuned candidate (tx_full): WORLD hard pitch quantization + envelope-gated
    # rasp grain + PA presence, on the E1_tuned_v3 DSP base. See docs/superpowers/ &
    # tuning/. Use with length_scale 1.22 and pitch_semitones 0 (WORLD handles pitch).
    "game-accurate-v2": Preset(
        name="game-accurate-v2", highpass_hz=120, lowmid_freq_hz=200, lowmid_gain_db=8.0,
        lowmid_q=1.2, lowpass_hz=3200, comp_threshold_db=-18, comp_ratio=2.5,
        reverb_room_size=0.42, reverb_damping=0.65, reverb_wet=0.24, reverb_width=1.0,
        drive_db=4.0, bitcrush_bit_depth=11.0,
        pitch_quantize=True, quant_snap=1.0, quant_transpose=-2.0, formant_alpha=1.0,
        rasp_amount=0.10, presence_freq_hz=2300.0, presence_gain_db=3.0, presence_q=1.0,
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


_extra_presets: dict[str, Preset] = {}


def register_preset(name: str, preset: Preset) -> None:
    _extra_presets[name] = preset


def all_presets() -> dict[str, Preset]:
    return {**PRESETS, **_extra_presets}


def load_tuning_candidates(tuning_dir: Path) -> int:
    """Scan tuning_dir/param_sets_*.json and register each candidate as a Preset.

    Each entry starts from its declared base preset then applies only the fields
    present in the JSON, so older param_sets files (missing pitch_quantize etc.)
    inherit the base preset's defaults for those newer fields.
    Returns the number of newly registered presets (0 if dir absent or files empty).
    """
    import json as _json
    valid = {f.name for f in fields(Preset)} - {"name"}
    count = 0
    for path in sorted(tuning_dir.glob("param_sets_*.json")):
        try:
            entries = _json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for entry in entries:
            cid = entry.get("candidate_id")
            if not cid or cid in PRESETS or cid in _extra_presets:
                continue
            raw = entry.get("preset", {})
            base = PRESETS.get(raw.get("name", "game-accurate"), PRESETS["game-accurate"])
            overrides = {k: v for k, v in raw.items() if k in valid}
            try:
                register_preset(cid, replace(base, name=cid, **overrides))
                count += 1
            except Exception:
                pass
    return count


@dataclass
class ServiceConfig:
    host: str = "127.0.0.1"
    port: int = 7788
    auth_token: str = ""


@dataclass
class EffectsConfig:
    """High-level effect overrides layered on top of the base preset.

    Each None field falls through to the preset's own value (see
    build_effective_preset). The GUI's effect sliders write here.
    """
    reverb_wet: float | None = None
    rasp_amount: float | None = None
    drive_db: float | None = None
    presence_gain_db: float | None = None


@dataclass
class VoiceConfig:
    model_path: str = field(default_factory=default_model_path)
    length_scale: float = 1.22
    pitch_semitones: float = 0.0  # WORLD quantization handles pitch in game-accurate-v2
    preset: str = "game-accurate-v2"
    effects: EffectsConfig = field(default_factory=EffectsConfig)


@dataclass
class HotkeyConfig:
    read_selection: str = "ctrl+alt+r"
    stop: str = "ctrl+alt+s"
    pause_resume: str = "ctrl+alt+p"


@dataclass
class AudioConfig:
    output_device: str = ""
    sample_rate: int = 0  # 0 = use model rate
    volume: float = 1.0   # master output gain applied in the player (0..1+)


@dataclass
class ReadConfig:
    """The double-right-click read-under-cursor feature."""
    trigger: str = "double_rmb"      # double_rmb | modifier_rmb | off
    modifier: str = "none"           # none | ctrl | alt | shift (only used when trigger=modifier_rmb)
    mode: str = "paragraph"          # sentence | paragraph (UIA text unit)
    auto_dismiss_menu: bool = True   # send Esc to close the context menu after grabbing text
    max_chars: int = 0               # 0 = unlimited; otherwise ignore reads longer than this


@dataclass
class BehaviorConfig:
    launch_on_login: bool = False
    start_minimized: bool = True
    read_dispatch: str = "interrupt"  # interrupt | enqueue — default mode for hotkey/right-click reads


@dataclass
class CyclopsConfig:
    service: ServiceConfig = field(default_factory=ServiceConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    read: ReadConfig = field(default_factory=ReadConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)


def _apply(section: dict, obj):
    for k, v in section.items():
        if hasattr(obj, k) and not is_dataclass(getattr(obj, k)):
            setattr(obj, k, v)


def load_config(path: Path | str | None = None) -> CyclopsConfig:
    cfg = CyclopsConfig()
    if path is None:
        # No explicit path: auto-load the per-user config if a shared user dropped one.
        user_cfg = default_config_path()
        if not user_cfg.exists():
            return cfg
        path = user_cfg
    path = Path(path)
    if not path.exists():
        return cfg
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    voice = data.get("voice", {})
    _apply(data.get("service", {}), cfg.service)
    _apply(voice, cfg.voice)
    _apply(voice.get("effects", {}), cfg.voice.effects)
    _apply(data.get("hotkeys", {}), cfg.hotkeys)
    _apply(data.get("audio", {}), cfg.audio)
    _apply(data.get("read", {}), cfg.read)
    _apply(data.get("behavior", {}), cfg.behavior)
    return cfg


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return "'" + v.replace("'", "\\'") + "'"
    return repr(v)


def save_config(cfg: CyclopsConfig, path: Path | str | None = None) -> Path:
    """Persist config to TOML (per-user config path by default). None override
    fields are omitted so the preset value keeps showing through."""
    path = Path(path) if path is not None else default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def emit(header: str, obj) -> None:
        body = [f"{f.name} = {_toml_value(getattr(obj, f.name))}"
                for f in fields(obj)
                if not is_dataclass(getattr(obj, f.name)) and getattr(obj, f.name) is not None]
        if body:
            lines.append(f"[{header}]")
            lines.extend(body)
            lines.append("")

    emit("service", cfg.service)
    emit("voice", cfg.voice)
    emit("voice.effects", cfg.voice.effects)
    emit("hotkeys", cfg.hotkeys)
    emit("audio", cfg.audio)
    emit("read", cfg.read)
    emit("behavior", cfg.behavior)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def to_dict(cfg: CyclopsConfig) -> dict:
    """Full config as nested JSON-friendly dict (for the GUI's GET /config)."""
    return asdict(cfg)


def from_dict(data: dict) -> CyclopsConfig:
    """Build a config from a (possibly partial) nested dict, falling back to
    defaults for anything omitted. Mirrors load_config's section handling."""
    cfg = CyclopsConfig()
    voice = data.get("voice", {})
    _apply(data.get("service", {}), cfg.service)
    _apply(voice, cfg.voice)
    _apply(voice.get("effects", {}), cfg.voice.effects)
    _apply(data.get("hotkeys", {}), cfg.hotkeys)
    _apply(data.get("audio", {}), cfg.audio)
    _apply(data.get("read", {}), cfg.read)
    _apply(data.get("behavior", {}), cfg.behavior)
    return cfg


def resolve_preset(name: str) -> Preset:
    if name in _extra_presets:
        return _extra_presets[name]
    if name not in PRESETS:
        raise KeyError(f"unknown preset {name!r}; choices: {sorted(all_presets())}")
    return PRESETS[name]


def build_effective_preset(cfg: CyclopsConfig) -> Preset:
    """Base preset with the GUI's effect overrides layered on top. Never
    mutates PRESETS — returns a fresh Preset via dataclasses.replace."""
    base = resolve_preset(cfg.voice.preset)
    overrides = {f.name: getattr(cfg.voice.effects, f.name)
                 for f in fields(cfg.voice.effects)
                 if getattr(cfg.voice.effects, f.name) is not None}
    return replace(base, **overrides) if overrides else base
