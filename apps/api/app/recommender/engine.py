from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

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
from app.services.interest import InterestSignals, saved_affinity

DEFAULT_WEIGHTS: dict[str, float] = {
    # Deterministic item-item co-occurrence CF (see rebuild_collaborative_edges).
    "collaborative": 0.25,
    "content": 0.4,
    # Optional pgvector/Ollama embedding similarity; 0 until embeddings exist.
    "embedding": 0.0,
    "popularity": 0.2,
    "novelty": 0.1,
    "diversity": 0.15,
    # Saved-item expansion: bump candidates similar to shortlisted/interested items.
    "interest": 0.2,
    # Small nudge toward off-profile picks so lists don't collapse to the obvious.
    "serendipity": 0.05,
    # Prefer titles already on the user's connected servers.
    "availability": 0.1,
    "seen_penalty": 1.0,
    "recent_pass_penalty": 0.8,
}

# Interaction types that count as a positive signal for collaborative filtering.
SERVER_SOURCES = ("jellyfin", "plex", "audiobookshelf", "komga")

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


def get_weights(db: Session, media_type: MediaType, name: str | None = None) -> dict[str, float]:
    """Per-media-type weights. ``name`` selects a specific config (e.g. a treatment);
    otherwise the active default is used. Unknown/absent config falls back to defaults."""
    q = db.query(ModelConfig).filter(ModelConfig.media_type == media_type)
    if name:
        q = q.filter(ModelConfig.name == name)
    else:
        q = q.filter(ModelConfig.active.is_(True))
    row = q.order_by(ModelConfig.name.asc()).first()
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


def build_user_profile(
    db: Session,
    user_id: UUID,
    media_type: MediaType | None = None,
    signals: InterestSignals | None = None,
) -> dict[str, Any]:
    q = (
        db.query(UserInteraction, Item)
        .join(Item, Item.id == UserInteraction.item_id)
        .filter(UserInteraction.user_id == user_id)
    )
    if media_type is not None:
        q = q.filter(Item.media_type == media_type)
    # Bound the scan to the most-recent N interactions (see profile_max_interactions).
    # Uses the ix_interactions_user_ts index so profile-building stays roughly constant
    # regardless of how long the account has been accumulating history.
    q = q.order_by(UserInteraction.timestamp.desc()).limit(get_settings().profile_max_interactions)

    genre_weights: dict[str, float] = {}
    tag_weights: dict[str, float] = {}
    creator_weights: dict[str, float] = {}
    liked_titles: list[str] = []
    rated_item_ids: set[UUID] = set()
    consumed_ids: set[UUID] = set()
    saved_ids: set[UUID] = set()
    passed: dict[UUID, datetime] = {}
    dismiss_counts: dict[UUID, int] = {}
    # Positive set drives collaborative filtering (users who liked the same items);
    # item_titles lets explanations name the specific driver titles.
    positive_ids: set[UUID] = set()
    item_titles: dict[UUID, str] = {}

    for interaction, item in q.all():
        itype = interaction.interaction_type
        item_titles[item.id] = item.title
        if itype == InteractionType.rate:
            rated_item_ids.add(item.id)
            weight = float(interaction.value or 0.0) * float(interaction.confidence or 1.0)
            if weight >= 1.0:
                liked_titles.append(item.title)
                positive_ids.add(item.id)
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
            if itype == InteractionType.finish:
                positive_ids.add(item.id)
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

    # Fold durable interest states into the profile (Phase 2). Positive states
    # reinforce genre/tag/creator preference; completed items count as seen;
    # interested/shortlisted mildly suppress re-recommending the same item; passed
    # states feed the pass-cooldown; hidden items are excluded outright.
    hidden_ids: set[UUID] = set()
    affinity_genres: set[str] = set()
    affinity_creators: set[str] = set()
    if signals is not None:
        for g, w in signals.genre_boosts.items():
            genre_weights[g] = genre_weights.get(g, 0.0) + w
        for t, w in signals.tag_boosts.items():
            tag_weights[t] = tag_weights.get(t, 0.0) + w
        for c, w in signals.creator_boosts.items():
            creator_weights[c] = creator_weights.get(c, 0.0) + w
        consumed_ids |= signals.completed_ids
        saved_ids |= signals.soft_seen_ids
        for iid, ts in signals.passed.items():
            passed.setdefault(iid, ts)
        hidden_ids = signals.hidden_ids
        affinity_genres = signals.affinity_genres
        affinity_creators = signals.affinity_creators
        # Completed / shortlisted items are strong positives for collaborative CF.
        positive_ids |= signals.completed_ids
        positive_ids |= signals.soft_seen_ids

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
        "hidden_ids": hidden_ids,
        "affinity_genres": affinity_genres,
        "affinity_creators": affinity_creators,
        "positive_ids": positive_ids,
        "item_titles": item_titles,
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


def _edge_scores(
    db: Session,
    kind: str,
    candidate_ids: set[UUID],
    positive_ids: set[UUID],
) -> dict[UUID, tuple[float, list[UUID]]]:
    """Aggregate similarity-edge weight from each candidate to the user's positive set.

    Deterministic: reads precomputed :class:`SimilarityEdge` rows (built by the
    nightly job). Returns {candidate_id: (summed_score, contributing_positive_ids)}.
    """
    from app.models import SimilarityEdge

    if not candidate_ids or not positive_ids:
        return {}
    cand = list(candidate_ids)
    pos = list(positive_ids)
    out: dict[UUID, tuple[float, list[UUID]]] = {}

    def _accumulate(cand_col, other_col) -> None:
        rows = (
            db.query(cand_col, other_col, SimilarityEdge.score)
            .filter(
                SimilarityEdge.kind == kind,
                cand_col.in_(cand),
                other_col.in_(pos),
            )
            .all()
        )
        for cand_id, other_id, score in rows:
            prev_score, contributors = out.get(cand_id, (0.0, []))
            contributors.append(other_id)
            out[cand_id] = (prev_score + float(score or 0.0), contributors)

    _accumulate(SimilarityEdge.item_a_id, SimilarityEdge.item_b_id)
    _accumulate(SimilarityEdge.item_b_id, SimilarityEdge.item_a_id)
    return out


def _available_ids(db: Session, candidate_ids: set[UUID]) -> set[UUID]:
    """Subset of candidates present on at least one connected server library."""
    from app.models import ItemExternalRef

    if not candidate_ids:
        return set()
    rows = (
        db.query(ItemExternalRef.item_id)
        .filter(
            ItemExternalRef.item_id.in_(list(candidate_ids)),
            ItemExternalRef.source.in_(list(SERVER_SOURCES)),
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def generate_candidates(
    db: Session,
    media_type: MediaType,
    profile: dict[str, Any],
    exclude_ids: set[UUID],
    feed_key: str,
    limit: int = 500,
) -> tuple[list[Item], dict[UUID, set[str]]]:
    """Layered candidate generation. Returns the pool and each item's source layers.

    Layers: popularity/trending base, collaborative neighbors of the user's positive
    items, and saved-item expansion (handled downstream via affinity). The layer tags
    are stored on factors so a list's provenance is inspectable.
    """
    from app.models import SimilarityEdge

    only_local = feed_key == "from_your_servers"
    base = retrieve_candidates(db, [media_type], exclude_ids=exclude_ids, limit=limit, only_local=only_local)
    layers: dict[UUID, set[str]] = {i.id: {"trending" if not only_local else "local_library"} for i in base}
    pool: dict[UUID, Item] = {i.id: i for i in base}

    # Collaborative expansion: pull in items linked to the user's positive set even
    # if they're outside the popularity head.
    positive_ids = profile.get("positive_ids") or set()
    if positive_ids and not only_local:
        pos = list(positive_ids)
        neighbor_ids: set[UUID] = set()
        for cand_col, other_col in (
            (SimilarityEdge.item_a_id, SimilarityEdge.item_b_id),
            (SimilarityEdge.item_b_id, SimilarityEdge.item_a_id),
        ):
            rows = (
                db.query(cand_col)
                .filter(SimilarityEdge.kind == "collaborative", other_col.in_(pos))
                .limit(limit)
                .all()
            )
            neighbor_ids.update(r[0] for r in rows)
        neighbor_ids -= exclude_ids
        neighbor_ids -= set(pool)
        if neighbor_ids:
            neighbors = (
                db.query(Item)
                .filter(Item.media_type == media_type, Item.id.in_(list(neighbor_ids)))
                .limit(limit)
                .all()
            )
            for it in neighbors:
                pool[it.id] = it
                layers.setdefault(it.id, set()).add("collaborative")

    return list(pool.values()), layers


def _structured_factors(
    profile: dict[str, Any],
    item: Item,
    collab_contributors: list[UUID],
    community_overlap: float,
    novelty: float,
    affinity: float,
    layers: set[str],
) -> dict[str, Any]:
    """Inspectable, source-of-truth factor payload the LLM later renders as prose."""
    titles = profile.get("item_titles") or {}
    shared_tags = sorted(set(str(t) for t in (item.tags or [])) & set(profile.get("tag_weights") or {}))
    same_creator = sorted(
        set(str(c) for c in (item.creators or [])) & set(profile.get("creator_weights") or {})
    )
    return {
        "liked_similar_items": [titles[i] for i in collab_contributors if i in titles][:3],
        "shared_tags": shared_tags[:6],
        "same_creator": same_creator[:3],
        "community_overlap": round(community_overlap, 4),
        "novelty_reason": "lesser_known" if novelty >= 0.6 else ("mainstream" if novelty <= 0.2 else "mid"),
        "saved_related_item": affinity > 0,
        "candidate_layers": sorted(layers),
    }


def score_candidates(
    items: list[Item],
    profile: dict[str, Any],
    weights: dict[str, float],
    feed_key: str,
    cooldown_days: int,
    *,
    collab_map: dict[UUID, tuple[float, list[UUID]]] | None = None,
    embedding_map: dict[UUID, tuple[float, list[UUID]]] | None = None,
    available_ids: set[UUID] | None = None,
    layers: dict[UUID, set[str]] | None = None,
) -> list[ScoredCandidate]:
    max_pop = max((float(i.popularity or 0.0) for i in items), default=1.0) or 1.0
    hidden_ids = profile.get("hidden_ids") or set()
    affinity_genres = profile.get("affinity_genres") or set()
    affinity_creators = profile.get("affinity_creators") or set()
    collab_map = collab_map or {}
    embedding_map = embedding_map or {}
    available_ids = available_ids or set()
    layers = layers or {}
    # Normalizers so collaborative/embedding contributions stay in a comparable range.
    max_collab = max((s for s, _ in collab_map.values()), default=0.0) or 1.0
    max_emb = max((s for s, _ in embedding_map.values()), default=0.0) or 1.0

    scored: list[ScoredCandidate] = []
    for item in items:
        # Items the user explicitly hid are never surfaced, in any feed.
        if item.id in hidden_ids:
            continue

        content, reasons = content_similarity(profile, item)
        pop = popularity_score(item, max_pop)
        nov = novelty_score(item)
        seen = seen_penalty(profile, item.id)
        recent_pass = pass_penalty(profile, item.id, cooldown_days)
        affinity = saved_affinity(item.genres or [], item.creators or [], affinity_genres, affinity_creators)
        if affinity > 0:
            reasons = list(set(reasons + ["saved_related_item"]))

        collab_raw, collab_contributors = collab_map.get(item.id, (0.0, []))
        collab = min(collab_raw / max_collab, 1.0)
        emb_raw, _ = embedding_map.get(item.id, (0.0, []))
        emb = min(emb_raw / max_emb, 1.0)
        available = 1.0 if item.id in available_ids else 0.0
        # Serendipity: reward items that are novel yet still connected to the user
        # (collaborative/affinity signal) — surprising but not random.
        serendipity = nov * max(collab, affinity) if (collab or affinity) else 0.0
        if collab > 0:
            reasons = list(set(reasons + ["community_overlap"]))
        if available > 0:
            reasons = list(set(reasons + ["local_library"]))

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

        diversity_placeholder = 0.0  # applied in rerank

        if feed_key == "something_different":
            content *= 0.35
            nov *= 1.4
            serendipity *= 1.5
            pop *= 0.5
            reasons = list(set(reasons + ["novelty_bias"]))
        elif feed_key == "because_you_loved":
            content *= 1.25
            if "genre_overlap" not in reasons and content < 0.15 and collab <= 0:
                continue

        raw = (
            weights["collaborative"] * collab
            + weights["content"] * content
            + weights["embedding"] * emb
            + weights["popularity"] * pop
            + weights["novelty"] * nov
            + weights["diversity"] * diversity_placeholder
            + weights.get("interest", 0.0) * affinity
            + weights.get("serendipity", 0.0) * serendipity
            + weights.get("availability", 0.0) * available
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
                    "interest_affinity": affinity,
                    "serendipity": serendipity,
                    "availability": available,
                    "seen_penalty": seen,
                    "recent_pass_penalty": recent_pass,
                    "reasons": reasons,
                    "structured": _structured_factors(
                        profile, item, collab_contributors, collab, nov, affinity, layers.get(item.id, set())
                    ),
                    "weights": weights,
                },
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def _series_key(item: Item) -> str | None:
    return (item.franchise or item.series or None) and str(item.franchise or item.series).lower()


def diversify(
    candidates: list[ScoredCandidate],
    limit: int,
    lambda_div: float = 0.7,
    *,
    max_per_series: int = 2,
    max_per_creator: int = 3,
) -> list[ScoredCandidate]:
    """Greedy MMR diversification over genres/creators with hard re-ranking caps.

    Caps prevent franchise spam (``max_per_series`` entries from one series/franchise)
    and creator over-concentration (``max_per_creator`` entries from one creator),
    balancing safe picks against variety.
    """
    if not candidates:
        return []
    selected: list[ScoredCandidate] = []
    remaining = list(candidates)
    selected_genres: set[str] = set()
    selected_creators: set[str] = set()
    series_counts: dict[str, int] = {}
    creator_counts: dict[str, int] = {}

    def _capped(item: Item) -> bool:
        skey = _series_key(item)
        if skey and series_counts.get(skey, 0) >= max_per_series:
            return True
        return any(
            creator_counts.get(str(c), 0) >= max_per_creator for c in (item.creators or [])
        )

    while remaining and len(selected) < limit:
        best_idx = None
        best_val = float("-inf")
        for i, cand in enumerate(remaining):
            if _capped(cand.item):
                continue
            genres = {str(g) for g in (cand.item.genres or [])}
            creators = {str(c) for c in (cand.item.creators or [])}
            overlap = len(genres & selected_genres) + 0.5 * len(creators & selected_creators)
            div_pen = overlap / max(len(genres) + len(creators), 1)
            mmr = lambda_div * cand.score - (1 - lambda_div) * div_pen
            if mmr > best_val:
                best_val = mmr
                best_idx = i
        if best_idx is None:
            # Every remaining candidate is capped; stop rather than pad with spam.
            break
        chosen = remaining.pop(best_idx)
        chosen.factors["diversity"] = best_val
        chosen.factors["reasons"] = list(set((chosen.factors.get("reasons") or []) + ["diversified"]))
        selected.append(chosen)
        selected_genres |= {str(g) for g in (chosen.item.genres or [])}
        selected_creators |= {str(c) for c in (chosen.item.creators or [])}
        skey = _series_key(chosen.item)
        if skey:
            series_counts[skey] = series_counts.get(skey, 0) + 1
        for c in chosen.item.creators or []:
            creator_counts[str(c)] = creator_counts.get(str(c), 0) + 1
    return selected


def generate_feed(
    db: Session,
    user: User,
    media_type: MediaType | str,
    feed_key: str,
    limit: int = 20,
    config_name: str | None = None,
) -> RecommendationFeedOutLike:
    from app.schemas import RecommendationCard, RecommendationFeedOut, ItemOut
    from app.services.interest import InterestService

    settings = get_settings()
    if isinstance(media_type, str):
        media_type = MediaType(media_type)

    # A single media type is scored per feed — a movie is never ranked against a
    # book. Per-domain weights come from that type's active (or named) ModelConfig.
    weights = get_weights(db, media_type, config_name)
    signals = InterestService(db).load_signals(user.id, media_type)
    profile = build_user_profile(db, user.id, media_type, signals=signals)

    # feed_key is scoped per domain so distinct verticals keep independent
    # RecommendationList/event rows.
    scoped_feed_key = f"{media_type.value}:{feed_key}"

    # Exclude already-consumed/rated and hidden items at the SQL layer — except for
    # pass_resurface, which intentionally revisits passed items (but still hides
    # hidden ones).
    hidden = set(profile.get("hidden_ids") or set())
    exclude = set(profile["consumed_ids"]) | set(profile["rated_item_ids"]) | hidden
    if feed_key == "pass_resurface":
        exclude = hidden
    only_local = feed_key == "from_your_servers"

    # Layered candidate generation (popularity/trending + collaborative expansion).
    pool, layers = generate_candidates(db, media_type, profile, exclude, feed_key, limit=500)

    # If local pool empty, fall back to catalog for that feed.
    if only_local and not pool:
        pool = retrieve_candidates(db, [media_type], exclude_ids=exclude, limit=500, only_local=False)
        layers = {i.id: {"trending"} for i in pool}

    candidate_ids = {i.id for i in pool}
    positive_ids = set(profile.get("positive_ids") or set())
    collab_map = _edge_scores(db, "collaborative", candidate_ids, positive_ids)
    embedding_map = _edge_scores(db, "embedding", candidate_ids, positive_ids)
    available_ids = _available_ids(db, candidate_ids)

    scored = score_candidates(
        pool,
        profile,
        weights,
        feed_key,
        settings.pass_cooldown_days,
        collab_map=collab_map,
        embedding_map=embedding_map,
        available_ids=available_ids,
        layers=layers,
    )
    ranked = diversify(scored, limit=limit)

    title = FEED_TITLES.get(feed_key, feed_key)
    rec_list = (
        db.query(RecommendationList)
        .filter(RecommendationList.user_id == user.id, RecommendationList.feed_key == scoped_feed_key)
        .first()
    )
    now = datetime.now(timezone.utc)
    if rec_list is None:
        rec_list = RecommendationList(user_id=user.id, feed_key=scoped_feed_key, title=title)
        db.add(rec_list)
        db.flush()
    else:
        rec_list.generated_at = now
        rec_list.title = title

    cards: list[RecommendationCard] = []
    liked = profile.get("liked_titles") or []
    config_used = config_name or "default"
    for rank, cand in enumerate(ranked, start=1):
        cand.factors["config"] = config_used
        explanation = _template_explanation(cand.item.title, cand.factors, liked)
        # Assign the id client-side so we can reference it without flushing every
        # iteration; all events are persisted together on the single commit below.
        event = RecommendationEvent(
            id=uuid4(),
            user_id=user.id,
            item_id=cand.item.id,
            list_id=rec_list.id,
            feed_key=scoped_feed_key,
            score=cand.score,
            rank=rank,
            factors=cand.factors,
            explanation=explanation,
        )
        db.add(event)
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

    # Bound RecommendationEvent growth: every generation writes up to `limit` rows, so
    # prune this (user, feed)'s rows older than the retention window. Scoped to the feed
    # being generated (cheap; a feed only accrues rows when it is regenerated). The rows
    # just added carry served_at=now and are always newer than the cutoff.
    retention_days = settings.recommendation_event_retention_days
    if retention_days > 0:
        cutoff = now - timedelta(days=retention_days)
        db.query(RecommendationEvent).filter(
            RecommendationEvent.user_id == user.id,
            RecommendationEvent.feed_key == scoped_feed_key,
            RecommendationEvent.served_at < cutoff,
        ).delete(synchronize_session=False)

    db.commit()
    return RecommendationFeedOut(
        feed_key=feed_key,
        title=title,
        items=cards,
        generated_at=now,
    )


def _template_explanation(title: str, factors: dict[str, Any], liked: list[str]) -> str:
    reasons = factors.get("reasons") or []
    structured = factors.get("structured") or {}
    bits = [f"Recommended “{title}”"]
    # Prefer the specific driver titles (collaborative) when we have them.
    similar = structured.get("liked_similar_items") or []
    if similar:
        bits.append(f"because you liked {', '.join(similar[:2])}")
    elif liked and ("genre_overlap" in reasons or "same_creator" in reasons):
        bits.append(f"because you liked {', '.join(liked[:2])}")
    if "community_overlap" in reasons:
        bits.append("and people with similar taste rated it highly")
    if "novelty_bias" in reasons:
        bits.append("as something different from your usual picks")
    if "local_library" in reasons:
        bits.append("from your connected servers")
    if "saved_related_item" in reasons:
        bits.append("related to items you shortlisted")
    if "genre_overlap" in reasons:
        bits.append("(shared genres)")
    if structured.get("same_creator"):
        bits.append(f"(same creator: {', '.join(structured['same_creator'][:2])})")
    return " ".join(bits)


# Forward type alias for typing without circular import pain
RecommendationFeedOutLike = Any
