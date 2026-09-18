from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.article import Article


class SourceType(StrEnum):
    OFFICIAL = "official"
    JOURNALIST = "journalist"
    NEWS = "news"
    STATISTICS = "statistics"


class CommercialUseStatus(StrEnum):
    UNKNOWN = "unknown"
    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    PROHIBITED = "prohibited"


class RSSUsageStatus(StrEnum):
    UNKNOWN = "unknown"
    ALLOWED = "allowed"
    RESTRICTED = "restricted"


class Source(TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "credibility_score BETWEEN 1 AND 10", name="credibility_score_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    rss_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(
            SourceType,
            name="source_type",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    credibility_score: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    commercial_use_status: Mapped[CommercialUseStatus] = mapped_column(
        Enum(
            CommercialUseStatus,
            name="commercial_use_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=CommercialUseStatus.UNKNOWN,
        nullable=False,
    )
    rss_usage_status: Mapped[RSSUsageStatus] = mapped_column(
        Enum(
            RSSUsageStatus,
            name="rss_usage_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=RSSUsageStatus.UNKNOWN,
        nullable=False,
    )
    terms_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    etag: Mapped[str | None] = mapped_column(String(500))
    last_modified: Mapped[str | None] = mapped_column(String(500))

    articles: Mapped[list[Article]] = relationship(back_populates="source")
