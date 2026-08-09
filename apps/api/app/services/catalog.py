"""CatalogService — per-domain browse with media-type-appropriate filters."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Item, ItemState, MediaType, UserItemState

VALID_BROWSE_SORTS = ("popularity", "title", "release_year", "recently_added")


def escape_like(term: str) -> str:
    """Escape LIKE/ILIKE wildcards so user input is matched literally.

    Without this, a ``%`` or ``_`` in a search term is treated as a wildcard (and a
    leading ``%`` also defeats the title index). Pair with ``escape="\\"`` on the
    ``ilike`` call.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class CatalogService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_item(self, item_id: UUID, media_type: MediaType | None = None) -> Item | None:
        item = self.db.get(Item, item_id)
        if item is None:
            return None
        if media_type is not None and item.media_type != media_type:
            return None
        return item

    def browse(
        self,
        media_type: MediaType,
        *,
        q: str | None = None,
        genre: str | None = None,
        creator: str | None = None,
        series: str | None = None,
        language: str | None = None,
        release_year: int | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        length_min: int | None = None,
        length_max: int | None = None,
        extension_filters: dict[str, str] | None = None,
        anchors_only: bool = False,
        user_id: UUID | None = None,
        state: ItemState | None = None,
        sort: str = "popularity",
        limit: int = 40,
        offset: int = 0,
    ) -> list[Item]:
        query = self.db.query(Item).filter(Item.media_type == media_type)

        if q:
            query = query.filter(Item.title.ilike(f"%{escape_like(q)}%", escape="\\"))
        if genre:
            query = query.filter(Item.genres.contains([genre]))
        if creator:
            query = query.filter(Item.creators.contains([creator]))
        if series:
            query = query.filter(Item.series.ilike(f"%{escape_like(series)}%", escape="\\"))
        if language:
            query = query.filter(Item.language == language)
        if release_year is not None:
            query = query.filter(Item.release_year == release_year)
        if year_min is not None:
            query = query.filter(Item.release_year >= year_min)
        if year_max is not None:
            query = query.filter(Item.release_year <= year_max)
        if length_min is not None:
            query = query.filter(Item.runtime_or_length >= length_min)
        if length_max is not None:
            query = query.filter(Item.runtime_or_length <= length_max)
        if anchors_only:
            query = query.filter(Item.is_anchor.is_(True))

        # Domain-specific attributes (publisher, narrator, platform, …) live in the
        # extensions JSONB. Each filter is an equality match on a top-level key.
        for key, value in (extension_filters or {}).items():
            query = query.filter(Item.extensions[key].astext == value)

        # Watched / reading / play status: filter by the current user's saved state.
        if state is not None and user_id is not None:
            query = query.join(
                UserItemState,
                (UserItemState.item_id == Item.id) & (UserItemState.user_id == user_id),
            ).filter(UserItemState.state == state)

        query = query.order_by(*self._sort_clause(sort))
        return query.offset(offset).limit(limit).all()

    @staticmethod
    def _sort_clause(sort: str) -> tuple[Any, ...]:
        if sort not in VALID_BROWSE_SORTS:
            sort = "popularity"
        if sort == "title":
            return (Item.sort_title.asc().nullslast(), Item.title.asc())
        if sort == "release_year":
            return (Item.release_year.desc().nullslast(), Item.popularity.desc())
        if sort == "recently_added":
            return (Item.created_at.desc(),)
        return (Item.popularity.desc(),)
