"""Admin/ops routes: per-media model-config management and offline metrics.

Gated by require_admin (first registered user is admin by default).
Domains are resolved by slug without per-user enablement so ops can inspect every vertical.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.db import get_db
from app.domains import resolve_domain
from app.models import Item, MediaType, ModelConfig, User
from app.schemas import AdminModelConfigIn, AdminModelConfigOut
from app.services.metadata import MetadataNormalizationService
from app.services.metrics import MetricsService

router = APIRouter(prefix="/api/admin", tags=["admin"])


class MergeItemsIn(BaseModel):
    primary_id: UUID
    duplicate_id: UUID


def admin_domain(domain: str = Path(...), _: User = Depends(require_admin)) -> MediaType:
    return resolve_domain(domain)


@router.post("/items/merge")
def merge_items(
    payload: MergeItemsIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Merge duplicate into primary; repoints FKs including UserInteraction."""
    if payload.primary_id == payload.duplicate_id:
        raise HTTPException(status_code=400, detail="primary and duplicate must differ")
    primary = db.get(Item, payload.primary_id)
    duplicate = db.get(Item, payload.duplicate_id)
    if primary is None or duplicate is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if primary.media_type != duplicate.media_type:
        raise HTTPException(status_code=400, detail="Items must share a media type")
    MetadataNormalizationService(db).merge_items(primary, duplicate)
    db.commit()
    return {"ok": True, "primary_id": str(primary.id)}


@router.get("/{domain}/model-configs", response_model=list[AdminModelConfigOut])
def list_model_configs(
    media_type: MediaType = Depends(admin_domain),
    db: Session = Depends(get_db),
) -> list[AdminModelConfigOut]:
    rows = (
        db.query(ModelConfig)
        .filter(ModelConfig.media_type == media_type)
        .order_by(ModelConfig.name.asc())
        .all()
    )
    return [AdminModelConfigOut.model_validate(r) for r in rows]


@router.post("/{domain}/model-configs", response_model=AdminModelConfigOut)
def upsert_model_config(
    payload: AdminModelConfigIn,
    media_type: MediaType = Depends(admin_domain),
    db: Session = Depends(get_db),
) -> AdminModelConfigOut:
    """Create or update a named per-media config (e.g. a treatment to A/B against default)."""
    row = (
        db.query(ModelConfig)
        .filter(ModelConfig.media_type == media_type, ModelConfig.name == payload.name)
        .first()
    )
    if row is None:
        row = ModelConfig(media_type=media_type, name=payload.name)
        db.add(row)
    row.weights = {k: float(v) for k, v in payload.weights.items()}
    row.active = payload.active
    # Only one active config per media type keeps the default deterministic.
    if payload.active:
        (
            db.query(ModelConfig)
            .filter(
                ModelConfig.media_type == media_type,
                ModelConfig.name != payload.name,
            )
            .update({ModelConfig.active: False})
        )
    db.commit()
    db.refresh(row)
    return AdminModelConfigOut.model_validate(row)


@router.get("/{domain}/metrics")
def domain_metrics(
    config: str | None = Query(None),
    k: int = Query(10, ge=1, le=100),
    media_type: MediaType = Depends(admin_domain),
    db: Session = Depends(get_db),
) -> dict:
    return MetricsService(db).domain_metrics(media_type, config, k=k)


@router.get("/{domain}/metrics/compare")
def compare_metrics(
    control: str = Query("default"),
    treatment: str = Query(...),
    k: int = Query(10, ge=1, le=100),
    media_type: MediaType = Depends(admin_domain),
    db: Session = Depends(get_db),
) -> dict:
    if control == treatment:
        raise HTTPException(status_code=400, detail="control and treatment must differ")
    return MetricsService(db).compare(media_type, control, treatment, k=k)
