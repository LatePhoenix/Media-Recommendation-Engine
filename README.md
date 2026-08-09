# Media Recommendation Engine

Local-first hybrid media recommender: deterministic retrieval + ranking first, optional Ollama enrichment at the edges.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React + Vite + TypeScript |
| API | FastAPI + SQLAlchemy 2 + Alembic |
| DB | PostgreSQL 16 + pgvector |
| Jobs | Redis + RQ |
| Enrichment | Ollama behind `EnrichmentPort` (optional) |

Media types: movies, TV, books, audiobooks, comics, games — each an operationally-separate vertical (default-enabled: movies, TV, audiobooks, games; books and comics are opt-in per user). See the [roadmap](docs/architecture/roadmap.md) for phase status (domain separation, interest layer, external links, metadata quality, collaborative filtering, and UI are implemented).

## Quick start

### Windows end users (native installer)

Build or download `MediaRecommendationEngine-Setup-*.exe` — see [`installer/BUILD.md`](installer/BUILD.md) and [`docs/packaging/README.md`](docs/packaging/README.md).

- No Docker Desktop, WSL, or host Python required
- App URL after install: http://127.0.0.1:8000/ (UI + API)
- Post-install smoke: `Verify-NativeInstall.ps1` under Program Files `\scripts`

### Developers (optional Compose)

```bash
cp .env.example .env
# Set API_SECRET_KEY (and prefer rotating POSTGRES_PASSWORD / REDIS_PASSWORD).
docker compose -f infra/docker-compose.yml up --build
# Or: make up
```

For live-reload bind mounts while developing inside Compose:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up --build
# Or: make dev
```

- Web (Compose): http://localhost:5173 (nginx static in prod compose; Vite HMR in `.dev.yml`)
- Native install UI/API: http://127.0.0.1:8000/
- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness: http://localhost:8000/health/ready
- Postgres / Redis: bound to `127.0.0.1` only (not LAN-exposed)

**Auth model (local-first single-household):** the first registered user is admin.
Set `REGISTRATION_ENABLED=false` after setup to lock signup. Admin routes and
manual external-link overrides require `is_admin`. The catalog is shared within
the household.

**Import URLs:** `ALLOW_PRIVATE_IMPORT_URLS=true` (default) allows LAN/loopback
Plex/Jellyfin base URLs; cloud metadata / link-local remain blocked.

### Local dev without Docker for the app

> **Use Python 3.12.** The API image is `python:3.12-slim` and the pinned deps have
> no wheels for 3.14+ (`psycopg[binary]`, `pydantic-core`, …), so a 3.14 venv fails
> to install. Postgres 16 + pgvector and Redis still run as containers (used purely
> as a database appliance).

Native runs need `API_SECRET_KEY` and `CREDENTIALS_FERNET_KEY` in the environment
(pydantic reads `.env` relative to cwd, so exporting them is the reliable path).
`DATABASE_URL`/`REDIS_URL` default to `localhost:5432` / `localhost:6379`, matching
the containers. Generate secrets with:
`python -c "import secrets,base64,os; print('API_SECRET_KEY='+secrets.token_urlsafe(48)); print('CREDENTIALS_FERNET_KEY='+base64.urlsafe_b64encode(os.urandom(32)).decode())"`

**Linux / macOS:**

```bash
docker compose -f infra/docker-compose.yml up -d postgres redis   # DB services only
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt pytest
export API_SECRET_KEY=... CREDENTIALS_FERNET_KEY=... PYTHONPATH="$PWD/apps/api:$PWD:$PWD/packages"
cd apps/api && alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload            # API on :8000
```

**Windows / PowerShell** (call `python.exe` directly — the execution policy blocks
`Activate.ps1`):

```powershell
docker compose -f infra/docker-compose.yml up -d postgres redis
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r apps\api\requirements.txt pytest
$env:API_SECRET_KEY="..."; $env:CREDENTIALS_FERNET_KEY="..."
$env:PYTHONPATH="$PWD\apps\api;$PWD;$PWD\packages"
Set-Location apps\api
..\..\.venv\Scripts\python.exe -m alembic upgrade head
..\..\.venv\Scripts\python.exe -m app.seed
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
```

Web (either OS):

```bash
cd apps/web && npm install && npm run dev   # http://localhost:5173
```

Tests are DB-free (no Postgres/Redis needed); `apps/api/conftest.py` sets the test
secrets and import paths, so from `apps/api`:

```bash
python -m pytest app/tests -q
```

## Monorepo layout

```
apps/web/                 React UI
apps/api/                 FastAPI + recommender
workers/importers/        Jellyfin, Plex, Audiobookshelf, Trakt, TMDB harvest, Komga stub, CSV
workers/recommender/      Nightly / online jobs
packages/shared-schema/   Shared enums / OpenAPI types
packages/enrichment/      EnrichmentPort + NoOp / Ollama stubs
docs/architecture/        Design, ERD, API contract, roadmap
docs/packaging/           Native Windows packaging runbooks
installer/                Inno Setup + WinSW service templates
infra/                    Optional Docker Compose for developers
scripts/                  Payload build / verify / service helpers
```

## Recommendation principle

Ranking math never calls an LLM. Ollama may generate embeddings, tags, or prose explanations; the deterministic scorer remains authoritative.

Pass is **not** negative feedback by default — it temporarily suppresses an item and may resurface later.

## Plex connection

In **Imports → Add source**, select Plex and enter:

- Server URL, commonly `http://your-plex-server:32400`
- A Plex access token authorized for that server

With Docker Desktop and Plex on the same Windows host, use
`http://host.docker.internal:32400` (allowed when `ALLOW_PRIVATE_IMPORT_URLS=true`).

Sync imports movie/TV sections and account-specific watched/progress state. The
token is encrypted at rest and is not embedded in stored artwork URLs — the UI
loads covers through an authenticated `/api/imports/sources/{id}/artwork` proxy.

## Docs

- [Packaging (native Windows)](docs/packaging/README.md)
- [Architecture overview](docs/architecture/overview.md)
- [ERD / schema](docs/architecture/erd.md)
- [API contract](docs/architecture/api-contract.md)
- [Connector interfaces](docs/architecture/connectors.md)
- [Roadmap v2/v3](docs/architecture/roadmap.md)
