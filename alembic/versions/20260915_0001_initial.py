"""Create sources, articles and generated posts.

Revision ID: 20260915_0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260915_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

source_type = sa.Enum(
    "official", "journalist", "news", "statistics", name="source_type"
)
article_status = sa.Enum(
    "discovered",
    "duplicate",
    "processing",
    "ready",
    "approved",
    "rejected",
    "published",
    "processing_failed",
    name="article_status",
)
post_status = sa.Enum("ready", "approved", "rejected", name="post_status")
post_category = sa.Enum(
    "breaking_news",
    "transfer",
    "match_result",
    "injury",
    "lineup",
    "statistics",
    "statement",
    "general",
    name="post_category",
)


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("rss_url", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("credibility_score", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("etag", sa.String(length=500), nullable=True),
        sa.Column("last_modified", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "credibility_score BETWEEN 1 AND 10",
            name="credibility_score_range",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("rss_url", name="uq_sources_rss_url"),
    )
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", article_status, nullable=False),
        sa.Column("credibility_score", sa.Integer(), nullable=False),
        sa.Column("processing_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "credibility_score BETWEEN 1 AND 10",
            name="credibility_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_articles_source_id_sources",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_articles"),
        sa.UniqueConstraint("content_hash", name="uq_articles_content_hash"),
        sa.UniqueConstraint("url", name="uq_articles_url"),
    )
    op.create_index(
        "ix_articles_source_published", "articles", ["source_id", "published_at"]
    )
    op.create_index("ix_articles_status", "articles", ["status"])
    op.create_table(
        "generated_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("ai_model", sa.String(length=200), nullable=False),
        sa.Column("status", post_status, nullable=False),
        sa.Column("category", post_category, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("edited_by_user", sa.Boolean(), nullable=False),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("telegram_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_error", sa.Text(), nullable=True),
        sa.Column("notification_attempts", sa.Integer(), nullable=False),
        sa.Column("next_notification_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["articles.id"],
            name="fk_generated_posts_article_id_articles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generated_posts"),
        sa.UniqueConstraint(
            "article_id", "version", name="uq_generated_posts_article_version"
        ),
    )
    op.create_index("ix_generated_posts_article_id", "generated_posts", ["article_id"])
    op.create_index("ix_generated_posts_status", "generated_posts", ["status"])


def downgrade() -> None:
    op.drop_table("generated_posts")
    op.drop_table("articles")
    op.drop_table("sources")
    post_category.drop(op.get_bind())
    post_status.drop(op.get_bind())
    article_status.drop(op.get_bind())
    source_type.drop(op.get_bind())
