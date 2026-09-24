from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.opportunity_post import OpportunityPost
    from app.models.product import Product
    from app.models.product_listing import ProductListing
    from app.models.store import Store


class OpportunityStatus(StrEnum):
    DETECTED = "detected"
    READY = "ready"
    TELEGRAM_SENT = "telegram_sent"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    PUBLISHED = "published"
    REVIEW_REQUIRED = "review_required"


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opportunities_status_detected", "status", "detected_at"),
        Index("ix_opportunities_listing_detected", "product_listing_id", "detected_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    product_listing_id: Mapped[int] = mapped_column(
        ForeignKey("product_listings.id", ondelete="RESTRICT"), nullable=False
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    current_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    previous_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    average_7d: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    average_30d: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    average_90d: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    low_30d: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    low_90d: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    historical_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    historical_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    advertised_discount: Mapped[float | None] = mapped_column(Float)
    discount_from_30d: Mapped[float | None] = mapped_column(Float)
    discount_from_90d: Mapped[float | None] = mapped_column(Float)
    price_drop_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_drop_percent: Mapped[float | None] = mapped_column(Float)
    opportunity_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(
            OpportunityStatus,
            name="opportunity_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        default=OpportunityStatus.DETECTED,
        nullable=False,
    )
    duplicate_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped[Product] = relationship(back_populates="opportunities")
    listing: Mapped[ProductListing] = relationship(back_populates="opportunities")
    store: Mapped[Store] = relationship()
    posts: Mapped[list[OpportunityPost]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
