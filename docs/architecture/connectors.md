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

## Status

| Connector | Module | Status |
|-----------|--------|--------|
| Jellyfin | `workers/importers/jellyfin.py` | Implemented — movies/TV library + played/resumable |
| Plex | `workers/importers/plex.py` | Implemented — movie/TV sections + watched/progress state |
| Audiobookshelf | `workers/importers/audiobookshelf.py` | Implemented — libraries/items + progress best-effort |
| Komga | `workers/importers/komga.py` | Stub — auth session + empty sync |
| Trakt | `workers/importers/trakt.py` | Stub — tracker abstraction |
| CSV / manual | `workers/importers/csv_importer.py` | Implemented — rows → items + optional ratings |

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
```

Plex uses the user's server URL (commonly `http://server:32400`) and an
account-authorized Plex access token. Tokens remain encrypted at rest and are
never embedded in persisted artwork URLs.

## Job runner

`workers/importers/runner.py`:

1. Prefer enqueue to Redis RQ queue `imports`
2. If Redis/RQ unavailable, run synchronously (local-dev friendly)
3. Writes items, consumption interactions (`source=import`), updates job stats/status

## Ownership policy

- External systems: source of truth for consume/finish/progress
- This app: source of truth for pass, save, rate, recommendation explanations
- Never hard-couple ranking to a single server product — candidates may come from catalog + any connector
