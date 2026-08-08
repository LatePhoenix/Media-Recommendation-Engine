"""ExternalLinkService — resolve outbound public-metadata links (Phase 3).

Deterministic and offline by default: it builds verified deep links when a provider
key can be harvested from import provenance (Plex/Trakt guids, etc.) or set manually,
and otherwise emits clearly-marked *search* links (low confidence). It never calls a
network service itself — an upstream resolver (TMDb/IGDB/etc.) can later feed keys in
via :meth:`ExternalLinkService.upsert`. URL builders and the merge policy are pure
module functions so they unit-test without a DB.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import quote, quote_plus
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import ExternalId, Item, ItemExternalRef, MediaType

# Which providers each vertical exposes. Movies/TV get the spec's IMDb/RT/Metacritic
# (plus TMDb as the upstream ID source); other media get best-available equivalents.
PROVIDERS_BY_MEDIA: dict[MediaType, list[str]] = {
    MediaType.movie: ["imdb", "rottentomatoes", "metacritic", "tmdb"],
    MediaType.tv: ["imdb", "rottentomatoes", "metacritic", "tmdb"],
    MediaType.book: ["openlibrary", "googlebooks"],
    MediaType.audiobook: ["openlibrary", "googlebooks"],
    MediaType.comic: ["comicvine"],
    MediaType.game: ["metacritic", "igdb"],
}

PROVIDER_LABEL: dict[str, str] = {
    "imdb": "IMDb",
    "rottentomatoes": "Rotten Tomatoes",
    "metacritic": "Metacritic",
    "tmdb": "TMDb",
    "openlibrary": "Open Library",
    "googlebooks": "Google Books",
    "igdb": "IGDB",
    "comicvine": "Comic Vine",
}

VERIFIED_THRESHOLD = 0.6

# Regexes for harvesting provider keys out of import-source guids / raw payloads.
_KEY_PATTERNS: dict[str, re.Pattern[str]] = {
    "imdb": re.compile(r"(tt\d{6,9})"),
    "tmdb": re.compile(r"(?:themoviedb|tmdb)://(?:movie/|tv/)?(\d+)"),
    "tvdb": re.compile(r"(?:thetvdb|tvdb)://(?:series/)?(\d+)"),
}


@dataclass(frozen=True)
class ResolvedLink:
    provider: str
    external_key: str | None
    external_url: str
    confidence: float
    resolution_method: str


def deep_link(provider: str, key: str, media_type: MediaType) -> str | None:
    """Canonical destination URL for a known provider key, or None if unsupported."""
    k = key.strip()
    if not k:
        return None
    if provider == "imdb":
        return f"https://www.imdb.com/title/{k}/"
    if provider == "tmdb":
        kind = "tv" if media_type == MediaType.tv else "movie"
        return f"https://www.themoviedb.org/{kind}/{quote(k, safe='')}"
    if provider == "tvdb":
        return f"https://thetvdb.com/dereferrer/series/{quote(k, safe='')}"
    if provider == "rottentomatoes":
        return f"https://www.rottentomatoes.com/{k.lstrip('/')}"
    if provider == "metacritic":
        return f"https://www.metacritic.com/{k.lstrip('/')}"
    if provider == "openlibrary":
        return f"https://openlibrary.org/works/{quote(k, safe='')}"
    if provider == "googlebooks":
        return f"https://books.google.com/books?id={quote(k, safe='')}"
    if provider == "igdb":
        return f"https://www.igdb.com/games/{quote(k, safe='')}"
    if provider == "comicvine":
        return f"https://comicvine.gamespot.com/{k.lstrip('/')}"
    return None


def search_link(provider: str, title: str, year: int | None) -> str | None:
    """Best-effort search URL used when no verified key exists (unresolved)."""
    q = quote_plus(f"{title} {year}".strip() if year else title)
    qt = quote_plus(title)
    if provider == "imdb":
        return f"https://www.imdb.com/find/?q={qt}&s=tt"
    if provider == "rottentomatoes":
        return f"https://www.rottentomatoes.com/search?search={qt}"
    if provider == "metacritic":
        return f"https://www.metacritic.com/search/{qt}/"
    if provider == "tmdb":
        return f"https://www.themoviedb.org/search?query={q}"
    if provider == "openlibrary":
        return f"https://openlibrary.org/search?q={q}"
    if provider == "googlebooks":
        return f"https://www.google.com/search?tbm=bks&q={q}"
    if provider == "igdb":
        return f"https://www.igdb.com/search?type=1&q={qt}"
    if provider == "comicvine":
        return f"https://comicvine.gamespot.com/search/?q={qt}"
    return None


def harvest_keys(refs) -> dict[str, str]:
    """Pull imdb/tmdb/tvdb keys from import-source external refs (guids/raw payloads)."""
    keys: dict[str, str] = {}
    for ref in refs:
        blob = f"{getattr(ref, 'external_id', '') or ''} {json.dumps(getattr(ref, 'raw', {}) or {})}"
        source = (getattr(ref, "source", "") or "").lower()
        if source in _KEY_PATTERNS and getattr(ref, "external_id", None):
            keys.setdefault(source, str(ref.external_id))
        for provider, pattern in _KEY_PATTERNS.items():
            if provider in keys:
                continue
            m = pattern.search(blob)
            if m:
                keys[provider] = m.group(1)
    return keys


def resolve_links(
    media_type: MediaType, title: str, year: int | None, harvested: dict[str, str]
) -> list[ResolvedLink]:
    """Compute the desired link set for an item. Pure; no DB, no network."""
    out: list[ResolvedLink] = []
    for provider in PROVIDERS_BY_MEDIA.get(media_type, []):
        key = harvested.get(provider)
        if key:
            url = deep_link(provider, key, media_type)
            if url:
                out.append(ResolvedLink(provider, key, url, 1.0, "imported"))
                continue
        url = search_link(provider, title, year)
        if url:
            out.append(ResolvedLink(provider, None, url, 0.2, "search"))
    return out


def should_write(existing: ExternalId | None, new: ResolvedLink) -> bool:
    """Never overwrite a manual link; never downgrade a higher-confidence link."""
    if existing is None:
        return True
    if existing.resolution_method == "manual":
        return False
    return new.confidence >= float(existing.confidence or 0.0)


class ExternalLinkService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_links(self, item_id: UUID) -> list[ExternalId]:
        return (
            self.db.query(ExternalId)
            .filter(ExternalId.item_id == item_id)
            .order_by(ExternalId.confidence.desc(), ExternalId.provider.asc())
            .all()
        )

    def resolve_item(self, item: Item) -> list[ExternalId]:
        """(Re)resolve links for an item, honoring the no-downgrade / no-clobber policy."""
        refs = self.db.query(ItemExternalRef).filter(ItemExternalRef.item_id == item.id).all()
        harvested = harvest_keys(refs)
        desired = resolve_links(item.media_type, item.title, item.release_year, harvested)
        existing = {e.provider: e for e in self.list_links(item.id)}
        for link in desired:
            cur = existing.get(link.provider)
            if not should_write(cur, link):
                continue
            self._upsert(item, cur, link)
        # The session is autoflush=False, so flush the just-added rows before
        # re-querying — otherwise the first resolve returns an empty list.
        self.db.flush()
        return self.list_links(item.id)

    def upsert(
        self,
        item: Item,
        provider: str,
        external_url: str,
        *,
        external_key: str | None = None,
        confidence: float = 1.0,
        resolution_method: str = "manual",
    ) -> ExternalId:
        """Manual / upstream-provided override. Manual writes always win."""
        cur = (
            self.db.query(ExternalId)
            .filter(ExternalId.item_id == item.id, ExternalId.provider == provider)
            .first()
        )
        link = ResolvedLink(provider, external_key, external_url, confidence, resolution_method)
        return self._upsert(item, cur, link)

    def _upsert(self, item: Item, cur: ExternalId | None, link: ResolvedLink) -> ExternalId:
        if cur is None:
            cur = ExternalId(item_id=item.id, media_type=item.media_type, provider=link.provider)
            self.db.add(cur)
        cur.external_key = link.external_key
        cur.external_url = link.external_url
        cur.confidence = link.confidence
        cur.resolution_method = link.resolution_method
        return cur
