from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_history import PriceHistory
from app.models.product_listing import ProductListing


@dataclass(slots=True, frozen=True)
class PriceTrackResult:
    history_created: bool
    price_changed: bool
    stock_changed: bool
    previous_price: Decimal | None


class PriceTracker:
    def __init__(self, session: AsyncSession, snapshot_hours: int = 24) -> None:
        self.session = session
        self.snapshot_interval = timedelta(hours=snapshot_hours)

    async def record(
        self,
        listing: ProductListing,
        *,
        price: Decimal,
        original_price: Decimal | None,
        currency: str,
        stock_status: str,
        captured_at: datetime | None = None,
    ) -> PriceTrackResult:
        captured_at = captured_at or datetime.now(UTC)
        previous = await self.session.scalar(
            select(PriceHistory)
            .where(PriceHistory.product_listing_id == listing.id)
            .order_by(PriceHistory.captured_at.desc(), PriceHistory.id.desc())
            .limit(1)
        )
        price_changed = bool(previous and previous.price != price)
        stock_changed = bool(previous and previous.stock_status != stock_status)
        periodic_snapshot = bool(
            previous
            and captured_at - self._aware(previous.captured_at)
            >= self.snapshot_interval
        )
        should_create = (
            previous is None or price_changed or stock_changed or periodic_snapshot
        )
        listing.current_price = price
        listing.original_price = original_price
        listing.currency = currency
        listing.stock_status = stock_status
        listing.last_seen_at = captured_at
        if should_create:
            self.session.add(
                PriceHistory(
                    product_listing_id=listing.id,
                    price=price,
                    original_price=original_price,
                    currency=currency,
                    stock_status=stock_status,
                    captured_at=captured_at,
                )
            )
            await self.session.flush()
        return PriceTrackResult(
            history_created=should_create,
            price_changed=price_changed,
            stock_changed=stock_changed,
            previous_price=previous.price if previous else None,
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)
