from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    InteractionType,
    Item,
    MediaType,
    ModelConfig,
    RecommendationEvent,
    RecommendationList,
    User,
    UserInteraction,
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "collaborative": 0.0,
    "content": 0.45,
    "embedding": 0.0,
    "popularity": 0.25,
    "novelty": 0.1,
    "diversity": 0.15,
    "seen_penalty": 1.0,
    "recent_pass_penalty": 0.8,
}

FEED_TITLES: dict[str, str] = {
    "best_next": "Best next",
    "something_different": "Something different",
    "from_your_servers": "From your servers now",
    "pass_resurface": "Shortlist from your passes resurfaced",
    "because_you_loved": "Because you loved…",
}


@dataclass
class ScoredCandidate:
    item: Item
    score: float
    factors: dict[str, Any] = field(default_factory=dict)


def get_weights(db: Session, media_type: MediaType) -> dict[str, float]:
    row = (
        db.query(ModelConfig)
        .filter(ModelConfig.media_type == media_type, ModelConfig.active.is_(True))
        .order_by(ModelConfig.name.asc())
        .first()
    )
    if row and row.weights:
        merged = dict(DEFAULT_WEIGHTS)
        merged.update({k: float(v) for k, v in row.weights.items()})
        return merged
    return dict(DEFAULT_WEIGHTS)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def build_user_profile(db: Session, user_id: UUID, media_type: MediaType | None = None) -> dict[str, Any]:
    q = (
        db.query(UserInteraction, Item)
        .join(Item, Item.id == UserInteraction.item_id)
        .filter(UserInteraction.user_id == user_id)
    )
    if media_type is not None:
        q = q.filter(Item.media_type == media_type)

    genre_weights: dict[str, float] = {}
    tag_weights: dict[str, float] = {}
    creator_weights: dict[str, float] = {}
    liked_titles: list[str] = []
    rated_item_ids: set[UUID] = set()
    consumed_ids: set[UUID] = set()
    saved_ids: set[UUID] = set()
    passed: dict[UUID, datetime] = {}
    dismiss_counts: dict[UUID, int] = {}

    for interaction, item in q.all():
        itype = interaction.interaction_type
        if itype == InteractionType.rate:
            rated_item_ids.add(item.id)
            weight = float(interaction.value or 0.0) * float(interaction.confidence or 1.0)
            if weight >= 1.0:
                liked_titles.append(item.title)
            for g in item.genres or []:
                genre_weights[str(g)] = genre_weights.get(str(g), 0.0) + weight
            for t in item.tags or []:
                tag_weights[str(t)] = tag_weights.get(str(t), 0.0) + weight
            for c in item.creators or []:
                creator_weights[str(c)] = creator_weights.get(str(c), 0.0) + weight
        elif itype in (InteractionType.consume, InteractionType.finish):
            consumed_ids.add(item.id)
            # Implicit mild positive for finish
            boost = 0.5 if itype == InteractionType.finish else 0.2
            for g in item.genres or []:
                genre_weights[str(g)] = genre_weights.get(str(g), 0.0) + boost
        elif itype == InteractionType.save:
            saved_ids.add(item.id)
            for g in item.genres or []:
                genre_weights[str(g)] = genre_weights.get(str(g), 0.0) + 0.15
        elif itype == InteractionType.pass_:
            passed[item.id] = interaction.timestamp
        elif itype == InteractionType.dismiss:
            dismiss_counts[item.id] = dismiss_counts.get(item.id, 0) + 1

    top_genres = sorted(genre_weights, key=genre_weights.get, reverse=True)[:12]
    return {
        "genre_weights": genre_weights,
        "tag_weights": tag_weights,
        "creator_weights": creator_weights,
        "top_genres": top_genres,
        "liked_titles": liked_titles[:20],
        "rated_item_ids": rated_item_ids,
        "consumed_ids": consumed_ids,
        "saved_ids": saved_ids,
        "passed": passed,
        "dismiss_counts": dismiss_counts,
    }


def content_similarity(profile: dict[str, Any], item: Item) -> tuple[float, list[str]]:
    reasons: list[str] = []
    g_score = _jaccard(set(profile["genre_weights"]), set(item.genres or []))
    t_score = _jaccard(set(profile["tag_weights"]), set(item.tags or []))
    c_score = _jaccard(set(profile["creator_weights"]), set(item.creators or []))

    # Weighted preference intensity
    genre_pref = sum(profile["genre_weights"].get(str(g), 0.0) for g in (item.genres or []))
    creator_pref = sum(profile["creator_weights"].get(str(c), 0.0) for c in (item.creators or []))
    pref_norm = max(genre_pref, 0.0) / (max(sum(abs(v) for v in profile["genre_weights"].values()), 1.0))
    creator_norm = max(creator_pref, 0.0) / (
        max(sum(abs(v) for v in profile["creator_weights"].values()), 1.0)
    )

    score = 0.4 * g_score + 0.2 * t_score + 0.25 * c_score + 0.1 * pref_norm + 0.05 * creator_norm
    if g_score > 0:
        reasons.append("genre_overlap")
    if c_score > 0:
        reasons.append("same_creator")
    if t_score > 0:
        reasons.append("tag_overlap")
    if item.series and any(
        item.series.lower() in title.lower() for title in profile.get("liked_titles", [])
    ):
        score += 0.1
        reasons.append("series_affinity")
    return min(score, 1.5), reasons


def popularity_score(item: Item, max_pop: float) -> float:
    if max_pop <= 0:
        return 0.0
    return min(float(item.popularity or 0.0) / max_pop, 1.0)


def novelty_score(item: Item) -> float:
    """Prefer mid/low popularity for novelty feed; mild bump for older/lesser-known."""
    pop = float(item.popularity or 0.0)
    return max(0.0, 1.0 - min(pop / 100.0, 1.0))


def seen_penalty(profile: dict[str, Any], item_id: UUID) -> float:
    if item_id in profile["consumed_ids"] or item_id in profile["rated_item_ids"]:
        return 1.0
    if item_id in profile["saved_ids"]:
        return 0.35
    dismisses = profile["dismiss_counts"].get(item_id, 0)
    if dismisses:
        return min(0.25 * dismisses, 0.9)
    return 0.0


def pass_penalty(profile: dict[str, Any], item_id: UUID, cooldown_days: int) -> float:
    ts = profile["passed"].get(item_id)
    if not ts:
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - ts
    if age < timedelta(days=cooldown_days):
        # Full suppress during cooldown
        return 1.0
    # Soft decay after cooldown — allow resurfacing
    days_over = (age - timedelta(days=cooldown_days)).days
    return max(0.0, 0.4 - 0.02 * days_over)


def retrieve_candidates(
    db: Session,
    media_types: list[MediaType],
    exclude_ids: set[UUID],
    limit: int = 400,
    only_local: bool = False,
) -> list[Item]:
    q = db.query(Item).filter(Item.media_type.in_(media_types))
    if exclude_ids:
        q = q.filter(~Item.id.in_(list(exclude_ids)))
    if only_local:
        # Items that have at least one server external ref
        from app.models import ItemExternalRef

        q = q.join(ItemExternalRef).filter(
            ItemExternalRef.source.in_(["jellyfin", "plex", "audiobookshelf", "komga"])
        )
    return q.order_by(Item.popularity.desc()).limit(limit).all()


def score_candidates(
    items: list[Item],
    profile: dict[str, Any],
    weights: dict[str, float],
    feed_key: str,
    cooldown_days: int,
) -> list[ScoredCandidate]:
    max_pop = max((float(i.popularity or 0.0) for i in items), default=1.0) or 1.0
    scored: list[ScoredCandidate] = []
    for item in items:
        content, reasons = content_similarity(profile, item)
        pop = popularity_score(item, max_pop)
        nov = novelty_score(item)
        seen = seen_penalty(profile, item.id)
        recent_pass = pass_penalty(profile, item.id, cooldown_days)

        # Hard suppress consumed / in-cooldown passes for most feeds
        if seen >= 1.0 and feed_key != "pass_resurface":
            continue
        if recent_pass >= 1.0 and feed_key != "pass_resurface":
            continue
        if feed_key == "pass_resurface":
            if item.id not in profile["passed"] or recent_pass >= 1.0:
                continue
            # Prefer items past cooldown
            recent_pass = min(recent_pass, 0.2)

        collab = 0.0
        emb = 0.0
        diversity_placeholder = 0.0  # applied in rerank

        if feed_key == "something_different":
            content *= 0.35
            nov *= 1.4
            pop *= 0.5
            reasons = list(set(reasons + ["novelty_bias"]))
        elif feed_key == "because_you_loved":
            content *= 1.25
            if "genre_overlap" not in reasons and content < 0.15:
                continue
        elif feed_key == "from_your_servers":
            reasons = list(set(reasons + ["local_library"]))

        raw = (
            weights["collaborative"] * collab
            + weights["content"] * content
            + weights["embedding"] * emb
            + weights["popularity"] * pop
            + weights["novelty"] * nov
            + weights["diversity"] * diversity_placeholder
            - weights["seen_penalty"] * seen
            - weights["recent_pass_penalty"] * recent_pass
        )
        scored.append(
            ScoredCandidate(
                item=item,
                score=raw,
                factors={
                    "collaborative": collab,
                    "content": content,
                    "embedding": emb,
                    "popularity": pop,
                    "novelty": nov,
                    "seen_penalty": seen,
                    "recent_pass_penalty": recent_pass,
                    "reasons": reasons,
                    "weights": weights,
                },
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def diversify(candidates: list[ScoredCandidate], limit: int, lambda_div: float = 0.7) -> list[ScoredCandidate]:
    """Greedy MMR-style diversification over genres/creators."""
    if not candidates:
        return []
    selected: list[ScoredCandidate] = []
    remaining = list(candidates)
    selected_genres: set[str] = set()
    selected_creators: set[str] = set()

    while remaining and len(selected) < limit:
        best_idx = 0
        best_val = float("-inf")
        for i, cand in enumerate(remaining):
            genres = {str(g) for g in (cand.item.genres or [])}
            creators = {str(c) for c in (cand.item.creators or [])}
            overlap = len(genres & selected_genres) + 0.5 * len(creators & selected_creators)
            div_pen = overlap / max(len(genres) + len(creators), 1)
            mmr = lambda_div * cand.score - (1 - lambda_div) * div_pen
            if mmr > best_val:
                best_val = mmr
                best_idx = i
        chosen = remaining.pop(best_idx)
        chosen.factors["diversity"] = best_val
        chosen.factors["reasons"] = list(set((chosen.factors.get("reasons") or []) + ["diversified"]))
        selected.append(chosen)
        selected_genres |= {str(g) for g in (chosen.item.genres or [])}
        selected_creators |= {str(c) for c in (chosen.item.creators or [])}
    return selected


def generate_feed(
    db: Session,
    user: User,
    feed_key: str,
    limit: int = 20,
) -> RecommendationFeedOutLike:
    from app.schemas import RecommendationCard, RecommendationFeedOut, ItemOut

    settings = get_settings()
    enabled = [MediaType(m) for m in (user.enabled_media_types or ["movie"]) if m in MediaType.__members__]
    if not enabled:
        enabled = [MediaType.movie]

    # Use first enabled type weights as baseline; score mixes types
    weights = get_weights(db, enabled[0])
    profile = build_user_profile(db, user.id)

    exclude = set(profile["consumed_ids"]) | set(profile["rated_item_ids"])
    only_local = feed_key == "from_your_servers"
    pool = retrieve_candidates(db, enabled, exclude_ids=set(), limit=500, only_local=only_local)

    # If local pool empty, fall back to catalog for that feed
    if only_local and not pool:
        pool = retrieve_candidates(db, enabled, exclude_ids=set(), limit=500, only_local=False)

    scored = score_candidates(pool, profile, weights, feed_key, settings.pass_cooldown_days)
    ranked = diversify(scored, limit=limit)

    title = FEED_TITLES.get(feed_key, feed_key)
    rec_list = (
        db.query(RecommendationList)
        .filter(RecommendationList.user_id == user.id, RecommendationList.feed_key == feed_key)
        .first()
    )
    now = datetime.now(timezone.utc)
    if rec_list is None:
        rec_list = RecommendationList(user_id=user.id, feed_key=feed_key, title=title)
        db.add(rec_list)
        db.flush()
    else:
        rec_list.generated_at = now
        rec_list.title = title

    cards: list[RecommendationCard] = []
    liked = profile.get("liked_titles") or []
    for rank, cand in enumerate(ranked, start=1):
        explanation = _template_explanation(cand.item.title, cand.factors, liked)
        event = RecommendationEvent(
            user_id=user.id,
            item_id=cand.item.id,
            list_id=rec_list.id,
            feed_key=feed_key,
            score=cand.score,
            rank=rank,
            factors=cand.factors,
            explanation=explanation,
        )
        db.add(event)
        db.flush()
        cards.append(
            RecommendationCard(
                event_id=event.id,
                item=ItemOut.model_validate(cand.item),
                score=cand.score,
                rank=rank,
                feed_key=feed_key,
                factors=cand.factors,
                explanation=explanation,
            )
        )
    db.commit()
    return RecommendationFeedOut(
        feed_key=feed_key,
        title=title,
        items=cards,
        generated_at=now,
    )


def _template_explanation(title: str, factors: dict[str, Any], liked: list[str]) -> str:
    reasons = factors.get("reasons") or []
    bits = [f"Recommended “{title}”"]
    if liked and ("genre_overlap" in reasons or "same_creator" in reasons):
        bits.append(f"because you liked {', '.join(liked[:2])}")
    if "novelty_bias" in reasons:
        bits.append("as something different from your usual picks")
    if "local_library" in reasons:
        bits.append("from your connected servers")
    if "genre_overlap" in reasons:
        bits.append("(shared genres)")
    if "same_creator" in reasons:
        bits.append("(shared creators)")
    return " ".join(bits)


# Forward type alias for typing without circular import pain
RecommendationFeedOutLike = Any
