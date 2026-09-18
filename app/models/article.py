from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ArticleStatus(StrEnum):
    DISCOVERED = "discovered"
    DUPLICATE = "duplicate"
    PROCESSING = "processing"
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    PROCESSING_FAILED = "processing_failed"
    CONTENT_REVIEW_REQUIRED = "content_review_required"
    BLOCKED_SOURCE = "blocked_source"


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        CheckConstraint(
            "credibility_score BETWEEN 1 AND 10", name="credibility_score_range"
        ),
        Index("ix_articles_source_published", "source_id", "published_at"),
        Index("ix_articles_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[ArticleStatus] = mapped_column(
        Enum(
            ArticleStatus,
            name="article_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ArticleStatus.DISCOVERED,
        nullable=False,
    )
    credibility_score: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    extracted_facts: Mapped[dict[str, object] | None] = mapped_column(JSON)
    fact_confidence: Mapped[float | None] = mapped_column()
    source_similarity: Mapped[float | None] = mapped_column()

    source: Mapped["Source"] = relationship(back_populates="articles")  # noqa: F821
    generated_posts: Mapped[list["GeneratedPost"]] = relationship(  # noqa: F821
        back_populates="article", cascade="all, delete-orphan"
    )
