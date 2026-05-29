"""Download the en_US-ryan Piper voice model into ./models (dev/source workflow).

Thin wrapper over cyclops_voice.model_download.ensure_model. The daemon's first-run
bootstrap and `cyclops install-model` target the per-user data dir when frozen; this
script always targets ./models so source checkouts and the test suite stay hermetic.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running directly from a source checkout without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cyclops_voice.model_download import ensure_model, MODEL_FILE


def main() -> int:
    try:
        ensure_model(Path("models") / MODEL_FILE)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
