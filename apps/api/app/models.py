from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MediaType(str, enum.Enum):
    movie = "movie"
    tv = "tv"
    book = "book"
    audiobook = "audiobook"
    comic = "comic"
    game = "game"


class InteractionType(str, enum.Enum):
    rate = "rate"
    pass_ = "pass"
    save = "save"
    consume = "consume"
    finish = "finish"
    dismiss = "dismiss"


class InteractionSource(str, enum.Enum):
    manual = "manual"
    import_ = "import"
    recommendation_flow = "recommendation_flow"


class InteractionContext(str, enum.Enum):
    onboarding = "onboarding"
    browse = "browse"
    recommendation_feed = "recommendation_feed"
    import_sync = "import_sync"


class ImportJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    enabled_media_types: Mapped[list] = mapped_column(
        JSONB, default=lambda: ["movie", "tv", "audiobook", "comic"]
    )
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    interactions: Mapped[list[UserInteraction]] = relationship(back_populates="user")
    import_sources: Mapped[list[ImportSource]] = relationship(back_populates="user")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type"), index=True)
    title: Mapped[str] = mapped_column(String(512), index=True)
    sort_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    series: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    franchise: Mapped[str | None] = mapped_column(String(512), nullable=True)
    genres: Mapped[list] = mapped_column(JSONB, default=list)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    creators: Mapped[list] = mapped_column(JSONB, default=list)
    release_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_or_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    maturity_flags: Mapped[list] = mapped_column(JSONB, default=list)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    popularity: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    is_anchor: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    extensions: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    external_refs: Mapped[list[ItemExternalRef]] = relationship(back_populates="item")


class ItemExternalRef(Base):
    __tablename__ = "item_external_refs"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external_id"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    item_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped[Item] = relationship(back_populates="external_refs")


class UserInteraction(Base):
    __tablename__ = "user_interactions"
    __table_args__ = (
        Index("ix_interactions_user_item_type", "user_id", "item_id", "interaction_type"),
        Index("ix_interactions_user_ts", "user_id", "timestamp"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    item_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"))
    interaction_type: Mapped[InteractionType] = mapped_column(
        Enum(
            InteractionType,
            name="interaction_type",
            values_callable=lambda x: [e.value for e in x],
        ),
        index=True,
    )
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[InteractionSource] = mapped_column(
        Enum(
            InteractionSource,
            name="interaction_source",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=InteractionSource.manual,
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    context: Mapped[InteractionContext | None] = mapped_column(
        Enum(
            InteractionContext,
            name="interaction_context",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="interactions")
    item: Mapped[Item] = relationship()


class RecommendationList(Base):
    __tablename__ = "recommendation_lists"
    __table_args__ = (UniqueConstraint("user_id", "feed_key", name="uq_user_feed"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    feed_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    item_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"))
    list_id: Mapped[Any | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recommendation_lists.id", ondelete="SET NULL"), nullable=True
    )
    feed_key: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)
    factors: Mapped[dict] = mapped_column(JSONB, default=dict)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(32), nullable=True)
    served_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImportSource(Base):
    __tablename__ = "import_sources"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="import_sources")
    jobs: Mapped[list[ImportJob]] = relationship(back_populates="import_source")


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    import_source_id: Mapped[Any] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_sources.id", ondelete="CASCADE")
    )
    status: Mapped[ImportJobStatus] = mapped_column(
        Enum(ImportJobStatus, name="import_job_status"), default=ImportJobStatus.pending
    )
    cursor: Mapped[dict] = mapped_column(JSONB, default=dict)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    import_source: Mapped[ImportSource] = relationship(back_populates="jobs")


class EmbeddingVector(Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "model", name="uq_embedding_entity_model"),
    )

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), index=True)
    model: Mapped[str] = mapped_column(String(128))
    # 768 dims suits nomic-embed-text; adjust when swapping models
    embedding: Mapped[Any] = mapped_column(Vector(768), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SimilarityEdge(Base):
    __tablename__ = "similarity_edges"
    __table_args__ = (UniqueConstraint("item_a_id", "item_b_id", "kind", name="uq_sim_edge"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    item_a_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"))
    item_b_id: Mapped[Any] = mapped_column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32), default="content")
    score: Mapped[float] = mapped_column(Float)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class ModelConfig(Base):
    __tablename__ = "model_configs"
    __table_args__ = (UniqueConstraint("media_type", "name", name="uq_model_media_name"),)

    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type", create_type=False))
    name: Mapped[str] = mapped_column(String(64), default="default")
    weights: Mapped[dict] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
