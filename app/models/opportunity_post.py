from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
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
    from app.models.opportunity import Opportunity


class OpportunityPostStatus(StrEnum):
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"


class OpportunityPost(Base):
    __tablename__ = "opportunity_posts"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "version", name="uq_opportunity_posts_version"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    final_text: Mapped[str | None] = mapped_column(Text)
    template_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[OpportunityPostStatus] = mapped_column(
        Enum(
            OpportunityPostStatus,
            name="opportunity_post_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        default=OpportunityPostStatus.READY,
        nullable=False,
    )
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    telegram_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telegram_error: Mapped[str | None] = mapped_column(Text)
    notification_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    next_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="posts")
