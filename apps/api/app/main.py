from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

_HERE = Path(__file__).resolve()
# Monorepo: <repo>/apps/api/app/main.py → parents[3] is repo root.
# Container: /app/app/main.py → packages mounted/copied at /packages.
if len(_HERE.parents) > 3 and (_HERE.parents[3] / "packages").is_dir():
    ROOT = _HERE.parents[3]
elif Path("/packages").is_dir():
    ROOT = Path("/")
else:
    ROOT = _HERE.parents[1]
for path in (ROOT, ROOT / "packages"):
    s = str(path)
    if s not in sys.path:
        sys.path.insert(0, s)

from app.config import get_settings
from app.routers import admin, auth, catalog, domain, imports, interactions, onboarding, recommendations

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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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

    ok = checks.get("database") == "ok" and checks.get("redis") == "ok"
    body = {"status": "ready" if ok else "degraded", "checks": checks, "version": app.version}
    if not ok:
        return JSONResponse(status_code=503, content=body)
    return body
