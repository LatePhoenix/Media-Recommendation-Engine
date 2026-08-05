from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import (
    ImportJobStatus,
    InteractionContext,
    InteractionSource,
    InteractionType,
    MediaType,
)


# --- Auth ---


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    username: str
    enabled_media_types: list[str]
    preferences: dict[str, Any]
    onboarding_complete: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserPrefsUpdate(BaseModel):
    enabled_media_types: list[str] | None = None
    preferences: dict[str, Any] | None = None
    onboarding_complete: bool | None = None


# --- Catalog ---


class ItemOut(BaseModel):
    id: UUID
    media_type: MediaType
    title: str
    sort_title: str | None = None
    series: str | None = None
    genres: list[Any] = []
    tags: list[Any] = []
    creators: list[Any] = []
    release_year: int | None = None
    description: str | None = None
    cover_url: str | None = None
    popularity: float = 0.0
    is_anchor: bool = False

    model_config = {"from_attributes": True}


class ItemSearchParams(BaseModel):
    q: str | None = None
    media_type: MediaType | None = None
    limit: int = 40
    offset: int = 0


# --- Interactions ---


class InteractionCreate(BaseModel):
    item_id: UUID
    interaction_type: InteractionType
    value: float | None = None
    rating_label: str | None = None
    source: InteractionSource = InteractionSource.manual
    confidence: float = 1.0
    context: InteractionContext | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("rating_label")
    @classmethod
    def _known_rating_label(cls, v: str | None) -> str | None:
        # Reject unknown labels at validation time (HTTP 422) rather than letting
        # them raise a ValueError deep in the handler (HTTP 500).
        if v is None:
            return v
        from app.auth import RATING_LABEL_TO_VALUE  # lazy import avoids import cycle

        if v not in RATING_LABEL_TO_VALUE:
            raise ValueError(
                f"Unknown rating_label {v!r}; valid values: {sorted(RATING_LABEL_TO_VALUE)}"
            )
        return v


class InteractionBatchCreate(BaseModel):
    interactions: list[InteractionCreate] = Field(min_length=1, max_length=500)


class InteractionOut(BaseModel):
    id: UUID
    user_id: UUID
    item_id: UUID
    interaction_type: InteractionType
    value: float | None
    source: InteractionSource
    confidence: float
    context: InteractionContext | None
    timestamp: datetime

    model_config = {"from_attributes": True}


# --- Onboarding ---


class OnboardingStatus(BaseModel):
    complete: bool
    ratings_by_media_type: dict[str, int]
    min_ratings: int
    ready_media_types: list[str]


# --- Recommendations ---


class RecommendationCard(BaseModel):
    event_id: UUID
    item: ItemOut
    score: float
    rank: int
    feed_key: str
    factors: dict[str, Any]
    explanation: str | None = None


class RecommendationFeedOut(BaseModel):
    feed_key: str
    title: str
    items: list[RecommendationCard]
    generated_at: datetime


class RecommendationAction(BaseModel):
    event_id: UUID
    action: str  # rate | save | pass | consume | finish | dismiss
    value: float | None = None
    rating_label: str | None = None


# --- Imports ---


class ImportSourceCreate(BaseModel):
    source: str
    display_name: str
    base_url: str | None = None
    credentials: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class ImportSourceOut(BaseModel):
    id: UUID
    source: str
    display_name: str
    base_url: str | None
    config: dict[str, Any]
    last_sync_at: datetime | None
    last_status: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportJobOut(BaseModel):
    id: UUID
    import_source_id: UUID
    status: ImportJobStatus
    stats: dict[str, Any]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CsvImportPayload(BaseModel):
    """Manual CSV-like rows: title,media_type,year,genres,creators,rating_label"""

    rows: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
