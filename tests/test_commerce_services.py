from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.stores.base import StoreProduct
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.product_listing import ProductListing
from app.models.store import DataSourceType, Store
from app.services.opportunity_detector import OpportunityDetector
from app.services.opportunity_scorer import OpportunityScorer
from app.services.price_tracker import PriceTracker
from app.services.product_matcher import ProductMatcher
from app.services.product_normalizer import ProductNormalizer


def item(**overrides) -> StoreProduct:
    values = {
        "external_product_id": "ssd-1",
        "title": "Samsung 990 PRO 2 TB NVMe M.2 SSD",
        "current_price": Decimal("6999"),
        "brand": "Samsung",
        "model": "990 PRO",
        "category": "SSD",
        "stock_status": "in_stock",
    }
    values.update(overrides)
    return StoreProduct(**values)


def test_product_normalization_standardizes_units_and_seller_words() -> None:
    normalizer = ProductNormalizer()
    first = normalizer.normalize(item())
    second = normalizer.normalize(
        item(title="Samsung 990 Pro NVMe 2TB - Amazon Mağaza")
    )
    assert "2tb" in first.normalized_title
    assert "amazon" not in second.normalized_title
    assert first.normalized_key == second.normalized_key


@pytest.mark.asyncio
async def test_ean_and_brand_model_matching(session: AsyncSession) -> None:
    product = Product(
        canonical_name="Samsung SSD",
        brand="samsung",
        model="990 pro",
        category="SSD",
        ean="8806094413748",
        normalized_key="ean:8806094413748",
    )
    session.add(product)
    await session.flush()
    matcher = ProductMatcher(session)

    ean_match = await matcher.match(
        ProductNormalizer().normalize(item(ean="8806094413748"))
    )
    model_match = await matcher.match(ProductNormalizer().normalize(item()))

    assert ean_match.product_id == product.id
    assert ean_match.method == "ean"
    assert model_match.product_id == product.id
    assert model_match.method == "brand_model"


@pytest.mark.asyncio
async def test_product_mismatch_prevention_marks_low_confidence_review(
    session: AsyncSession,
) -> None:
    session.add(
        Product(
            canonical_name="Samsung 990 PRO 1TB",
            brand="samsung",
            model=None,
            category="SSD",
            normalized_key="samsung 990 pro 1tb",
        )
    )
    await session.flush()
    candidate = ProductNormalizer().normalize(
        item(title="Samsung 990 PRO 2TB", model=None)
    )
    match = await ProductMatcher(session).match(candidate)
    assert not match.matched
    assert match.manual_review_required


async def create_listing(session: AsyncSession) -> ProductListing:
    store = Store(
        name="Test",
        slug="test",
        base_url="https://example.com",
        active=True,
        adapter_type="test",
        affiliate_enabled=False,
        data_source_type=DataSourceType.MANUAL,
    )
    product = Product(
        canonical_name="Test Product",
        normalized_key="test product",
        category="SSD",
    )
    session.add_all([store, product])
    await session.flush()
    listing = ProductListing(
        product_id=product.id,
        store_id=store.id,
        external_product_id="x1",
        title="Test Product",
        product_url="https://example.com/x1",
        current_price=Decimal("100"),
        currency="TRY",
        stock_status="in_stock",
        last_seen_at=datetime.now(UTC),
    )
    session.add(listing)
    await session.flush()
    return listing


@pytest.mark.asyncio
async def test_price_history_change_and_same_price_suppression(
    session: AsyncSession,
) -> None:
    listing = await create_listing(session)
    tracker = PriceTracker(session, snapshot_hours=24)
    now = datetime.now(UTC)
    first = await tracker.record(
        listing,
        price=Decimal("100"),
        original_price=None,
        currency="TRY",
        stock_status="in_stock",
        captured_at=now,
    )
    same = await tracker.record(
        listing,
        price=Decimal("100"),
        original_price=None,
        currency="TRY",
        stock_status="in_stock",
        captured_at=now + timedelta(hours=1),
    )
    changed = await tracker.record(
        listing,
        price=Decimal("80"),
        original_price=None,
        currency="TRY",
        stock_status="in_stock",
        captured_at=now + timedelta(hours=2),
    )
    rows = list((await session.scalars(select(PriceHistory))).all())
    assert first.history_created
    assert not same.history_created
    assert changed.price_changed
    assert len(rows) == 2


def history(price: str, days_ago: int) -> PriceHistory:
    return PriceHistory(
        product_listing_id=1,
        price=Decimal(price),
        original_price=None,
        currency="TRY",
        stock_status="in_stock",
        captured_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


def test_averages_lows_and_real_discount() -> None:
    metrics = OpportunityDetector().analyze(
        current_price=Decimal("70"),
        previous_price=Decimal("90"),
        original_price=Decimal("100"),
        history=[history("80", 2), history("100", 20), history("120", 60)],
    )
    assert metrics.average_7d == Decimal("80.0")
    assert metrics.average_30d == Decimal("90.0")
    assert metrics.average_90d == Decimal("100.0")
    assert metrics.low_30d == Decimal("80")
    assert metrics.historical_low == Decimal("80")
    assert round(metrics.real_discount_30d or 0, 2) == 22.22


def test_fake_advertised_discount_does_not_inflate_real_discount() -> None:
    metrics = OpportunityDetector().analyze(
        current_price=Decimal("7000"),
        previous_price=Decimal("7200"),
        original_price=Decimal("10000"),
        history=[history("7200", 2), history("7200", 10)],
    )
    assert metrics.advertised_discount == 30
    assert round(metrics.real_discount_30d or 0, 1) == 2.8
    score = OpportunityScorer().score(
        metrics, popularity=0.1, seller_quality=0.5, stock_status="in_stock"
    )
    assert score.price_drop < 5


def test_opportunity_score_reaches_threshold_for_real_drop() -> None:
    metrics = OpportunityDetector().analyze(
        current_price=Decimal("6999"),
        previous_price=Decimal("7999"),
        original_price=Decimal("9999"),
        history=[history("8499", 2), history("7999", 1)],
    )
    score = OpportunityScorer().score(
        metrics, popularity=0.95, seller_quality=0.98, stock_status="in_stock"
    )
    assert score.total >= 90
