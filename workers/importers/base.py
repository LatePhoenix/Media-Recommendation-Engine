from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Library:
    id: str
    name: str
    media_hint: str | None = None


@dataclass
class NormalizedItem:
    external_id: str
    media_type: str
    title: str
    sort_title: str | None = None
    series: str | None = None
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    creators: list[str] = field(default_factory=list)
    release_year: int | None = None
    description: str | None = None
    runtime_or_length: int | None = None
    cover_url: str | None = None
    external_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedConsumption:
    external_item_id: str
    interaction_type: str  # consume | finish
    progress: float | None = None
    confidence: float = 0.6
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncResult:
    items_upserted: int = 0
    consumption_written: int = 0
    errors: list[str] = field(default_factory=list)
    cursor: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorSession:
    token: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Connector(Protocol):
    source_name: str

    async def authenticate(self, credentials: dict[str, Any]) -> ConnectorSession: ...

    async def list_libraries(self, session: ConnectorSession) -> list[Library]: ...

    async def sync_items(
        self,
        session: ConnectorSession,
        libraries: list[Library] | None = None,
        cursor: dict[str, Any] | None = None,
    ) -> tuple[list[NormalizedItem], dict[str, Any]]: ...

    async def sync_consumption(
        self,
        session: ConnectorSession,
        cursor: dict[str, Any] | None = None,
    ) -> list[NormalizedConsumption]: ...
