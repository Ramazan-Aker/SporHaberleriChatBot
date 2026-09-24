from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity
    from app.models.price_history import PriceHistory
    from app.models.product import Product
    from app.models.store import Store


class ProductListing(TimestampMixin, Base):
    __tablename__ = "product_listings"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "external_product_id", name="uq_listing_store_external"
        ),
        Index("ix_product_listings_product_store", "product_id", "store_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    external_product_id: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    affiliate_url: Mapped[str | None] = mapped_column(Text)
    seller_name: Mapped[str | None] = mapped_column(String(300))
    seller_score: Mapped[float | None] = mapped_column(Float)
    current_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="TRY", nullable=False)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    discount_percent: Mapped[float | None] = mapped_column(Float)
    stock_status: Mapped[str] = mapped_column(
        String(50), default="unknown", nullable=False
    )
    shipping_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped[Product] = relationship(back_populates="listings")
    store: Mapped[Store] = relationship(back_populates="listings")
    price_history: Mapped[list[PriceHistory]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )
    opportunities: Mapped[list[Opportunity]] = relationship(back_populates="listing")
