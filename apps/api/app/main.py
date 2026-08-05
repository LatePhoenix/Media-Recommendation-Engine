from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[3]
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
