from pathlib import Path
from cyclops_voice.config import load_config, PRESETS, Preset

def test_presets_exist():
    assert {"game-accurate", "game-accurate-v2", "subtle", "heavy"} <= set(PRESETS)
    assert isinstance(PRESETS["game-accurate"], Preset)

def test_v2_preset_enables_quantization():
    v2 = PRESETS["game-accurate-v2"]
    assert v2.pitch_quantize is True
    assert v2.quant_transpose == -2.0
    assert v2.rasp_amount > 0 and v2.presence_gain_db > 0

def test_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg.service.port == 7788
    assert cfg.voice.preset == "game-accurate-v2"  # tx_full is the shipped voice
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
