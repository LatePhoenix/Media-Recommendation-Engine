# Runtime assumptions inventory

Inventory of runtime behavior currently provided by Docker Compose and related entrypoints.
This document is the Phase 1.1 design freeze for native Windows packaging.

**Sources (canonical):**

- [`infra/docker-compose.yml`](../../infra/docker-compose.yml)
- [`infra/docker-compose.dev.yml`](../../infra/docker-compose.dev.yml)
- [`infra/Dockerfile.api`](../../infra/Dockerfile.api)
- [`infra/Dockerfile.web`](../../infra/Dockerfile.web)
- [`infra/Dockerfile.web.dev`](../../infra/Dockerfile.web.dev)
- [`infra/entrypoint-api.sh`](../../infra/entrypoint-api.sh)
- [`infra/entrypoint-recommender-scheduler.sh`](../../infra/entrypoint-recommender-scheduler.sh)
- [`infra/nginx-web.conf`](../../infra/nginx-web.conf)
- [`infra/init-db.sql`](../../infra/init-db.sql)
- [`.env.example`](../../.env.example)
- [`apps/api/app/config.py`](../../apps/api/app/config.py)
- [`apps/api/app/main.py`](../../apps/api/app/main.py)
- [`README.md`](../../README.md)

Docker remains the supported developer/runtime path until the native installer is validated.
Do not remove Compose for **developers** based on this document alone. The Windows
Docker-based installer path is retired in favor of the native `.iss`.

---

## 1. Process model (today)

| Process | How it runs | Start command / entry |
|---------|-------------|------------------------|
| PostgreSQL 16 + pgvector | `pgvector/pgvector:pg16` | image default |
| Redis 7 | `redis:7-alpine` | `redis-server --requirepass …` |
| API | same image as workers (`infra/Dockerfile.api`) | `/entrypoint.sh` → migrate/seed → `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| importer-worker | same image; entrypoint overridden | `rq worker imports --url …@redis:6379/0` |
| recommender-worker | same image; entrypoint overridden | `rq worker recommender --url …@redis:6379/0` |
| recommender-scheduler | same image | `/bin/sh /entrypoint-recommender-scheduler.sh` |
| web (prod) | Vite build → nginx | `nginx -g 'daemon off;'` (`infra/Dockerfile.web`) |
| web (dev overlay) | Vite HMR | `npm run dev -- --host 0.0.0.0` |
| ollama | optional, commented out in compose | not required |

Workers replace `ENTRYPOINT` so they **do not** run migrate/seed; only the API process does ([`infra/docker-compose.yml`](../../infra/docker-compose.yml) comment on `importer-worker`).

---

## 2. Environment variables

### Compose overrides (container network)

Compose injects Docker DNS hostnames for API and workers ([`infra/docker-compose.yml`](../../infra/docker-compose.yml)):

| Variable | Compose value (typical) | Notes |
|----------|-------------------------|-------|
| `DATABASE_URL` | `postgresql+psycopg://…@postgres:5432/…` | Host `postgres` is Compose DNS only |
| `REDIS_URL` | `redis://:${REDIS_PASSWORD}@redis:6379/0` | Host `redis` is Compose DNS only |
| `API_CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000,http://web:80` | Adds container origin `web` |
| `PYTHONPATH` | `/:/packages:/app` | Matches image layout |
| `SEED_FAIL_SOFT` | from `.env`, default `false` | Soft-fail seed in API entrypoint |
| `ENRICHMENT_ENABLED` | `"false"` on recommender-worker | Hardcoded off for that service |
| `CF_REBUILD_INTERVAL_SECONDS` | default `86400` | Scheduler sleep interval |
| `VITE_API_BASE_URL` | build-arg default `http://localhost:8000` | Baked into web image at build time |

### Host / native defaults (`.env.example` + `config.py`)

App and example env use **localhost**, not Compose DNS:

| Variable | Default / example | Source |
|----------|-------------------|--------|
| `POSTGRES_USER` / `PASSWORD` / `DB` | `mediarec` | `.env.example` |
| `DATABASE_URL` | `postgresql+psycopg://mediarec:mediarec@localhost:5432/mediarec` | `.env.example`, `config.py` |
| `REDIS_PASSWORD` | `mediarec-redis` | `.env.example` |
| `REDIS_URL` | `redis://:mediarec-redis@localhost:6379/0` (example); app default `redis://localhost:6379/0` (**no password**) | mismatch risk if Redis has `requirepass` |
| `API_SECRET_KEY` | required; rejects placeholder / length &lt; 32 | `config.py` |
| `API_CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | `.env.example`, `config.py` |
| `CREDENTIALS_FERNET_KEY` | empty default; needed for encrypted import creds | `.env.example`, `config.py` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | optional enrichment |
| `ENRICHMENT_ENABLED` | `false` | optional |

`Settings` loads `env_file=".env"` **relative to process cwd** ([`apps/api/app/config.py`](../../apps/api/app/config.py)). Wrong cwd ⇒ missing secrets / wrong URLs.

### Critical assumption

Containers ignore localhost DB/Redis hosts because Compose `environment:` overrides them to `postgres` / `redis`. Native packaging must ship localhost (or named-pipe/local) URLs and must **never** leave Compose DNS names in a Windows service environment.

---

## 3. Working directories and import layout

| Context | Path | Source |
|---------|------|--------|
| API image `WORKDIR` | `/app` (`apps/api` copied here) | `Dockerfile.api` |
| Shared packages | `/packages` | `Dockerfile.api` |
| Workers tree | `/workers` | `Dockerfile.api` |
| `PYTHONPATH` | `/:/packages:/app` | compose + Dockerfile |
| Alembic | run from `/app` (has `alembic.ini`) | `entrypoint-api.sh` |
| Worker `working_dir` | `/app` | compose |
| Nginx static root | `/usr/share/nginx/html` | `Dockerfile.web`, `nginx-web.conf` |
| Postgres data | `/var/lib/postgresql/data` | compose volume `pgdata` |
| Postgres init SQL | `/docker-entrypoint-initdb.d/01-init.sql` ← `infra/init-db.sql` | first cluster init only |

Monorepo bootstrap in [`apps/api/app/main.py`](../../apps/api/app/main.py) detects either:

1. repo root via `parents[3]/packages`, or
2. container layout via `/packages`, else
3. falls back to API package root.

Native install must preserve an equivalent import layout or set an explicit `PYTHONPATH` / packaged entrypoints.

---

## 4. Port bindings

All published Compose ports are loopback-only (`127.0.0.1`):

| Service | Host binding | Container |
|---------|--------------|-----------|
| postgres | `127.0.0.1:5432` | `5432` |
| redis | `127.0.0.1:6379` | `6379` |
| api | `127.0.0.1:8000` | `8000` |
| web (prod) | `127.0.0.1:5173` | `80` (nginx) |
| web (dev) | `127.0.0.1:5173` | `5173` (Vite) |
| ollama (optional) | `127.0.0.1:11434` | `11434` |

Browser → API uses host `localhost:8000` via `VITE_API_BASE_URL`. Nginx does **not** reverse-proxy the API ([`infra/nginx-web.conf`](../../infra/nginx-web.conf) is static SPA only).

---

## 5. Container hostnames / DNS

| Hostname | Role |
|----------|------|
| `postgres` | `DATABASE_URL` host inside Compose |
| `redis` | `REDIS_URL` host; scheduler default fallback |
| `web` | CORS origin `http://web:80` only |
| `api` | dependency target for `web`; browsers do not call this hostname |

Scheduler shell default if unset: `redis://redis:6379/0` ([`entrypoint-recommender-scheduler.sh`](../../infra/entrypoint-recommender-scheduler.sh)) — Docker-centric and passwordless; compose normally overrides with a password URL.

Host → container special case: `host.docker.internal` for reaching Plex on the Windows host (documented in README).

---

## 6. Persistent paths / volumes

| Mount | Target | Persistence |
|-------|--------|-------------|
| named volume `pgdata` | `/var/lib/postgresql/data` | Yes (Compose project prefix typically `infra_pgdata`) |
| `./init-db.sql` (ro) | initdb.d | First init only |
| Redis | none | **Ephemeral** in current compose |
| Optional `ollama_data` | `/root/.ollama` | Commented |

No application file-data volume: catalog and auth live in Postgres. Redis holds RQ queues (`imports`, `recommender`).

Current Windows installer writes `.env` under Program Files install root ([`installer/setup-env.ps1`](../../installer/setup-env.ps1)) — that violates the native packaging rule of “no production writes into the install directory after install.” Native layout must move mutable config to ProgramData (see [`windows-layout.md`](windows-layout.md)).

---

## 7. Health checks and readiness

### Compose healthchecks

| Service | Test | Timing |
|---------|------|--------|
| postgres | `pg_isready -U ${POSTGRES_USER}` | 5s / 5s / 10 retries |
| redis | `redis-cli -a … ping` | 5s / 3s / 10 retries |

No Compose healthchecks on `api`, workers, scheduler, or `web`.

### Application HTTP

| Endpoint | Behavior | Source |
|----------|----------|--------|
| `GET /health` | Liveness JSON (`status`, `enrichment_enabled`, `version`) | `apps/api/app/main.py` |
| `GET /health/ready` | Postgres `SELECT 1` + Redis `PING`; HTTP 503 if either fails | `apps/api/app/main.py` |

---

## 8. Startup order

```
postgres (healthy) ─┬─► api
redis (healthy)   ─┤
                    ├─► importer-worker
                    ├─► recommender-worker
                    └─► recommender-scheduler (also waits recommender-worker started)
api (started) ─────► web
```

Workers can race API migrate/seed: they require schema already applied by the API entrypoint, but Compose only waits for postgres/redis health, not API readiness.

---

## 9. Bootstrap / migrations

Only the API entrypoint runs bootstrap ([`infra/entrypoint-api.sh`](../../infra/entrypoint-api.sh)):

1. `alembic upgrade head` (must succeed; `set -e`)
2. `python -m app.seed` — hard-fail unless `SEED_FAIL_SOFT=true`
3. `exec "$@"` → uvicorn

Postgres first-boot ([`infra/init-db.sql`](../../infra/init-db.sql)):

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

Scheduler warm-start ([`entrypoint-recommender-scheduler.sh`](../../infra/entrypoint-recommender-scheduler.sh)):

1. `sleep 30`
2. Enqueue `workers.recommender.jobs.nightly_retrain_stub`
3. Loop sleep `CF_REBUILD_INTERVAL_SECONDS` (default 86400)

---

## 10. Frontend serving (today)

| Mode | Mechanism | Port |
|------|-----------|------|
| Prod Compose | Vite `dist` served by nginx SPA (`try_files` → `index.html`) | host `5173` → container `80` |
| Dev overlay | Vite HMR | `5173` |
| FastAPI | **No** `StaticFiles` / SPA fallback today | API is JSON-only on `8000` |

Client code ([`apps/web/src/api.ts`](../../apps/web/src/api.ts), [`Poster.tsx`](../../apps/web/src/components/Poster.tsx)) uses bake-time `VITE_API_BASE_URL` defaulting to `http://localhost:8000`. There is no Vite `server.proxy` to the API.

Native packaging decision: serve built assets from FastAPI on a single port — see [`adr-serve-web.md`](adr-serve-web.md).

---

## 11. Mapping Docker assumptions → native Windows

| Docker provides | Native equivalent |
|-----------------|-------------------|
| Compose DNS `postgres` / `redis` | `localhost` (or service-local) URLs in ProgramData config |
| `pgdata` volume | `%ProgramData%\MediaRecommendationEngine\postgres\data` |
| Redis (no volume today) | Redis with ProgramData dir + persistence enabled |
| `PYTHONPATH=/:/packages:/app` | App-local runtime + explicit launchers / packaged layout |
| `/entrypoint.sh` migrate+seed | Install or first-start script; API service should not race workers |
| `/bin/sh` scheduler | Windows-native loop (PowerShell service / WinSW) |
| nginx on `:5173` | FastAPI static mount on `:8000` (preferred) |
| Loopback port publishing | Bind services to `127.0.0.1` unless explicitly opened |
| `.env` beside repo / `{app}` | Mutable config under ProgramData; inject via env or absolute path |
| Docker health → `depends_on` | WinSW dependencies + `/health/ready` probes |

---

## 12. Verification (this document)

1. Open [`infra/docker-compose.yml`](../../infra/docker-compose.yml) and confirm every service, port, volume, and `depends_on` row above matches.
2. Confirm API entrypoint still runs migrate then seed: `infra/entrypoint-api.sh`.
3. Confirm app defaults are localhost: `apps/api/app/config.py` `database_url` / `redis_url`.
4. Confirm web is nginx-static only (no API proxy): `infra/nginx-web.conf`.
5. Confirm no FastAPI static mount: search `apps/api` for `StaticFiles` (expect none).
6. Bring up Docker stack and check:
   - `GET http://127.0.0.1:8000/health` → 200
   - `GET http://127.0.0.1:8000/health/ready` → 200 when DB+Redis up
   - UI at `http://127.0.0.1:5173` (prod compose)

**Expected:** a reviewer can reconstruct the Compose runtime model from this file alone without inventing hostnames, ports, or bootstrap steps.
