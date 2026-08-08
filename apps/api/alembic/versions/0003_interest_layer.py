"""Persistent interest layer: item states, state history, and saved collections."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_interest_layer"
down_revision: Union[str, None] = "0002_user_token_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    item_state = postgresql.ENUM(
        "interested",
        "shortlisted",
        "in_progress",
        "completed",
        "passed",
        "hidden",
        name="item_state",
        create_type=False,
    )
    item_state.create(op.get_bind(), checkfirst=True)

    interest_source = postgresql.ENUM(
        "manual", "imported", "inferred", name="interest_source", create_type=False
    )
    interest_source.create(op.get_bind(), checkfirst=True)

    # Reference the pre-existing media_type enum without trying to recreate it.
    media_type = postgresql.ENUM(
        "movie", "tv", "book", "audiobook", "comic", "game", name="media_type", create_type=False
    )

    op.create_table(
        "user_item_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_type", media_type, nullable=False),
        sa.Column("state", item_state, nullable=False),
        sa.Column("source", interest_source, nullable=False, server_default="manual"),
        sa.Column("notes", sa.Text()),
        sa.Column("priority", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "item_id", name="uq_user_item_state"),
    )
    op.create_index("ix_user_item_state_media_type", "user_item_state", ["media_type"])
    op.create_index(
        "ix_user_item_state_user_media_state",
        "user_item_state",
        ["user_id", "media_type", "state"],
    )

    op.create_table(
        "user_item_state_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_type", media_type, nullable=False),
        sa.Column("old_state", item_state),
        sa.Column("new_state", item_state),
        sa.Column("reason", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_user_item_state_history_user_item",
        "user_item_state_history",
        ["user_id", "item_id"],
    )

    op.create_table(
        "saved_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_type", media_type, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "media_type", "name", name="uq_collection_user_media_name"),
    )
    op.create_index("ix_saved_collections_media_type", "saved_collections", ["media_type"])

    op.create_table(
        "saved_collection_items",
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("saved_collections.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("saved_collection_items")
    op.drop_table("saved_collections")
    op.drop_table("user_item_state_history")
    op.drop_table("user_item_state")
    op.execute("DROP TYPE IF EXISTS interest_source")
    op.execute("DROP TYPE IF EXISTS item_state")
