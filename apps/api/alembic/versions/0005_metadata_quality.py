"""Metadata quality layer (Phase 4): canonical creators, series, aliases, tags."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_metadata_quality"
down_revision: Union[str, None] = "0004_external_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    media_type = postgresql.ENUM(
        "movie", "tv", "book", "audiobook", "comic", "game", name="media_type", create_type=False
    )

    op.create_table(
        "creators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("normalized_name", name="uq_creator_normalized"),
    )
    op.create_index("ix_creators_normalized_name", "creators", ["normalized_name"])

    op.create_table(
        "item_creators",
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("creator_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("creators.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(32), primary_key=True, server_default=""),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
    )

    op.create_table(
        "series",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_type", media_type, nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("normalized_name", sa.String(512), nullable=False),
        sa.Column("franchise", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("media_type", "normalized_name", name="uq_series_media_normalized"),
    )
    op.create_index("ix_series_media_type", "series", ["media_type"])
    op.create_index("ix_series_normalized_name", "series", ["normalized_name"])

    op.create_table(
        "series_items",
        sa.Column("series_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("sequence", sa.Float()),
    )

    op.create_table(
        "item_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(512), nullable=False),
        sa.Column("normalized_alias", sa.String(512), nullable=False),
        sa.Column("source", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("item_id", "normalized_alias", name="uq_item_alias"),
    )
    op.create_index("ix_item_aliases_normalized_alias", "item_aliases", ["normalized_alias"])

    op.create_table(
        "canonical_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("category", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("slug", name="uq_canonical_tag_slug"),
    )
    op.create_index("ix_canonical_tags_slug", "canonical_tags", ["slug"])

    op.create_table(
        "item_tags",
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("canonical_tags.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("weight", sa.Float()),
    )


def downgrade() -> None:
    op.drop_table("item_tags")
    op.drop_table("canonical_tags")
    op.drop_table("item_aliases")
    op.drop_table("series_items")
    op.drop_table("series")
    op.drop_table("item_creators")
    op.drop_table("creators")
