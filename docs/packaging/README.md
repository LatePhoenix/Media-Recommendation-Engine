# Packaging docs (native Windows)

End-user Windows distribution is a **native** Inno Setup installer (bundled Python,
Postgres+pgvector, Redis, WinSW). Docker Desktop is **not** required for installs.

| Doc | Topic |
|-----|-------|
| [`installer.md`](installer.md) | Installer UX, branding, signing notes |
| [`ci-release.md`](ci-release.md) | GitHub Actions release pipeline |
| [`test-matrix.md`](test-matrix.md) | Fresh / reboot / upgrade / failure / uninstall checks |
| [`upgrades.md`](upgrades.md) | Upgrade-safe ProgramData / secrets |
| [`windows-layout.md`](windows-layout.md) | Program Files vs ProgramData |
| [`windows-services.md`](windows-services.md) | WinSW service map |
| [`python-runtime.md`](python-runtime.md) | Embeddable CPython payload |
| [`postgres-distribution.md`](postgres-distribution.md) | EDB Postgres + pgvector pins |
| [`redis-distribution.md`](redis-distribution.md) | Redis + WinSW pins |
| [`runtime-assumptions.md`](runtime-assumptions.md) | Ports / env inventory from Compose era |
| [`adr-serve-web.md`](adr-serve-web.md) | UI served from FastAPI `:8000` |

Build instructions: [`installer/BUILD.md`](../../installer/BUILD.md).  
Plan (phases 1–10): [`.cursor/plans/native-windows-packaging.md`](../../.cursor/plans/native-windows-packaging.md).

## Handoff notes

- **Shipping path:** `installer/MediaRecommendationEngine.iss` + `scripts/prepare_native_installer_payload.ps1`
- **CI:** `.github/workflows/build-native-windows-installer.yml` (tag `v*` or workflow_dispatch)
- **Post-install smoke:** `scripts/Verify-NativeInstall.ps1`
- **Dev Compose:** `infra/docker-compose.yml` is still useful for developers; it is not the Windows product runtime
- **Do not commit:** `dist/`, `installer/output/`, real `.env`, signing certs
- **Known gaps before public release:** run [`test-matrix.md`](test-matrix.md) on a clean VM; optional Authenticode signing; first CI run is slow until `dist/cache` warms
