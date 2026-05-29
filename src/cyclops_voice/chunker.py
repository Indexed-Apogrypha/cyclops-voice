from __future__ import annotations
import re

_SENTENCE = re.compile(r"[^.!?\n]*[.!?]+|\S[^\n]*", re.UNICODE)


def _split_long(piece: str, max_chars: int) -> list[str]:
    words = piece.split(" ")
    out, cur = [], ""
    for w in words:
        cand = w if not cur else cur + " " + w
        if len(cand) > max_chars and cur:
            out.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out


def chunk_text(text: str, max_chars: int = 240) -> list[str]:
    """Split text into sentence-sized chunks for streaming synthesis."""
    chunks: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for m in _SENTENCE.finditer(line):
            s = m.group().strip()
            if not s:
                continue
            if len(s) <= max_chars:
                chunks.append(s)
            else:
                chunks.extend(_split_long(s, max_chars))
    return chunks
