from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.opportunity_detector import OpportunityMetrics


@dataclass(slots=True, frozen=True)
class ScoreWeights:
    price_drop: float = 30
    historical_low: float = 25
    popularity: float = 15
    seller: float = 15
    stock: float = 10
    savings: float = 5


@dataclass(slots=True, frozen=True)
class OpportunityScore:
    total: float
    price_drop: float
    historical_low: float
    popularity: float
    seller: float
    stock: float
    savings: float


class OpportunityScorer:
    def __init__(self, weights: ScoreWeights | None = None) -> None:
        self.weights = weights or ScoreWeights()

    def score(
        self,
        metrics: OpportunityMetrics,
        *,
        popularity: float,
        seller_quality: float | None,
        stock_status: str,
    ) -> OpportunityScore:
        real_drop = metrics.real_discount_30d
        if real_drop is None:
            real_drop = metrics.price_drop_percent or 0
        price_points = min(max(real_drop, 0) / 20, 1) * self.weights.price_drop

        low_points = 0.0
        if metrics.historical_low and metrics.historical_low > 0:
            distance = max(
                0.0,
                float(
                    (metrics.current_price - metrics.historical_low)
                    / metrics.historical_low
                    * 100
                ),
            )
            low_points = max(0.0, 1 - distance / 10) * self.weights.historical_low

        popularity_points = min(max(popularity, 0), 1) * self.weights.popularity
        seller_points = min(max(seller_quality or 0.5, 0), 1) * self.weights.seller
        stock_points = self.weights.stock if stock_status.lower() == "in_stock" else 0.0
        savings = metrics.price_drop_amount or Decimal("0")
        savings_points = min(max(float(savings), 0) / 1000, 1) * self.weights.savings
        total = min(
            100.0,
            price_points
            + low_points
            + popularity_points
            + seller_points
            + stock_points
            + savings_points,
        )
        return OpportunityScore(
            total=round(total, 2),
            price_drop=round(price_points, 2),
            historical_low=round(low_points, 2),
            popularity=round(popularity_points, 2),
            seller=round(seller_points, 2),
            stock=round(stock_points, 2),
            savings=round(savings_points, 2),
        )
