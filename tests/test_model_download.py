from pathlib import Path

import pytest

import cyclops_voice.model_download as md


def test_ensure_model_skips_existing(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    for name in md.FILES:
        (models / name).write_bytes(b"already-here")

    calls = []
    monkeypatch.setattr(md.urllib.request, "urlretrieve",
                        lambda *a, **k: calls.append(a))
    out = md.ensure_model(models / md.MODEL_FILE)
    assert out == models / md.MODEL_FILE
    assert calls == []  # nothing downloaded


def test_ensure_model_downloads_when_missing(tmp_path, monkeypatch):
    dest = tmp_path / "models" / md.MODEL_FILE

    def fake_urlretrieve(url, tmp, hook=None):
        Path(tmp).write_bytes(b"downloaded")  # simulate a successful fetch

    got = []
    monkeypatch.setattr(md.urllib.request, "urlretrieve",
                        lambda url, tmp, hook=None: (got.append(url), fake_urlretrieve(url, tmp))[1])
    md.ensure_model(dest)
    assert len(got) == len(md.FILES)
    for name in md.FILES:
        assert (tmp_path / "models" / name).read_bytes() == b"downloaded"


def test_ensure_model_raises_on_failure(tmp_path, monkeypatch):
    dest = tmp_path / "models" / md.MODEL_FILE

    def boom(url, tmp, hook=None):
        raise OSError("network down")

    monkeypatch.setattr(md.urllib.request, "urlretrieve", boom)
    with pytest.raises(RuntimeError, match="Failed to download"):
        md.ensure_model(dest)
    # partial file cleaned up
    assert not list((tmp_path / "models").glob("*.part"))
