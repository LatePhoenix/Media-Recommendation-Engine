"""Per-domain API routes: /api/{domain}/... where {domain} is a media slug.

One parameterized router serves all six verticals (movies, tv, audiobooks, games,
books, comics) so ranking, browse, filters, and saved-state workflows stay
media-type-separated without six copies of the same code. Books and comics are
gated by :func:`app.domains.enabled_domain`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.domains import enabled_domain
from app.models import ItemState, MediaType, User
from app.recommender import FEED_TITLES
from app.models import ExternalId
from app.schemas import (
    CollectionCreate,
    CollectionDetailOut,
    CollectionItemIn,
    CollectionOut,
    CreatorDetailOut,
    ExternalLinkOut,
    ItemDetailOut,
    ItemOut,
    ItemStateOut,
    ManualLinkIn,
    ModelConfigOut,
    SavedItemOut,
    SeriesDetailOut,
    SeriesOut,
    SetStateIn,
)
from app.services.catalog import VALID_BROWSE_SORTS, CatalogService
from app.services.external_links import (
    PROVIDER_LABEL,
    VERIFIED_THRESHOLD,
    ExternalLinkService,
)
from app.services.interest import VALID_SAVED_SORTS, InterestService
from app.services.metadata import MetadataNormalizationService
from app.services.recommendation import RecommendationService


def _link_out(link: ExternalId) -> ExternalLinkOut:
    return ExternalLinkOut(
        provider=link.provider,
        label=PROVIDER_LABEL.get(link.provider, link.provider),
        external_key=link.external_key,
        external_url=link.external_url,
        confidence=link.confidence,
        resolution_method=link.resolution_method,
        verified=float(link.confidence or 0.0) >= VERIFIED_THRESHOLD,
    )

router = APIRouter(prefix="/api/{domain}", tags=["domain"])


# --- Recommendations (single-domain) ---


@router.get("/recommendations/feeds", response_model=list[dict])
def domain_feeds(media_type: MediaType = Depends(enabled_domain)) -> list[dict]:
    return [{"feed_key": k, "title": v} for k, v in FEED_TITLES.items()]


@router.get("/recommendations/feeds/{feed_key}")
def domain_feed(
    feed_key: str,
    limit: int = Query(20, ge=1, le=100),
    config: str | None = Query(None, description="Named model config (e.g. a treatment)"),
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if feed_key not in FEED_TITLES:
        raise HTTPException(status_code=404, detail="Unknown feed")
    return RecommendationService(db).feed(user, media_type, feed_key, limit=limit, config_name=config)


@router.get("/model-config", response_model=ModelConfigOut)
def domain_model_config(
    media_type: MediaType = Depends(enabled_domain),
    db: Session = Depends(get_db),
) -> ModelConfigOut:
    """Inspect the active per-media-type ranking weights."""
    return ModelConfigOut(
        media_type=media_type,
        name="default",
        weights=RecommendationService(db).weights(media_type),
        active=True,
    )


# --- Catalog browse with per-domain filters ---


@router.get("/catalog/items", response_model=list[ItemOut])
def browse(
    q: str | None = None,
    genre: str | None = None,
    creator: str | None = None,
    series: str | None = None,
    language: str | None = None,
    release_year: int | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    length_min: int | None = None,
    length_max: int | None = None,
    # Domain-specific extension attributes (comics: publisher; audiobooks: narrator;
    # games: platform). Ignored by domains that don't populate them.
    publisher: str | None = None,
    narrator: str | None = None,
    platform: str | None = None,
    # Watched / reading / play status = the current user's saved state on the item.
    state: ItemState | None = None,
    anchors_only: bool = False,
    sort: str = Query("popularity"),
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ItemOut]:
    if sort not in VALID_BROWSE_SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {VALID_BROWSE_SORTS}")
    ext = {k: v for k, v in {"publisher": publisher, "narrator": narrator, "platform": platform}.items() if v}
    items = CatalogService(db).browse(
        media_type,
        q=q,
        genre=genre,
        creator=creator,
        series=series,
        language=language,
        release_year=release_year,
        year_min=year_min,
        year_max=year_max,
        length_min=length_min,
        length_max=length_max,
        extension_filters=ext or None,
        anchors_only=anchors_only,
        user_id=user.id,
        state=state,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return [ItemOut.model_validate(i) for i in items]


@router.get("/catalog/items/{item_id}", response_model=ItemDetailOut)
def get_domain_item(
    item_id: UUID,
    media_type: MediaType = Depends(enabled_domain),
    db: Session = Depends(get_db),
) -> ItemDetailOut:
    item = CatalogService(db).get_item(item_id, media_type)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    svc = ExternalLinkService(db)
    links = svc.list_links(item.id)
    if not links:
        # Resolve lazily on first view so the source panel is never empty.
        links = svc.resolve_item(item)
        db.commit()
    detail = ItemDetailOut.model_validate(item)
    detail.links = [_link_out(link) for link in links]
    return detail


# --- External source links (Phase 3) ---


@router.get("/items/{item_id}/links", response_model=list[ExternalLinkOut])
def get_item_links(
    item_id: UUID,
    media_type: MediaType = Depends(enabled_domain),
    db: Session = Depends(get_db),
) -> list[ExternalLinkOut]:
    item = CatalogService(db).get_item(item_id, media_type)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    svc = ExternalLinkService(db)
    links = svc.list_links(item.id)
    if not links:
        links = svc.resolve_item(item)
        db.commit()
    return [_link_out(link) for link in links]


@router.post("/items/{item_id}/links/resolve", response_model=list[ExternalLinkOut])
def resolve_item_links(
    item_id: UUID,
    media_type: MediaType = Depends(enabled_domain),
    db: Session = Depends(get_db),
) -> list[ExternalLinkOut]:
    item = CatalogService(db).get_item(item_id, media_type)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    links = ExternalLinkService(db).resolve_item(item)
    db.commit()
    return [_link_out(link) for link in links]


@router.put("/items/{item_id}/links/{provider}", response_model=ExternalLinkOut)
def set_manual_link(
    item_id: UUID,
    provider: str,
    payload: ManualLinkIn,
    media_type: MediaType = Depends(enabled_domain),
    db: Session = Depends(get_db),
) -> ExternalLinkOut:
    """Manual override (admin). Manual links are authoritative and never auto-overwritten."""
    item = CatalogService(db).get_item(item_id, media_type)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    link = ExternalLinkService(db).upsert(
        item,
        provider,
        payload.external_url,
        external_key=payload.external_key,
        confidence=payload.confidence,
        resolution_method="manual",
    )
    db.commit()
    db.refresh(link)
    return _link_out(link)


# --- Franchise / series & creators (Phase 4) ---


@router.get("/series", response_model=list[SeriesOut])
def list_series(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    media_type: MediaType = Depends(enabled_domain),
    db: Session = Depends(get_db),
) -> list[SeriesOut]:
    rows = MetadataNormalizationService(db).list_series(media_type, limit=limit, offset=offset)
    return [SeriesOut.model_validate(s) for s in rows]


@router.get("/series/{series_id}", response_model=SeriesDetailOut)
def get_series(
    series_id: UUID,
    media_type: MediaType = Depends(enabled_domain),
    db: Session = Depends(get_db),
) -> SeriesDetailOut:
    svc = MetadataNormalizationService(db)
    series = svc.get_series(series_id, media_type)
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")
    return SeriesDetailOut(
        id=series.id,
        media_type=series.media_type,
        name=series.name,
        franchise=series.franchise,
        items=[ItemOut.model_validate(i) for i in svc.series_items(series)],
    )


@router.get("/creators/{creator_id}", response_model=CreatorDetailOut)
def get_creator(
    creator_id: UUID,
    media_type: MediaType = Depends(enabled_domain),
    db: Session = Depends(get_db),
) -> CreatorDetailOut:
    svc = MetadataNormalizationService(db)
    creator = svc.get_creator(creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="Creator not found")
    return CreatorDetailOut(
        id=creator.id,
        name=creator.name,
        kind=creator.kind,
        items=[ItemOut.model_validate(i) for i in svc.creator_items(creator_id, media_type)],
    )


# --- Interest state ---


@router.get("/items/{item_id}/state", response_model=ItemStateOut | None)
def get_state(
    item_id: UUID,
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemStateOut | None:
    row = InterestService(db).get_state(user.id, item_id)
    if row is None or row.media_type != media_type:
        return None
    return ItemStateOut.model_validate(row)


@router.put("/items/{item_id}/state", response_model=ItemStateOut)
def set_state(
    item_id: UUID,
    payload: SetStateIn,
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ItemStateOut:
    item = CatalogService(db).get_item(item_id, media_type)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in this domain")
    row = InterestService(db).set_state(
        user.id,
        item,
        payload.state,
        source=payload.source,
        notes=payload.notes,
        priority=payload.priority,
        reason="api",
    )
    db.commit()
    db.refresh(row)
    return ItemStateOut.model_validate(row)


@router.delete("/items/{item_id}/state", status_code=204, response_model=None)
def clear_state(
    item_id: UUID,
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    removed = InterestService(db).clear_state(user.id, item_id)
    db.commit()
    if not removed:
        raise HTTPException(status_code=404, detail="No saved state for this item")


@router.get("/saved", response_model=list[SavedItemOut])
def list_saved(
    state: list[ItemState] | None = Query(default=None),
    sort: str = Query("recently_added"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SavedItemOut]:
    if sort not in VALID_SAVED_SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {VALID_SAVED_SORTS}")
    rows = InterestService(db).list_states(
        user.id, media_type, states=state, sort=sort, limit=limit, offset=offset
    )
    return [
        SavedItemOut(
            item=ItemOut.model_validate(r.item),
            state=r.state,
            source=r.source,
            notes=r.notes,
            priority=r.priority,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


# --- Saved collections ---


@router.get("/collections", response_model=list[CollectionOut])
def list_collections(
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CollectionOut]:
    return [CollectionOut.model_validate(c) for c in InterestService(db).list_collections(user.id, media_type)]


@router.post("/collections", response_model=CollectionOut, status_code=201)
def create_collection(
    payload: CollectionCreate,
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CollectionOut:
    col = InterestService(db).create_collection(
        user.id, media_type, payload.name, description=payload.description, is_default=payload.is_default
    )
    db.commit()
    db.refresh(col)
    return CollectionOut.model_validate(col)


@router.get("/collections/{collection_id}", response_model=CollectionDetailOut)
def get_collection(
    collection_id: UUID,
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CollectionDetailOut:
    svc = InterestService(db)
    col = svc.get_collection(user.id, collection_id)
    if col is None or col.media_type != media_type:
        raise HTTPException(status_code=404, detail="Collection not found")
    ordered = sorted(col.items, key=lambda ci: ci.sort_order)
    return CollectionDetailOut(
        id=col.id,
        media_type=col.media_type,
        name=col.name,
        description=col.description,
        is_default=col.is_default,
        created_at=col.created_at,
        updated_at=col.updated_at,
        items=[ItemOut.model_validate(ci.item) for ci in ordered],
    )


@router.post("/collections/{collection_id}/items", status_code=204, response_model=None)
def add_collection_item(
    collection_id: UUID,
    payload: CollectionItemIn,
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = InterestService(db)
    col = svc.get_collection(user.id, collection_id)
    if col is None or col.media_type != media_type:
        raise HTTPException(status_code=404, detail="Collection not found")
    item = CatalogService(db).get_item(payload.item_id, media_type)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found in this domain")
    svc.add_to_collection(col, payload.item_id, sort_order=payload.sort_order)
    db.commit()


@router.delete("/collections/{collection_id}/items/{item_id}", status_code=204, response_model=None)
def remove_collection_item(
    collection_id: UUID,
    item_id: UUID,
    media_type: MediaType = Depends(enabled_domain),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = InterestService(db)
    col = svc.get_collection(user.id, collection_id)
    if col is None or col.media_type != media_type:
        raise HTTPException(status_code=404, detail="Collection not found")
    removed = svc.remove_from_collection(col, item_id)
    db.commit()
    if not removed:
        raise HTTPException(status_code=404, detail="Item not in collection")
