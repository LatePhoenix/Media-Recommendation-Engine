from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    ImportJob,
    ImportJobStatus,
    ImportSource,
    InteractionContext,
    InteractionSource,
    InteractionType,
    ItemExternalRef,
    UserInteraction,
)
from app.security_crypto import decrypt_credentials
from workers.importers.audiobookshelf import AudiobookshelfConnector
from workers.importers.catalog_utils import upsert_item
from workers.importers.jellyfin import JellyfinConnector
from workers.importers.komga import KomgaConnector
from workers.importers.plex import PlexConnector
from workers.importers.trakt import TraktConnector

logger = logging.getLogger(__name__)


def get_connector(source: str, base_url: str | None):
    s = source.lower()
    if s == "jellyfin":
        return JellyfinConnector(base_url or "")
    if s == "plex":
        return PlexConnector(base_url or "")
    if s == "audiobookshelf":
        return AudiobookshelfConnector(base_url or "")
    if s == "komga":
        return KomgaConnector(base_url or "")
    if s == "trakt":
        return TraktConnector(base_url or "https://api.trakt.tv")
    raise ValueError(f"Unsupported connector: {source}")


def enqueue_import_job(job_id: str) -> bool:
    try:
        from redis import Redis
        from rq import Queue

        from app.config import get_settings

        settings = get_settings()
        conn = Redis.from_url(settings.redis_url)
        conn.ping()
        q = Queue("imports", connection=conn)
        q.enqueue("workers.importers.runner.run_import_job_sync", job_id, job_timeout=3600)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.info("RQ enqueue unavailable, will run sync: %s", exc)
        return False


def run_import_job_sync(job_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return asyncio.run(_run_job(db, job_id))
    finally:
        db.close()


async def _run_job(db: Session, job_id: str) -> dict[str, Any]:
    job = db.get(ImportJob, job_id)
    if not job:
        return {"error": "job not found"}
    src = db.get(ImportSource, job.import_source_id)
    if not src:
        job.status = ImportJobStatus.failed
        job.error = "import source missing"
        db.commit()
        return {"error": job.error}

    job.status = ImportJobStatus.running
    job.started_at = datetime.now(timezone.utc)
    job.error = None
    db.commit()

    try:
        credentials: dict[str, Any] = {}
        if src.credentials_encrypted:
            credentials = json.loads(decrypt_credentials(src.credentials_encrypted))
        connector = get_connector(src.source, src.base_url)
        session = await connector.authenticate(credentials)
        libraries = await connector.list_libraries(session)
        items, cursor = await connector.sync_items(session, libraries=libraries, cursor=job.cursor or {})
        upserted = 0
        for norm in items:
            upsert_item(db, src.source, norm)
            upserted += 1

        consumption = await connector.sync_consumption(session, cursor=job.cursor or {})
        written = 0
        for c in consumption:
            ref = (
                db.query(ItemExternalRef)
                .filter(
                    ItemExternalRef.source == src.source,
                    ItemExternalRef.external_id == c.external_item_id,
                )
                .first()
            )
            if not ref:
                continue
            itype = (
                InteractionType.finish if c.interaction_type == "finish" else InteractionType.consume
            )
            db.add(
                UserInteraction(
                    user_id=src.user_id,
                    item_id=ref.item_id,
                    interaction_type=itype,
                    value=None,
                    source=InteractionSource.import_,
                    context=InteractionContext.import_sync,
                    confidence=c.confidence,
                    meta={"progress": c.progress, "connector": src.source},
                )
            )
            written += 1

        job.cursor = cursor
        job.stats = {"items_upserted": upserted, "consumption_written": written}
        job.status = ImportJobStatus.succeeded
        job.finished_at = datetime.now(timezone.utc)
        src.last_sync_at = job.finished_at
        src.last_status = "succeeded"
        db.add(src)
        db.commit()
        return job.stats
    except Exception as exc:  # noqa: BLE001
        logger.exception("Import job failed")
        job.status = ImportJobStatus.failed
        job.error = str(exc)
        job.finished_at = datetime.now(timezone.utc)
        src.last_status = "failed"
        db.add(src)
        db.commit()
        return {"error": str(exc)}
