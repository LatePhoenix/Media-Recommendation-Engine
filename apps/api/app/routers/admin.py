"""Admin/ops routes: per-media model-config management and offline metrics (Phase 5).

Authenticated-only. There is no admin role in the data model yet, so these are gated
by authentication; role-gating is a follow-up. Domains here are resolved by slug
without the per-user enablement check so ops can inspect every vertical.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.domains import resolve_domain
from app.models import MediaType, ModelConfig, User
from app.schemas import AdminModelConfigIn, AdminModelConfigOut
from app.services.metrics import MetricsService

router = APIRouter(prefix="/api/admin", tags=["admin"])


def admin_domain(domain: str = Path(...), _: User = Depends(get_current_user)) -> MediaType:
    return resolve_domain(domain)


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
