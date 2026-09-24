from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import fmean

from app.models.price_history import PriceHistory


@dataclass(slots=True, frozen=True)
class OpportunityMetrics:
    current_price: Decimal
    previous_price: Decimal | None
    average_7d: Decimal | None
    average_30d: Decimal | None
    average_90d: Decimal | None
    low_30d: Decimal | None
    low_90d: Decimal | None
    historical_low: Decimal | None
    historical_high: Decimal | None
    advertised_discount: float | None
    real_discount_30d: float | None
    real_discount_90d: float | None
    price_drop_amount: Decimal | None
    price_drop_percent: float | None


class OpportunityDetector:
    @staticmethod
    def _discount(reference: Decimal | None, current: Decimal) -> float | None:
        if reference is None or reference <= 0:
            return None
        return max(0.0, float((reference - current) / reference * 100))

    @staticmethod
    def _average(values: list[Decimal]) -> Decimal | None:
        if not values:
            return None
        return Decimal(str(round(fmean(float(value) for value in values), 2)))

    def analyze(
        self,
        *,
        current_price: Decimal,
        previous_price: Decimal | None,
        original_price: Decimal | None,
        history: list[PriceHistory],
        now: datetime | None = None,
    ) -> OpportunityMetrics:
        now = now or datetime.now(UTC)

        def prices(days: int | None) -> list[Decimal]:
            if days is None:
                return [row.price for row in history]
            cutoff = now - timedelta(days=days)
            return [
                row.price for row in history if self._aware(row.captured_at) >= cutoff
            ]

        prices_7d = prices(7)
        prices_30d = prices(30)
        prices_90d = prices(90)
        all_prices = prices(None)
        average_7d = self._average(prices_7d)
        average_30d = self._average(prices_30d)
        average_90d = self._average(prices_90d)
        price_drop = (
            max(Decimal("0"), previous_price - current_price)
            if previous_price is not None
            else None
        )
        return OpportunityMetrics(
            current_price=current_price,
            previous_price=previous_price,
            average_7d=average_7d,
            average_30d=average_30d,
            average_90d=average_90d,
            low_30d=min(prices_30d) if prices_30d else None,
            low_90d=min(prices_90d) if prices_90d else None,
            historical_low=min(all_prices) if all_prices else None,
            historical_high=max(all_prices) if all_prices else None,
            advertised_discount=self._discount(original_price, current_price),
            real_discount_30d=self._discount(average_30d, current_price),
            real_discount_90d=self._discount(average_90d, current_price),
            price_drop_amount=price_drop,
            price_drop_percent=self._discount(previous_price, current_price),
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)
