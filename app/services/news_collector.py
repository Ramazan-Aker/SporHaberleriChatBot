from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.rss.rss_client import FeedEntry, RSSClient
from app.models.article import ArticleStatus
from app.repositories.article_repository import ArticleRepository
from app.repositories.post_repository import PostRepository
from app.repositories.source_repository import SourceRepository
from app.services.content_generator import ContentGenerator, ContentInput
from app.services.content_workflow import ContentWorkflow
from app.services.credibility_service import CredibilityService
from app.services.duplicate_detector import DuplicateDetector, make_content_hash
from app.services.quality_service import is_live_match_update, is_quality_article
from app.services.source_usage_policy import source_policy_blocks_processing

logger = structlog.get_logger(__name__)


class PostNotifier(Protocol):
    async def notify_post(self, post_id: int) -> None: ...

    async def retry_pending(self) -> None: ...


class NewsCollector:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        rss_client: RSSClient,
        content_generator: ContentGenerator,
        content_workflow: ContentWorkflow | None = None,
        notifier: PostNotifier | None,
        initial_lookback_hours: int = 24,
        only_current_day: bool = True,
        news_timezone: str = "Europe/Istanbul",
        enforce_source_usage_policy: bool = True,
        failed_retry_limit: int = 5,
        max_processing_attempts: int = 3,
    ) -> None:
        self.session_factory = session_factory
        self.rss_client = rss_client
        self.content_generator = content_generator
        self.content_workflow = content_workflow
        self.notifier = notifier
        self.initial_lookback = timedelta(hours=initial_lookback_hours)
        self.only_current_day = only_current_day
        self.news_timezone = ZoneInfo(news_timezone)
        self.enforce_source_usage_policy = enforce_source_usage_policy
        self.failed_retry_limit = failed_retry_limit
        self.max_processing_attempts = max_processing_attempts
        self.credibility = CredibilityService()

    def _is_current_news_day(self, published_at: datetime | None) -> bool:
        if published_at is None:
            return True
        local_published = published_at.astimezone(self.news_timezone).date()
        local_today = datetime.now(self.news_timezone).date()
        return local_published == local_today

    async def fetch_news(self) -> None:
        if self.notifier:
            await self.notifier.retry_pending()
        await self._retry_failed_articles()
        async with self.session_factory() as session:
            source_ids = [
                source.id
                for source in await SourceRepository(session).list(active_only=True)
            ]
        for source_id in source_ids:
            try:
                await self._collect_source(source_id)
            except Exception as error:
                logger.exception(
                    "source_collection_failed",
                    source=source_id,
                    operation="fetch_rss",
                    error=f"{type(error).__name__}: {error}",
                )

    async def _retry_failed_articles(self) -> None:
        if self.failed_retry_limit == 0:
            return
        async with self.session_factory() as session:
            articles = await ArticleRepository(session).list_processing_failed(
                limit=self.failed_retry_limit,
                max_attempts=self.max_processing_attempts,
            )
            retry_items = [
                (
                    article.id,
                    article.source_id,
                    ContentInput(
                        title=article.title,
                        description=article.description,
                        source_name=article.source.name,
                        url=article.url,
                        published_at=article.published_at,
                        credibility_score=article.credibility_score,
                    ),
                )
                for article in articles
                if not is_live_match_update(article.title)
                and not (
                    self.enforce_source_usage_policy
                    and source_policy_blocks_processing(
                        article.source.commercial_use_status,
                        article.source.rss_usage_status,
                    )
                )
                and (
                    not self.only_current_day
                    or self._is_current_news_day(article.published_at)
                )
            ]
            blocked_article_ids: list[int] = []
            for article in articles:
                policy_blocked = (
                    self.enforce_source_usage_policy
                    and source_policy_blocks_processing(
                        article.source.commercial_use_status,
                        article.source.rss_usage_status,
                    )
                )
                if policy_blocked:
                    article.status = ArticleStatus.BLOCKED_SOURCE
                    article.last_error = "Source policy blocks content generation"
                    blocked_article_ids.append(article.id)
                elif is_live_match_update(article.title) or (
                    self.only_current_day
                    and not self._is_current_news_day(article.published_at)
                ):
                    article.status = ArticleStatus.DISCOVERED
                    article.last_error = None
            await session.commit()

        if self.notifier and hasattr(self.notifier, "notify_blocked_article"):
            for article_id in blocked_article_ids:
                await self.notifier.notify_blocked_article(article_id)

        for article_id, source_id, content_input in retry_items:
            try:
                await self._generate_and_store(article_id, content_input)
                logger.info(
                    "failed_article_recovered",
                    source=source_id,
                    article_id=article_id,
                    operation="retry_article",
                )
            except Exception as error:
                logger.warning(
                    "failed_article_retry_failed",
                    source=source_id,
                    article_id=article_id,
                    operation="retry_article",
                    error=f"{type(error).__name__}: {error}",
                )

    async def _collect_source(self, source_id: int) -> None:
        async with self.session_factory() as session:
            source = await SourceRepository(session).get(source_id)
            if source is None or not source.active:
                return
            if (
                self.enforce_source_usage_policy
                and source.rss_usage_status.value == "restricted"
            ):
                logger.warning(
                    "source_skipped_usage_not_approved",
                    source=source.id,
                    operation="source_usage_policy",
                )
                return
            first_scan = source.last_checked_at is None
            result = await self.rss_client.fetch(
                source.rss_url, etag=source.etag, last_modified=source.last_modified
            )
            source_name = source.name
            credibility = self.credibility.calculate(source)

        if not result.not_modified:
            for entry in result.entries:
                try:
                    await self._store_and_process(
                        source_id=source_id,
                        source_name=source_name,
                        credibility=credibility,
                        first_scan=first_scan,
                        entry=entry,
                    )
                except Exception as error:
                    logger.exception(
                        "article_pipeline_failed",
                        source=source_id,
                        operation="process_article",
                        error=f"{type(error).__name__}: {error}",
                    )

        async with self.session_factory() as session:
            source = await SourceRepository(session).get(source_id)
            if source:
                source.last_checked_at = datetime.now(UTC)
                source.etag = result.etag
                source.last_modified = result.last_modified
                await session.commit()

    async def _store_and_process(
        self,
        *,
        source_id: int,
        source_name: str,
        credibility: int,
        first_scan: bool,
        entry: FeedEntry,
    ) -> None:
        if is_live_match_update(entry.title):
            logger.info(
                "article_skipped_live_match_update",
                source=source_id,
                operation="live_update_filter",
            )
            return
        if not is_quality_article(
            title=entry.title, description=entry.description, url=entry.url
        ):
            logger.info(
                "article_skipped_low_quality",
                source=source_id,
                operation="quality_check",
            )
            return

        if self.only_current_day:
            should_process = (
                entry.published_at is not None
                and self._is_current_news_day(entry.published_at)
            ) or (not first_scan and entry.published_at is None)
        else:
            should_process = not first_scan or (
                entry.published_at is not None
                and entry.published_at >= datetime.now(UTC) - self.initial_lookback
            )
        async with self.session_factory() as session:
            article_repository = ArticleRepository(session)
            detector = DuplicateDetector(article_repository)
            if await detector.is_duplicate(url=entry.url, title=entry.title):
                return
            try:
                article = await article_repository.create(
                    source_id=source_id,
                    title=entry.title,
                    description=entry.description,
                    url=entry.url,
                    published_at=entry.published_at,
                    content_hash=make_content_hash(entry.title),
                    credibility_score=credibility,
                    status=(
                        ArticleStatus.PROCESSING
                        if should_process
                        else ArticleStatus.DISCOVERED
                    ),
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return
            article_id = article.id

        if not should_process:
            return

        await self._generate_and_store(
            article_id,
            ContentInput(
                title=entry.title,
                description=entry.description,
                source_name=source_name,
                url=entry.url,
                published_at=entry.published_at,
                credibility_score=credibility,
            ),
        )

    async def _generate_and_store(
        self, article_id: int, content_input: ContentInput
    ) -> None:
        if self.content_workflow is not None:
            result = await self.content_workflow.process_article(article_id)
            if result.post_id is not None and self.notifier:
                try:
                    await self.notifier.notify_post(result.post_id)
                except Exception as error:
                    logger.exception(
                        "post_notification_failed",
                        post_id=result.post_id,
                        article_id=article_id,
                        operation="telegram_send",
                        error=f"{type(error).__name__}: {error}",
                    )
            elif (
                result.article_status == ArticleStatus.BLOCKED_SOURCE
                and self.notifier
                and hasattr(self.notifier, "notify_blocked_article")
            ):
                await self.notifier.notify_blocked_article(article_id)
            return
        try:
            generated = await self.content_generator.generate(content_input)
            async with self.session_factory() as session:
                article = await ArticleRepository(session).get(article_id)
                if article is None:
                    return
                article.processing_attempts += 1
                article.status = ArticleStatus.READY
                article.last_error = None
                post = await PostRepository(session).create(
                    article_id=article.id,
                    text=generated.post_text,
                    ai_model=self.content_generator.ai_client.model,
                    category=generated.category,
                    confidence=generated.confidence,
                )
                await session.commit()
                post_id = post.id
        except Exception as error:
            async with self.session_factory() as session:
                article = await ArticleRepository(session).get(article_id)
                if article:
                    article.processing_attempts += 1
                    article.status = ArticleStatus.PROCESSING_FAILED
                    article.last_error = f"{type(error).__name__}: {error}"[:2000]
                    await session.commit()
            raise

        if self.notifier:
            try:
                await self.notifier.notify_post(post_id)
            except Exception as error:
                logger.exception(
                    "post_notification_failed",
                    post_id=post_id,
                    article_id=article_id,
                    operation="telegram_send",
                    error=f"{type(error).__name__}: {error}",
                )
