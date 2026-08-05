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
from app.routers import auth, catalog, imports, interactions, onboarding, recommendations

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


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "enrichment_enabled": settings.enrichment_enabled,
        "version": "0.1.0",
    }
