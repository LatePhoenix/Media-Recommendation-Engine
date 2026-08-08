"""InterestService — durable per-user intent (Phase 2).

The scoring-relevant math lives in module-level pure functions
(:func:`build_interest_signals`) so it can be unit-tested without a database, in
keeping with the DB-free test suite. The :class:`InterestService` class holds the
SQLAlchemy read/write logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InterestSource,
    Item,
    ItemState,
    MediaType,
    SavedCollection,
    SavedCollectionItem,
    UserItemState,
    UserItemStateHistory,
)

# How strongly each "positive" state reinforces the item's genres/tags/creators in
# the user profile. Deterministic and inspectable; passed/hidden are handled
# structurally (suppression / exclusion) rather than as content boosts.
STATE_CONTENT_BOOST: dict[ItemState, float] = {
    ItemState.interested: 0.2,
    ItemState.shortlisted: 0.5,
    ItemState.completed: 0.5,
}

# States that should mildly suppress re-recommending the same item (the user has
# already engaged with it) without banning it — it still shows on saved pages.
SOFT_SEEN_STATES = {ItemState.interested, ItemState.shortlisted}

VALID_SAVED_SORTS = ("recently_added", "priority", "release_date", "score")


@dataclass(frozen=True)
class InterestRecord:
    """Minimal, DB-free view of a state row used by the pure signal builder."""

    state: ItemState
    item_id: UUID
    genres: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    creators: tuple[str, ...] = ()
    updated_at: datetime | None = None


@dataclass
class InterestSignals:
    genre_boosts: dict[str, float] = field(default_factory=dict)
    tag_boosts: dict[str, float] = field(default_factory=dict)
    creator_boosts: dict[str, float] = field(default_factory=dict)
    affinity_genres: set[str] = field(default_factory=set)
    affinity_creators: set[str] = field(default_factory=set)
    hidden_ids: set[UUID] = field(default_factory=set)
    completed_ids: set[UUID] = field(default_factory=set)
    soft_seen_ids: set[UUID] = field(default_factory=set)
    passed: dict[UUID, datetime] = field(default_factory=dict)


def build_interest_signals(records: Iterable[InterestRecord]) -> InterestSignals:
    """Fold interest-state rows into ranking signals. Pure function, no DB."""
    sig = InterestSignals()
    for r in records:
        if r.state == ItemState.hidden:
            sig.hidden_ids.add(r.item_id)
            continue
        if r.state == ItemState.passed:
            if r.updated_at is not None:
                sig.passed[r.item_id] = r.updated_at
            continue
        if r.state == ItemState.completed:
            sig.completed_ids.add(r.item_id)
        if r.state in SOFT_SEEN_STATES:
            sig.soft_seen_ids.add(r.item_id)

        boost = STATE_CONTENT_BOOST.get(r.state)
        if boost:
            for g in r.genres:
                sig.genre_boosts[g] = sig.genre_boosts.get(g, 0.0) + boost
            for t in r.tags:
                sig.tag_boosts[t] = sig.tag_boosts.get(t, 0.0) + boost
            for c in r.creators:
                sig.creator_boosts[c] = sig.creator_boosts.get(c, 0.0) + boost
        # Shortlisted + interested items define the "saved affinity" surface used
        # to bump structurally similar candidates (saved-item expansion).
        if r.state in (ItemState.shortlisted, ItemState.interested):
            sig.affinity_genres.update(r.genres)
            sig.affinity_creators.update(r.creators)
    return sig


def saved_affinity(
    item_genres: Iterable[str],
    item_creators: Iterable[str],
    affinity_genres: set[str],
    affinity_creators: set[str],
) -> float:
    """Overlap of a candidate with the user's saved-affinity surface, in [0, 1]."""
    genres = set(item_genres or [])
    creators = set(item_creators or [])
    if not affinity_genres and not affinity_creators:
        return 0.0
    g = len(genres & affinity_genres) / max(len(affinity_genres), 1)
    c = len(creators & affinity_creators) / max(len(affinity_creators), 1)
    return min(1.0, 0.7 * g + 0.3 * c)


class InterestService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # --- state ---

    def get_state(self, user_id: UUID, item_id: UUID) -> UserItemState | None:
        return (
            self.db.query(UserItemState)
            .filter(UserItemState.user_id == user_id, UserItemState.item_id == item_id)
            .first()
        )

    def set_state(
        self,
        user_id: UUID,
        item: Item,
        state: ItemState,
        *,
        source: InterestSource = InterestSource.manual,
        notes: str | None = None,
        priority: int | None = None,
        reason: str | None = None,
    ) -> UserItemState:
        """Upsert the current-state row and append a history entry."""
        row = self.get_state(user_id, item.id)
        old_state = row.state if row else None
        if row is None:
            row = UserItemState(
                id=uuid4(),
                user_id=user_id,
                item_id=item.id,
                media_type=item.media_type,
                state=state,
                source=source,
                notes=notes,
                priority=priority,
            )
            self.db.add(row)
        else:
            row.state = state
            row.source = source
            if notes is not None:
                row.notes = notes
            if priority is not None:
                row.priority = priority
        self.db.add(
            UserItemStateHistory(
                id=uuid4(),
                user_id=user_id,
                item_id=item.id,
                media_type=item.media_type,
                old_state=old_state,
                new_state=state,
                reason=reason,
            )
        )
        return row

    def clear_state(
        self, user_id: UUID, item_id: UUID, *, reason: str | None = "cleared"
    ) -> bool:
        row = self.get_state(user_id, item_id)
        if row is None:
            return False
        self.db.add(
            UserItemStateHistory(
                id=uuid4(),
                user_id=user_id,
                item_id=item_id,
                media_type=row.media_type,
                old_state=row.state,
                new_state=None,
                reason=reason,
            )
        )
        self.db.delete(row)
        return True

    def list_states(
        self,
        user_id: UUID,
        media_type: MediaType,
        *,
        states: list[ItemState] | None = None,
        sort: str = "recently_added",
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserItemState]:
        q = (
            self.db.query(UserItemState)
            .join(Item, Item.id == UserItemState.item_id)
            .filter(
                UserItemState.user_id == user_id,
                UserItemState.media_type == media_type,
            )
        )
        if states:
            q = q.filter(UserItemState.state.in_(states))
        q = q.order_by(*self._sort_clause(sort))
        return q.offset(offset).limit(limit).all()

    @staticmethod
    def _sort_clause(sort: str) -> tuple[Any, ...]:
        if sort not in VALID_SAVED_SORTS:
            sort = "recently_added"
        if sort == "priority":
            # Higher priority first; NULLs last via a coalesced key.
            return (UserItemState.priority.desc().nullslast(), UserItemState.updated_at.desc())
        if sort == "release_date":
            return (Item.release_year.desc().nullslast(), UserItemState.updated_at.desc())
        if sort == "score":
            # Deterministic proxy for "quality" without a live scoring pass.
            return (Item.popularity.desc(), UserItemState.updated_at.desc())
        return (UserItemState.updated_at.desc(),)

    def load_signals(self, user_id: UUID, media_type: MediaType) -> InterestSignals:
        """Query state rows for a domain and fold them into ranking signals."""
        rows = (
            self.db.execute(
                select(UserItemState, Item)
                .join(Item, Item.id == UserItemState.item_id)
                .where(
                    UserItemState.user_id == user_id,
                    UserItemState.media_type == media_type,
                )
            )
            .all()
        )
        records = [
            InterestRecord(
                state=st.state,
                item_id=st.item_id,
                genres=tuple(str(g) for g in (item.genres or [])),
                tags=tuple(str(t) for t in (item.tags or [])),
                creators=tuple(str(c) for c in (item.creators or [])),
                updated_at=st.updated_at,
            )
            for st, item in rows
        ]
        return build_interest_signals(records)

    # --- collections ---

    def list_collections(self, user_id: UUID, media_type: MediaType) -> list[SavedCollection]:
        return (
            self.db.query(SavedCollection)
            .filter(
                SavedCollection.user_id == user_id,
                SavedCollection.media_type == media_type,
            )
            .order_by(SavedCollection.is_default.desc(), SavedCollection.name.asc())
            .all()
        )

    def create_collection(
        self,
        user_id: UUID,
        media_type: MediaType,
        name: str,
        *,
        description: str | None = None,
        is_default: bool = False,
    ) -> SavedCollection:
        col = SavedCollection(
            id=uuid4(),
            user_id=user_id,
            media_type=media_type,
            name=name,
            description=description,
            is_default=is_default,
        )
        self.db.add(col)
        return col

    def get_collection(self, user_id: UUID, collection_id: UUID) -> SavedCollection | None:
        col = self.db.get(SavedCollection, collection_id)
        if col is None or col.user_id != user_id:
            return None
        return col

    def add_to_collection(
        self, collection: SavedCollection, item_id: UUID, *, sort_order: int = 0
    ) -> SavedCollectionItem:
        existing = self.db.get(SavedCollectionItem, {"collection_id": collection.id, "item_id": item_id})
        if existing is not None:
            existing.sort_order = sort_order
            return existing
        link = SavedCollectionItem(
            collection_id=collection.id, item_id=item_id, sort_order=sort_order
        )
        self.db.add(link)
        return link

    def remove_from_collection(self, collection: SavedCollection, item_id: UUID) -> bool:
        existing = self.db.get(SavedCollectionItem, {"collection_id": collection.id, "item_id": item_id})
        if existing is None:
            return False
        self.db.delete(existing)
        return True
