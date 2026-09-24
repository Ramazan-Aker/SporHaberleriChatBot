from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product_listing import ProductListing


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_listing_captured", "product_listing_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_listing_id: Mapped[int] = mapped_column(
        ForeignKey("product_listings.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    stock_status: Mapped[str] = mapped_column(String(50), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    listing: Mapped[ProductListing] = relationship(back_populates="price_history")
