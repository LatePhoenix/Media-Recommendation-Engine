; Inno Setup script for the Media Recommendation Engine
; Builds a Windows installer that deploys the Docker Compose stack, generates
; secure secrets on first install, and adds Start/Stop shortcuts.
;
; Build:  iscc installer\MediaRecommendationEngine.iss   (run from the repo root)
; Output: installer\output\MediaRecommendationEngine-Setup.exe
;
; Requires Inno Setup 6 (https://jrsoftware.org/isdl.php).

#define MyAppName "Media Recommendation Engine"
#define MyAppShortName "MediaRecommendationEngine"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Media Recommendation Engine"
#define MyAppURL "http://localhost:5173"
; Paths below are relative to this .iss file (installer\), so ".." is the repo root.
#define RepoRoot ".."

[Setup]
AppId={{7C1F3A2E-9B54-4E7A-B0D2-6F1A2C3D4E5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename={#MyAppShortName}-Setup
SetupIconFile={#RepoRoot}\assets\icons\app-icon.ico
UninstallDisplayIcon={app}\assets\icons\app-icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole repo (Compose builds images from source; runtime uses image
; contents — no Program Files bind mounts), minus virtualenvs, VCS,
; node_modules, local env/data, and this installer folder.
Source: "{#RepoRoot}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; \
  Excludes: "\.git\*,\.git,\.venv\*,\.venv,\node_modules\*,node_modules,\apps\web\dist\*,\.env,\pgdata\*,\data\*,*.pyc,__pycache__\*,\.pytest_cache\*,\.mypy_cache\*,\.ruff_cache\*,\.claude\*,\.claude,*.tsbuildinfo,\installer\*,\installer"

; Launcher scripts land in the app root so shortcuts can call them.
Source: "setup-env.ps1";    DestDir: "{app}"; Flags: ignoreversion
Source: "Start-MediaRec.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "Stop-MediaRec.ps1";  DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\Start-MediaRec.ps1"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\app-icon.ico"; \
  Comment: "Start the Media Recommendation Engine"
Name: "{group}\Stop {#MyAppName}"; Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\Stop-MediaRec.ps1"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\app-icon.ico"; \
  Comment: "Stop the Media Recommendation Engine"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\Start-MediaRec.ps1"""; \
  WorkingDir: "{app}"; IconFilename: "{app}\assets\icons\app-icon.ico"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup-env.ps1"""; \
  StatusMsg: "Generating secure configuration..."; Flags: runhidden waituntilterminated
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\Start-MediaRec.ps1"""; \
  Description: "Start {#MyAppName} now"; WorkingDir: "{app}"; \
  Flags: postinstall nowait skipifsilent

[UninstallRun]
; Best-effort stop of running containers before files are removed.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\Stop-MediaRec.ps1"""; \
  WorkingDir: "{app}"; Flags: runhidden; RunOnceId: "StopStack"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Warn (do not block) if Docker is not detectable - it's a hard runtime dependency.
  if not Exec('cmd.exe', '/c where docker', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
  begin
    if MsgBox('Docker was not found on this machine.' + #13#10 + #13#10 +
              'This application runs on Docker Desktop, which must be installed and running to use it.' + #13#10 + #13#10 +
              'Continue with installation anyway?', mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;
