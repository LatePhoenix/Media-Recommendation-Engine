"""Add items.normalized_title for indexed dedup lookups."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_normalized_title"
down_revision: Union[str, None] = "0006_user_is_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("items", sa.Column("normalized_title", sa.String(512), nullable=True))
    op.create_index("ix_items_media_normalized_title", "items", ["media_type", "normalized_title"])


def downgrade() -> None:
    op.drop_index("ix_items_media_normalized_title", table_name="items")
    op.drop_column("items", "normalized_title")
