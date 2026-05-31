# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: one-file, console-enabled CyclopsVoice.exe (Phase 1).

Collects piper (espeak-ng-data + espeakbridge.pyd), then prunes the bundled
espeak data to English-only to keep the exe small. Native deps (onnxruntime,
sounddevice/PortAudio, pedalboard, pyworld) are collected too. Model is NOT
embedded -- it is downloaded on first run to the per-user data dir.

Build:  python scripts/build_exe.py      (or: pyinstaller packaging/CyclopsVoice.spec)
"""
import os
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

ROOT = os.path.abspath(os.getcwd())
SRC = os.path.join(ROOT, "src")
ENTRY = os.path.join(ROOT, "packaging", "entry.py")

datas, binaries, hiddenimports = [], [], []

# piper carries espeak-ng-data, espeakbridge.pyd, tashkeel in-package.
# webview/pythonnet/comtypes carry the EdgeChromium backend + UIA COM plumbing.
for pkg in ("piper", "onnxruntime", "sounddevice", "pedalboard", "pyworld",
            "webview", "clr_loader", "comtypes"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# The settings GUI's static assets (HTML/CSS/JS), served by the daemon at /ui/.
datas += [(os.path.join(SRC, "cyclops_voice", "web"), "cyclops_voice/web")]

# Prune espeak data to English-only: drop the large non-English pronunciation
# dictionaries and the Arabic tashkeel model (~13 MB+ total) we never use.
def _keep(dest: str) -> bool:
    norm = dest.replace("\\", "/")
    if "espeak-ng-data" not in norm:
        return True
    if "/tashkeel" in norm:
        return False
    base = norm.rsplit("/", 1)[-1]
    if base.endswith("_dict") and base != "en_dict":
        return False
    return True

datas = [(src, dest) for (src, dest) in datas if _keep(dest)]

hiddenimports += [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    "pystray._win32", "PIL.Image", "pynput.keyboard._win32", "pynput.mouse._win32",
    "mcp", "cyclops_voice.pitch_quantize", "cyclops_voice.texture",
    # settings GUI + read-under-cursor
    "cyclops_voice.gui", "cyclops_voice.mouse_trigger",
    "cyclops_voice.text_under_cursor", "cyclops_voice.autostart",
    "webview.platforms.edgechromium", "clr", "fastapi.staticfiles",
]

a = Analysis(
    [ENTRY],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "matplotlib", "scipy"],  # scipy unused at runtime; fails under PyInstaller
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="CyclopsVoice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,            # Phase 1: keep console for first-run download visibility
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
