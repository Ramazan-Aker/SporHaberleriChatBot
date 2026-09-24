"""Add store-independent price and opportunity radar tables.

Revision ID: 20260924_0004
Revises: 20260918_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0004"
down_revision: str | None = "20260918_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

store_data_source_type = sa.Enum(
    "official_api",
    "affiliate_api",
    "feed",
    "manual",
    "other",
    name="store_data_source_type",
)
opportunity_status = sa.Enum(
    "detected",
    "ready",
    "telegram_sent",
    "approved",
    "rejected",
    "expired",
    "published",
    "review_required",
    name="opportunity_status",
)
opportunity_post_status = sa.Enum(
    "ready", "approved", "rejected", name="opportunity_post_status"
)


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("adapter_type", sa.String(length=100), nullable=False),
        sa.Column("affiliate_enabled", sa.Boolean(), nullable=False),
        sa.Column("data_source_type", store_data_source_type, nullable=False),
        sa.Column("terms_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_stores"),
        sa.UniqueConstraint("slug", name="uq_stores_slug"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_name", sa.String(length=1000), nullable=False),
        sa.Column("brand", sa.String(length=200), nullable=True),
        sa.Column("model", sa.String(length=300), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("sub_category", sa.String(length=100), nullable=True),
        sa.Column("gtin", sa.String(length=32), nullable=True),
        sa.Column("ean", sa.String(length=32), nullable=True),
        sa.Column("upc", sa.String(length=32), nullable=True),
        sa.Column("mpn", sa.String(length=200), nullable=True),
        sa.Column("normalized_key", sa.String(length=1000), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("popularity_score", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_products"),
    )
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index(
        "ix_products_identifiers", "products", ["gtin", "ean", "upc", "mpn"]
    )
    op.create_index("ix_products_brand_model", "products", ["brand", "model"])
    op.create_index("ix_products_normalized_key", "products", ["normalized_key"])
    op.create_table(
        "product_listings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("external_product_id", sa.String(length=300), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("product_url", sa.Text(), nullable=False),
        sa.Column("affiliate_url", sa.Text(), nullable=True),
        sa.Column("seller_name", sa.String(length=300), nullable=True),
        sa.Column("seller_score", sa.Float(), nullable=True),
        sa.Column("current_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("original_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("discount_percent", sa.Float(), nullable=True),
        sa.Column("stock_status", sa.String(length=50), nullable=False),
        sa.Column("shipping_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_listings_product_id_products",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name="fk_product_listings_store_id_stores",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_listings"),
        sa.UniqueConstraint(
            "store_id", "external_product_id", name="uq_listing_store_external"
        ),
    )
    op.create_index(
        "ix_product_listings_product_store",
        "product_listings",
        ["product_id", "store_id"],
    )
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_listing_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("original_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("stock_status", sa.String(length=50), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["product_listing_id"],
            ["product_listings.id"],
            name="fk_price_history_product_listing_id_product_listings",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_price_history"),
    )
    op.create_index(
        "ix_price_history_listing_captured",
        "price_history",
        ["product_listing_id", "captured_at"],
    )
    op.create_table(
        "product_watches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("target_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_product_watches_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_product_watches"),
        sa.UniqueConstraint("product_id", name="uq_product_watches_product_id"),
    )
    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_listing_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("current_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("previous_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("average_7d", sa.Numeric(14, 2), nullable=True),
        sa.Column("average_30d", sa.Numeric(14, 2), nullable=True),
        sa.Column("average_90d", sa.Numeric(14, 2), nullable=True),
        sa.Column("low_30d", sa.Numeric(14, 2), nullable=True),
        sa.Column("low_90d", sa.Numeric(14, 2), nullable=True),
        sa.Column("historical_low", sa.Numeric(14, 2), nullable=True),
        sa.Column("historical_high", sa.Numeric(14, 2), nullable=True),
        sa.Column("advertised_discount", sa.Float(), nullable=True),
        sa.Column("discount_from_30d", sa.Float(), nullable=True),
        sa.Column("discount_from_90d", sa.Float(), nullable=True),
        sa.Column("price_drop_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_drop_percent", sa.Float(), nullable=True),
        sa.Column("opportunity_score", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", opportunity_status, nullable=False),
        sa.Column("duplicate_key", sa.String(length=200), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_opportunities_product_id_products",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_listing_id"],
            ["product_listings.id"],
            name="fk_opportunities_product_listing_id_product_listings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name="fk_opportunities_store_id_stores",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_opportunities"),
        sa.UniqueConstraint("duplicate_key", name="uq_opportunities_duplicate_key"),
    )
    op.create_index(
        "ix_opportunities_status_detected", "opportunities", ["status", "detected_at"]
    )
    op.create_index(
        "ix_opportunities_listing_detected",
        "opportunities",
        ["product_listing_id", "detected_at"],
    )
    op.create_table(
        "opportunity_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("template_name", sa.String(length=100), nullable=False),
        sa.Column("status", opportunity_post_status, nullable=False),
        sa.Column("edited_by_user", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("telegram_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_error", sa.Text(), nullable=True),
        sa.Column("notification_attempts", sa.Integer(), nullable=False),
        sa.Column("next_notification_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name="fk_opportunity_posts_opportunity_id_opportunities",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_opportunity_posts"),
        sa.UniqueConstraint(
            "opportunity_id", "version", name="uq_opportunity_posts_version"
        ),
    )
    op.create_index(
        "ix_opportunity_posts_opportunity_id", "opportunity_posts", ["opportunity_id"]
    )


def downgrade() -> None:
    op.drop_table("opportunity_posts")
    op.drop_table("opportunities")
    op.drop_table("product_watches")
    op.drop_table("price_history")
    op.drop_table("product_listings")
    op.drop_table("products")
    op.drop_table("stores")
    opportunity_post_status.drop(op.get_bind(), checkfirst=True)
    opportunity_status.drop(op.get_bind(), checkfirst=True)
    store_data_source_type.drop(op.get_bind(), checkfirst=True)
