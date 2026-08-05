from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Item, MediaType, User
from app.schemas import ItemOut

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/items", response_model=list[ItemOut])
def list_items(
    q: str | None = None,
    media_type: MediaType | None = None,
    anchors_only: bool = False,
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Item]:
    query = db.query(Item)
    if media_type:
        query = query.filter(Item.media_type == media_type)
    if anchors_only:
        query = query.filter(Item.is_anchor.is_(True))
    if q:
        like = f"%{q}%"
        query = query.filter(Item.title.ilike(like))
    return query.order_by(Item.popularity.desc()).offset(offset).limit(limit).all()


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Item:
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
