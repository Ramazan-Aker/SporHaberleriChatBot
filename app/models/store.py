from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product_listing import ProductListing


class DataSourceType(StrEnum):
    OFFICIAL_API = "official_api"
    AFFILIATE_API = "affiliate_api"
    FEED = "feed"
    MANUAL = "manual"
    OTHER = "other"


class Store(TimestampMixin, Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(100), nullable=False)
    affiliate_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    data_source_type: Mapped[DataSourceType] = mapped_column(
        Enum(
            DataSourceType,
            name="store_data_source_type",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    terms_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    listings: Mapped[list[ProductListing]] = relationship(back_populates="store")
