from __future__ import annotations

from typing import Any

from workers.importers.base import (
    ConnectorSession,
    Library,
    NormalizedConsumption,
    NormalizedItem,
)
from workers.importers.catalog_utils import parse_year
from workers.importers.secure_http import pinned_async_client


class AudiobookshelfConnector:
    source_name = "audiobookshelf"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def authenticate(self, credentials: dict[str, Any]) -> ConnectorSession:
        if credentials.get("api_key") or credentials.get("token"):
            return ConnectorSession(
                token=credentials.get("api_key") or credentials.get("token"),
                meta={"auth": "token"},
            )
        username = credentials.get("username")
        password = credentials.get("password")
        if not username or password is None:
            raise ValueError("Audiobookshelf requires api_key/token or username/password")
        async with pinned_async_client(self.base_url, timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/login",
                json={"username": username, "password": password},
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("user", {}).get("token") or data.get("token")
            return ConnectorSession(token=token, meta={"auth": "password", "user": data.get("user")})

    def _headers(self, token: str | None) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    async def list_libraries(self, session: ConnectorSession) -> list[Library]:
        async with pinned_async_client(self.base_url, timeout=30.0) as client:
            resp = await client.get(f"{self.base_url}/api/libraries", headers=self._headers(session.token))
            resp.raise_for_status()
            data = resp.json()
            libs = []
            for lib in data.get("libraries") or data or []:
                media_type = (lib.get("mediaType") or "").lower()
                hint = "audiobook" if media_type in {"book", "audiobook"} else "book"
                libs.append(Library(id=lib.get("id"), name=lib.get("name"), media_hint=hint))
            return libs

    async def sync_items(
        self,
        session: ConnectorSession,
        libraries: list[Library] | None = None,
        cursor: dict[str, Any] | None = None,
    ) -> tuple[list[NormalizedItem], dict[str, Any]]:
        libs = libraries or await self.list_libraries(session)
        items: list[NormalizedItem] = []
        async with pinned_async_client(self.base_url, timeout=60.0) as client:
            for lib in libs:
                resp = await client.get(
                    f"{self.base_url}/api/libraries/{lib.id}/items",
                    headers=self._headers(session.token),
                    params={"limit": 500},
                )
                if resp.status_code >= 400:
                    continue
                payload = resp.json()
                for raw in payload.get("results") or payload.get("entities") or []:
                    media = raw.get("media") or {}
                    metadata = media.get("metadata") or raw.get("metadata") or {}
                    authors = metadata.get("authors") or []
                    if authors and isinstance(authors[0], dict):
                        creators = [a.get("name") for a in authors if a.get("name")]
                    else:
                        creators = [str(a) for a in authors]
                    narrators = metadata.get("narrators") or []
                    creators = creators + [str(n) for n in narrators]
                    media_type = "audiobook" if (lib.media_hint or "audiobook") == "audiobook" else "book"
                    cover = None
                    if raw.get("id"):
                        cover = f"{self.base_url}/api/items/{raw['id']}/cover"
                    items.append(
                        NormalizedItem(
                            external_id=str(raw.get("id")),
                            media_type=media_type,
                            title=metadata.get("title") or raw.get("name") or "Untitled",
                            series=(metadata.get("series") or [None])[0]
                            if isinstance(metadata.get("series"), list)
                            else metadata.get("seriesName") or metadata.get("series"),
                            genres=list(metadata.get("genres") or []),
                            tags=list(metadata.get("tags") or []),
                            creators=creators,
                            release_year=parse_year(metadata.get("publishedYear") or metadata.get("year")),
                            description=metadata.get("description"),
                            runtime_or_length=media.get("duration"),
                            cover_url=cover,
                            raw=raw,
                        )
                    )
        return items, {"done": True}

    async def sync_consumption(
        self,
        session: ConnectorSession,
        cursor: dict[str, Any] | None = None,
    ) -> list[NormalizedConsumption]:
        # ABS progress often lives on media progress endpoints; best-effort
        async with pinned_async_client(self.base_url, timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/api/me/progress",
                headers=self._headers(session.token),
            )
            if resp.status_code >= 400:
                return []
            out: list[NormalizedConsumption] = []
            data = resp.json()
            rows = data if isinstance(data, list) else data.get("progress") or []
            for raw in rows:
                progress = float(raw.get("progress") or 0)
                out.append(
                    NormalizedConsumption(
                        external_item_id=str(raw.get("libraryItemId") or raw.get("id")),
                        interaction_type="finish" if progress >= 0.95 else "consume",
                        progress=progress,
                        confidence=0.8 if progress >= 0.95 else 0.5,
                        raw=raw,
                    )
                )
            return out
