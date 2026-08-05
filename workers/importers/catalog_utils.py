from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Item, ItemExternalRef, MediaType

# Cap so repeated re-syncs of the same item can't let popularity grow without bound
# and dominate ranking over time.
POPULARITY_CEILING = 1000.0


def parse_year(value: Any) -> int | None:
    if value is None:
        return None
    try:
        s = str(value)[:4]
        year = int(s)
        if 1800 <= year <= 2100:
            return year
    except (TypeError, ValueError):
        return None
    return None


def upsert_item(
    db: Session,
    source: str,
    norm: Any,
) -> Item:
    """Upsert by external ref, else fuzzy title/year/media_type match."""
    existing_ref = (
        db.query(ItemExternalRef)
        .filter(ItemExternalRef.source == source, ItemExternalRef.external_id == norm.external_id)
        .first()
    )
    if existing_ref:
        item = existing_ref.item
    else:
        q = db.query(Item).filter(
            Item.media_type == MediaType(norm.media_type),
            Item.title.ilike(norm.title),
        )
        if norm.release_year:
            q = q.filter(Item.release_year == norm.release_year)
        item = q.first()
        if item is None:
            item = Item(
                media_type=MediaType(norm.media_type),
                title=norm.title,
                sort_title=norm.sort_title or norm.title,
                series=norm.series,
                genres=norm.genres or [],
                tags=norm.tags or [],
                creators=norm.creators or [],
                release_year=norm.release_year,
                description=norm.description,
                runtime_or_length=norm.runtime_or_length,
                cover_url=norm.cover_url,
                popularity=1.0,
            )
            db.add(item)
            db.flush()
        ref = ItemExternalRef(
            item_id=item.id,
            source=source,
            external_id=norm.external_id,
            external_url=getattr(norm, "external_url", None),
            raw=getattr(norm, "raw", {}) or {},
        )
        db.add(ref)

    # Refresh mutable metadata when re-syncing
    item.genres = norm.genres or item.genres or []
    item.tags = norm.tags or item.tags or []
    item.creators = norm.creators or item.creators or []
    if norm.description:
        item.description = norm.description
    if norm.cover_url:
        item.cover_url = norm.cover_url
    if norm.series:
        item.series = norm.series
    item.popularity = min(float(item.popularity or 0.0) + 0.1, POPULARITY_CEILING)
    db.add(item)
    return item
