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


class JellyfinConnector:
    source_name = "jellyfin"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def authenticate(self, credentials: dict[str, Any]) -> ConnectorSession:
        # Prefer API key; fall back to username/password auth
        if credentials.get("api_key"):
            return ConnectorSession(token=credentials["api_key"], meta={"auth": "api_key"})
        username = credentials.get("username")
        password = credentials.get("password")
        if not username or password is None:
            raise ValueError("Jellyfin requires api_key or username/password")
        async with pinned_async_client(self.base_url, timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/Users/AuthenticateByName",
                json={"Username": username, "Pw": password},
                headers=self._headers(None),
            )
            resp.raise_for_status()
            data = resp.json()
            return ConnectorSession(
                token=data.get("AccessToken"),
                meta={"user_id": data.get("User", {}).get("Id"), "auth": "password"},
            )

    def _headers(self, token: str | None) -> dict[str, str]:
        auth = (
            'MediaBrowser Client="MediaRec", Device="MediaRec", DeviceId="media-rec", Version="0.1.0"'
        )
        if token:
            auth += f', Token="{token}"'
        return {"Authorization": auth, "X-Emby-Authorization": auth}

    async def list_libraries(self, session: ConnectorSession) -> list[Library]:
        async with pinned_async_client(self.base_url, timeout=30.0) as client:
            resp = await client.get(
                f"{self.base_url}/Library/VirtualFolders",
                headers=self._headers(session.token),
            )
            resp.raise_for_status()
            libs = []
            for folder in resp.json():
                collection = (folder.get("CollectionType") or "").lower()
                hint = None
                if collection in {"movies", "movie"}:
                    hint = "movie"
                elif collection in {"tvshows", "tv"}:
                    hint = "tv"
                libs.append(
                    Library(id=folder.get("ItemId") or folder.get("Name"), name=folder.get("Name"), media_hint=hint)
                )
            return libs

    def _map_type(self, jf_type: str, collection_hint: str | None = None) -> str:
        t = (jf_type or "").lower()
        if t == "movie":
            return "movie"
        if t in {"series", "episode"}:
            return "tv"
        if collection_hint:
            return collection_hint
        return "movie"

    async def sync_items(
        self,
        session: ConnectorSession,
        libraries: list[Library] | None = None,
        cursor: dict[str, Any] | None = None,
    ) -> tuple[list[NormalizedItem], dict[str, Any]]:
        start = int((cursor or {}).get("start_index", 0))
        page = 100
        items: list[NormalizedItem] = []
        params: dict[str, Any] = {
            "Recursive": "true",
            "IncludeItemTypes": "Movie,Series",
            "Fields": "Genres,Overview,People,DateCreated,ProductionYear,Path",
            "StartIndex": start,
            "Limit": page,
        }
        async with pinned_async_client(self.base_url, timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/Items",
                headers=self._headers(session.token),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            for raw in data.get("Items") or []:
                people = raw.get("People") or []
                creators = [
                    p.get("Name")
                    for p in people
                    if p.get("Type") in {"Director", "Writer", "Actor"} and p.get("Name")
                ][:12]
                item_id = raw.get("Id")
                cover = None
                if item_id:
                    # Relative path — browsers fetch via authenticated artwork proxy.
                    cover = f"/Items/{item_id}/Images/Primary"
                items.append(
                    NormalizedItem(
                        external_id=str(item_id),
                        media_type=self._map_type(raw.get("Type")),
                        title=raw.get("Name") or "Untitled",
                        sort_title=raw.get("SortName") or raw.get("Name"),
                        series=raw.get("SeriesName"),
                        genres=list(raw.get("Genres") or []),
                        creators=creators,
                        release_year=parse_year(raw.get("ProductionYear")),
                        description=raw.get("Overview"),
                        runtime_or_length=raw.get("RunTimeTicks") and int(raw["RunTimeTicks"] / 10_000_000),
                        cover_url=cover,
                        external_url=f"{self.base_url}/web/index.html#!/details?id={item_id}",
                        raw=raw,
                    )
                )
            total = int(data.get("TotalRecordCount") or 0)
            next_cursor = {"start_index": start + page, "done": start + page >= total}
            return items, next_cursor

    async def sync_consumption(
        self,
        session: ConnectorSession,
        cursor: dict[str, Any] | None = None,
    ) -> list[NormalizedConsumption]:
        user_id = session.meta.get("user_id")
        if not user_id:
            return []
        async with pinned_async_client(self.base_url, timeout=60.0) as client:
            resp = await client.get(
                f"{self.base_url}/Users/{user_id}/Items",
                headers=self._headers(session.token),
                params={
                    "Filters": "IsPlayed,IsResumable",
                    "Recursive": "true",
                    "IncludeItemTypes": "Movie,Series,Episode",
                    "Limit": 200,
                },
            )
            if resp.status_code >= 400:
                return []
            out: list[NormalizedConsumption] = []
            for raw in resp.json().get("Items") or []:
                played = bool(raw.get("UserData", {}).get("Played"))
                out.append(
                    NormalizedConsumption(
                        external_item_id=str(raw.get("Id")),
                        interaction_type="finish" if played else "consume",
                        progress=raw.get("UserData", {}).get("PlayedPercentage"),
                        confidence=0.85 if played else 0.55,
                        raw=raw,
                    )
                )
            return out
