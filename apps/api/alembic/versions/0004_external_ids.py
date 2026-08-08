"""External source links per item (Phase 3): IMDb / Rotten Tomatoes / Metacritic / etc."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_external_ids"
down_revision: Union[str, None] = "0003_interest_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    media_type = postgresql.ENUM(
        "movie", "tv", "book", "audiobook", "comic", "game", name="media_type", create_type=False
    )

    op.create_table(
        "external_ids",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_type", media_type, nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_key", sa.String(255)),
        sa.Column("external_url", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0"),
        sa.Column("resolution_method", sa.String(16), server_default="search"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("item_id", "provider", name="uq_external_id_item_provider"),
    )
    op.create_index("ix_external_ids_media_type", "external_ids", ["media_type"])
    op.create_index("ix_external_ids_provider", "external_ids", ["provider"])


def downgrade() -> None:
    op.drop_table("external_ids")
