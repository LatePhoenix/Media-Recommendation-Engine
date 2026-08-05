"""Optional enrichment behind a stable port. Ranking never depends on this."""

from .port import EnrichmentPort, EnrichmentResult
from .noop import NoOpEnricher
from .ollama import OllamaEnricher
from .factory import get_enricher

__all__ = [
    "EnrichmentPort",
    "EnrichmentResult",
    "NoOpEnricher",
    "OllamaEnricher",
    "get_enricher",
]
