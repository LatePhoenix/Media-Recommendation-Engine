"""Offline recommendation metrics (Phase 5).

Computed deterministically from persisted ``recommendation_events`` (served items,
rank, factors, action_taken) — no external analytics. Supports comparing two named
model configs (control vs treatment) since each event records the config it was
served under in ``factors.config``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Item, MediaType, RecommendationEvent

# action_taken values that count as a positive outcome for precision/save metrics.
_POSITIVE_ACTIONS = ("save", "consume", "finish", "rate")
_COMPLETION_ACTIONS = ("consume", "finish")


class MetricsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def domain_metrics(
        self, media_type: MediaType, config_name: str | None = None, k: int = 10
    ) -> dict[str, Any]:
        """Aggregate served-list metrics for a domain, optionally filtered by config."""
        prefix = f"{media_type.value}:"
        filters = [RecommendationEvent.feed_key.like(f"{prefix}%")]
        if config_name is not None:
            filters.append(RecommendationEvent.factors.op("->>")("config") == config_name)

        served = (
            self.db.execute(select(func.count()).select_from(RecommendationEvent).where(*filters))
            .scalar_one()
        )
        if not served:
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

        def _rate(actions: tuple[str, ...]) -> float:
            count = (
                self.db.execute(
                    select(func.count())
                    .select_from(RecommendationEvent)
                    .where(*filters, RecommendationEvent.action_taken.in_(actions))
                ).scalar_one()
            )
            return round(count / served, 4)

        saves = _rate(("save",))
        positives = _rate(_POSITIVE_ACTIONS)
        passes = _rate(("pass",))
        completions = _rate(_COMPLETION_ACTIONS)

        topk_filters = [*filters, RecommendationEvent.rank <= k]
        topk_n = (
            self.db.execute(select(func.count()).select_from(RecommendationEvent).where(*topk_filters))
            .scalar_one()
        )
        topk_pos = (
            self.db.execute(
                select(func.count())
                .select_from(RecommendationEvent)
                .where(*topk_filters, RecommendationEvent.action_taken.in_(_POSITIVE_ACTIONS))
            ).scalar_one()
        )

        resurface_filters = [*filters, RecommendationEvent.feed_key == f"{prefix}pass_resurface"]
        resurface_n = (
            self.db.execute(
                select(func.count()).select_from(RecommendationEvent).where(*resurface_filters)
            ).scalar_one()
        )
        resurface_pos = (
            self.db.execute(
                select(func.count())
                .select_from(RecommendationEvent)
                .where(*resurface_filters, RecommendationEvent.action_taken.in_(_POSITIVE_ACTIONS))
            ).scalar_one()
        )

        # Diversity still needs item genres; load only the event item_ids for this filter set.
        events = (
            self.db.execute(
                select(
                    RecommendationEvent.list_id,
                    RecommendationEvent.item_id,
                ).where(*filters)
            ).all()
        )

        return {
            "media_type": media_type.value,
            "config": config_name,
            "served": served,
            "save_rate": saves,
            "positive_rate": positives,
            "pass_rate": passes,
            "completion_rate": completions,
            f"precision_at_{k}": round(topk_pos / topk_n, 4) if topk_n else 0.0,
            "pass_resurface_success": round(resurface_pos / resurface_n, 4) if resurface_n else 0.0,
            "diversity_index": round(self._diversity_index_rows(events), 4),
        }

    def _diversity_index_rows(self, rows: list[Any]) -> float:
        by_list: dict[UUID | None, list[UUID]] = {}
        for list_id, item_id in rows:
            by_list.setdefault(list_id, []).append(item_id)
        item_ids = {item_id for _, item_id in rows}
        genres_by_item: dict[UUID, list[str]] = {}
        if item_ids:
            for item in self.db.query(Item).filter(Item.id.in_(list(item_ids))).all():
                genres_by_item[item.id] = [str(g) for g in (item.genres or [])]

        ratios: list[float] = []
        for group in by_list.values():
            if not group:
                continue
            seen: set[str] = set()
            for item_id in group:
                seen.update(genres_by_item.get(item_id, []))
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
