from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source
from app.schemas.source import SourceCreate, SourceUpdate
from app.services.source_usage_policy import classify_source_usage


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, active_only: bool = False) -> list[Source]:
        statement = select(Source).order_by(Source.id)
        if active_only:
            statement = statement.where(Source.active.is_(True))
        return list((await self.session.scalars(statement)).all())

    async def get(self, source_id: int) -> Source | None:
        return await self.session.get(Source, source_id)

    async def create(self, data: SourceCreate) -> Source:
        values = data.model_dump(mode="json", exclude={"url", "rss_url"})
        reviewed = classify_source_usage(str(data.url), str(data.rss_url))
        if values["commercial_use_status"] == "unknown":
            values["commercial_use_status"] = reviewed.commercial_use_status.value
        if values["rss_usage_status"] == "unknown":
            values["rss_usage_status"] = reviewed.rss_usage_status.value
        if not values.get("terms_url"):
            values["terms_url"] = reviewed.terms_url
        if not values.get("notes") and reviewed.note:
            values["notes"] = reviewed.note
        source = Source(
            **values,
            url=str(data.url),
            rss_url=str(data.rss_url),
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def update(self, source: Source, data: SourceUpdate) -> Source:
        values = data.model_dump(exclude_unset=True)
        for field in ("url", "rss_url", "terms_url"):
            if field in values:
                values[field] = str(values[field]) if values[field] else None
        for key, value in values.items():
            setattr(source, key, value)
        await self.session.flush()
        return source

    async def deactivate(self, source: Source) -> None:
        source.active = False
        await self.session.flush()
