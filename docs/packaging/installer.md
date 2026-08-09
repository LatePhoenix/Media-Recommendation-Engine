# Native Windows installer

Windows shipping path is the **native** Inno Setup script. Docker Desktop is not used
at install or runtime for end users.

| Artifact | Path |
|----------|------|
| Native `.iss` | [`installer/MediaRecommendationEngine.iss`](../../installer/MediaRecommendationEngine.iss) |
| Build instructions | [`installer/BUILD.md`](../../installer/BUILD.md) |
| Payload assembler | [`scripts/prepare_native_installer_payload.ps1`](../../scripts/prepare_native_installer_payload.ps1) |
| First-run bootstrap | [`installer/Initialize-NativeInstall.ps1`](../../installer/Initialize-NativeInstall.ps1) |
| Upgrades | [`upgrades.md`](upgrades.md) |
| Layout | [`windows-layout.md`](windows-layout.md) |
| CI / release | [`ci-release.md`](ci-release.md) |
| Test matrix | [`test-matrix.md`](test-matrix.md) |

`infra/docker-compose.yml` remains for optional **developer** workflows only.

## User experience

| Action | Mechanism |
|--------|-----------|
| Open app | `Open-MediaRec.vbs` → ensure services → `http://127.0.0.1:8000/` (Start Menu / Desktop) |
| Stop services | `Stop-MediaRecServices.vbs` → hidden `Install-MediaRecServices.ps1 -Action stop` |
| Diagnostics | `Collect-Diagnostics.vbs` → `Collect-Diagnostics.ps1 -NonInteractive` |
| Uninstall | Inno uninstaller + service uninstall; ProgramData retained unless user confirms wipe |

Normal users never need a terminal to open the app. PowerShell under `{app}\scripts` is maintenance/install only.

## Branding / version metadata

- `AppId` constant for in-place upgrades
- `UninstallDisplayName`, `VersionInfo*`, publisher fields
- Output: `MediaRecommendationEngine-Setup-{version}.exe`
- Shipped `version.txt` + `INFOBEFORE.txt` welcome page
- Icon from `assets/icons/app-icon.ico`

Keep `installer/VERSION` in sync with `#define MyAppVersion` in the `.iss` (CI overrides via `/DMyAppVersion=`).

## Code signing (optional)

Signing is optional until CI secrets and a certificate are available. Recommended approach:

1. Build unsigned Setup with ISCC (or enable `SignTool=` in the `.iss` once configured).
2. Sign the output EXE with Authenticode, e.g.:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  /f $env:CODE_SIGN_PFX /p $env:CODE_SIGN_PASSWORD `
  installer\output\MediaRecommendationEngine-Setup-0.1.0.exe
```

3. Prefer also signing WinSW service EXEs under `runtime\winsw\` before packaging (reduces SmartScreen friction).

Do **not** commit PFX files or passwords. Wire secrets in GitHub Actions when ready.

## Verification

```powershell
.\scripts\prepare_native_installer_payload.ps1
& "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe" installer\MediaRecommendationEngine.iss
```

Install the resulting `Setup.exe` on a clean machine and confirm:

1. No Docker / WSL / host Python required
2. Start Menu open shortcut launches the browser to port 8000 (after services are healthy)
3. `Get-Service mediarec-*` is Running after setup
4. Stop Services shortcut stops services without a PowerShell window
5. Collect Diagnostics writes a zip under ProgramData `\diagnostics`
6. Upgrade over a prior install preserves ProgramData secrets and DB
7. `Verify-NativeInstall.ps1` reports all PASS

Full matrix: [`test-matrix.md`](test-matrix.md). Post-install smoke: [`scripts/Verify-NativeInstall.ps1`](../../scripts/Verify-NativeInstall.ps1).
