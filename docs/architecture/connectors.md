# Connector Interfaces

All connectors implement `workers/importers/base.py` → `Connector` protocol.

```python
class Connector(Protocol):
    source_name: str
    async def authenticate(self, credentials: dict) -> ConnectorSession: ...
    async def list_libraries(self, session) -> list[Library]: ...
    async def sync_items(self, session, libraries=None, cursor=None) -> tuple[list[NormalizedItem], dict]: ...
    async def sync_consumption(self, session, cursor=None) -> list[NormalizedConsumption]: ...
```

Normalized items are upserted via `catalog_utils.upsert_item` (external ref first, then title/year/type).
Missing covers are optionally filled by `workers/importers/poster_enrichment.py` (TMDB / Open Library).

## Status

| Connector | Module | Status |
|-----------|--------|--------|
| Jellyfin | `workers/importers/jellyfin.py` | Implemented — movies/TV library + played/resumable; relative artwork via proxy |
| Plex | `workers/importers/plex.py` | Implemented — movie/TV sections + watched/progress state; relative artwork via proxy |
| Audiobookshelf | `workers/importers/audiobookshelf.py` | Implemented — libraries/items + progress best-effort; relative artwork via proxy |
| Trakt | `workers/importers/trakt.py` | Implemented — watched/rated movies & shows + consumption |
| TMDB | `workers/importers/tmdb.py` | Implemented — popular/trending movie & TV catalog harvest (non-authoritative) |
| Komga | `workers/importers/komga.py` | Stub — auth session + empty sync |
| CSV / manual | `workers/importers/csv_importer.py` | Implemented — rows → items + optional ratings |

Steam / IGDB / AniList / ComicVine remain out of scope for now.

## Credentials

Stored encrypted on `import_sources.credentials_encrypted` (Fernet). Typical shapes:

```json
// Jellyfin
{"api_key": "..."} 
// or
{"username": "...", "password": "..."}

// Audiobookshelf
{"token": "..."}
// or
{"username": "...", "password": "..."}

// Plex
{"api_key": "PLEX_ACCESS_TOKEN"}

// Trakt
{"client_id": "TRAKT_APP_CLIENT_ID", "access_token": "OAUTH_TOKEN"}

// TMDB (optional if TMDB_API_KEY is set in the environment)
{"api_key": "TMDB_API_KEY"}
```

Plex / Jellyfin / Audiobookshelf use the user's server URL. Tokens remain encrypted at rest and are
never embedded in persisted artwork URLs — the UI loads covers through
`GET /api/imports/sources/{id}/artwork?path=…`.

## Poster enrichment

Env keys (optional; ranking never depends on them):

| Key | Use |
|-----|-----|
| `TMDB_API_KEY` | Movie/TV posters when library cover missing; TMDB harvest connector |
| Open Library | Book/audiobook covers via public HTTPS (no key) |

## Job runner

`workers/importers/runner.py`:

1. Prefer enqueue to Redis RQ queue `imports`
2. If Redis/RQ unavailable, run synchronously (local-dev friendly)
3. Writes items, consumption interactions (`source=import`), updates job stats/status

## Ownership policy

- External systems: source of truth for consume/finish/progress
- This app: source of truth for pass, save, rate, recommendation explanations
- Never hard-couple ranking to a single server product — candidates may come from catalog + any connector
