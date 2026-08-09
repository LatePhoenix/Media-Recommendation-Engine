"""Optional Vite production UI served from FastAPI (native packaging).

See docs/packaging/adr-serve-web.md. Mount only when WEB_DIST_DIR points at a
directory containing index.html. Docker/nginx and Vite HMR remain unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# Paths that must never be claimed by the SPA catch-all (defense in depth;
# FastAPI still prefers earlier-registered API routes).
_RESERVED_PREFIXES = (
    "api/",
    "api",
    "health",
    "docs",
    "redoc",
    "openapi.json",
    "assets/",
)


def mount_web_ui(app: FastAPI, web_dist_dir: str) -> bool:
    """Mount static assets + SPA fallback. Returns True if mounted."""
    if not web_dist_dir or not str(web_dist_dir).strip():
        return False

    root = Path(web_dist_dir).expanduser().resolve()
    index = root / "index.html"
    if not index.is_file():
        logger.warning("WEB_DIST_DIR set but index.html missing: %s", root)
        return False

    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="web-assets")

    @app.get("/")
    async def web_index() -> FileResponse:
        return FileResponse(index)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        normalized = full_path.lstrip("/")
        if not normalized or any(
            normalized == p.rstrip("/") or normalized.startswith(p)
            for p in _RESERVED_PREFIXES
        ):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = (root / normalized).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not Found") from exc

        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    logger.info("Serving web UI from %s", root)
    return True
