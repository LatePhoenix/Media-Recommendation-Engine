"""Optional public poster enrichment (TMDB / Open Library). Ranking never depends on this."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def resolve_poster_url(
    *,
    media_type: str,
    title: str,
    release_year: int | None = None,
    tmdb_id: str | None = None,
    imdb_id: str | None = None,
    isbn: str | None = None,
    tmdb_api_key: str | None = None,
) -> str | None:
    """Best-effort public HTTPS cover URL. Returns None when keys/APIs unavailable."""
    mt = (media_type or "").lower()
    try:
        if mt in {"movie", "tv"} and tmdb_api_key:
            return _tmdb_poster(
                media_type=mt,
                title=title,
                release_year=release_year,
                tmdb_id=tmdb_id,
                imdb_id=imdb_id,
                api_key=tmdb_api_key,
            )
        if mt in {"book", "audiobook"}:
            return _open_library_cover(title=title, isbn=isbn, release_year=release_year)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Poster enrichment failed for %s (%s): %s", title, mt, exc)
    return None


def _tmdb_poster(
    *,
    media_type: str,
    title: str,
    release_year: int | None,
    tmdb_id: str | None,
    imdb_id: str | None,
    api_key: str,
) -> str | None:
    kind = "movie" if media_type == "movie" else "tv"
    with httpx.Client(timeout=20.0) as client:
        if tmdb_id:
            resp = client.get(
                f"https://api.themoviedb.org/3/{kind}/{tmdb_id}",
                params={"api_key": api_key},
            )
            if resp.status_code < 400:
                path = (resp.json() or {}).get("poster_path")
                if path:
                    return f"{TMDB_IMAGE_BASE}{path}"

        if imdb_id:
            resp = client.get(
                f"https://api.themoviedb.org/3/find/{imdb_id}",
                params={"api_key": api_key, "external_source": "imdb_id"},
            )
            if resp.status_code < 400:
                data = resp.json() or {}
                results = data.get("movie_results") if kind == "movie" else data.get("tv_results")
                if results:
                    path = results[0].get("poster_path")
                    if path:
                        return f"{TMDB_IMAGE_BASE}{path}"

        params: dict[str, Any] = {"api_key": api_key, "query": title}
        if release_year:
            params["year" if kind == "movie" else "first_air_date_year"] = release_year
        resp = client.get(f"https://api.themoviedb.org/3/search/{kind}", params=params)
        if resp.status_code >= 400:
            return None
        results = (resp.json() or {}).get("results") or []
        if not results:
            return None
        path = results[0].get("poster_path")
        return f"{TMDB_IMAGE_BASE}{path}" if path else None


def _open_library_cover(
    *,
    title: str,
    isbn: str | None,
    release_year: int | None,
) -> str | None:
    if isbn:
        clean = "".join(c for c in isbn if c.isalnum())
        if clean:
            return f"https://covers.openlibrary.org/b/isbn/{clean}-L.jpg"

    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            "https://openlibrary.org/search.json",
            params={"title": title, "limit": 5},
        )
        if resp.status_code >= 400:
            return None
        docs = (resp.json() or {}).get("docs") or []
        for doc in docs:
            if release_year and doc.get("first_publish_year") and int(doc["first_publish_year"]) != release_year:
                continue
            cover_id = doc.get("cover_i")
            if cover_id:
                return f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
            isbns = doc.get("isbn") or []
            if isbns:
                return f"https://covers.openlibrary.org/b/isbn/{isbns[0]}-L.jpg"
    return None


def extract_provider_ids(raw: dict[str, Any] | None) -> dict[str, str | None]:
    """Pull common provider keys from connector raw payloads (Trakt, Plex guids, …)."""
    raw = raw or {}
    out: dict[str, str | None] = {"tmdb": None, "imdb": None, "isbn": None}

    ids = raw.get("ids") if isinstance(raw.get("ids"), dict) else {}
    if ids.get("tmdb"):
        out["tmdb"] = str(ids["tmdb"])
    if ids.get("imdb"):
        out["imdb"] = str(ids["imdb"])
    if ids.get("isbn"):
        out["isbn"] = str(ids["isbn"])

    for guid in raw.get("guids") or []:
        g = str(guid)
        if g.startswith("tmdb://"):
            out["tmdb"] = g.split("://", 1)[-1]
        elif g.startswith("imdb://"):
            out["imdb"] = g.split("://", 1)[-1]

    provider_ids = raw.get("ProviderIds") if isinstance(raw.get("ProviderIds"), dict) else {}
    if provider_ids.get("Tmdb"):
        out["tmdb"] = str(provider_ids["Tmdb"])
    if provider_ids.get("Imdb"):
        out["imdb"] = str(provider_ids["Imdb"])
    if provider_ids.get("Isbn") or provider_ids.get("ISBN"):
        out["isbn"] = str(provider_ids.get("Isbn") or provider_ids.get("ISBN"))

    return out
