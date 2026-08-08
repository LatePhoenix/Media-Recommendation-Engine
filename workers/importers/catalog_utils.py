from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Item, ItemExternalRef, MediaType
from app.services.metadata import MetadataNormalizationService

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
    *,
    import_source_id: Any | None = None,
) -> Item:
    """Upsert by external ref, else fuzzy title/year/media_type match."""
    meta = MetadataNormalizationService(db)
    cover = getattr(norm, "cover_url", None)
    if cover and import_source_id and str(cover).startswith("/"):
        from urllib.parse import quote

        cover = (
            f"/api/imports/sources/{import_source_id}/artwork"
            f"?path={quote(str(cover), safe='/')}"
        )

    existing_ref = (
        db.query(ItemExternalRef)
        .filter(ItemExternalRef.source == source, ItemExternalRef.external_id == norm.external_id)
        .first()
    )
    if existing_ref:
        item = existing_ref.item
    else:
        # Canonical dedup across sources: match by normalized title/alias before
        # creating a new item, so the same title from Plex and Trakt collapses.
        item = meta.find_duplicate(
            MediaType(norm.media_type), norm.title, norm.release_year
        )
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
                cover_url=cover,
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
    if cover:
        item.cover_url = cover
    if norm.series:
        item.series = norm.series
    item.popularity = min(float(item.popularity or 0.0) + 0.1, POPULARITY_CEILING)
    db.add(item)
    db.flush()
    # Populate canonical creators/series/tags/aliases from the refreshed fields.
    meta.normalize_item(item, source=source)
    return item
