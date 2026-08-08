"""Domain (media-type) routing helpers.

The product keeps media types operationally separate. URLs use plural slugs
(``/api/movies/...``) that map onto the singular :class:`MediaType` enum. Books and
comics are opt-in, so a domain the user has not enabled resolves to 403.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Path

from app.auth import get_current_user
from app.models import MediaType, User

# Plural URL slug -> MediaType. Order defines default nav order in the UI.
SLUG_TO_MEDIA: dict[str, MediaType] = {
    "movies": MediaType.movie,
    "tv": MediaType.tv,
    "audiobooks": MediaType.audiobook,
    "games": MediaType.game,
    "books": MediaType.book,
    "comics": MediaType.comic,
}
MEDIA_TO_SLUG: dict[MediaType, str] = {v: k for k, v in SLUG_TO_MEDIA.items()}


def resolve_domain(domain: str) -> MediaType:
    """Slug -> MediaType, or 404 for an unknown slug."""
    mt = SLUG_TO_MEDIA.get(domain)
    if mt is None:
        raise HTTPException(status_code=404, detail=f"Unknown domain {domain!r}")
    return mt


def enabled_domain(
    domain: str = Path(..., description="Media domain slug, e.g. 'movies'"),
    user: User = Depends(get_current_user),
) -> MediaType:
    """Resolve a domain slug and enforce that the user has it enabled.

    Used as a FastAPI dependency for every per-domain route so a disabled domain
    (books/comics by default) cannot be read or written through the API.
    """
    mt = resolve_domain(domain)
    if mt.value not in (user.enabled_media_types or []):
        raise HTTPException(status_code=403, detail=f"Domain {domain!r} is not enabled")
    return mt
