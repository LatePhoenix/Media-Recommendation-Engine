' Collect diagnostics (non-interactive). Opens Explorer on the zip when done.
Option Explicit
Dim sh, fso, cmd, app, dataRoot, lastFile, zipPath, ts
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
app = fso.GetParentFolderName(WScript.ScriptFullName)
dataRoot = sh.ExpandEnvironmentStrings("%ProgramData%") & "\MediaRecommendationEngine"
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & app & "\scripts\Collect-Diagnostics.ps1"" -InstallRoot """ & app & """ -NonInteractive"
sh.Run cmd, 0, True
lastFile = dataRoot & "\diagnostics\last-diagnostics-path.txt"
If fso.FileExists(lastFile) Then
  zipPath = Trim(fso.OpenTextFile(lastFile, 1).ReadAll)
  If Len(zipPath) > 0 And fso.FileExists(zipPath) Then
    sh.Run "explorer.exe /select,""" & zipPath & """", 1, False
  End If
End If
