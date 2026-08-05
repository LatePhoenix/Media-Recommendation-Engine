from __future__ import annotations

import os

from .noop import NoOpEnricher
from .ollama import OllamaEnricher
from .port import EnrichmentPort


def get_enricher() -> EnrichmentPort:
    enabled = os.getenv("ENRICHMENT_ENABLED", "false").lower() in {"1", "true", "yes"}
    if not enabled:
        return NoOpEnricher()
    return OllamaEnricher()
