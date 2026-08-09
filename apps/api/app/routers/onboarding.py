from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import get_settings
from app.db import get_db
from app.models import InteractionType, Item, MediaType, User, UserInteraction
from app.schemas import ItemOut, OnboardingStatus

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.get("/anchors", response_model=list[ItemOut])
def get_anchors(
    media_type: MediaType,
    limit: int = Query(40, ge=5, le=80),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Item]:
    # Gate opt-in domains (books/comics) the same way the per-domain routes do, so a user
    # can't enumerate anchors for a media type they haven't enabled.
    if media_type.value not in (user.enabled_media_types or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Domain {media_type.value!r} is not enabled",
        )
    rated_ids = {
        r.item_id
        for r in db.query(UserInteraction)
        .filter(
            UserInteraction.user_id == user.id,
            UserInteraction.interaction_type == InteractionType.rate,
        )
        .all()
    }
    q = (
        db.query(Item)
        .filter(Item.media_type == media_type, Item.is_anchor.is_(True))
        .order_by(Item.popularity.desc())
    )
    items = q.limit(limit * 2).all()
    unseen = [i for i in items if i.id not in rated_ids]
    if len(unseen) < limit:
        # Fall back to popular non-anchors
        extra = (
            db.query(Item)
            .filter(Item.media_type == media_type)
            .order_by(Item.popularity.desc())
            .limit(limit * 2)
            .all()
        )
        for e in extra:
            if e.id not in rated_ids and e.id not in {i.id for i in unseen}:
                unseen.append(e)
            if len(unseen) >= limit:
                break
    return unseen[:limit]


@router.get("/status", response_model=OnboardingStatus)
def onboarding_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OnboardingStatus:
    settings = get_settings()
    rows = (
        db.query(UserInteraction, Item)
        .join(Item, Item.id == UserInteraction.item_id)
        .filter(
            UserInteraction.user_id == user.id,
            UserInteraction.interaction_type == InteractionType.rate,
        )
        .all()
    )
    counts: dict[str, int] = defaultdict(int)
    for interaction, item in rows:
        counts[item.media_type.value] += 1
    ready = [mt for mt, n in counts.items() if n >= settings.onboarding_min_ratings]
    complete = user.onboarding_complete or any(
        counts.get(mt, 0) >= settings.onboarding_min_ratings for mt in (user.enabled_media_types or [])
    )
    return OnboardingStatus(
        complete=complete,
        ratings_by_media_type=dict(counts),
        min_ratings=settings.onboarding_min_ratings,
        ready_media_types=ready,
    )
