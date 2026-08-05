from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.auth import RATING_LABEL_TO_VALUE
from app.models import (
    InteractionContext,
    InteractionSource,
    InteractionType,
    Item,
    MediaType,
    User,
    UserInteraction,
)
from workers.importers.catalog_utils import parse_year, upsert_item
from workers.importers.base import NormalizedItem


def import_csv_rows(db: Session, user: User, rows: list[dict[str, Any]]) -> dict[str, int]:
    items_upserted = 0
    ratings_written = 0
    for i, row in enumerate(rows):
        title = (row.get("title") or "").strip()
        if not title:
            continue
        media_type = (row.get("media_type") or "movie").strip().lower()
        if media_type not in MediaType.__members__:
            media_type = "movie"
        genres = row.get("genres") or []
        if isinstance(genres, str):
            genres = [g.strip() for g in genres.split("|") if g.strip()]
        creators = row.get("creators") or []
        if isinstance(creators, str):
            creators = [c.strip() for c in creators.split("|") if c.strip()]
        norm = NormalizedItem(
            external_id=f"csv:{media_type}:{title}:{row.get('year') or i}",
            media_type=media_type,
            title=title,
            genres=list(genres),
            creators=list(creators),
            release_year=parse_year(row.get("year") or row.get("release_year")),
            description=row.get("description"),
            raw=row,
        )
        item = upsert_item(db, "csv", norm)
        items_upserted += 1
        label = row.get("rating_label")
        if label and label in RATING_LABEL_TO_VALUE:
            db.add(
                UserInteraction(
                    user_id=user.id,
                    item_id=item.id,
                    interaction_type=InteractionType.rate,
                    value=RATING_LABEL_TO_VALUE[label],
                    source=InteractionSource.import_,
                    context=InteractionContext.import_sync,
                    confidence=1.0,
                    meta={"csv": True},
                )
            )
            ratings_written += 1
    return {"items_upserted": items_upserted, "ratings_written": ratings_written}
