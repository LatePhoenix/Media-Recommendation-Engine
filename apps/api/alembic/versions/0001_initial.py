"""Initial schema for hybrid media recommender."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    media_type = postgresql.ENUM(
        "movie", "tv", "book", "audiobook", "comic", "game", name="media_type", create_type=False
    )
    media_type.create(op.get_bind(), checkfirst=True)

    interaction_type = postgresql.ENUM(
        "rate", "pass", "save", "consume", "finish", "dismiss",
        name="interaction_type",
        create_type=False,
    )
    interaction_type.create(op.get_bind(), checkfirst=True)

    interaction_source = postgresql.ENUM(
        "manual", "import", "recommendation_flow", name="interaction_source", create_type=False
    )
    interaction_source.create(op.get_bind(), checkfirst=True)

    interaction_context = postgresql.ENUM(
        "onboarding", "browse", "recommendation_feed", "import_sync",
        name="interaction_context",
        create_type=False,
    )
    interaction_context.create(op.get_bind(), checkfirst=True)

    import_job_status = postgresql.ENUM(
        "pending", "running", "succeeded", "failed", name="import_job_status", create_type=False
    )
    import_job_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("enabled_media_types", postgresql.JSONB(), nullable=False, server_default=sa.text("'[\"movie\",\"tv\",\"audiobook\",\"comic\"]'::jsonb")),
        sa.Column("preferences", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("onboarding_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_type", media_type, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("sort_title", sa.String(512)),
        sa.Column("series", sa.String(512)),
        sa.Column("franchise", sa.String(512)),
        sa.Column("genres", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("tags", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("creators", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("release_year", sa.Integer()),
        sa.Column("description", sa.Text()),
        sa.Column("runtime_or_length", sa.Integer()),
        sa.Column("language", sa.String(32)),
        sa.Column("maturity_flags", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("cover_url", sa.Text()),
        sa.Column("popularity", sa.Float(), server_default="0"),
        sa.Column("is_anchor", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("extensions", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_items_media_type", "items", ["media_type"])
    op.create_index("ix_items_title", "items", ["title"])
    op.create_index("ix_items_series", "items", ["series"])
    op.create_index("ix_items_release_year", "items", ["release_year"])
    op.create_index("ix_items_popularity", "items", ["popularity"])
    op.create_index("ix_items_is_anchor", "items", ["is_anchor"])

    op.create_table(
        "item_external_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("external_url", sa.Text()),
        sa.Column("raw", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("source", "external_id", name="uq_source_external_id"),
    )
    op.create_index("ix_item_external_refs_source", "item_external_refs", ["source"])

    op.create_table(
        "user_interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("interaction_type", interaction_type, nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("source", interaction_source, nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1"),
        sa.Column("context", interaction_context),
        sa.Column("meta", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_user_interactions_interaction_type", "user_interactions", ["interaction_type"])
    op.create_index("ix_interactions_user_item_type", "user_interactions", ["user_id", "item_id", "interaction_type"])
    op.create_index("ix_interactions_user_ts", "user_interactions", ["user_id", "timestamp"])

    op.create_table(
        "recommendation_lists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("feed_key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("meta", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "feed_key", name="uq_user_feed"),
    )

    op.create_table(
        "recommendation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("list_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recommendation_lists.id", ondelete="SET NULL")),
        sa.Column("feed_key", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("factors", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("explanation", sa.Text()),
        sa.Column("action_taken", sa.String(32)),
        sa.Column("served_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_recommendation_events_feed_key", "recommendation_events", ["feed_key"])

    op.create_table(
        "import_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("base_url", sa.Text()),
        sa.Column("credentials_encrypted", sa.Text()),
        sa.Column("config", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_status", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_import_sources_source", "import_sources", ["source"])

    op.create_table(
        "import_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_sources.id", ondelete="CASCADE")),
        sa.Column("status", import_job_status, nullable=False),
        sa.Column("cursor", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("stats", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("embedding", Vector(768)),
        sa.Column("meta", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("entity_type", "entity_id", "model", name="uq_embedding_entity_model"),
    )
    op.create_index("ix_embeddings_entity_type", "embeddings", ["entity_type"])
    op.create_index("ix_embeddings_entity_id", "embeddings", ["entity_id"])

    op.create_table(
        "similarity_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_a_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("item_b_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(32), server_default="content"),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("item_a_id", "item_b_id", "kind", name="uq_sim_edge"),
    )

    op.create_table(
        "model_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_type", media_type, nullable=False),
        sa.Column("name", sa.String(64), server_default="default"),
        sa.Column("weights", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("media_type", "name", name="uq_model_media_name"),
    )


def downgrade() -> None:
    op.drop_table("model_configs")
    op.drop_table("similarity_edges")
    op.drop_table("embeddings")
    op.drop_table("import_jobs")
    op.drop_table("import_sources")
    op.drop_table("recommendation_events")
    op.drop_table("recommendation_lists")
    op.drop_table("user_interactions")
    op.drop_table("item_external_refs")
    op.drop_table("items")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS import_job_status")
    op.execute("DROP TYPE IF EXISTS interaction_context")
    op.execute("DROP TYPE IF EXISTS interaction_source")
    op.execute("DROP TYPE IF EXISTS interaction_type")
    op.execute("DROP TYPE IF EXISTS media_type")
