from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.article import Article
from app.models.generated_post import GeneratedPost, PostStatus


class PostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        article_id: int,
        text: str,
        ai_model: str,
        category: str,
        confidence: float,
        status: PostStatus = PostStatus.READY,
        source_similarity: float | None = None,
        validation_confidence: float | None = None,
        unsupported_claims: list[str] | None = None,
    ) -> GeneratedPost:
        version = (
            await self.session.scalar(
                select(func.coalesce(func.max(GeneratedPost.version), 0)).where(
                    GeneratedPost.article_id == article_id
                )
            )
        ) + 1
        post = GeneratedPost(
            article_id=article_id,
            version=version,
            text=text,
            ai_model=ai_model,
            category=category,
            confidence=confidence,
            status=status,
            source_similarity=source_similarity,
            validation_confidence=validation_confidence,
            unsupported_claims=unsupported_claims,
        )
        self.session.add(post)
        await self.session.flush()
        return post

    async def get(
        self, post_id: int, *, with_article: bool = False
    ) -> GeneratedPost | None:
        if not with_article:
            return await self.session.get(GeneratedPost, post_id)
        statement = (
            select(GeneratedPost)
            .where(GeneratedPost.id == post_id)
            .options(selectinload(GeneratedPost.article).selectinload(Article.source))
        )
        return await self.session.scalar(statement)

    async def pending_notifications(self, *, limit: int = 50) -> list[GeneratedPost]:
        now = datetime.now(UTC)
        statement = (
            select(GeneratedPost)
            .where(
                GeneratedPost.status.in_(
                    [PostStatus.READY, PostStatus.REVIEW_REQUIRED]
                ),
                GeneratedPost.telegram_sent_at.is_(None),
                (
                    GeneratedPost.next_notification_at.is_(None)
                    | (GeneratedPost.next_notification_at <= now)
                ),
            )
            .order_by(GeneratedPost.created_at)
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: PostStatus | None = None,
        source_id: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[GeneratedPost]:
        statement: Select[tuple[GeneratedPost]] = select(GeneratedPost).join(
            GeneratedPost.article
        )
        if status:
            statement = statement.where(GeneratedPost.status == status)
        if source_id:
            statement = statement.where(Article.source_id == source_id)
        if date_from:
            statement = statement.where(GeneratedPost.created_at >= date_from)
        if date_to:
            statement = statement.where(GeneratedPost.created_at <= date_to)
        statement = (
            statement.order_by(GeneratedPost.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())
