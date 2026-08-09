# Native Windows CI / release pipeline (Phase 9)

Workflow: [`.github/workflows/build-native-windows-installer.yml`](../../.github/workflows/build-native-windows-installer.yml)

Related: [`installer.md`](installer.md), [`adr-serve-web.md`](adr-serve-web.md), [`installer/BUILD.md`](../../installer/BUILD.md), [`test-matrix.md`](test-matrix.md).

---

## What the pipeline builds

On a `windows-latest` runner:

1. **Web** — `scripts/package_web_dist.ps1` (Node 20, empty `VITE_API_BASE_URL` for same-origin)
2. **Python / Postgres+pgvector / Redis / WinSW** — `scripts/prepare_native_installer_payload.ps1`
3. **Inno Setup** — Chocolatey `innosetup` + `ISCC /DMyAppVersion=…`
4. **Artifacts** — Setup.exe, SHA-256 checksums, optional portable zip of `dist/native-windows`

| Trigger | Behavior |
|---------|----------|
| Tag `v*` (e.g. `v0.1.0`) | Full build; GitHub Release with installer + checksums |
| `workflow_dispatch` | Manual build; optional draft release if “create_release” is checked |

Version source: tag without the leading `v`, otherwise `installer/VERSION`.

---

## Caching

`dist/cache` (Python embed, EDB Postgres, Redis, WinSW zips) is cached via `actions/cache` keyed on the package scripts / packaging docs. First run is slow (multi‑GB downloads); later runs should hit cache when pins are unchanged.

---

## Code signing

Not enabled in CI yet. After a certificate is available:

1. Store PFX (or cloud HSM) credentials as GitHub Actions secrets.
2. Add a `signtool` step after ISCC (see [`installer.md`](installer.md)).
3. Optionally sign WinSW service EXEs before packaging.

---

## Local parity

```powershell
.\scripts\prepare_native_installer_payload.ps1
& "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe" "/DMyAppVersion=$((Get-Content installer\VERSION -Raw).Trim())" installer\MediaRecommendationEngine.iss
Get-FileHash installer\output\MediaRecommendationEngine-Setup-*.exe -Algorithm SHA256
```

---

## Acceptance

- Pushing tag `vX.Y.Z` produces a downloadable `MediaRecommendationEngine-Setup-X.Y.Z.exe` on the GitHub Release.
- Artifact upload also retains the build for 30 days under Actions.
- Portable zip is for internal smoke tests only (not a supported end-user install path).
- Before a public release, run [`test-matrix.md`](test-matrix.md) on a clean VM (at least fresh install + reboot + uninstall keep-data).
