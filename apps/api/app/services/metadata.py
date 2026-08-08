"""MetadataNormalizationService — canonical identity, dedup, and grouping (Phase 4).

Turns the denormalized JSONB fields on ``Item`` (creators/series/genres/tags) into
canonical entities so the same title from different sources collapses to one item and
series/creator grouping becomes possible. The JSONB fields remain as the engine's
fast read cache; these tables are the identity/grouping source of truth.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    CanonicalTag,
    Creator,
    EmbeddingVector,
    ExternalId,
    Item,
    ItemAlias,
    ItemCreator,
    ItemExternalRef,
    ItemTag,
    MediaType,
    RecommendationEvent,
    SavedCollectionItem,
    Series,
    SeriesItem,
    SimilarityEdge,
    UserItemState,
    UserItemStateHistory,
)
from app.services.normalize import normalize_name, normalize_title, slugify


class MetadataNormalizationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- creators ---

    def resolve_creator(self, name: str, kind: str | None = None) -> Creator | None:
        norm = normalize_name(name)
        if not norm:
            return None
        c = self.db.execute(
            select(Creator).where(Creator.normalized_name == norm)
        ).scalar_one_or_none()
        if c is None:
            c = Creator(name=name, normalized_name=norm, kind=kind)
            self.db.add(c)
            self.db.flush()
        return c

    def link_creator(self, item: Item, name: str, role: str = "", sort_order: int = 0) -> ItemCreator | None:
        c = self.resolve_creator(name)
        if c is None:
            return None
        existing = self.db.get(ItemCreator, {"item_id": item.id, "creator_id": c.id, "role": role})
        if existing is not None:
            return existing
        link = ItemCreator(item_id=item.id, creator_id=c.id, role=role, sort_order=sort_order)
        self.db.add(link)
        return link

    # --- series ---

    def resolve_series(self, media_type: MediaType, name: str, franchise: str | None = None) -> Series | None:
        norm = normalize_name(name)
        if not norm:
            return None
        s = self.db.execute(
            select(Series).where(Series.media_type == media_type, Series.normalized_name == norm)
        ).scalar_one_or_none()
        if s is None:
            s = Series(media_type=media_type, name=name, normalized_name=norm, franchise=franchise)
            self.db.add(s)
            self.db.flush()
        elif franchise and not s.franchise:
            s.franchise = franchise
        return s

    def link_series(
        self, item: Item, name: str, franchise: str | None = None, sequence: float | None = None
    ) -> SeriesItem | None:
        s = self.resolve_series(item.media_type, name, franchise)
        if s is None:
            return None
        existing = self.db.get(SeriesItem, {"series_id": s.id, "item_id": item.id})
        if existing is not None:
            if sequence is not None:
                existing.sequence = sequence
            return existing
        link = SeriesItem(series_id=s.id, item_id=item.id, sequence=sequence)
        self.db.add(link)
        # Flush so a repeat call in the same (autoflush=False) session sees this row
        # via db.get and updates it, rather than inserting a duplicate PK.
        self.db.flush()
        return link

    # --- tags ---

    def resolve_tag(self, label: str, category: str | None = None) -> CanonicalTag | None:
        slug = slugify(label)
        if not slug:
            return None
        t = self.db.execute(
            select(CanonicalTag).where(CanonicalTag.slug == slug)
        ).scalar_one_or_none()
        if t is None:
            t = CanonicalTag(slug=slug, label=label, category=category)
            self.db.add(t)
            self.db.flush()
        return t

    def link_tag(self, item: Item, label: str, weight: float | None = None, category: str | None = None) -> ItemTag | None:
        t = self.resolve_tag(label, category)
        if t is None:
            return None
        existing = self.db.get(ItemTag, {"item_id": item.id, "tag_id": t.id})
        if existing is not None:
            return existing
        link = ItemTag(item_id=item.id, tag_id=t.id, weight=weight)
        self.db.add(link)
        return link

    # --- aliases ---

    def add_alias(self, item: Item, alias: str, source: str | None = None) -> ItemAlias | None:
        norm = normalize_title(alias)
        if not norm:
            return None
        existing = self.db.execute(
            select(ItemAlias).where(ItemAlias.item_id == item.id, ItemAlias.normalized_alias == norm)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = ItemAlias(item_id=item.id, alias=alias, normalized_alias=norm, source=source)
        self.db.add(row)
        return row

    # --- orchestration ---

    def normalize_item(self, item: Item, source: str | None = None) -> None:
        """Populate canonical tables from an item's denormalized fields. Idempotent."""
        self.add_alias(item, item.title, source=source)
        if item.sort_title and normalize_title(item.sort_title) != normalize_title(item.title):
            self.add_alias(item, item.sort_title, source=source)
        for i, name in enumerate(item.creators or []):
            self.link_creator(item, str(name), sort_order=i)
        if item.series:
            self.link_series(item, item.series, franchise=item.franchise)
        for g in item.genres or []:
            self.link_tag(item, str(g), category="genre")
        for t in item.tags or []:
            self.link_tag(item, str(t), category="tag")

    # --- dedup ---

    def find_duplicate(
        self,
        media_type: MediaType,
        title: str,
        year: int | None = None,
        exclude_id: UUID | None = None,
    ) -> Item | None:
        """Find an existing canonical item matching title (via alias or normalized title)."""
        norm = normalize_title(title)
        if not norm:
            return None
        alias_q = (
            select(Item)
            .join(ItemAlias, ItemAlias.item_id == Item.id)
            .where(Item.media_type == media_type, ItemAlias.normalized_alias == norm)
        )
        if exclude_id is not None:
            alias_q = alias_q.where(Item.id != exclude_id)
        for item in self.db.execute(alias_q).scalars().all():
            if year is None or item.release_year is None or item.release_year == year:
                return item

        title_q = select(Item).where(Item.media_type == media_type)
        if year is not None:
            title_q = title_q.where(Item.release_year == year)
        if exclude_id is not None:
            title_q = title_q.where(Item.id != exclude_id)
        for item in self.db.execute(title_q).scalars().all():
            if normalize_title(item.title) == norm:
                return item
        return None

    def merge_items(self, primary: Item, duplicate: Item) -> Item:
        """Collapse ``duplicate`` into ``primary``, repointing all references.

        Derived/regenerable data (embeddings, similarity edges) on the duplicate is
        dropped rather than merged. User/collection/link rows are moved with
        conflict-aware repointing so composite-unique constraints hold.
        """
        if primary.id == duplicate.id:
            return primary

        self.db.execute(
            delete(SimilarityEdge).where(
                (SimilarityEdge.item_a_id == duplicate.id) | (SimilarityEdge.item_b_id == duplicate.id)
            )
        )
        self.db.execute(delete(EmbeddingVector).where(EmbeddingVector.entity_id == duplicate.id))

        # No per-item unique constraint -> plain repoint.
        for model in (ItemExternalRef, RecommendationEvent, UserItemStateHistory):
            self.db.execute(
                update(model).where(model.item_id == duplicate.id).values(item_id=primary.id)
            )

        # Composite-unique children -> move only non-colliding rows.
        self._move_conflict_aware(UserItemState, [UserItemState.user_id], primary.id, duplicate.id)
        self._move_conflict_aware(ExternalId, [ExternalId.provider], primary.id, duplicate.id)
        self._move_conflict_aware(ItemAlias, [ItemAlias.normalized_alias], primary.id, duplicate.id)
        self._move_conflict_aware(ItemCreator, [ItemCreator.creator_id, ItemCreator.role], primary.id, duplicate.id)
        self._move_conflict_aware(SeriesItem, [SeriesItem.series_id], primary.id, duplicate.id)
        self._move_conflict_aware(ItemTag, [ItemTag.tag_id], primary.id, duplicate.id)
        self._move_conflict_aware(SavedCollectionItem, [SavedCollectionItem.collection_id], primary.id, duplicate.id)

        # Preserve the duplicate's title as a searchable alias of the survivor.
        self.add_alias(primary, duplicate.title, source="merge")
        self.db.flush()
        self.db.delete(duplicate)
        return primary

    def _move_conflict_aware(self, model: Any, key_cols: list, primary_id: UUID, dup_id: UUID) -> None:
        dup_rows = self.db.execute(select(model).where(model.item_id == dup_id)).scalars().all()
        for row in dup_rows:
            conds = [model.item_id == primary_id]
            for col in key_cols:
                conds.append(col == getattr(row, col.key))
            collides = self.db.execute(select(model).where(and_(*conds))).first() is not None
            if collides:
                self.db.delete(row)
            else:
                row.item_id = primary_id
        self.db.flush()

    # --- reads for franchise / creator pages ---

    def list_series(self, media_type: MediaType, limit: int = 50, offset: int = 0) -> list[Series]:
        return (
            self.db.query(Series)
            .filter(Series.media_type == media_type)
            .order_by(Series.name.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_series(self, series_id: UUID, media_type: MediaType) -> Series | None:
        s = self.db.get(Series, series_id)
        if s is None or s.media_type != media_type:
            return None
        return s

    def series_items(self, series: Series) -> list[Item]:
        links = sorted(
            series.items,
            key=lambda si: (si.sequence if si.sequence is not None else 1e9, si.item.release_year or 0),
        )
        return [li.item for li in links]

    def get_creator(self, creator_id: UUID) -> Creator | None:
        return self.db.get(Creator, creator_id)

    def creator_items(self, creator_id: UUID, media_type: MediaType) -> list[Item]:
        return (
            self.db.query(Item)
            .join(ItemCreator, ItemCreator.item_id == Item.id)
            .filter(ItemCreator.creator_id == creator_id, Item.media_type == media_type)
            .order_by(Item.release_year.asc().nullslast())
            .all()
        )
