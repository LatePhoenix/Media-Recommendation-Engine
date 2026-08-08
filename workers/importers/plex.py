from __future__ import annotations

from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree  # Element type only; parsing uses defusedxml below

from defusedxml.ElementTree import fromstring as safe_fromstring

from workers.importers.base import (
    ConnectorSession,
    Library,
    NormalizedConsumption,
    NormalizedItem,
)
from workers.importers.catalog_utils import parse_year
from workers.importers.secure_http import pinned_async_client


class PlexConnector:
    """Import movie/TV libraries and watched progress from a Plex Media Server."""

    source_name = "plex"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.machine_id: str | None = None
        self._consumption: list[NormalizedConsumption] = []

    def _headers(self, token: str | None) -> dict[str, str]:
        headers = {
            "Accept": "application/xml",
            "X-Plex-Product": "MediaRec",
            "X-Plex-Version": "0.1.0",
            "X-Plex-Client-Identifier": "media-rec-engine",
        }
        if token:
            headers["X-Plex-Token"] = token
        return headers

    async def authenticate(self, credentials: dict[str, Any]) -> ConnectorSession:
        token = (
            credentials.get("plex_token")
            or credentials.get("token")
            or credentials.get("api_key")
        )
        if not self.base_url:
            raise ValueError("Plex requires a server base URL")
        if not token:
            raise ValueError("Plex requires a Plex access token")

        async with pinned_async_client(self.base_url, timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/identity",
                headers=self._headers(str(token)),
            )
            response.raise_for_status()
            root = safe_fromstring(response.content)
            self.machine_id = root.get("machineIdentifier")
            return ConnectorSession(
                token=str(token),
                meta={"machine_id": self.machine_id, "auth": "token"},
            )

    async def list_libraries(self, session: ConnectorSession) -> list[Library]:
        async with pinned_async_client(self.base_url, timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/library/sections",
                headers=self._headers(session.token),
            )
            response.raise_for_status()
            root = safe_fromstring(response.content)

        libraries: list[Library] = []
        for directory in root.findall("Directory"):
            section_type = (directory.get("type") or "").lower()
            media_hint = {"movie": "movie", "show": "tv"}.get(section_type)
            if not media_hint:
                continue
            key = directory.get("key")
            if key:
                libraries.append(
                    Library(
                        id=key,
                        name=directory.get("title") or f"Plex section {key}",
                        media_hint=media_hint,
                    )
                )
        return libraries

    async def sync_items(
        self,
        session: ConnectorSession,
        libraries: list[Library] | None = None,
        cursor: dict[str, Any] | None = None,
    ) -> tuple[list[NormalizedItem], dict[str, Any]]:
        sections = libraries or await self.list_libraries(session)
        items: list[NormalizedItem] = []
        self._consumption = []

        async with pinned_async_client(self.base_url, timeout=60.0) as client:
            for library in sections:
                response = await client.get(
                    f"{self.base_url}/library/sections/{quote(library.id, safe='')}/all",
                    headers=self._headers(session.token),
                    params={"includeGuids": "1"},
                )
                response.raise_for_status()
                root = safe_fromstring(response.content)
                for element in root:
                    normalized = self._normalize_element(element, library.media_hint)
                    if normalized is None:
                        continue
                    items.append(normalized)
                    consumption = self._normalize_consumption(element, normalized.external_id)
                    if consumption is not None:
                        self._consumption.append(consumption)

        return items, {"done": True, "sections_synced": len(sections)}

    async def sync_consumption(
        self,
        session: ConnectorSession,
        cursor: dict[str, Any] | None = None,
    ) -> list[NormalizedConsumption]:
        # Plex includes account-specific view state in section metadata. sync_items
        # captures it so consumption and catalog rows share the same ratingKey.
        return list(self._consumption)

    def _normalize_element(
        self,
        element: ElementTree.Element,
        media_hint: str | None,
    ) -> NormalizedItem | None:
        plex_type = (element.get("type") or "").lower()
        media_type = {"movie": "movie", "show": "tv"}.get(plex_type, media_hint)
        if media_type not in {"movie", "tv"}:
            return None

        rating_key = element.get("ratingKey")
        title = element.get("title")
        if not rating_key or not title:
            return None

        genres = [
            node.get("tag")
            for node in element.findall("Genre")
            if node.get("tag")
        ]
        creators = [
            node.get("tag")
            for tag in ("Director", "Writer")
            for node in element.findall(tag)
            if node.get("tag")
        ]
        tags = [
            node.get("tag")
            for tag in ("Collection", "Label", "Country")
            for node in element.findall(tag)
            if node.get("tag")
        ]
        duration_ms = self._as_int(element.get("duration"))
        thumb = element.get("thumb")
        details_key = quote(f"/library/metadata/{rating_key}", safe="")
        external_url = (
            f"{self.base_url}/web/index.html#!/server/{self.machine_id}/details?key={details_key}"
            if self.machine_id
            else f"{self.base_url}/web"
        )

        return NormalizedItem(
            external_id=rating_key,
            media_type=media_type,
            title=title,
            sort_title=element.get("titleSort") or title,
            series=element.get("parentTitle") or element.get("grandparentTitle"),
            genres=genres,
            tags=tags,
            creators=creators[:12],
            release_year=parse_year(element.get("year")),
            description=element.get("summary"),
            runtime_or_length=int(duration_ms / 1000) if duration_ms else None,
            # Relative thumb path — browsers fetch via authenticated artwork proxy.
            cover_url=thumb if thumb else None,
            external_url=external_url,
            raw={
                "ratingKey": rating_key,
                "type": plex_type,
                "guid": element.get("guid"),
                # Provider guids (imdb://tt…, tmdb://…, tvdb://…) enable verified
                # external links; requested via includeGuids=1.
                "guids": [g.get("id") for g in element.findall("Guid") if g.get("id")],
                "viewCount": element.get("viewCount"),
                "viewOffset": element.get("viewOffset"),
                "duration": element.get("duration"),
                "leafCount": element.get("leafCount"),
                "viewedLeafCount": element.get("viewedLeafCount"),
            },
        )

    def _normalize_consumption(
        self,
        element: ElementTree.Element,
        external_id: str,
    ) -> NormalizedConsumption | None:
        view_count = self._as_int(element.get("viewCount")) or 0
        duration = self._as_int(element.get("duration")) or 0
        view_offset = self._as_int(element.get("viewOffset")) or 0
        leaf_count = self._as_int(element.get("leafCount")) or 0
        viewed_leaf_count = self._as_int(element.get("viewedLeafCount")) or 0

        finished = view_count > 0 or (leaf_count > 0 and viewed_leaf_count >= leaf_count)
        has_progress = view_offset > 0 or viewed_leaf_count > 0
        if not finished and not has_progress:
            return None

        if duration > 0:
            progress = min(view_offset / duration, 1.0)
        elif leaf_count > 0:
            progress = min(viewed_leaf_count / leaf_count, 1.0)
        else:
            progress = 1.0 if finished else None

        return NormalizedConsumption(
            external_item_id=external_id,
            interaction_type="finish" if finished else "consume",
            progress=progress,
            confidence=0.9 if finished else 0.6,
            raw={
                "viewCount": view_count,
                "viewOffset": view_offset,
                "duration": duration,
                "leafCount": leaf_count,
                "viewedLeafCount": viewed_leaf_count,
            },
        )

    @staticmethod
    def _as_int(value: str | None) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
