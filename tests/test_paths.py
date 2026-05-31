import sys
from pathlib import Path

import cyclops_voice.paths as paths


def test_data_dir_created(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = paths.data_dir()
    assert d == tmp_path / "CyclopsVoice"
    assert d.is_dir()


def test_default_model_path_prefers_source(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / paths.MODEL_FILENAME).write_bytes(b"x")
    assert paths.default_model_path() == str(Path("models") / paths.MODEL_FILENAME)


def test_default_model_path_falls_back_to_data_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no ./models here
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    expected = tmp_path / "appdata" / "CyclopsVoice" / "models" / paths.MODEL_FILENAME
    assert paths.default_model_path() == str(expected)


def test_is_frozen_default():
    assert paths.is_frozen() is False
