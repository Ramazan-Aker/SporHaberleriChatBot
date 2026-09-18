from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.generated_post import PostStatus
from app.repositories.post_repository import PostRepository
from app.schemas.generated_post import GeneratedPostRead

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("", response_model=list[GeneratedPostRead])
async def list_posts(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: PostStatus | None = None,
    source_id: int | None = Query(default=None, ge=1),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[GeneratedPostRead]:
    posts = await PostRepository(session).list(
        offset=offset,
        limit=limit,
        status=status,
        source_id=source_id,
        date_from=date_from,
        date_to=date_to,
    )
    return [GeneratedPostRead.model_validate(post) for post in posts]
