"""Reusable first-run voice-model bootstrap.

`ensure_model(dest)` downloads the en_US-ryan-medium Piper model (and its .json)
next to `dest` if missing. Idempotent, prints progress, raises on failure. Used by
the daemon (first-run), the `install-model` CLI subcommand, and the dev script.
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

BASE = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "en/en_US/ryan/medium/")
MODEL_FILE = "en_US-ryan-medium.onnx"
CONFIG_FILE = "en_US-ryan-medium.onnx.json"
FILES = [MODEL_FILE, CONFIG_FILE]


def _progress(name: str):
    def hook(block: int, block_size: int, total: int) -> None:
        if total <= 0:
            return
        pct = min(100, int(block * block_size * 100 / total))
        print(f"\r  {name}: {pct}%", end="", flush=True)
    return hook


def ensure_model(dest: Path | str) -> Path:
    """Ensure the model (+ .json) exist next to `dest`; download missing files.

    `dest` is the .onnx path; the sibling .onnx.json is fetched alongside it.
    Returns the resolved .onnx path.
    """
    dest = Path(dest)
    models_dir = dest.parent
    models_dir.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        target = models_dir / name
        if target.exists() and target.stat().st_size > 0:
            print(f"  exists: {target}")
            continue
        url = BASE + name + "?download=true"
        print(f"  downloading {name} ...")
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            urllib.request.urlretrieve(url, tmp, _progress(name))
            print()  # newline after progress
            tmp.replace(target)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(
                f"Failed to download {name}: {e}\n"
                f"Manually download {BASE + name} -> {target}"
            ) from e
        print(f"  saved: {target}")
    return dest


def main(argv: list[str] | None = None) -> int:
    """CLI/script entry: download into the resolved default model location."""
    from .paths import default_model_path
    try:
        path = ensure_model(default_model_path())
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Model ready: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
