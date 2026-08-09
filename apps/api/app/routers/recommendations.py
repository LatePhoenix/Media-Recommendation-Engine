from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import RATING_LABEL_TO_VALUE, get_current_user
from app.db import get_db
from app.models import (
    InteractionContext,
    InteractionSource,
    InteractionType,
    RecommendationEvent,
    User,
    UserInteraction,
)
from app.config import get_settings
from app.rate_limit import UserRateLimiter
from app.recommender import FEED_TITLES
from app.schemas import RecommendationAction, RecommendationFeedOut
from app.services.recommendation import RecommendationService

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

# Feed generation is expensive; throttle regeneration per authenticated user.
_feed_limiter = UserRateLimiter("feed", get_settings().feed_rate_limit_per_minute, 60)


@router.get("/feeds", response_model=list[dict])
def list_feeds(_: User = Depends(get_current_user)) -> list[dict]:
    return [{"feed_key": k, "title": v} for k, v in FEED_TITLES.items()]


@router.get(
    "/feeds/{feed_key}",
    response_model=RecommendationFeedOut,
    dependencies=[Depends(_feed_limiter)],
)
def get_feed(
    feed_key: str,
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationFeedOut:
    """Deprecated: media-agnostic feed. Prefer /api/{domain}/recommendations/feeds/{feed_key}.

    Retained for backward compatibility; scopes to the user's first enabled domain
    so it never mixes media types.
    """
    if feed_key not in FEED_TITLES:
        raise HTTPException(status_code=404, detail="Unknown feed")
    service = RecommendationService(db)
    media_type = service.default_media_type(user)
    return service.feed(user, media_type, feed_key, limit=limit)


@router.post("/actions")
def recommendation_action(
    payload: RecommendationAction,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    event = db.get(RecommendationEvent, payload.event_id)
    if not event or event.user_id != user.id:
        raise HTTPException(status_code=404, detail="Recommendation event not found")

    action = payload.action.lower()
    type_map = {
        "rate": InteractionType.rate,
        "save": InteractionType.save,
        "pass": InteractionType.pass_,
        "consume": InteractionType.consume,
        "finish": InteractionType.finish,
        "dismiss": InteractionType.dismiss,
    }
    if action not in type_map:
        raise HTTPException(status_code=400, detail="Unknown action")

    value = payload.value
    if payload.rating_label:
        value = RATING_LABEL_TO_VALUE.get(payload.rating_label, value)

    interaction = UserInteraction(
        user_id=user.id,
        item_id=event.item_id,
        interaction_type=type_map[action],
        value=value,
        source=InteractionSource.recommendation_flow,
        context=InteractionContext.recommendation_feed,
        confidence=1.0,
        meta={"event_id": str(event.id)},
        timestamp=datetime.now(timezone.utc),
    )
    event.action_taken = action
    db.add(interaction)
    db.add(event)
    prefs = dict(user.preferences or {})
    prefs["last_interaction_at"] = interaction.timestamp.isoformat()
    user.preferences = prefs
    db.add(user)
    db.commit()
    return {"ok": True, "action": action, "event_id": str(event.id)}
