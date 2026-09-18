from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.rss.rss_client import FeedEntry, FeedResult
from app.models.article import Article, ArticleStatus
from app.models.generated_post import GeneratedPost, PostCategory
from app.repositories.source_repository import SourceRepository
from app.schemas.generated_post import GeneratedPostContent
from app.schemas.source import SourceCreate
from app.services.news_collector import NewsCollector


class FakeRSSClient:
    def __init__(self, entries: list[FeedEntry]) -> None:
        self.entries = entries

    async def fetch(self, rss_url: str, *, etag=None, last_modified=None) -> FeedResult:
        if "broken" in rss_url:
            raise RuntimeError("feed unavailable")
        return FeedResult(self.entries, "etag", "last-modified")


class FakeGenerator:
    class Client:
        model = "mock-model"

    ai_client = Client()

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def generate(self, data):
        self.calls += 1
        if self.fail:
            raise RuntimeError("AI unavailable")
        return GeneratedPostContent(
            post_text="⚽ Test için üretilen geçerli gönderi",
            category=PostCategory.GENERAL,
            confidence=0.9,
        )


class FailingNotifier:
    async def retry_pending(self) -> None:
        return None

    async def notify_post(self, post_id: int) -> None:
        raise RuntimeError("Telegram unavailable")


async def add_source(
    factory: async_sessionmaker[AsyncSession],
    *,
    rss_url: str = "https://example.com/feed",
) -> int:
    async with factory() as session:
        source = await SourceRepository(session).create(
            SourceCreate(
                name="Test Source",
                url="https://example.com",
                rss_url=rss_url,
                category="football",
                source_type="news",
                credibility_score=8,
            )
        )
        await session.commit()
        return source.id


@pytest.mark.asyncio
async def test_first_scan_stores_all_but_generates_only_recent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add_source(session_factory)
    now = datetime.now(UTC)
    entries = [
        FeedEntry(
            "Yeni ve yeterince uzun spor haberi",
            "Açıklama",
            "https://example.com/1",
            now,
        ),
        FeedEntry(
            "Eski ve yeterince uzun spor haberi",
            "Açıklama",
            "https://example.com/2",
            now - timedelta(days=2),
        ),
        FeedEntry(
            "Tarihsiz ve yeterince uzun spor haberi",
            "Açıklama",
            "https://example.com/3",
            None,
        ),
    ]
    generator = FakeGenerator()
    collector = NewsCollector(
        session_factory=session_factory,
        rss_client=FakeRSSClient(entries),
        content_generator=generator,
        notifier=None,
        initial_lookback_hours=24,
    )
    await collector.fetch_news()
    async with session_factory() as session:
        article_count = await session.scalar(select(func.count(Article.id)))
        post_count = await session.scalar(select(func.count(GeneratedPost.id)))
    assert article_count == 3
    assert post_count == 1
    assert generator.calls == 1


@pytest.mark.asyncio
async def test_live_goal_update_is_not_sent_to_ai(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add_source(session_factory)
    entry = FeedEntry(
        "GOL | Orduspor 1967 8-0 Torul Belediye Spor",
        "60. dakikada Atakan Aybastı'nın golü geldi.",
        "https://example.com/live-goal",
        datetime.now(UTC),
    )
    generator = FakeGenerator()
    collector = NewsCollector(
        session_factory=session_factory,
        rss_client=FakeRSSClient([entry]),
        content_generator=generator,
        notifier=None,
    )

    await collector.fetch_news()

    async with session_factory() as session:
        article_count = await session.scalar(select(func.count(Article.id)))
    assert generator.calls == 0
    assert article_count == 0


@pytest.mark.asyncio
async def test_failed_ai_marks_article_without_losing_it(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add_source(session_factory)
    entry = FeedEntry(
        "AI hatası için yeterince uzun spor haberi",
        "Haber açıklaması",
        "https://example.com/failed",
        datetime.now(UTC),
    )
    collector = NewsCollector(
        session_factory=session_factory,
        rss_client=FakeRSSClient([entry]),
        content_generator=FakeGenerator(fail=True),
        notifier=None,
    )
    await collector.fetch_news()
    async with session_factory() as session:
        article = await session.scalar(select(Article))
    assert article is not None
    assert article.status == ArticleStatus.PROCESSING_FAILED
    assert "AI unavailable" in (article.last_error or "")


@pytest.mark.asyncio
async def test_failed_article_is_retried_on_next_job(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add_source(session_factory)
    entry = FeedEntry(
        "Yeniden denenecek yeterince uzun spor haberi",
        "Haber açıklaması",
        "https://example.com/retry-failed",
        datetime.now(UTC),
    )
    generator = FakeGenerator(fail=True)
    collector = NewsCollector(
        session_factory=session_factory,
        rss_client=FakeRSSClient([entry]),
        content_generator=generator,
        notifier=None,
    )

    await collector.fetch_news()
    generator.fail = False
    await collector.fetch_news()

    async with session_factory() as session:
        article = await session.scalar(select(Article))
        post_count = await session.scalar(select(func.count(GeneratedPost.id)))
    assert article is not None
    assert article.status == ArticleStatus.READY
    assert article.processing_attempts == 2
    assert post_count == 1


@pytest.mark.asyncio
async def test_subsequent_scan_processes_new_undated_entry(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add_source(session_factory)
    rss = FakeRSSClient(
        [
            FeedEntry(
                "İlk tarihsiz ve yeterince uzun haber",
                "Açıklama",
                "https://example.com/baseline",
                None,
            )
        ]
    )
    generator = FakeGenerator()
    collector = NewsCollector(
        session_factory=session_factory,
        rss_client=rss,
        content_generator=generator,
        notifier=None,
    )
    await collector.fetch_news()
    rss.entries = [
        FeedEntry(
            "Sonraki tarihsiz ve yeterince uzun haber",
            "Açıklama",
            "https://example.com/new-undated",
            None,
        )
    ]
    await collector.fetch_news()
    assert generator.calls == 1


@pytest.mark.asyncio
async def test_broken_source_does_not_stop_other_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add_source(session_factory, rss_url="https://broken.example/feed")
    await add_source(session_factory, rss_url="https://working.example/feed")
    entry = FeedEntry(
        "Çalışan kaynak için yeterince uzun haber",
        "Açıklama",
        "https://example.com/working-news",
        datetime.now(UTC),
    )
    generator = FakeGenerator()
    collector = NewsCollector(
        session_factory=session_factory,
        rss_client=FakeRSSClient([entry]),
        content_generator=generator,
        notifier=None,
    )
    await collector.fetch_news()
    assert generator.calls == 1


@pytest.mark.asyncio
async def test_notification_failure_does_not_change_ready_article(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await add_source(session_factory)
    entry = FeedEntry(
        "Telegram hatası için yeterince uzun haber",
        "Açıklama",
        "https://example.com/telegram-failed",
        datetime.now(UTC),
    )
    collector = NewsCollector(
        session_factory=session_factory,
        rss_client=FakeRSSClient([entry]),
        content_generator=FakeGenerator(),
        notifier=FailingNotifier(),
    )
    await collector.fetch_news()
    async with session_factory() as session:
        article = await session.scalar(select(Article))
    assert article is not None
    assert article.status == ArticleStatus.READY
