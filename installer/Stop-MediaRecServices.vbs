' Stop Media Recommendation Engine services without showing a console window.
Option Explicit
Dim sh, cmd, app
Set sh = CreateObject("WScript.Shell")
app = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & app & "\scripts\Install-MediaRecServices.ps1"" -Action stop -InstallRoot """ & app & """"
sh.Run cmd, 0, True
