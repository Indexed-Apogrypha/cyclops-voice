"""Download the en_US-ryan Piper voice model into ./models."""
from __future__ import annotations
import sys
from pathlib import Path
import urllib.request

BASE = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
        "en/en_US/ryan/medium/")
FILES = ["en_US-ryan-medium.onnx", "en_US-ryan-medium.onnx.json"]


def main() -> int:
    models = Path("models"); models.mkdir(exist_ok=True)
    for name in FILES:
        dest = models / name
        if dest.exists():
            print(f"exists: {dest}"); continue
        url = BASE + name + "?download=true"
        print(f"downloading {url}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            print(f"FAILED: {e}\nManually download {BASE+name} -> {dest}", file=sys.stderr)
            return 1
        print(f"saved: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
