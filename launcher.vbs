Set ws = CreateObject("Wscript.Shell")

strPath = WScript.ScriptFullName
strDir = Left(strPath, InStrRev(strPath, "\"))

strCommand = """" & strDir & ".venv\Scripts\python.exe"" """ & strDir & "gui.py"""

ws.Run strCommand, 0, False