from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.opportunity import Opportunity
    from app.models.product_listing import ProductListing
    from app.models.product_watch import ProductWatch


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_identifiers", "gtin", "ean", "upc", "mpn"),
        Index("ix_products_brand_model", "brand", "model"),
        Index("ix_products_normalized_key", "normalized_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(1000), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    sub_category: Mapped[str | None] = mapped_column(String(100))
    gtin: Mapped[str | None] = mapped_column(String(32))
    ean: Mapped[str | None] = mapped_column(String(32))
    upc: Mapped[str | None] = mapped_column(String(32))
    mpn: Mapped[str | None] = mapped_column(String(200))
    normalized_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    popularity_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    listings: Mapped[list[ProductListing]] = relationship(back_populates="product")
    opportunities: Mapped[list[Opportunity]] = relationship(back_populates="product")
    watches: Mapped[list[ProductWatch]] = relationship(back_populates="product")
