import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.stores.mock import MockAmazonAdapter
from app.services.deal_pipeline import DealPipeline
from app.services.opportunity_post_generator import OpportunityPostGenerator
from app.services.opportunity_scorer import OpportunityScorer


@pytest.mark.asyncio
async def test_commerce_endpoints_and_filters(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    pipeline = DealPipeline(
        session_factory=session_factory,
        adapters=[MockAmazonAdapter()],
        scorer=OpportunityScorer(),
        post_generator=OpportunityPostGenerator(),
        notifier=None,
        min_score=75,
        active_categories=["SSD"],
    )
    await pipeline.run()
    await pipeline.run()

    stores = await api_client.get("/stores")
    products = await api_client.get("/products?category=SSD&store=amazon-tr")
    listings = await api_client.get("/listings?store=amazon-tr")
    opportunities = await api_client.get("/opportunities?min_score=75&status=ready")

    assert stores.status_code == 200
    assert stores.json()[0]["data_source_type"] == "manual"
    assert products.status_code == 200 and len(products.json()) == 1
    assert listings.status_code == 200 and len(listings.json()) == 1
    assert opportunities.status_code == 200 and len(opportunities.json()) == 1

    product_id = products.json()[0]["id"]
    opportunity_id = opportunities.json()[0]["id"]
    assert (await api_client.get(f"/products/{product_id}")).status_code == 200
    prices = await api_client.get(f"/products/{product_id}/prices")
    assert prices.status_code == 200 and len(prices.json()) == 2
    assert (await api_client.get(f"/opportunities/{opportunity_id}")).status_code == 200
