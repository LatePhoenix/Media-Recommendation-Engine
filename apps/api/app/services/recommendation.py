"""RecommendationService — thin wrapper over the deterministic engine, scoped per domain."""

from __future__ import annotations

from app.models import MediaType, User
from app.recommender.engine import generate_feed, get_weights
from sqlalchemy.orm import Session


class RecommendationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def feed(
        self,
        user: User,
        media_type: MediaType,
        feed_key: str,
        limit: int = 20,
        config_name: str | None = None,
    ):
        return generate_feed(self.db, user, media_type, feed_key, limit=limit, config_name=config_name)

    def weights(self, media_type: MediaType, config_name: str | None = None) -> dict[str, float]:
        return get_weights(self.db, media_type, config_name)

    @staticmethod
    def default_media_type(user: User) -> MediaType:
        """First enabled domain — used by the deprecated media-agnostic routes."""
        for m in user.enabled_media_types or []:
            if m in MediaType.__members__:
                return MediaType(m)
        return MediaType.movie
