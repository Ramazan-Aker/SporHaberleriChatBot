from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.article import Article, ArticleStatus


class ArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def duplicate_exists(self, *, url: str, content_hash: str) -> bool:
        statement = select(Article.id).where(
            or_(Article.url == url, Article.content_hash == content_hash)
        )
        return (await self.session.scalar(statement)) is not None

    async def create(
        self,
        *,
        source_id: int,
        title: str,
        description: str | None,
        url: str,
        published_at: datetime | None,
        content_hash: str,
        credibility_score: int,
        status: ArticleStatus = ArticleStatus.DISCOVERED,
    ) -> Article:
        article = Article(
            source_id=source_id,
            title=title,
            description=description,
            url=url,
            published_at=published_at,
            content_hash=content_hash,
            credibility_score=credibility_score,
            status=status,
        )
        self.session.add(article)
        await self.session.flush()
        return article

    async def get(
        self,
        article_id: int,
        *,
        with_posts: bool = False,
        with_source: bool = False,
    ) -> Article | None:
        if not with_posts and not with_source:
            return await self.session.get(Article, article_id)
        statement = select(Article).where(Article.id == article_id)
        if with_posts:
            statement = statement.options(selectinload(Article.generated_posts))
        if with_source:
            statement = statement.options(selectinload(Article.source))
        return await self.session.scalar(statement)

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: ArticleStatus | None = None,
        source_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[Article]:
        statement: Select[tuple[Article]] = select(Article)
        if status:
            statement = statement.where(Article.status == status)
        if source_id:
            statement = statement.where(Article.source_id == source_id)
        if date_from:
            statement = statement.where(Article.published_at >= date_from)
        if date_to:
            statement = statement.where(Article.published_at <= date_to)
        statement = (
            statement.order_by(Article.fetched_at.desc()).offset(offset).limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_processing_failed(
        self, *, limit: int, max_attempts: int
    ) -> list[Article]:
        statement = (
            select(Article)
            .where(
                Article.status == ArticleStatus.PROCESSING_FAILED,
                Article.processing_attempts < max_attempts,
            )
            .options(selectinload(Article.source))
            .order_by(Article.fetched_at.asc())
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())
