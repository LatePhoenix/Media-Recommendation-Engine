# Handoff — native Windows install + web fixes

_Last updated: 2026-08-09. Written for the next agent (Cursor) picking up this repo._

This note captures the current state, what was fixed, what is NOT yet deployed, and the
gotchas that cost the most time — so you can start without re-deriving them.

## TL;DR status

- The app **runs locally** as a native Windows install (no Docker): FastAPI serves the
  built web UI same-origin on `http://127.0.0.1:8000/`, backed by bundled Postgres + Redis
  running as WinSW services (`mediarec-postgres`, `mediarec-redis`, `mediarec-api`,
  `mediarec-worker`, `mediarec-scheduler`).
- Root causes of the "site can't be reached" saga are fixed (see below). The install was
  never actually completed before; a rebuilt installer + a Postgres service-account fix got
  it healthy.
- Several **web bugs are fixed in source but the running install may still show the old
  bundle** until the fixed web dist is copied in (or the installer is rebuilt + reinstalled).
  See "Not yet deployed".

## What was fixed this session

1. **Never-actually-installed / stale installer.** The real `Setup.exe` had never completed
   on the test machine (no `unins000.exe`, no uninstall registry entry, no ProgramData). The
   installer was also rebuilt because it predated the service-script fixes. Installer now
   bundles the current scripts + service XMLs.
2. **Postgres crash-loop (LocalSystem).** PostgreSQL on Windows refuses to run under an
   administrative account. The WinSW `<serviceaccount>NT AUTHORITY\LocalService</serviceaccount>`
   was not applied, and the `sc.exe config … password= ""` fallback silently no-op'd (Windows
   PowerShell drops the trailing empty-string arg). Fixed in
   `scripts/Install-MediaRecServices.ps1` → `Set-LocalServiceAccount`: now sets the account via
   **WMI `Win32_Service.Change`** and **verifies** with `sc qc` (throws if it didn't take).
   Data-dir ACLs already grant LocalService.
3. **Infinite render/fetch loop (jitter, 429 storm, "Failed to fetch", dead "Rate" button).**
   `apps/web/src/useDomain.ts` returned a fresh object every render, making
   `DomainHomePage`'s feed effect re-run every render. Fixed by memoizing on the route param.
   This one bug caused all four symptoms (the 429s were the rate limiter working correctly
   against the storm; `busy` never settled, so every button stayed disabled).
4. **App icon in the UI.** The sidebar/auth brand was a CSS placeholder glyph. The real icon
   (`apps/web/src/assets/app-icon.png`) is now bundled and shown. See `.brand-logo` in
   `styles.css`.
5. **Debug instrumentation removed.** The `#region agent log` blocks in `main.py`, `api.ts`,
   `App.tsx` and the `debug-959f20.log` artifact are gone. Do not reintroduce.

## Not yet deployed / open items (start here)

- **Deploy the fixed web bundle to the running install.** The source fix is built into
  `dist/native-windows/app/web` but the live install at
  `C:\Program Files\Media Recommendation Engine\app\web` may still serve the old bundle. From an
  **elevated** shell:
  `robocopy "<repo>\dist\native-windows\app\web" "C:\Program Files\Media Recommendation Engine\app\web" /MIR`
  then hard-refresh (Ctrl+F5). No service restart needed (static files served from disk).
- **Rebuild the installer** so a fresh machine ships all of the above (see build steps). The
  committed source is current; the `Setup.exe` artifact is git-ignored and must be rebuilt.
- **Posters are empty by design, not a bug.** All 85 seeded catalog items have
  `cover_url = NULL` (seed adds title/genre/year only). No CSP blocks images. To get real
  posters you need either a **library import** (Plex/etc. → authenticated artwork proxy at
  `apps/api/app/routers/imports.py`) or **cover-art enrichment** from a metadata provider.
- **Onboarding gaps.** `apps/web/src/pages/OnboardingPage.tsx` hardcodes
  `MEDIA_OPTIONS = movie/tv/audiobook/comic/book` — it **omits Games** (a default domain, 10
  seeded) and **includes books/comics** (opt-in). It should follow the user's
  `enabled_media_types`. The user also asked about a free-text "top 3 per domain" onboarding —
  that needs a metadata provider to resolve arbitrary titles (same dependency as poster art),
  so it's really one feature: **wire a metadata provider (TMDB / IGDB / OpenLibrary)**, which
  unlocks both posters and free-text onboarding.

## Build / run / verify

Two-step native build from repo root (details in `docs/packaging/installer.md`):
1. `.\scripts\prepare_native_installer_payload.ps1` → assembles `dist\native-windows`
   (python embed, Postgres+pgvector, Redis, WinSW, web dist, app trees). Big downloads cache
   in `dist\cache`. For a web-only change, just rerun `.\scripts\package_web_dist.ps1 -SkipInstall`.
2. Compile: `& "C:\Program Files\Inno Setup 7\ISCC.exe" "/DMyAppVersion=$((Get-Content installer\VERSION -Raw).Trim())" installer\MediaRecommendationEngine.iss`
   → `installer\output\MediaRecommendationEngine-Setup-<VERSION>.exe` (~101 MB).

Verify a running install (elevated for service ops):
`Get-Service mediarec-*` (all Running) · `sc.exe qc mediarec-postgres` (SERVICE_START_NAME =
`NT AUTHORITY\LocalService`) · `http://127.0.0.1:8000/` returns HTML (200), not JSON.

Tests (Python): use the repo `.venv` (Python 3.12), e.g. `.\.venv\Scripts\python.exe -m pytest`.
Note: the frontend fixes here have no unit tests; verify in-browser.

## Gotchas that cost time (do not relearn)

- **The installer bundles scripts + service XMLs straight from the working tree** (the `.iss`
  `[Files]` sources `scripts\*.ps1`, `installer\services\*.xml`, `installer\*.vbs`,
  `Repair-MediaRecLaunch.ps1`), NOT from the payload. After editing any of those you **must
  recompile ISCC** — a stale `installer\output\Setup.exe` reinstalls old scripts and silently
  reintroduces fixed bugs. WinSW XMLs also live in the payload's `runtime\winsw\`; regenerate
  with `package_winsw_services.ps1 -OutDir <payload> -KeepPlaceholders` before recompiling.
- **Do not run the Docker/dev stack (`start.bat`, compose, `npm run dev` on :5173) at the
  same time as the installed app** — the bootstrap aborts if 5432/6379 are already in use.
  `installer/Start-MediaRec.ps1` is the DEPRECATED Docker path, kept only as a dev convenience.
- **Postgres must be LocalService, set via WMI + verified** (see fix #2). Never trust a silent
  `sc.exe config` success.
- Worker/scheduler do **not** self-retry if they were killed during a DB outage — after any
  Postgres downtime, `Start-Service mediarec-worker, mediarec-scheduler`.

## Repo state

- All work committed on branch **`assets/app-icon`** and pushed to
  `origin` (`github.com/LatePhoenix/Media-Recommendation-Engine`). Consider opening a PR to
  `main` (history uses PR merges).
- Git-ignored, so **must be rebuilt, not fetched**: `dist/`, `installer/output/`,
  `apps/web/dist/`, `.env*` (except `.env.example`). Secrets live in
  `C:\ProgramData\MediaRecommendationEngine\config\.env` (generated at bootstrap), never in git.
