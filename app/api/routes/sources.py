from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.source_repository import SourceRepository
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceRead])
async def list_sources(
    session: AsyncSession = Depends(get_session),
) -> list[SourceRead]:
    sources = await SourceRepository(session).list()
    return [SourceRead.model_validate(source) for source in sources]


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    data: SourceCreate, session: AsyncSession = Depends(get_session)
) -> SourceRead:
    try:
        source = await SourceRepository(session).create(data)
        await session.commit()
        await session.refresh(source)
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="RSS URL already exists") from error
    return SourceRead.model_validate(source)


@router.put("/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: int,
    data: SourceUpdate,
    session: AsyncSession = Depends(get_session),
) -> SourceRead:
    repository = SourceRepository(session)
    source = await repository.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        source = await repository.update(source, data)
        await session.commit()
        await session.refresh(source)
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="RSS URL already exists") from error
    return SourceRead.model_validate(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_source(
    source_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    repository = SourceRepository(session)
    source = await repository.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    await repository.deactivate(source)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
