from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.config import get_settings
from app.net_security import validate_import_url
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
from workers.importers.tmdb import TmdbConnector
from workers.importers.trakt import TraktConnector

logger = logging.getLogger(__name__)


def _safe_error(exc: Exception) -> str:
    """Map an exception to a client-safe message. Full detail is logged separately;
    only category-level text is persisted to job.error / returned to the user, so
    internal hosts, connection strings and tracebacks are never disclosed."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return "Timed out while contacting the server."
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return "Authentication with the server failed (check your token/credentials)."
        return "The server returned an error response."
    if isinstance(exc, httpx.HTTPError):
        return "Could not reach the server."
    if isinstance(exc, ValueError):
        # ValueError is used for intentional, non-sensitive config/validation messages
        # (missing token, unsupported connector, unsafe base_url).
        return str(exc)
    return "An internal error occurred during import."


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
    if s == "tmdb":
        return TmdbConnector(base_url or "https://api.themoviedb.org")
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


def run_import_job_sync(job_id: str, timeout: float | None = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return asyncio.run(_run_job(db, job_id, timeout=timeout))
    finally:
        db.close()


async def _run_job(db: Session, job_id: str, timeout: float | None = None) -> dict[str, Any]:
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
        # Re-validate the target immediately before any outbound request: the base_url
        # (or the DNS it points to) may have changed since the source was registered.
        if src.base_url:
            validate_import_url(
                src.base_url,
                allow_private=get_settings().allow_private_import_urls,
            )
        credentials: dict[str, Any] = {}
        if src.credentials_encrypted:
            credentials = json.loads(decrypt_credentials(src.credentials_encrypted))
        connector = get_connector(src.source, src.base_url)

        async def _fetch() -> tuple[list, dict, list]:
            session = await connector.authenticate(credentials)
            libraries = await connector.list_libraries(session)
            fetched_items, fetched_cursor = await connector.sync_items(
                session, libraries=libraries, cursor=job.cursor or {}
            )
            fetched_consumption = await connector.sync_consumption(session, cursor=job.cursor or {})
            return fetched_items, fetched_cursor, fetched_consumption

        if timeout is not None:
            items, cursor, consumption = await asyncio.wait_for(_fetch(), timeout=timeout)
        else:
            items, cursor, consumption = await _fetch()

        upserted = 0
        for norm in items:
            upsert_item(db, src.source, norm, import_source_id=src.id)
            upserted += 1

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
        stub = bool(cursor.get("stub")) if isinstance(cursor, dict) else False
        job.stats = {
            "items_upserted": upserted,
            "consumption_written": written,
            **({"stub": True} if stub else {}),
        }
        job.status = ImportJobStatus.succeeded
        job.finished_at = datetime.now(timezone.utc)
        src.last_sync_at = job.finished_at
        src.last_status = "stub" if stub else "succeeded"
        db.add(src)
        db.commit()
        return job.stats
    except Exception as exc:  # noqa: BLE001
        logger.exception("Import job %s failed", job_id)
        safe = _safe_error(exc)
        job.status = ImportJobStatus.failed
        job.error = safe
        job.finished_at = datetime.now(timezone.utc)
        src.last_status = "failed"
        db.add(src)
        db.commit()
        return {"error": safe}
