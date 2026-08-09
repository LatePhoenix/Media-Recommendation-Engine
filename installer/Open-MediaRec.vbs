' Open Media Recommendation Engine: start services if needed, then open the UI.
' Replaces a bare .url shortcut so a failed/incomplete bootstrap does not leave
' users on a dead http://127.0.0.1:8000/ page with no recovery path.
Option Explicit
Dim sh, fso, app, cmd, http, ready, i, url
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
app = fso.GetParentFolderName(WScript.ScriptFullName)
url = "http://127.0.0.1:8000/"

Function IsReady()
  On Error Resume Next
  Set http = CreateObject("MSXML2.XMLHTTP")
  http.Open "GET", "http://127.0.0.1:8000/health", False
  http.Send
  IsReady = (Err.Number = 0 And http.Status >= 200 And http.Status < 500)
  Err.Clear
  On Error GoTo 0
End Function

If Not IsReady() Then
  ' Start (and install if missing) WinSW services — requires elevation.
  cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & app & "\scripts\Repair-MediaRecLaunch.ps1"" -InstallRoot """ & app & """"
  sh.Run cmd, 0, True
End If

ready = False
For i = 1 To 60
  If IsReady() Then
    ready = True
    Exit For
  End If
  WScript.Sleep 2000
Next

If ready Then
  sh.Run url, 1, False
Else
  MsgBox "Media Recommendation Engine did not become ready on " & url & vbCrLf & vbCrLf & _
    "Try Start Menu → Collect Diagnostics, or re-run the installer as Administrator.", _
    48, "Media Recommendation Engine"
End If
