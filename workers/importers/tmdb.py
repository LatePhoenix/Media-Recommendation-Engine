"""TMDB catalog harvest — popular/trending movies & TV (non-authoritative for ranking)."""

from __future__ import annotations

from typing import Any

import httpx

from workers.importers.base import (
    ConnectorSession,
    Library,
    NormalizedConsumption,
    NormalizedItem,
)
from workers.importers.catalog_utils import parse_year

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


class TmdbConnector:
    """Pull popular/trending catalog rows into the local item table."""

    source_name = "tmdb"

    def __init__(self, base_url: str = "https://api.themoviedb.org") -> None:
        self.base_url = (base_url or "https://api.themoviedb.org").rstrip("/")

    async def authenticate(self, credentials: dict[str, Any]) -> ConnectorSession:
        api_key = credentials.get("api_key") or credentials.get("tmdb_api_key")
        if not api_key:
            try:
                from app.config import get_settings

                api_key = get_settings().tmdb_api_key or None
            except Exception:  # noqa: BLE001
                api_key = None
        if not api_key:
            raise ValueError("TMDB requires api_key (or set TMDB_API_KEY in the environment)")
        return ConnectorSession(token=str(api_key), meta={"auth": "api_key"})

    async def list_libraries(self, session: ConnectorSession) -> list[Library]:
        return [
            Library(id="movie", name="TMDB Movies", media_hint="movie"),
            Library(id="tv", name="TMDB TV", media_hint="tv"),
        ]

    async def sync_items(
        self,
        session: ConnectorSession,
        libraries: list[Library] | None = None,
        cursor: dict[str, Any] | None = None,
    ) -> tuple[list[NormalizedItem], dict[str, Any]]:
        page = int((cursor or {}).get("page") or 1)
        libs = libraries or await self.list_libraries(session)
        items: list[NormalizedItem] = []
        max_page_seen = page

        async with httpx.AsyncClient(timeout=60.0) as client:
            for lib in libs:
                kind = "movie" if (lib.media_hint or lib.id) == "movie" else "tv"
                for endpoint in (f"/3/trending/{kind}/week", f"/3/{kind}/popular"):
                    resp = await client.get(
                        f"{self.base_url}{endpoint}",
                        params={"api_key": session.token, "page": page},
                    )
                    if resp.status_code >= 400:
                        continue
                    data = resp.json() or {}
                    max_page_seen = max(max_page_seen, int(data.get("total_pages") or page))
                    for raw in data.get("results") or []:
                        item = self._normalize(kind, raw)
                        if item and all(i.external_id != item.external_id for i in items):
                            items.append(item)

        next_page = page + 1
        done = next_page > min(max_page_seen, 5)  # Cap harvest depth per sync
        return items, {"page": next_page if not done else page, "done": done}

    async def sync_consumption(
        self,
        session: ConnectorSession,
        cursor: dict[str, Any] | None = None,
    ) -> list[NormalizedConsumption]:
        return []

    def _normalize(self, kind: str, raw: dict[str, Any]) -> NormalizedItem | None:
        tmdb_id = raw.get("id")
        if not tmdb_id:
            return None
        title = raw.get("title") or raw.get("name") or "Untitled"
        year = parse_year(raw.get("release_date") or raw.get("first_air_date"))
        poster = raw.get("poster_path")
        cover = f"{TMDB_IMAGE_BASE}{poster}" if poster else None
        media_type = "movie" if kind == "movie" else "tv"
        genres = []  # genre_ids need a separate lookup; leave empty
        return NormalizedItem(
            external_id=f"{kind}-{tmdb_id}",
            media_type=media_type,
            title=title,
            series=title if media_type == "tv" else None,
            genres=genres,
            release_year=year,
            description=raw.get("overview"),
            cover_url=cover,
            external_url=f"https://www.themoviedb.org/{kind}/{tmdb_id}",
            raw={"ids": {"tmdb": tmdb_id}, **{k: raw.get(k) for k in ("popularity", "vote_average")}},
        )
