import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import ArticleStatus
from app.models.generated_post import PostCategory
from app.repositories.article_repository import ArticleRepository
from app.repositories.post_repository import PostRepository
from app.repositories.source_repository import SourceRepository
from app.schemas.source import SourceCreate
from app.services.duplicate_detector import make_content_hash


def source_data(rss_url: str = "https://example.com/feed") -> SourceCreate:
    return SourceCreate(
        name="Example",
        url="https://example.com",
        rss_url=rss_url,
        category="football",
        source_type="news",
        credibility_score=8,
    )


@pytest.mark.asyncio
async def test_article_repository_detects_url_and_hash_duplicates(
    session: AsyncSession,
) -> None:
    source = await SourceRepository(session).create(source_data())
    await session.flush()
    repository = ArticleRepository(session)
    title = "Galatasaray transfer görüşmelerine başladı"
    await repository.create(
        source_id=source.id,
        title=title,
        description="Kulüp görüşmelerin başladığını açıkladı.",
        url="https://example.com/news/1",
        published_at=None,
        content_hash=make_content_hash(title),
        credibility_score=8,
    )
    await session.commit()

    assert await repository.duplicate_exists(
        url="https://example.com/news/1", content_hash="different"
    )
    assert await repository.duplicate_exists(
        url="https://example.com/news/2", content_hash=make_content_hash(title)
    )


@pytest.mark.asyncio
async def test_database_unique_constraints_close_duplicate_race(
    session: AsyncSession,
) -> None:
    source = await SourceRepository(session).create(source_data())
    await session.commit()
    repository = ArticleRepository(session)
    kwargs = dict(
        source_id=source.id,
        title="Aynı haber için yeterince uzun başlık",
        description=None,
        url="https://example.com/news/race",
        published_at=None,
        content_hash=make_content_hash("Aynı haber için yeterince uzun başlık"),
        credibility_score=7,
    )
    await repository.create(**kwargs)
    await session.commit()
    with pytest.raises(IntegrityError):
        await repository.create(**kwargs)
        await session.commit()
    await session.rollback()


@pytest.mark.asyncio
async def test_article_has_versioned_posts(session: AsyncSession) -> None:
    source = await SourceRepository(session).create(source_data())
    await session.flush()
    article = await ArticleRepository(session).create(
        source_id=source.id,
        title="Sürüm testi için yeterince uzun haber",
        description=None,
        url="https://example.com/versioned",
        published_at=None,
        content_hash=make_content_hash("Sürüm testi için yeterince uzun haber"),
        credibility_score=7,
        status=ArticleStatus.READY,
    )
    await session.flush()
    posts = PostRepository(session)
    first = await posts.create(
        article_id=article.id,
        text="İlk sürüm",
        ai_model="test-model",
        category=PostCategory.GENERAL,
        confidence=0.9,
    )
    second = await posts.create(
        article_id=article.id,
        text="İkinci sürüm",
        ai_model="test-model",
        category=PostCategory.GENERAL,
        confidence=0.8,
    )
    await session.commit()
    loaded = await ArticleRepository(session).get(article.id, with_posts=True)
    assert loaded is not None
    assert (first.version, second.version) == (1, 2)
    assert len(loaded.generated_posts) == 2


@pytest.mark.asyncio
async def test_source_delete_is_soft(session: AsyncSession) -> None:
    repository = SourceRepository(session)
    source = await repository.create(source_data())
    await repository.deactivate(source)
    await session.commit()
    assert source.active is False
    assert await repository.get(source.id) is not None
