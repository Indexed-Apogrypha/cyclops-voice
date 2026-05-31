"""Resolve the text under a screen point via Windows UI Automation (UIA).

The double-right-click read feature needs the *sentence* or *paragraph* under the
cursor with no prior selection. UIA's TextPattern gives us exactly that:
`RangeFromPoint` finds the text range at a point and `ExpandToEnclosingUnit`
grows it to a sentence or paragraph boundary.

Coverage depends on the target app exposing UIA TextPattern (modern browsers with
accessibility active, Word, WordPad, many editors); apps without it return None and
the feature degrades silently. All comtypes/UIA use is isolated here, behind the
`TextUnderCursor` protocol, so the rest of the package (and the test suite) never
imports comtypes.

Spike / manual test:  python -m cyclops_voice.text_under_cursor [sentence|paragraph]
Hover over text and the resolved string is printed each second.
"""
from __future__ import annotations
from typing import Protocol


class TextUnderCursor(Protocol):
    def get_text_at(self, x: int, y: int, mode: str) -> str | None: ...


class NullTextUnderCursor:
    """Fallback used off-Windows or when UIA is unavailable: always None."""
    def get_text_at(self, x: int, y: int, mode: str) -> str | None:
        return None


class UiaTextUnderCursor:
    """UIA-backed extractor. Lazily creates the COM client on first use so import
    is cheap and failures degrade to None rather than raising."""

    def __init__(self):
        self._uia = None
        self._mod = None

    def _ensure(self):
        if self._uia is not None:
            return
        import comtypes.client
        self._mod = comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
        self._uia = comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)

    def get_text_at(self, x: int, y: int, mode: str) -> str | None:
        try:
            self._ensure()
            from ctypes.wintypes import POINT
            mod, uia = self._mod, self._uia
            element = uia.ElementFromPoint(POINT(int(x), int(y)))
            if not element:
                return None
            text = self._from_text_pattern(element, mod, x, y, mode)
            if text:
                return text
            return self._fallback(element, mod)
        except Exception:
            return None

    def _from_text_pattern(self, element, mod, x, y, mode):
        from ctypes.wintypes import POINT
        from comtypes.gen.UIAutomationClient import IUIAutomationTextPattern
        raw = element.GetCurrentPattern(mod.UIA_TextPatternId)
        if not raw:
            return None
        tp = raw.QueryInterface(IUIAutomationTextPattern)
        rng = tp.RangeFromPoint(POINT(int(x), int(y)))
        if not rng:
            return None
        unit = mod.TextUnit_Paragraph if mode == "paragraph" else mod.TextUnit_Sentence
        rng.ExpandToEnclosingUnit(unit)
        text = rng.GetText(-1)
        return text.strip() if text else None

    def _fallback(self, element, mod):
        # No TextPattern: try ValuePattern then the element's name/label.
        try:
            from comtypes.gen.UIAutomationClient import IUIAutomationValuePattern
            raw = element.GetCurrentPattern(mod.UIA_ValuePatternId)
            if raw:
                vp = raw.QueryInterface(IUIAutomationValuePattern)
                v = vp.CurrentValue
                if v and v.strip():
                    return v.strip()
        except Exception:
            pass
        try:
            name = element.CurrentName
            return name.strip() if name and name.strip() else None
        except Exception:
            return None


def make_text_under_cursor() -> TextUnderCursor:
    """UIA extractor on Windows, else a null extractor."""
    import sys
    if sys.platform == "win32":
        return UiaTextUnderCursor()
    return NullTextUnderCursor()


def _spike(mode: str = "sentence") -> int:  # pragma: no cover - manual desktop test
    import time
    from pynput import mouse
    ex = make_text_under_cursor()
    ctrl = mouse.Controller()
    print(f"UIA spike ({mode}). Hover over text; Ctrl+C to quit.")
    try:
        while True:
            x, y = ctrl.position
            print(repr(ex.get_text_at(x, y, mode)))
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    raise SystemExit(_spike(sys.argv[1] if len(sys.argv) > 1 else "sentence"))
