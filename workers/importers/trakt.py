from __future__ import annotations

from typing import Any

from workers.importers.base import (
    ConnectorSession,
    Library,
    NormalizedConsumption,
    NormalizedItem,
)


class TraktConnector:
    """Tracker abstraction stub for watch history / ratings import."""

    source_name = "trakt"

    def __init__(self, base_url: str = "https://api.trakt.tv") -> None:
        self.base_url = base_url.rstrip("/")

    async def authenticate(self, credentials: dict[str, Any]) -> ConnectorSession:
        return ConnectorSession(
            token=credentials.get("access_token"),
            meta={"client_id": credentials.get("client_id"), "stub": True},
        )

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
        return [], {"done": True, "stub": True}

    async def sync_consumption(
        self,
        session: ConnectorSession,
        cursor: dict[str, Any] | None = None,
    ) -> list[NormalizedConsumption]:
        return []
