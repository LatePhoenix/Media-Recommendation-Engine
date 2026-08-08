"""Recommender background jobs.

Deterministic item-item collaborative filtering via co-occurrence of positive
signals across users (no ML black box — inspectable counts and cosine scores).
Embedding edges are optional and only produced when item embeddings exist.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from typing import Any
from uuid import UUID

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import (
    InteractionType,
    Item,
    ItemState,
    MediaType,
    SimilarityEdge,
    UserInteraction,
    UserItemState,
)

logger = logging.getLogger(__name__)

# Interaction types that count as an implicit/explicit positive for CF.
_POSITIVE_INTERACTIONS = (InteractionType.finish, InteractionType.consume, InteractionType.rate)
_POSITIVE_STATES = (ItemState.completed, ItemState.shortlisted, ItemState.interested)


def _positive_user_items(db, media_type: MediaType) -> dict[UUID, set[UUID]]:
    """user_id -> set of item_ids the user positively engaged with, for one media type."""
    user_items: dict[UUID, set[UUID]] = defaultdict(set)

    rows = (
        db.query(UserInteraction.user_id, UserInteraction.item_id, UserInteraction.interaction_type, UserInteraction.value)
        .join(Item, Item.id == UserInteraction.item_id)
        .filter(Item.media_type == media_type, UserInteraction.interaction_type.in_(_POSITIVE_INTERACTIONS))
        .all()
    )
    for user_id, item_id, itype, value in rows:
        # A "rate" only counts as positive when the score is favorable.
        if itype == InteractionType.rate and float(value or 0.0) < 1.0:
            continue
        user_items[user_id].add(item_id)

    state_rows = (
        db.query(UserItemState.user_id, UserItemState.item_id)
        .filter(UserItemState.media_type == media_type, UserItemState.state.in_(_POSITIVE_STATES))
        .all()
    )
    for user_id, item_id in state_rows:
        user_items[user_id].add(item_id)

    return user_items


def cooccurrence_scores(
    user_items: dict[Any, set],
    top_k: int = 25,
    min_co: int = 2,
) -> dict[tuple, float]:
    """Pure item-item cosine over co-occurring positive signals. No DB.

    score(i, j) = co(i, j) / sqrt(|users_i| * |users_j|); keeps top_k neighbors per
    item as undirected pairs keyed (min, max) by str. Unit-testable in isolation.
    """
    item_count: dict[Any, int] = defaultdict(int)
    co: dict[tuple, int] = defaultdict(int)
    for items in user_items.values():
        uniq = set(items)
        for it in uniq:
            item_count[it] += 1
        for a, b in combinations(sorted(uniq, key=str), 2):
            co[(a, b)] += 1

    neighbors: dict[Any, list[tuple[float, Any]]] = defaultdict(list)
    for (a, b), c in co.items():
        if c < min_co:
            continue
        score = c / math.sqrt(item_count[a] * item_count[b])
        neighbors[a].append((score, b))
        neighbors[b].append((score, a))

    kept: dict[tuple, float] = {}
    for item_id, neigh in neighbors.items():
        neigh.sort(key=lambda x: (x[0], str(x[1])), reverse=True)
        for score, other in neigh[:top_k]:
            key = (item_id, other) if str(item_id) < str(other) else (other, item_id)
            kept[key] = max(kept.get(key, 0.0), score)
    return kept


def rebuild_collaborative_edges(
    media_type: str | None = None,
    top_k: int = 25,
    min_co: int = 2,
) -> dict:
    """Recompute collaborative similarity edges from co-occurring positive signals.

    Keeps the top_k neighbors per item; one undirected row per pair.
    """
    media_types = [MediaType(media_type)] if media_type else list(MediaType)
    db = SessionLocal()
    total_edges = 0
    try:
        for mt in media_types:
            user_items = _positive_user_items(db, mt)
            kept_pairs = cooccurrence_scores(user_items, top_k=top_k, min_co=min_co)
            item_ids = list({it for items in user_items.values() for it in items})

            # Replace this media type's collaborative edges.
            if item_ids:
                db.execute(
                    delete(SimilarityEdge).where(
                        SimilarityEdge.kind == "collaborative",
                        SimilarityEdge.item_a_id.in_(item_ids),
                    )
                )
            for (a, b), score in kept_pairs.items():
                db.add(SimilarityEdge(item_a_id=a, item_b_id=b, kind="collaborative", score=score))
            total_edges += len(kept_pairs)
        db.commit()
        logger.info("rebuild_collaborative_edges wrote %s edges", total_edges)
        return {"ok": True, "edges": total_edges, "media_types": [m.value for m in media_types]}
    finally:
        db.close()


def nightly_retrain_stub() -> dict:
    """Nightly job: rebuild deterministic collaborative edges across all media types."""
    logger.info("nightly retrain at %s", datetime.now(timezone.utc).isoformat())
    return rebuild_collaborative_edges()


def generate_embeddings_stub(batch_size: int = 50) -> dict:
    """Placeholder: Ollama embed → pgvector. Requires enrichment enabled."""
    return {"ok": True, "stage": "stub", "batch_size": batch_size}
