"""Add fact-based content and source policy fields.

Revision ID: 20260918_0003
Revises: 20260918_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260918_0003"
down_revision: str | None = "20260918_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

commercial_use_status = sa.Enum(
    "unknown", "allowed", "restricted", "prohibited", name="commercial_use_status"
)
rss_usage_status = sa.Enum("unknown", "allowed", "restricted", name="rss_usage_status")


def upgrade() -> None:
    bind = op.get_bind()
    commercial_use_status.create(bind, checkfirst=True)
    rss_usage_status.create(bind, checkfirst=True)

    op.add_column(
        "sources",
        sa.Column(
            "commercial_use_status",
            commercial_use_status,
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "sources",
        sa.Column(
            "rss_usage_status",
            rss_usage_status,
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column("sources", sa.Column("terms_url", sa.Text(), nullable=True))
    op.add_column("sources", sa.Column("notes", sa.Text(), nullable=True))

    op.add_column("articles", sa.Column("extracted_facts", sa.JSON(), nullable=True))
    op.add_column("articles", sa.Column("fact_confidence", sa.Float(), nullable=True))
    op.add_column("articles", sa.Column("source_similarity", sa.Float(), nullable=True))

    op.add_column(
        "generated_posts", sa.Column("source_similarity", sa.Float(), nullable=True)
    )
    op.add_column(
        "generated_posts",
        sa.Column("validation_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "generated_posts", sa.Column("unsupported_claims", sa.JSON(), nullable=True)
    )

    op.execute(
        "ALTER TYPE article_status ADD VALUE IF NOT EXISTS 'content_review_required'"
    )
    op.execute("ALTER TYPE article_status ADD VALUE IF NOT EXISTS 'blocked_source'")
    op.execute("ALTER TYPE post_status ADD VALUE IF NOT EXISTS 'review_required'")
    op.execute("ALTER TYPE post_category ADD VALUE IF NOT EXISTS 'transfer_rumor'")
    op.execute("ALTER TYPE post_category ADD VALUE IF NOT EXISTS 'official_transfer'")
    op.execute("ALTER TYPE post_category ADD VALUE IF NOT EXISTS 'disciplinary'")

    op.execute(
        sa.text(
            """
            UPDATE sources
            SET rss_usage_status = 'allowed',
                terms_url = CASE
                    WHEN lower(url) LIKE '%trthaber.com%'
                        THEN 'https://www.trthaber.com/sitene_ekle.html'
                    ELSE 'https://www.aspor.com.tr/rss-bilgi'
                END,
                notes = 'Resmi RSS mevcut; ticari yeniden yayın lisansı teyit edilmedi.'
            WHERE lower(url) LIKE '%trthaber.com%'
               OR lower(rss_url) LIKE '%trthaber.com%'
               OR lower(url) LIKE '%aspor.com.tr%'
               OR lower(rss_url) LIKE '%aspor.com.tr%'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE sources
            SET commercial_use_status = 'restricted',
                rss_usage_status = 'restricted',
                terms_url = CASE
                    WHEN lower(url) LIKE '%haberturk.com%'
                      OR lower(rss_url) LIKE '%haberturk.com%'
                        THEN 'https://www.haberturk.com/kullanim-kosullari'
                    WHEN lower(url) LIKE '%ntvspor.net%'
                      OR lower(rss_url) LIKE '%ntvspor.net%'
                        THEN 'https://www.ntvspor.net/kullanim-kosullari'
                    ELSE 'https://www.transfermarkt.com.tr/intern/anb'
                END,
                notes = 'Yazılı izin olmadan işlenmez.'
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
    op.drop_column("generated_posts", "unsupported_claims")
    op.drop_column("generated_posts", "validation_confidence")
    op.drop_column("generated_posts", "source_similarity")
    op.drop_column("articles", "source_similarity")
    op.drop_column("articles", "fact_confidence")
    op.drop_column("articles", "extracted_facts")
    op.drop_column("sources", "notes")
    op.drop_column("sources", "terms_url")
    op.drop_column("sources", "rss_usage_status")
    op.drop_column("sources", "commercial_use_status")
    rss_usage_status.drop(op.get_bind(), checkfirst=True)
    commercial_use_status.drop(op.get_bind(), checkfirst=True)
