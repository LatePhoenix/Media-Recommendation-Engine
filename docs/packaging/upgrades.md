# Upgrade-safe native installs

Phase 8.1 rules for upgrading Media Recommendation Engine on Windows without
losing user data or secrets.

Related: [`windows-layout.md`](windows-layout.md), [`installer.md`](installer.md).

---

## What upgrades replace vs preserve

| Location | On upgrade |
|----------|------------|
| `%ProgramFiles%\Media Recommendation Engine\` | Replaced by Inno (new runtimes, app code, scripts, icons) |
| `%ProgramData%\MediaRecommendationEngine\postgres\data\` | **Preserved** (never deleted by installer) |
| `%ProgramData%\MediaRecommendationEngine\redis\` | **Preserved** (`redis.conf`, `data\`, AOF/RDB) |
| `%ProgramData%\MediaRecommendationEngine\config\.env` | **Preserved**; bootstrap only fills missing keys / replaces insecure placeholders |
| `%ProgramData%\MediaRecommendationEngine\logs\` | Preserved (append) |
| WinSW service registrations | Re-installed / restarted with new XML from the new Program Files tree |

Inno `AppId` stays constant (`{7C1F3A2E-…}`) so Setup performs an in-place upgrade of the same product.

---

## Bootstrap behavior (`Initialize-NativeInstall.ps1`)

1. If `config\.env` is missing → create from `.env.example` and generate secrets.
2. If `config\.env` exists → **do not** overwrite existing secrets or passwords.
3. Merge: add keys that exist in the new `.env.example` but are absent from `.env`.
4. Replace only known insecure placeholders (`change-me-in-production…`, default `mediarec` / `mediarec-redis` passwords).
5. `Initialize-MediaRecDatabase.ps1` skips `initdb` when `PG_VERSION` already exists.
6. `Initialize-MediaRecRedis.ps1` does not rewrite `redis.conf` unless `-Force` or the file is missing.
7. Writes `config\install-state.json` with app version and timestamps (upgrade detection).

---

## Uninstall

Default uninstall:

- Stops and unregisters `mediarec-*` services
- Removes Program Files payload
- **Retains** ProgramData (DB, Redis, secrets)

During uninstall, Setup asks whether to also delete ProgramData. Default is **No** (keep data for reinstall).

---

## Verification

1. Install vN, create data (register user / rate items) or note DB file timestamps.
2. Install vN+1 over it (same `AppId`).
3. Confirm:
   - `config\.env` secrets unchanged
   - Postgres data directory still present; app still authenticates
   - Redis persistence files still present
   - Services running; `http://127.0.0.1:8000/health/ready` OK

Full upgrade + reboot/uninstall cases: [`test-matrix.md`](test-matrix.md).
