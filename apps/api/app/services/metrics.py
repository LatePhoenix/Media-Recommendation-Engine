"""Offline recommendation metrics (Phase 5).

Computed deterministically from persisted ``recommendation_events`` (served items,
rank, factors, action_taken) — no external analytics. Supports comparing two named
model configs (control vs treatment) since each event records the config it was
served under in ``factors.config``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Item, MediaType, RecommendationEvent

# action_taken values that count as a positive outcome for precision/save metrics.
_POSITIVE_ACTIONS = {"save", "consume", "finish", "rate"}
_COMPLETION_ACTIONS = {"consume", "finish"}


class MetricsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def domain_metrics(
        self, media_type: MediaType, config_name: str | None = None, k: int = 10
    ) -> dict[str, Any]:
        """Aggregate served-list metrics for a domain, optionally filtered by config."""
        prefix = f"{media_type.value}:"
        q = self.db.query(RecommendationEvent).filter(
            RecommendationEvent.feed_key.like(f"{prefix}%")
        )
        events = q.all()
        if config_name is not None:
            events = [e for e in events if (e.factors or {}).get("config") == config_name]

        served = len(events)
        if served == 0:
            return {
                "media_type": media_type.value,
                "config": config_name,
                "served": 0,
                "save_rate": 0.0,
                "positive_rate": 0.0,
                "pass_rate": 0.0,
                "completion_rate": 0.0,
                f"precision_at_{k}": 0.0,
                "pass_resurface_success": 0.0,
                "diversity_index": 0.0,
            }

        positives = sum(1 for e in events if e.action_taken in _POSITIVE_ACTIONS)
        saves = sum(1 for e in events if e.action_taken == "save")
        passes = sum(1 for e in events if e.action_taken == "pass")
        completions = sum(1 for e in events if e.action_taken in _COMPLETION_ACTIONS)

        topk = [e for e in events if e.rank <= k]
        topk_pos = sum(1 for e in topk if e.action_taken in _POSITIVE_ACTIONS)

        resurface = [e for e in events if e.feed_key == f"{prefix}pass_resurface"]
        resurface_pos = sum(1 for e in resurface if e.action_taken in _POSITIVE_ACTIONS)

        return {
            "media_type": media_type.value,
            "config": config_name,
            "served": served,
            "save_rate": round(saves / served, 4),
            "positive_rate": round(positives / served, 4),
            "pass_rate": round(passes / served, 4),
            "completion_rate": round(completions / served, 4),
            f"precision_at_{k}": round(topk_pos / len(topk), 4) if topk else 0.0,
            "pass_resurface_success": round(resurface_pos / len(resurface), 4) if resurface else 0.0,
            "diversity_index": round(self._diversity_index(events), 4),
        }

    def _diversity_index(self, events: list[RecommendationEvent]) -> float:
        """Mean distinct-genre ratio across served lists (1.0 = every item a new genre)."""
        by_list: dict[UUID | None, list[RecommendationEvent]] = {}
        for e in events:
            by_list.setdefault(e.list_id, []).append(e)
        item_ids = {e.item_id for e in events}
        genres_by_item: dict[UUID, list[str]] = {}
        if item_ids:
            for item in self.db.query(Item).filter(Item.id.in_(list(item_ids))).all():
                genres_by_item[item.id] = [str(g) for g in (item.genres or [])]

        ratios: list[float] = []
        for group in by_list.values():
            if not group:
                continue
            seen: set[str] = set()
            for e in group:
                seen.update(genres_by_item.get(e.item_id, []))
            ratios.append(len(seen) / max(len(group), 1))
        return sum(ratios) / len(ratios) if ratios else 0.0

    def compare(
        self, media_type: MediaType, control: str, treatment: str, k: int = 10
    ) -> dict[str, Any]:
        return {
            "media_type": media_type.value,
            "control": self.domain_metrics(media_type, control, k=k),
            "treatment": self.domain_metrics(media_type, treatment, k=k),
        }
