from __future__ import annotations

from typing import Any

from workers.importers.base import (
    ConnectorSession,
    Library,
    NormalizedConsumption,
    NormalizedItem,
)


class KomgaConnector:
    """Stub — series/library sync skeleton for comics/manga."""

    source_name = "komga"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def authenticate(self, credentials: dict[str, Any]) -> ConnectorSession:
        # Komga typically uses HTTP basic or session cookie; stub stores creds in session meta
        return ConnectorSession(
            token=credentials.get("api_key") or credentials.get("password"),
            meta={
                "username": credentials.get("username"),
                "password": credentials.get("password"),
                "stub": True,
            },
        )

    async def list_libraries(self, session: ConnectorSession) -> list[Library]:
        return []

    async def sync_items(
        self,
        session: ConnectorSession,
        libraries: list[Library] | None = None,
        cursor: dict[str, Any] | None = None,
    ) -> tuple[list[NormalizedItem], dict[str, Any]]:
        # Intentionally empty until Komga API wiring is completed
        return [], {"done": True, "stub": True}

    async def sync_consumption(
        self,
        session: ConnectorSession,
        cursor: dict[str, Any] | None = None,
    ) -> list[NormalizedConsumption]:
        return []
