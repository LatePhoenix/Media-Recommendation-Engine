from __future__ import annotations

from .port import EnrichmentPort, EnrichmentResult


class NoOpEnricher:
    """Default enricher when Ollama is disabled or unavailable."""

    enabled: bool = False

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]

    def extract_tags(self, title: str, description: str) -> list[str]:
        return []

    def explain_from_factors(
        self,
        item_title: str,
        factors: dict,
        liked_titles: list[str] | None = None,
    ) -> str:
        reasons = factors.get("reasons") or []
        parts = [f"Recommended '{item_title}'"]
        if liked_titles:
            parts.append(f"because you liked {', '.join(liked_titles[:3])}")
        if reasons:
            parts.append(f"({', '.join(str(r) for r in reasons)})")
        return " ".join(parts)

    def summarize_taste(self, preference_blob: dict) -> str:
        genres = preference_blob.get("top_genres") or []
        if genres:
            return f"Prefers: {', '.join(genres[:5])}"
        return "Taste profile not yet rich enough for a summary."


# Satisfy Protocol typing
_: EnrichmentPort = NoOpEnricher()  # type: ignore[assignment]
