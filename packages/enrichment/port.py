from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class EnrichmentResult:
    embeddings: list[float] | None = None
    tags: list[str] = field(default_factory=list)
    explanation_prose: str | None = None
    taste_summary: str | None = None
    model: str | None = None


@runtime_checkable
class EnrichmentPort(Protocol):
    """LLM/embedding side-channel. Deterministic ranking must not call this for scores."""

    enabled: bool

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for each input text."""
        ...

    def extract_tags(self, title: str, description: str) -> list[str]:
        """Optional structured tags from messy metadata."""
        ...

    def explain_from_factors(
        self,
        item_title: str,
        factors: dict,
        liked_titles: list[str] | None = None,
    ) -> str:
        """Turn structured ranking factors into human-readable prose."""
        ...

    def summarize_taste(self, preference_blob: dict) -> str:
        """Human-readable taste summary from profile stats."""
        ...
