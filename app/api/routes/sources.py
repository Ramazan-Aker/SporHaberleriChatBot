from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.source import CommercialUseStatus, RSSUsageStatus
from app.repositories.source_repository import SourceRepository
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate
from app.services.source_usage_policy import classify_source_usage

router = APIRouter(prefix="/sources", tags=["sources"])


def _ensure_activation_allowed(
    *,
    commercial_status: CommercialUseStatus,
    rss_status: RSSUsageStatus,
    active: bool,
) -> None:
    if active and (
        commercial_status == CommercialUseStatus.PROHIBITED
        or rss_status == RSSUsageStatus.RESTRICTED
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Source cannot be activated because commercial use is prohibited "
                "or RSS use is restricted"
            ),
        )


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
    reviewed = classify_source_usage(str(data.url), str(data.rss_url))
    _ensure_activation_allowed(
        commercial_status=(
            reviewed.commercial_use_status
            if data.commercial_use_status == CommercialUseStatus.UNKNOWN
            else data.commercial_use_status
        ),
        rss_status=(
            reviewed.rss_usage_status
            if data.rss_usage_status == RSSUsageStatus.UNKNOWN
            else data.rss_usage_status
        ),
        active=data.active,
    )
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
    candidate_url = str(data.url or source.url)
    candidate_rss_url = str(data.rss_url or source.rss_url)
    reviewed = classify_source_usage(candidate_url, candidate_rss_url)
    inferred_updates: dict[str, object] = {}
    urls_changed = data.url is not None or data.rss_url is not None
    if urls_changed and data.commercial_use_status is None:
        inferred_updates["commercial_use_status"] = reviewed.commercial_use_status
    if urls_changed and data.rss_usage_status is None:
        inferred_updates["rss_usage_status"] = reviewed.rss_usage_status
    if urls_changed and data.terms_url is None and reviewed.terms_url:
        inferred_updates["terms_url"] = reviewed.terms_url
    if urls_changed and data.notes is None and reviewed.note:
        inferred_updates["notes"] = reviewed.note
    if inferred_updates:
        data = data.model_copy(update=inferred_updates)
    _ensure_activation_allowed(
        commercial_status=(data.commercial_use_status or source.commercial_use_status),
        rss_status=data.rss_usage_status or source.rss_usage_status,
        active=data.active if data.active is not None else source.active,
    )
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
