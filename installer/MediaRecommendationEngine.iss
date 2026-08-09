; Native Windows installer (no Docker runtime).
; Build payload first:
;   .\scripts\prepare_native_installer_payload.ps1
; Then:
;   ISCC "/DMyAppVersion=0.1.0" installer\MediaRecommendationEngine.iss
;
; Optional code signing (release pipeline):
;   ISCC with SignTool=... or post-sign installer\output\*-Setup.exe
;   See docs/packaging/installer.md

#define MyAppName "Media Recommendation Engine"
#define MyAppShortName "MediaRecommendationEngine"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Singularity Solutions and Services"
#define MyAppURL "http://127.0.0.1:8000/"
#define MyAppSupportURL "http://127.0.0.1:8000/"
#define RepoRoot ".."
#define PayloadRoot "..\dist\native-windows"

#if !FileExists(PayloadRoot + "\runtime\python\python.exe")
  #error Native payload missing: dist\native-windows\runtime\python\python.exe - run scripts\prepare_native_installer_payload.ps1 first.
#endif
#if !FileExists(PayloadRoot + "\runtime\postgres\bin\postgres.exe")
  #error Native payload missing Postgres - run scripts\prepare_native_installer_payload.ps1 first.
#endif
#if !FileExists(PayloadRoot + "\runtime\redis\redis-server.exe")
  #error Native payload missing Redis - run scripts\prepare_native_installer_payload.ps1 first.
#endif
#if !FileExists(PayloadRoot + "\app\web\index.html")
  #error Native payload missing web UI - run scripts\prepare_native_installer_payload.ps1 (package_web_dist) first.
#endif

[Setup]
AppId={{7C1F3A2E-9B54-4E7A-B0D2-6F1A2C3D4E5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppSupportURL}
AppCopyright=Copyright (C) {#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
OutputDir=output
OutputBaseFilename={#MyAppShortName}-Setup-{#MyAppVersion}
SetupIconFile={#RepoRoot}\assets\icons\app-icon.ico
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\assets\icons\app-icon.ico
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright=Copyright (C) {#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageStretch=no
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
; Upgrades keep ProgramData; only Program Files payload is replaced.
CloseApplications=no
RestartIfNeededByRun=no
InfoBeforeFile=INFOBEFORE.txt
; Uncomment and configure for Authenticode signing in CI:
; SignTool=signtool
; SignedUninstaller=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
; ProgramData roots created early so bootstrap can write config/data.
; uninsneveruninstall: keep data across uninstall unless the user opts in (see [Code]).
Name: "{commonappdata}\MediaRecommendationEngine"; Flags: uninsneveruninstall
Name: "{commonappdata}\MediaRecommendationEngine\config"; Flags: uninsneveruninstall
Name: "{commonappdata}\MediaRecommendationEngine\logs"; Flags: uninsneveruninstall
Name: "{commonappdata}\MediaRecommendationEngine\postgres"; Flags: uninsneveruninstall
Name: "{commonappdata}\MediaRecommendationEngine\redis"; Flags: uninsneveruninstall
Name: "{commonappdata}\MediaRecommendationEngine\diagnostics"; Flags: uninsneveruninstall

[Files]
; Packaged runtimes + app trees (built by prepare_native_installer_payload.ps1)
Source: "{#PayloadRoot}\runtime\*"; DestDir: "{app}\runtime"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#PayloadRoot}\app\*"; DestDir: "{app}\app"; Flags: recursesubdirs createallsubdirs ignoreversion

; Branding + version stamp
Source: "{#RepoRoot}\assets\icons\*"; DestDir: "{app}\assets\icons"; Flags: ignoreversion
Source: "VERSION"; DestDir: "{app}"; DestName: "version.txt"; Flags: ignoreversion
Source: "INFOBEFORE.txt"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion isreadme

; Env template (secrets land in ProgramData, not Program Files)
Source: "{#RepoRoot}\.env.example"; DestDir: "{app}\config"; DestName: ".env.example"; Flags: ignoreversion onlyifdoesntexist

; Maintenance / bootstrap scripts (not primary UX)
Source: "{#RepoRoot}\scripts\Initialize-MediaRecDatabase.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "{#RepoRoot}\scripts\Initialize-MediaRecRedis.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "{#RepoRoot}\scripts\package_winsw_services.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "{#RepoRoot}\scripts\Install-MediaRecServices.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "{#RepoRoot}\scripts\verify_winsw_services.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "Initialize-NativeInstall.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "Collect-Diagnostics.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "{#RepoRoot}\scripts\Verify-NativeInstall.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion

; Service XML templates (also staged under runtime\winsw at bootstrap)
Source: "services\*.xml"; DestDir: "{app}\services"; Flags: ignoreversion
Source: "redis\redis.conf.template"; DestDir: "{app}\runtime\redis"; DestName: "redis.conf.template"; Flags: ignoreversion

; User-facing open / stop / diagnostics (no Docker; no interactive PowerShell Start)
Source: "Open-MediaRec.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "Open-MediaRec.url"; DestDir: "{app}"; Flags: ignoreversion
Source: "Stop-MediaRecServices.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "Collect-Diagnostics.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\scripts\Repair-MediaRecLaunch.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion

[Icons]
; Primary: start services if needed, then open the local app URL
Name: "{group}\{#MyAppName}"; Filename: "{app}\Open-MediaRec.vbs"; \
  IconFilename: "{app}\assets\icons\app-icon.ico"; Comment: "Open {#MyAppName}"
Name: "{group}\Stop Services"; Filename: "{app}\Stop-MediaRecServices.vbs"; \
  IconFilename: "{app}\assets\icons\app-icon.ico"; Comment: "Stop {#MyAppName} services"
Name: "{group}\Collect Diagnostics"; Filename: "{app}\Collect-Diagnostics.vbs"; \
  IconFilename: "{app}\assets\icons\app-icon.ico"; Comment: "Collect a support diagnostics bundle"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Open-MediaRec.vbs"; \
  IconFilename: "{app}\assets\icons\app-icon.ico"; Tasks: desktopicon

[Run]
; First-time / upgrade bootstrap: secrets, DB, Redis, WinSW install+start (hidden)
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\scripts\Initialize-NativeInstall.ps1"" -InstallRoot ""{app}"" -DataRoot ""{commonappdata}\MediaRecommendationEngine"" -Quiet"; \
  StatusMsg: "Configuring services and database..."; Flags: runhidden waituntilterminated
; Open the app (starts services if needed)
Filename: "{app}\Open-MediaRec.vbs"; \
  Description: "Open {#MyAppName}"; Flags: postinstall shellexec skipifsilent nowait

[UninstallRun]
; Best-effort stop + unregister services before files are removed.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\scripts\Install-MediaRecServices.ps1"" -Action uninstall -InstallRoot ""{app}"""; \
  Flags: runhidden; RunOnceId: "UninstallServices"

[Code]
var
  GRemoveProgramData: Boolean;

function InitializeSetup(): Boolean;
begin
  { Native installer does not require Docker, WSL, or host Python. }
  Result := True;
end;

function InitializeUninstall(): Boolean;
var
  DataRoot: String;
begin
  GRemoveProgramData := False;
  DataRoot := ExpandConstant('{commonappdata}\MediaRecommendationEngine');
  if DirExists(DataRoot) then
  begin
    if MsgBox(
      'Also remove application data (database, Redis, and settings)?'#13#10#13#10 +
      DataRoot + #13#10#13#10 +
      'Choose No to keep your data for a future reinstall.',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      GRemoveProgramData := True;
  end;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and GRemoveProgramData then
  begin
    DelTree(ExpandConstant('{commonappdata}\MediaRecommendationEngine'), True, True, True);
  end;
end;
