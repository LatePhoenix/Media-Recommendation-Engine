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

Media types: movies, TV, books, audiobooks, comics, games (games schema-ready; connectors deferred).

## Quick start

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

For live-reload bind mounts while developing inside Docker:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up --build
```

(The Windows installer uses the base compose file only — no bind mounts — so Program Files ACLs cannot block the web container.)

- Web: http://localhost:5173
- API docs: http://localhost:8000/docs
- Postgres: localhost:5432
- Redis: localhost:6379

### Local API (without Docker for the app)

```bash
# Start postgres + redis via compose
docker compose -f infra/docker-compose.yml up -d postgres redis

python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r apps/api/requirements.txt
cd apps/api && alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload --app-dir .
```

```bash
cd apps/web && npm install && npm run dev
```

## Monorepo layout

```
apps/web/                 React UI
apps/api/                 FastAPI + recommender
workers/importers/        Jellyfin, Plex, Audiobookshelf, Komga stub, CSV
workers/recommender/      Nightly / online jobs
packages/shared-schema/   Shared enums / OpenAPI types
packages/enrichment/      EnrichmentPort + NoOp / Ollama stubs
docs/architecture/        Design, ERD, API contract, roadmap
infra/                    Docker Compose, Dockerfiles
```

## Recommendation principle

Ranking math never calls an LLM. Ollama may generate embeddings, tags, or prose explanations; the deterministic scorer remains authoritative.

Pass is **not** negative feedback by default — it temporarily suppresses an item and may resurface later.

## Plex connection

In **Imports → Add source**, select Plex and enter:

- Server URL, commonly `http://your-plex-server:32400`
- A Plex access token authorized for that server

With Docker Desktop and Plex on the same Windows host, use
`http://host.docker.internal:32400`.

Sync imports movie/TV sections and account-specific watched/progress state. The
token is encrypted at rest and is not embedded in stored artwork URLs.

## Docs

- [Architecture overview](docs/architecture/overview.md)
- [ERD / schema](docs/architecture/erd.md)
- [API contract](docs/architecture/api-contract.md)
- [Connector interfaces](docs/architecture/connectors.md)
- [Roadmap v2/v3](docs/architecture/roadmap.md)
