import json
from dataclasses import replace
from pathlib import Path
from cyclops_voice.config import (
    CyclopsConfig, load_config, save_config, build_effective_preset,
    PRESETS, Preset, all_presets, register_preset, load_tuning_candidates,
)

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


def test_new_section_defaults():
    cfg = CyclopsConfig()
    assert cfg.audio.volume == 1.0
    assert cfg.hotkeys.pause_resume == "ctrl+alt+p"
    assert cfg.read.trigger == "double_rmb" and cfg.read.mode == "paragraph"
    assert cfg.read.modifier == "none"
    assert cfg.read.auto_dismiss_menu is True and cfg.read.max_chars == 0
    assert cfg.behavior.start_minimized is True
    assert cfg.behavior.read_dispatch == "interrupt"
    assert all(getattr(cfg.voice.effects, f) is None
               for f in ("reverb_wet", "rasp_amount", "drive_db", "presence_gain_db"))


def test_save_load_round_trip(tmp_path):
    cfg = CyclopsConfig()
    cfg.service.port = 9100
    cfg.voice.preset = "subtle"
    cfg.voice.length_scale = 1.4
    cfg.voice.effects.reverb_wet = 0.33
    cfg.voice.effects.drive_db = 5.0
    cfg.audio.volume = 0.6
    cfg.read.mode = "paragraph"
    cfg.read.trigger = "modifier_rmb"
    cfg.read.max_chars = 500
    cfg.behavior.read_dispatch = "enqueue"
    cfg.hotkeys.pause_resume = "ctrl+alt+space"

    p = save_config(cfg, tmp_path / "c.toml")
    out = load_config(p)
    assert out.service.port == 9100
    assert out.voice.preset == "subtle" and out.voice.length_scale == 1.4
    assert out.voice.effects.reverb_wet == 0.33 and out.voice.effects.drive_db == 5.0
    assert out.voice.effects.rasp_amount is None  # None overrides stay omitted
    assert out.audio.volume == 0.6
    assert out.read.mode == "paragraph" and out.read.trigger == "modifier_rmb"
    assert out.read.max_chars == 500
    assert out.behavior.read_dispatch == "enqueue"
    assert out.hotkeys.pause_resume == "ctrl+alt+space"


def test_effective_preset_layers_overrides_without_mutating_presets():
    base = PRESETS["game-accurate-v2"]
    snapshot = replace(base)  # value copy for comparison
    cfg = CyclopsConfig()
    cfg.voice.preset = "game-accurate-v2"
    cfg.voice.effects.reverb_wet = 0.5
    cfg.voice.effects.rasp_amount = 0.2

    eff = build_effective_preset(cfg)
    assert eff.reverb_wet == 0.5 and eff.rasp_amount == 0.2
    assert eff.drive_db == base.drive_db  # untouched fields fall through to preset
    # The frozen preset object is not mutated (protects the acoustic golden test).
    assert PRESETS["game-accurate-v2"] == snapshot
    assert eff is not PRESETS["game-accurate-v2"]


def test_effective_preset_no_overrides_returns_base():
    cfg = CyclopsConfig()
    assert build_effective_preset(cfg) is PRESETS[cfg.voice.preset]


def test_load_tuning_candidates_missing_dir(tmp_path):
    count = load_tuning_candidates(tmp_path / "nonexistent")
    assert count == 0


def test_load_tuning_candidates_registers_presets(tmp_path):
    import cyclops_voice.config as _cfg_mod
    _cfg_mod._extra_presets.clear()
    data = [{"candidate_id": "test_cand", "preset": {
        "name": "game-accurate", "highpass_hz": 80, "lowmid_freq_hz": 200,
        "lowmid_gain_db": 7.0, "lowmid_q": 1.2, "lowpass_hz": 3200,
        "comp_threshold_db": -18, "comp_ratio": 2.5,
        "reverb_room_size": 0.4, "reverb_damping": 0.6,
        "reverb_wet": 0.22, "reverb_width": 1.0,
    }}]
    (tmp_path / "param_sets_test.json").write_text(json.dumps(data), encoding="utf-8")
    count = load_tuning_candidates(tmp_path)
    assert count == 1
    ap = all_presets()
    assert "test_cand" in ap
    from cyclops_voice.config import resolve_preset
    p = resolve_preset("test_cand")
    assert p.name == "test_cand" and p.highpass_hz == 80
    _cfg_mod._extra_presets.clear()


def test_extra_preset_does_not_mutate_PRESETS(tmp_path):
    import cyclops_voice.config as _cfg_mod
    _cfg_mod._extra_presets.clear()
    before = set(PRESETS)
    register_preset("tmp_test", PRESETS["game-accurate"])
    assert set(PRESETS) == before  # frozen dict unchanged
    _cfg_mod._extra_presets.clear()
