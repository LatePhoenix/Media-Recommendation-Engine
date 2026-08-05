from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import ImportJob, ImportJobStatus, ImportSource, User
from app.schemas import CsvImportPayload, ImportJobOut, ImportSourceCreate, ImportSourceOut
from app.security_crypto import encrypt_credentials
from workers.importers.runner import enqueue_import_job, run_import_job_sync

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.get("/sources", response_model=list[ImportSourceOut])
def list_sources(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ImportSource]:
    return db.query(ImportSource).filter(ImportSource.user_id == user.id).all()


@router.post("/sources", response_model=ImportSourceOut, status_code=201)
def create_source(
    payload: ImportSourceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportSource:
    encrypted = None
    if payload.credentials:
        encrypted = encrypt_credentials(json.dumps(payload.credentials))
    src = ImportSource(
        user_id=user.id,
        source=payload.source,
        display_name=payload.display_name,
        base_url=payload.base_url,
        credentials_encrypted=encrypted,
        config=payload.config or {},
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


@router.post("/sources/{source_id}/sync", response_model=ImportJobOut)
def trigger_sync(
    source_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportJob:
    src = db.get(ImportSource, source_id)
    if not src or src.user_id != user.id:
        raise HTTPException(status_code=404, detail="Import source not found")
    job = ImportJob(import_source_id=src.id, status=ImportJobStatus.pending)
    db.add(job)
    db.commit()
    db.refresh(job)
    # Prefer RQ; fall back to sync for local-dev without worker
    queued = enqueue_import_job(str(job.id))
    if not queued:
        run_import_job_sync(str(job.id))
        db.refresh(job)
    return job


@router.get("/jobs", response_model=list[ImportJobOut])
def list_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ImportJob]:
    return (
        db.query(ImportJob)
        .join(ImportSource)
        .filter(ImportSource.user_id == user.id)
        .order_by(ImportJob.created_at.desc())
        .limit(50)
        .all()
    )


@router.post("/csv", response_model=dict)
def import_csv(
    payload: CsvImportPayload,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from workers.importers.csv_importer import import_csv_rows

    stats = import_csv_rows(db, user, payload.rows)
    db.commit()
    return {"ok": True, "stats": stats, "imported_at": datetime.now(timezone.utc).isoformat()}
