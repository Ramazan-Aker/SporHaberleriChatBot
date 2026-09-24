from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.product import Product


class ProductWatch(Base):
    __tablename__ = "product_watches"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_product_watches_product_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="watches")
