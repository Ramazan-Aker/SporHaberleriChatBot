"""Deactivate sources that require written reuse permission.

Revision ID: 20260918_0002
Revises: 20260915_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260918_0002"
down_revision: str | None = "20260915_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE sources
            SET active = false
            WHERE lower(url) LIKE '%haberturk.com%'
               OR lower(rss_url) LIKE '%haberturk.com%'
               OR lower(url) LIKE '%ntvspor.net%'
               OR lower(rss_url) LIKE '%ntvspor.net%'
               OR lower(url) LIKE '%transfermarkt.com.tr%'
               OR lower(rss_url) LIKE '%transfermarkt.com.tr%'
            """
        )
    )


def downgrade() -> None:
    # Previous active state cannot be reconstructed safely.
    pass
