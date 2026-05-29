from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
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
    bitcrush_bit_depth: float = 0.0  # 0 = disabled; 8-16 = subtle digital grain


PRESETS: dict[str, Preset] = {
    # Derived from the measured reference profile (see design spec §2-3).
    "game-accurate": Preset(
        name="game-accurate", highpass_hz=60, lowmid_freq_hz=200, lowmid_gain_db=8.0,
        lowmid_q=1.2, lowpass_hz=3200, comp_threshold_db=-18, comp_ratio=2.5,
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
