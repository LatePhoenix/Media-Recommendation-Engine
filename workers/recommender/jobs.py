"""Recommender background jobs — nightly retrain stubs and online feature hooks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def nightly_retrain_stub() -> dict:
    """Stage 5 placeholder: item-item CF / ALS will land here."""
    logger.info("nightly_retrain_stub invoked at %s", datetime.now(timezone.utc).isoformat())
    return {"ok": True, "stage": "stub", "message": "CF retraining not implemented until Stage 5"}


def generate_embeddings_stub(batch_size: int = 50) -> dict:
    """Stage 6 placeholder: Ollama embed → pgvector."""
    return {"ok": True, "stage": "stub", "batch_size": batch_size}
