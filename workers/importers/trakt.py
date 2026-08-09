"""Trakt watch history / ratings import (movies & shows)."""

from __future__ import annotations

import asyncio
from typing import Any

from workers.importers.base import (
    ConnectorSession,
    Library,
    NormalizedConsumption,
    NormalizedItem,
)
from workers.importers.catalog_utils import parse_year
from workers.importers.poster_enrichment import extract_provider_ids, resolve_poster_url
from workers.importers.secure_http import pinned_async_client

# Cap concurrent poster lookups so enrichment doesn't fan out unbounded worker threads.
_POSTER_CONCURRENCY = 8


class TraktConnector:
    """Import watched/rated movies and shows from Trakt.tv."""

    source_name = "trakt"

    def __init__(self, base_url: str = "https://api.trakt.tv") -> None:
        self.base_url = (base_url or "https://api.trakt.tv").rstrip("/")

    async def authenticate(self, credentials: dict[str, Any]) -> ConnectorSession:
        client_id = credentials.get("client_id") or credentials.get("api_key")
        token = credentials.get("access_token") or credentials.get("token")
        if not client_id:
            raise ValueError("Trakt requires client_id (Trakt API app client id)")
        if not token:
            raise ValueError("Trakt requires access_token (OAuth bearer token)")
        return ConnectorSession(token=str(token), meta={"client_id": str(client_id)})

    def _headers(self, session: ConnectorSession) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": str(session.meta.get("client_id") or ""),
            "Authorization": f"Bearer {session.token}",
        }

    async def list_libraries(self, session: ConnectorSession) -> list[Library]:
        return [
            Library(id="movies", name="Trakt Movies", media_hint="movie"),
            Library(id="shows", name="Trakt Shows", media_hint="tv"),
        ]

    async def sync_items(
        self,
        session: ConnectorSession,
        libraries: list[Library] | None = None,
        cursor: dict[str, Any] | None = None,
    ) -> tuple[list[NormalizedItem], dict[str, Any]]:
        libs = {lib.id for lib in (libraries or await self.list_libraries(session))}
        items: list[NormalizedItem] = []

        async with pinned_async_client(self.base_url, timeout=60.0) as client:
            if "movies" in libs:
                resp = await client.get(
                    f"{self.base_url}/sync/watched/movies",
                    headers=self._headers(session),
                )
                resp.raise_for_status()
                for row in resp.json() or []:
                    movie = row.get("movie") or {}
                    item = self._normalize_movie(movie)
                    if item:
                        items.append(item)

                rated = await client.get(
                    f"{self.base_url}/users/me/ratings/movies",
                    headers=self._headers(session),
                )
                if rated.status_code < 400:
                    for row in rated.json() or []:
                        movie = row.get("movie") or {}
                        item = self._normalize_movie(movie)
                        if item and all(i.external_id != item.external_id for i in items):
                            items.append(item)

            if "shows" in libs:
                resp = await client.get(
                    f"{self.base_url}/sync/watched/shows",
                    headers=self._headers(session),
                )
                resp.raise_for_status()
                for row in resp.json() or []:
                    show = row.get("show") or {}
                    item = self._normalize_show(show)
                    if item:
                        items.append(item)

        # Poster enrichment uses a blocking (sync) HTTP client; run it in a bounded pool
        # of worker threads AFTER normalization so it never blocks the event loop and the
        # lookups run concurrently instead of one-per-item serially.
        await self._enrich_posters(items)
        return items, {"done": True}

    async def _enrich_posters(self, items: list[NormalizedItem]) -> None:
        """Best-effort concurrent poster fetch (ranking never depends on covers)."""
        tmdb_key = ""
        try:
            from app.config import get_settings

            tmdb_key = get_settings().tmdb_api_key or ""
        except Exception:  # noqa: BLE001
            tmdb_key = ""
        if not tmdb_key or not items:
            return

        sem = asyncio.Semaphore(_POSTER_CONCURRENCY)

        async def _one(item: NormalizedItem) -> None:
            ids = extract_provider_ids(item.raw)
            async with sem:
                # to_thread offloads the sync httpx call so the loop stays responsive.
                item.cover_url = await asyncio.to_thread(
                    resolve_poster_url,
                    media_type=item.media_type,
                    title=item.title,
                    release_year=item.release_year,
                    tmdb_id=ids.get("tmdb"),
                    imdb_id=ids.get("imdb"),
                    tmdb_api_key=tmdb_key,
                )

        await asyncio.gather(*(_one(item) for item in items))

    async def sync_consumption(
        self,
        session: ConnectorSession,
        cursor: dict[str, Any] | None = None,
    ) -> list[NormalizedConsumption]:
        out: list[NormalizedConsumption] = []
        async with pinned_async_client(self.base_url, timeout=60.0) as client:
            for path, media in (
                ("/sync/watched/movies", "movie"),
                ("/sync/watched/shows", "show"),
            ):
                resp = await client.get(f"{self.base_url}{path}", headers=self._headers(session))
                if resp.status_code >= 400:
                    continue
                for row in resp.json() or []:
                    entity = row.get(media) or {}
                    ids = entity.get("ids") or {}
                    ext = self._external_id(ids, media)
                    if not ext:
                        continue
                    plays = int(row.get("plays") or 1)
                    out.append(
                        NormalizedConsumption(
                            external_item_id=ext,
                            interaction_type="finish" if plays >= 1 else "consume",
                            progress=1.0 if plays >= 1 else 0.5,
                            confidence=0.75,
                            raw=row,
                        )
                    )
        return out

    def _external_id(self, ids: dict[str, Any], kind: str) -> str | None:
        if ids.get("trakt"):
            return f"{kind}-{ids['trakt']}"
        if ids.get("tmdb"):
            return f"{kind}-tmdb-{ids['tmdb']}"
        if ids.get("imdb"):
            return f"{kind}-imdb-{ids['imdb']}"
        return None

    def _normalize_movie(self, movie: dict[str, Any]) -> NormalizedItem | None:
        # Posters are filled in later by the concurrent _enrich_posters pass so this
        # normalization stays pure (no network) and doesn't block the event loop.
        ids = movie.get("ids") or {}
        ext = self._external_id(ids, "movie")
        if not ext:
            return None
        title = movie.get("title") or "Untitled"
        year = parse_year(movie.get("year"))
        return NormalizedItem(
            external_id=ext,
            media_type="movie",
            title=title,
            release_year=year,
            external_url=f"https://trakt.tv/movies/{ids.get('slug')}" if ids.get("slug") else None,
            raw={"ids": ids, "title": title, "year": year},
        )

    def _normalize_show(self, show: dict[str, Any]) -> NormalizedItem | None:
        ids = show.get("ids") or {}
        ext = self._external_id(ids, "show")
        if not ext:
            return None
        title = show.get("title") or "Untitled"
        year = parse_year(show.get("year"))
        return NormalizedItem(
            external_id=ext,
            media_type="tv",
            title=title,
            series=title,
            release_year=year,
            external_url=f"https://trakt.tv/shows/{ids.get('slug')}" if ids.get("slug") else None,
            raw={"ids": ids, "title": title, "year": year},
        )
