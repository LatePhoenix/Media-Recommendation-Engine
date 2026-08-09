# Windows install layout

Phase 1.2 design freeze for native Windows packaging paths.

**Decision rules** (from [`.cursor/plans/native-windows-packaging.md`](../../.cursor/plans/native-windows-packaging.md) and [`.cursor/rules/windows-packaging.mdc`](../../.cursor/rules/windows-packaging.mdc)):

- Binaries and immutable payload live under Program Files.
- Mutable state lives under ProgramData.
- No production writes into the install directory after install.
- Windows product runtime is native (no Docker Desktop). Compose under `infra/` is developer-only.

Related inventory: [`runtime-assumptions.md`](runtime-assumptions.md).  
Web serving decision: [`adr-serve-web.md`](adr-serve-web.md).  
Python runtime assembly: [`python-runtime.md`](python-runtime.md).  
PostgreSQL + pgvector: [`postgres-distribution.md`](postgres-distribution.md).  
Redis: [`redis-distribution.md`](redis-distribution.md).  
Services: [`windows-services.md`](windows-services.md).  
Installer: [`installer.md`](installer.md).  
Upgrades: [`upgrades.md`](upgrades.md).  
CI / release: [`ci-release.md`](ci-release.md).  
Test matrix: [`test-matrix.md`](test-matrix.md).

---

## 1. Historical note (retired Docker installer)

Earlier Windows builds dumped the repo and launched Compose (`Start-MediaRec.ps1`,
`.env` under Program Files, Docker volume `infra_pgdata`). That product path is
**retired**. Helper scripts may still exist under `installer/` for reference; they
are not shipped by the native `.iss`. Compose under `infra/` remains for developers.

---

## 2. Target native layout

### 2.1 Program Files (immutable after install)

Root:

`%ProgramFiles%\Media Recommendation Engine\`

Suggested tree:

```text
%ProgramFiles%\Media Recommendation Engine\
  app\
    api\                    # packaged apps/api (or equivalent layout)
    packages\               # shared packages
    workers\                # RQ job modules
    web\                    # Vite production dist (index.html, assets/)
  runtime\
    python\                 # app-local Python 3.12 + site-packages
    postgres\               # portable PostgreSQL 16 binaries
    redis\                  # Windows Redis (or approved alternative) binaries
    winsw\                  # WinSW executables
  services\                 # WinSW XML configs (or copies under installer/services)
  scripts\                  # maintenance: migrate, diagnostics (not primary UX)
  assets\icons\             # app icon, installer branding
  LICENSE / NOTICE          # redistribution notices for bundled components
```

Rules:

- Installer may replace this tree on upgrade.
- Services must not write logs, DB files, or secrets here.
- Read-only for normal operation after install (ACLs may still allow TrustedInstaller/admin updates).

### 2.2 ProgramData (mutable state)

Root:

`%ProgramData%\MediaRecommendationEngine\`

Suggested tree:

```text
%ProgramData%\MediaRecommendationEngine\
  config\
    .env                    # secrets + URLs (localhost DB/Redis)
    appsettings.local.env   # optional overlays
  postgres\
    data\                   # PGDATA cluster
  redis\
    data\                   # RDB/AOF if enabled
  logs\
    mediarec-api\
    mediarec-worker\
    mediarec-postgres\
    mediarec-redis\
    mediarec-scheduler\     # if separate service
  diagnostics\              # support bundles (optional)
```

Rules:

- Survives app upgrades when Program Files is replaced.
- Uninstall may offer “retain user data” (leave ProgramData) vs “remove all data.”
- Generated secrets stay here; upgrades must not overwrite existing `.env` blindly ([`installer/setup-env.ps1`](../../installer/setup-env.ps1) already avoids clobbering strong keys — native setup must keep that idempotency).

### 2.3 LocalAppData

`%LocalAppData%\MediaRecommendationEngine\` is **not** the primary production state root.

Allowed uses only if intentionally chosen later:

- Per-user UI preferences (if a tray/control app needs them).
- Temporary diagnostics staging.

Do **not** put Postgres, Redis, or service secrets in LocalAppData for the machine-wide service model (admin install + WinSW).

---

## 3. Config and URL mapping

Native services must use host-local URLs, not Compose DNS names (`postgres`, `redis`). See [`runtime-assumptions.md`](runtime-assumptions.md).

Example ProgramData `.env` shape (illustrative):

```env
DATABASE_URL=postgresql+psycopg://mediarec:<secret>@127.0.0.1:5432/mediarec
REDIS_URL=redis://:<secret>@127.0.0.1:6379/0
API_SECRET_KEY=<generated>
CREDENTIALS_FERNET_KEY=<generated>
# After FastAPI serves the UI (adr-serve-web):
# API_CORS_ORIGINS can be empty/minimal for same-origin; or include http://127.0.0.1:8000 if needed
```

Process environment for API/worker services should point at:

- `WEB_DIST_DIR=%ProgramFiles%\Media Recommendation Engine\app\web` (or equivalent)
- Absolute path to config / `dotenv` file under ProgramData (avoid cwd-relative `.env` from Program Files)

---

## 4. Service names (preview)

Target WinSW service names (see [`windows-services.md`](windows-services.md)):

| Service name | Role |
|--------------|------|
| `mediarec-postgres` | Bundled PostgreSQL |
| `mediarec-redis` | Bundled Redis |
| `mediarec-api` | uvicorn: API + static UI |
| `mediarec-worker` | RQ workers (`imports` and/or `recommender`; may split later) |
| `mediarec-scheduler` | Optional if CF enqueue loop stays a separate process |

Dependency order: postgres + redis healthy → api (migrate/seed once) → workers → scheduler.

Ports (loopback preferred, matching current compose intent):

| Port | Process |
|------|---------|
| `5432` | Postgres |
| `6379` | Redis |
| `8000` | API + UI (native preferred single HTTP port) |

Port `5173` is Compose/Vite **developer** UI only — not part of the native product.

---

## 5. Upgrade and uninstall behavior

### Upgrade

- Replace Program Files payload.
- Preserve `%ProgramData%\MediaRecommendationEngine\postgres\data`.
- Preserve Redis data directory if persistence is enabled.
- Preserve `config\.env` and secrets; merge only new keys with safe defaults.
- Re-run Alembic migrations as an idempotent post-install / first-start step.
- Do not re-init PGDATA if the cluster already exists.

### Uninstall

- Stop and unregister WinSW services.
- Remove Program Files payload.
- Ask whether to delete ProgramData (default: retain data).

---

## 6. Developer Compose vs product install

| Concern | Policy |
|---------|--------|
| Native `.iss` | Sole Windows end-user distribution |
| `infra/docker-compose.yml` | Optional developer stack |
| Legacy `Start-MediaRec.ps1` / `Stop-MediaRec.ps1` | Not shipped; Compose helpers only if useful locally |
| `.env` location | ProgramData for native product; repo `.env` for Compose/dev |

Uninstall any old Docker-based install before installing native (same Program Files folder name).

---

## 7. Verification

1. Confirm this layout obeys: binaries → Program Files; state → ProgramData; no required post-install writes under Program Files.
2. Confirm single UI+API port plan matches [`adr-serve-web.md`](adr-serve-web.md) (`8000`).
3. When native services exist, verify:
   - After reboot, services start without writing under Program Files.
   - Upgrading the installer replaces Program Files but Postgres data under ProgramData remains.
   - Uninstall with “retain data” leaves ProgramData; “remove data” deletes it.

**Expected:** install, upgrade, and uninstall stories work without dumping state into Program Files.
