from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware

from app.paths import ensure_sys_path

ensure_sys_path()

from app.config import get_settings
from app.routers import admin, auth, catalog, domain, imports, interactions, onboarding, recommendations

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Media Recommendation Engine",
    version="0.1.0",
    description="Local-first hybrid recommender — deterministic ranking with optional Ollama enrichment.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Auth is a Bearer token in the Authorization header, not a cookie, so credentialed
    # CORS is unnecessary — and disabling it prevents accidental cookie/credential
    # exposure if origins are ever widened.
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline hardening headers for all API responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response


app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(IntegrityError)
async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Safety net: a DB constraint violation (FK / unique) that reaches here would
    otherwise become an opaque HTTP 500. Log the full detail server-side and return a
    generic 409 so no schema/constraint internals leak to the client. Handlers that can
    give a more specific status (404 for a missing item, 400 for a known collision)
    should still do so up front — this only catches what slips through."""
    logger.warning(
        "IntegrityError on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=409,
        content={"detail": "The request conflicts with existing data."},
    )


app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(interactions.router)
app.include_router(onboarding.router)
app.include_router(recommendations.router)
app.include_router(imports.router)
app.include_router(admin.router)
# Registered last: its /api/{domain} prefix must not shadow the specific routers above.
app.include_router(domain.router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "enrichment_enabled": settings.enrichment_enabled,
        "version": app.version,
    }


@app.get("/health/ready")
def ready() -> dict:
    """Readiness: Postgres + Redis must respond."""
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    from app.db import SessionLocal
    from app.models import SimilarityEdge

    checks: dict[str, str] = {}
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            edge_count = db.query(SimilarityEdge).count()
            checks["database"] = "ok"
            checks["similarity_edges"] = str(edge_count)
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        checks["database"] = "error"

    try:
        from redis import Redis

        conn = Redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
        conn.ping()
        checks["redis"] = "ok"
    except Exception:  # noqa: BLE001
        checks["redis"] = "error"

    # Surface which rate-limit backend is live so operators can tell whether shared
    # (Redis) limits are actually engaged or the process fell back to per-process memory.
    from app.rate_limit import active_backend_name

    checks["rate_limiter"] = active_backend_name()

    ok = checks.get("database") == "ok" and checks.get("redis") == "ok"
    body = {"status": "ready" if ok else "degraded", "checks": checks, "version": app.version}
    if not ok:
        return JSONResponse(status_code=503, content=body)
    return body


# Native packaging: serve Vite dist when WEB_DIST_DIR is set (after API routes).
from app.static_ui import mount_web_ui  # noqa: E402

mount_web_ui(app, settings.web_dist_dir)
