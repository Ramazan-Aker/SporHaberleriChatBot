from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.api.routes import articles, commerce, health, posts, sources
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.integrations.ai.factory import create_ai_client
from app.integrations.stores import (
    AmazonAdapter,
    HepsiburadaAdapter,
    MockAmazonAdapter,
    StoreAdapter,
    TrendyolAdapter,
)
from app.jobs.deal_job import DealJob
from app.services.deal_pipeline import DealPipeline
from app.services.opportunity_ai_polisher import OpportunityAIPolisher
from app.services.opportunity_post_generator import OpportunityPostGenerator
from app.services.opportunity_scorer import OpportunityScorer, ScoreWeights
from app.services.telegram_service import TelegramService

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)


def build_store_adapters() -> list[StoreAdapter]:
    adapters: list[StoreAdapter] = []
    if settings.enable_amazon:
        if settings.use_mock_store_data:
            adapters.append(MockAmazonAdapter(settings.amazon_partner_tag))
        else:
            if settings.amazon_access_key or settings.amazon_secret_key:
                logger.warning(
                    "amazon_legacy_credentials_ignored",
                    store="amazon-tr",
                    operation="adapter_config",
                    error="PA-API credentials are deprecated; configure Creators API OAuth credentials",
                )
            adapters.append(
                AmazonAdapter(
                    credential_id=settings.amazon_credential_id or "",
                    credential_secret=settings.amazon_credential_secret or "",
                    partner_tag=settings.amazon_partner_tag or "",
                    marketplace=settings.amazon_marketplace,
                    item_ids=settings.amazon_item_ids,
                    search_keywords=settings.amazon_keywords,
                    timeout_seconds=settings.http_timeout_seconds,
                    max_retries=settings.external_api_max_retries,
                    requests_per_second=settings.amazon_requests_per_second,
                )
            )
    if settings.enable_trendyol:
        adapters.append(TrendyolAdapter())
    if settings.enable_hepsiburada:
        adapters.append(HepsiburadaAdapter())
    return adapters


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    telegram: TelegramService | None = None
    scheduler: AsyncIOScheduler | None = None
    deal_pipeline: DealPipeline | None = None

    if settings.telegram_enabled:
        telegram = TelegramService(
            token=settings.telegram_bot_token or "",
            chat_id=settings.telegram_chat_id or 0,
            allowed_user_id=settings.telegram_allowed_user_id or 0,
            session_factory=SessionLocal,
            max_post_length=settings.max_post_length,
            max_source_similarity=settings.max_source_similarity,
            content_workflow=None,
            affiliate_disclosure=settings.affiliate_disclosure,
        )
        await telegram.start()

    if settings.scheduler_enabled:
        scheduler = AsyncIOScheduler(timezone="UTC")

    if settings.scheduler_enabled:
        assert scheduler is not None
        adapters = build_store_adapters()
        if telegram:
            telegram.set_store_adapters(adapters)
        if adapters:
            deal_pipeline = DealPipeline(
                session_factory=SessionLocal,
                adapters=adapters,
                scorer=OpportunityScorer(
                    ScoreWeights(
                        price_drop=settings.score_price_drop_weight,
                        historical_low=settings.score_historical_low_weight,
                        popularity=settings.score_popularity_weight,
                        seller=settings.score_seller_weight,
                        stock=settings.score_stock_weight,
                        savings=settings.score_savings_weight,
                    )
                ),
                post_generator=OpportunityPostGenerator(settings.affiliate_disclosure),
                notifier=telegram,
                min_score=settings.min_opportunity_score,
                cooldown_hours=settings.opportunity_cooldown_hours,
                snapshot_hours=settings.price_snapshot_interval_hours,
                active_categories=settings.product_categories,
                ai_polisher=(
                    OpportunityAIPolisher(create_ai_client(settings))
                    if settings.enable_ai_post_polish
                    else None
                ),
            )
            scheduler.add_job(
                DealJob(deal_pipeline).run,
                "interval",
                minutes=settings.price_check_interval_minutes,
                id="fetch_prices",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=60,
                next_run_time=datetime.now(UTC),
            )
        scheduler.start()
        logger.info(
            "scheduler_started",
            operation="scheduler_start",
            store_count=len(adapters),
        )

    app.state.telegram = telegram
    app.state.scheduler = scheduler
    app.state.deal_pipeline = deal_pipeline
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        if deal_pipeline:
            await deal_pipeline.close()
        if telegram:
            await telegram.stop()


app = FastAPI(
    title="Türkiye Fiyat / Fırsat Radarı",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(commerce.router)
# The legacy tables remain queryable, but no sports/RSS collection job is started.
app.include_router(articles.router)
app.include_router(sources.router)
app.include_router(posts.router)
