from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import RATING_LABEL_TO_VALUE, get_current_user
from app.db import get_db
from app.models import InteractionType, Item, User, UserInteraction
from app.schemas import InteractionBatchCreate, InteractionCreate, InteractionOut

router = APIRouter(prefix="/api/interactions", tags=["interactions"])


def _resolve_value(payload: InteractionCreate) -> float | None:
    if payload.rating_label:
        if payload.rating_label not in RATING_LABEL_TO_VALUE:
            raise ValueError(f"Unknown rating label: {payload.rating_label}")
        return RATING_LABEL_TO_VALUE[payload.rating_label]
    return payload.value


def create_interaction(
    db: Session,
    user: User,
    payload: InteractionCreate,
) -> UserInteraction:
    # Reject unknown item_ids up front with a 404 instead of letting the FK violation
    # surface as a 500 on flush/commit. (db.get hits the identity map, so a batch that
    # references the same item repeatedly pays a single lookup.)
    if db.get(Item, payload.item_id) is None:
        raise HTTPException(status_code=404, detail="Item not found")
    value = _resolve_value(payload)
    if payload.interaction_type == InteractionType.rate and value is None:
        value = 0.0
    row = UserInteraction(
        user_id=user.id,
        item_id=payload.item_id,
        interaction_type=payload.interaction_type,
        value=value,
        source=payload.source,
        confidence=payload.confidence,
        context=payload.context,
        meta=payload.meta or {},
    )
    db.add(row)
    return row


@router.post("", response_model=InteractionOut)
def post_interaction(
    payload: InteractionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserInteraction:
    row = create_interaction(db, user, payload)
    db.flush()
    db.refresh(row)  # populate server-side timestamp within the same transaction
    # Lightweight online update: bump preference cache stamp — committed atomically
    # together with the interaction row so the two can't diverge on a crash.
    prefs = dict(user.preferences or {})
    prefs["last_interaction_at"] = row.timestamp.isoformat() if row.timestamp else None
    user.preferences = prefs
    db.add(user)
    db.commit()
    db.refresh(row)
    return row


@router.post("/batch", response_model=list[InteractionOut])
def post_interactions_batch(
    payload: InteractionBatchCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UserInteraction]:
    rows = [create_interaction(db, user, item) for item in payload.interactions]
    db.flush()
    for row in rows:
        db.refresh(row)  # populate server-side timestamps within the same transaction
    prefs = dict(user.preferences or {})
    prefs["last_interaction_at"] = rows[-1].timestamp.isoformat() if rows else None
    user.preferences = prefs
    db.add(user)
    db.commit()  # single atomic commit for the whole batch + preference stamp
    return rows
