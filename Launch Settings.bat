@echo off
rem Delegate to the VBS launcher so there's no lingering console and the
rem pywebview window shows correctly (python.exe, not pythonw.exe).
cd /d "%~dp0"
start "" wscript.exe "%~dp0Launch Settings.vbs"
