from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.article import Article


class PostStatus(StrEnum):
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"


class PostCategory(StrEnum):
    BREAKING_NEWS = "breaking_news"
    TRANSFER = "transfer"
    MATCH_RESULT = "match_result"
    INJURY = "injury"
    LINEUP = "lineup"
    STATISTICS = "statistics"
    STATEMENT = "statement"
    GENERAL = "general"


class GeneratedPost(Base):
    __tablename__ = "generated_posts"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "version", name="uq_generated_posts_article_version"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    final_text: Mapped[str | None] = mapped_column(Text)
    ai_model: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[PostStatus] = mapped_column(
        Enum(
            PostStatus,
            name="post_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=PostStatus.READY,
        nullable=False,
        index=True,
    )
    category: Mapped[PostCategory] = mapped_column(
        Enum(
            PostCategory,
            name="post_category",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    telegram_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_error: Mapped[str | None] = mapped_column(Text)
    notification_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    next_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    article: Mapped[Article] = relationship(back_populates="generated_posts")
