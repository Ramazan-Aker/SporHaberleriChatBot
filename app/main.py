from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.api.routes import articles, health, posts, sources
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import configure_logging
from app.integrations.ai.openai_client import OpenAIClient
from app.integrations.rss.rss_client import RSSClient
from app.jobs.news_job import NewsJob
from app.services.content_generator import ContentGenerator
from app.services.news_collector import NewsCollector
from app.services.telegram_service import TelegramService

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    telegram: TelegramService | None = None
    rss_client: RSSClient | None = None
    scheduler: AsyncIOScheduler | None = None

    if settings.telegram_enabled:
        telegram = TelegramService(
            token=settings.telegram_bot_token or "",
            chat_id=settings.telegram_chat_id or 0,
            allowed_user_id=settings.telegram_allowed_user_id or 0,
            session_factory=SessionLocal,
            max_post_length=settings.max_post_length,
        )
        await telegram.start()

    if settings.scheduler_enabled:
        rss_client = RSSClient(timeout_seconds=settings.http_timeout_seconds)
        ai_client = OpenAIClient(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model or "",
            timeout_seconds=settings.http_timeout_seconds,
        )
        collector = NewsCollector(
            session_factory=SessionLocal,
            rss_client=rss_client,
            content_generator=ContentGenerator(
                ai_client,
                max_length=settings.max_post_length,
                max_attempts=settings.external_api_max_retries,
            ),
            notifier=telegram,
            initial_lookback_hours=settings.news_initial_lookback_hours,
        )
        job = NewsJob(collector)
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            job.run,
            "interval",
            minutes=settings.news_fetch_interval_minutes,
            id="fetch_news",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
            next_run_time=datetime.now(UTC),
        )
        scheduler.start()
        logger.info("scheduler_started", operation="scheduler_start")

    app.state.telegram = telegram
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        if rss_client:
            await rss_client.close()
        if telegram:
            await telegram.stop()


app = FastAPI(
    title="Spor Haberleri İçerik Sistemi",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(health.router)
app.include_router(articles.router)
app.include_router(sources.router)
app.include_router(posts.router)
