from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.stores.amazon import AmazonAdapter
from app.integrations.stores.base import StoreAdapter, StoreProduct, StoreRateLimitError
from app.integrations.stores.mock import MockAmazonAdapter
from app.integrations.telegram.telegram_bot import (
    opportunity_keyboard,
    opportunity_x_share_url,
)
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.opportunity_post import OpportunityPost
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.product_listing import ProductListing
from app.models.store import DataSourceType
from app.services.deal_pipeline import DealPipeline
from app.services.opportunity_post_generator import OpportunityPostGenerator
from app.services.opportunity_scorer import OpportunityScorer
from app.services.telegram_service import TelegramService


def pipeline(
    session_factory: async_sessionmaker[AsyncSession],
    adapters: list[StoreAdapter],
    *,
    min_score: float = 75,
) -> DealPipeline:
    return DealPipeline(
        session_factory=session_factory,
        adapters=adapters,
        scorer=OpportunityScorer(),
        post_generator=OpportunityPostGenerator("#reklam"),
        notifier=None,
        min_score=min_score,
        active_categories=["SSD"],
    )


@pytest.mark.asyncio
async def test_mock_amazon_pipeline_history_scoring_cooldown_and_affiliate(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    deal_pipeline = pipeline(session_factory, [MockAmazonAdapter("example-21")])
    await deal_pipeline.run()
    await deal_pipeline.run()
    await deal_pipeline.run()
    await deal_pipeline.run()

    async with session_factory() as session:
        listing_count = await session.scalar(
            select(func.count()).select_from(ProductListing)
        )
        history_count = await session.scalar(
            select(func.count()).select_from(PriceHistory)
        )
        opportunity_count = await session.scalar(
            select(func.count()).select_from(Opportunity)
        )
        latest = await session.scalar(
            select(Opportunity).order_by(
                Opportunity.detected_at.desc(), Opportunity.id.desc()
            )
        )
        post = await session.scalar(
            select(OpportunityPost).where(OpportunityPost.opportunity_id == latest.id)
        )
        assert listing_count == 1
        assert history_count == 3
        assert opportunity_count == 2
        assert latest.opportunity_score >= 90
        assert "#reklam" in post.text
        assert "?tag=example-21" in post.text


class FailingAdapter(StoreAdapter):
    slug = "broken"
    name = "Broken"
    base_url = "https://example.com"
    adapter_type = "broken"
    data_source_type = DataSourceType.OTHER

    async def fetch_products(self) -> list[StoreProduct]:
        raise RuntimeError("isolated")

    async def get_product(self, external_id: str) -> StoreProduct | None:
        return None

    async def build_product_url(self, external_id: str) -> str:
        return self.base_url


@pytest.mark.asyncio
async def test_store_adapter_failure_isolation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    deal_pipeline = pipeline(session_factory, [FailingAdapter(), MockAmazonAdapter()])
    await deal_pipeline.run()
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Product)) == 1


@pytest.mark.asyncio
async def test_minimum_score_prevents_low_score_opportunity(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    deal_pipeline = pipeline(session_factory, [MockAmazonAdapter()], min_score=99)
    await deal_pipeline.run()
    await deal_pipeline.run()
    await deal_pipeline.run()
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Opportunity)) == 0


@pytest.mark.asyncio
async def test_expired_opportunity_when_listing_price_changes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    deal_pipeline = pipeline(session_factory, [MockAmazonAdapter()])
    await deal_pipeline.run()
    await deal_pipeline.run()
    await deal_pipeline.run()
    async with session_factory() as session:
        opportunity = await session.scalar(
            select(Opportunity).order_by(Opportunity.id.desc())
        )
        listing = await session.get(ProductListing, opportunity.product_listing_id)
        listing.current_price = Decimal("9000")
        await session.commit()
        post = await session.scalar(
            select(OpportunityPost).where(
                OpportunityPost.opportunity_id == opportunity.id
            )
        )
        post_id = post.id

    service = TelegramService(
        token="123456:TEST_TOKEN",
        chat_id=100,
        allowed_user_id=200,
        session_factory=session_factory,
        max_post_length=260,
    )
    reply_text = AsyncMock()
    update = SimpleNamespace(
        callback_query=SimpleNamespace(message=SimpleNamespace(reply_text=reply_text))
    )
    await service._approve_opportunity(update, post_id)
    assert "Fiyat değişti" in reply_text.await_args.args[0]
    async with session_factory() as session:
        loaded = await session.get(Opportunity, opportunity.id)
        assert loaded.status == OpportunityStatus.EXPIRED


@pytest.mark.asyncio
async def test_amazon_rate_limit_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if "auth/o2/token" in str(request.url):
            return httpx.Response(
                200, json={"access_token": "token", "expires_in": 3600}
            )
        return httpx.Response(429, headers={"Retry-After": "0"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr("app.integrations.stores.amazon.asyncio.sleep", AsyncMock())
    adapter = AmazonAdapter(
        credential_id="id",
        credential_secret="secret",
        partner_tag="tag-21",
        item_ids=["B012345678"],
        max_retries=2,
        requests_per_second=10,
        client=client,
    )
    with pytest.raises(StoreRateLimitError):
        await adapter.fetch_products()
    assert calls == 3
    await client.aclose()


def test_amazon_response_parser() -> None:
    products = AmazonAdapter._parse_items(
        [
            {
                "asin": "B012345678",
                "detailPageURL": "https://www.amazon.com.tr/dp/B012345678?tag=x",
                "itemInfo": {
                    "title": {"displayValue": "Samsung SSD"},
                    "byLineInfo": {"brand": {"displayValue": "Samsung"}},
                },
                "offersV2": {
                    "listings": [
                        {
                            "price": {"amount": 6999, "currency": "TRY"},
                            "availability": {"type": "Now"},
                        }
                    ]
                },
            }
        ]
    )
    assert products[0].current_price == Decimal("6999")
    assert products[0].stock_status == "in_stock"


def test_opportunity_keyboard_contains_all_actions() -> None:
    keyboard = opportunity_keyboard(7, product_url="https://example.com/product")
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == [
        "deal_approve:7",
        "deal_reject:7",
        "deal_edit:7",
        "deal_regenerate:7",
        "deal_show:7",
        "deal_history:7",
    ]


def test_non_affiliate_post_omits_disclosure() -> None:
    opportunity = SimpleNamespace(
        product=SimpleNamespace(canonical_name="Test SSD"),
        listing=SimpleNamespace(
            affiliate_url=None, product_url="https://example.com/product"
        ),
        store=SimpleNamespace(name="Test Store"),
        current_price=Decimal("1000"),
        previous_price=Decimal("1200"),
        average_30d=Decimal("1150"),
        low_90d=Decimal("900"),
        discount_from_30d=13.0,
        opportunity_score=82,
    )
    generated = OpportunityPostGenerator("#reklam").generate(opportunity)
    assert "#reklam" not in generated.text


def test_x_share_keeps_disclosure_and_does_not_duplicate_link() -> None:
    link = "https://example.com/affiliate"
    post = SimpleNamespace(
        text=("A" * 300) + f"\n\n#reklam\n\n🔗 {link}",
        final_text=None,
        opportunity=SimpleNamespace(
            listing=SimpleNamespace(affiliate_url=link, product_url=link)
        ),
    )
    query = parse_qs(urlparse(opportunity_x_share_url(post)).query)
    assert query["url"] == [link]
    assert "#reklam" in query["text"][0]
    assert link not in query["text"][0]
    assert len(query["text"][0]) + 1 + 23 <= 280


@pytest.mark.asyncio
async def test_regenerate_uses_saved_opportunity_and_versions_post(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    deal_pipeline = pipeline(session_factory, [MockAmazonAdapter()])
    await deal_pipeline.run()
    await deal_pipeline.run()
    await deal_pipeline.run()
    async with session_factory() as session:
        first_post = await session.scalar(select(OpportunityPost))
        post_id = first_post.id
        opportunity_id = first_post.opportunity_id

    service = TelegramService(
        token="123456:TEST_TOKEN",
        chat_id=100,
        allowed_user_id=200,
        session_factory=session_factory,
        max_post_length=260,
    )
    service.notify_opportunity_post = AsyncMock()
    reply_text = AsyncMock()
    update = SimpleNamespace(
        callback_query=SimpleNamespace(message=SimpleNamespace(reply_text=reply_text))
    )
    await service._regenerate_opportunity(update, post_id)
    async with session_factory() as session:
        versions = list(
            (
                await session.scalars(
                    select(OpportunityPost.version)
                    .where(OpportunityPost.opportunity_id == opportunity_id)
                    .order_by(OpportunityPost.version)
                )
            ).all()
        )
    assert versions == [1, 2]
    service.notify_opportunity_post.assert_awaited_once()
