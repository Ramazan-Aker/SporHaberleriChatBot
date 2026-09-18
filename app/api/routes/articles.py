from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.article import ArticleStatus
from app.repositories.article_repository import ArticleRepository
from app.schemas.article import ArticleDetail, ArticleRead

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=list[ArticleRead])
async def list_articles(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: ArticleStatus | None = None,
    source_id: int | None = Query(default=None, ge=1),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ArticleRead]:
    articles = await ArticleRepository(session).list(
        offset=offset,
        limit=limit,
        status=status,
        source_id=source_id,
        date_from=date_from,
        date_to=date_to,
    )
    return [ArticleRead.model_validate(article) for article in articles]


@router.get("/{article_id}", response_model=ArticleDetail)
async def get_article(
    article_id: int, session: AsyncSession = Depends(get_session)
) -> ArticleDetail:
    article = await ArticleRepository(session).get(article_id, with_posts=True)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleDetail.model_validate(article)
