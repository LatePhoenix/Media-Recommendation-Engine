# Building the Windows installer

Native-only Inno Setup script (no Docker Desktop runtime):

| Script | Output |
|--------|--------|
| [`MediaRecommendationEngine.iss`](MediaRecommendationEngine.iss) | `installer\output\MediaRecommendationEngine-Setup-{version}.exe` |

Requires [Inno Setup 6+](https://jrsoftware.org/isdl.php) (`ISCC`).

Compose under `infra/` remains optional for **developers** cloning the repo — it is not used by the Windows Setup.exe.

---

## Prerequisites

1. Inno Setup (`ISCC`)
2. Node.js 20+ (web UI build)
3. Network access on first payload build (Python embed, EDB Postgres, Redis, WinSW, PyPI)

## Build

From the **repo root**:

```powershell
# 1) Assemble runtimes under dist\native-windows (slow first run)
.\scripts\prepare_native_installer_payload.ps1

# 2) Compile Setup.exe
& "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe" "/DMyAppVersion=$((Get-Content installer\VERSION -Raw).Trim())" installer\MediaRecommendationEngine.iss
```

If `ISCC` is on `PATH`:

```powershell
ISCC "/DMyAppVersion=0.1.0" installer\MediaRecommendationEngine.iss
```

Output: `installer\output\MediaRecommendationEngine-Setup-0.1.0.exe`  
Keep `installer/VERSION` aligned with the `/DMyAppVersion=` override (CI does this from the git tag).

## What Setup does

1. Does **not** require Docker, WSL, or host Python.
2. Installs payload into `%ProgramFiles%\Media Recommendation Engine\`
3. Creates `%ProgramData%\MediaRecommendationEngine\` for config, DB, Redis, logs.
4. Runs `Initialize-NativeInstall.ps1` (hidden): secrets, Postgres, Redis, WinSW services.
5. Start Menu opens `http://127.0.0.1:8000/` (API + static UI).
6. Extra shortcuts: Stop Services, Collect Diagnostics, Uninstall.

Uninstall removes services + Program Files. ProgramData is kept unless the user confirms wipe.

## Verification

```powershell
.\scripts\prepare_native_installer_payload.ps1 -SkipDownload   # if caches exist
ISCC "/DMyAppVersion=0.1.0" installer\MediaRecommendationEngine.iss
# On a clean VM after install:
& "$env:ProgramFiles\Media Recommendation Engine\scripts\Verify-NativeInstall.ps1"
```

Full matrix: [`docs/packaging/test-matrix.md`](../docs/packaging/test-matrix.md).

Docs: [`docs/packaging/installer.md`](../docs/packaging/installer.md),
[`docs/packaging/ci-release.md`](../docs/packaging/ci-release.md),
[`docs/packaging/windows-services.md`](../docs/packaging/windows-services.md).

## GitHub Actions

```text
git tag v0.1.0
git push origin v0.1.0
```

Or run **Build native Windows installer** via `workflow_dispatch`.  
Workflow: [`.github/workflows/build-native-windows-installer.yml`](../.github/workflows/build-native-windows-installer.yml)
