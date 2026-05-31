' Cyclops Voice — settings launcher (no console window).
' Uses python.exe (NOT pythonw.exe — pywebview's WinForms/Edge backend fails to
' show its window under pythonw). WScript.Shell.Run with intWindowStyle=0 hides
' python's console while pywebview still shows its own settings window.
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
projDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = projDir
sh.Run """" & projDir & "\.venv\Scripts\python.exe"" -m cyclops_voice.cli gui", 0, False
