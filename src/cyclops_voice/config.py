from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
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


@dataclass
class ServiceConfig:
    host: str = "127.0.0.1"
    port: int = 7788
    auth_token: str = ""


@dataclass
class VoiceConfig:
    model_path: str = field(default_factory=default_model_path)
    length_scale: float = 1.22
    pitch_semitones: float = 0.0  # WORLD quantization handles pitch in game-accurate-v2
    preset: str = "game-accurate-v2"


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
        # No explicit path: auto-load the per-user config if a shared user dropped one.
        user_cfg = default_config_path()
        if not user_cfg.exists():
            return cfg
        path = user_cfg
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
