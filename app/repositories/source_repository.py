from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source
from app.schemas.source import SourceCreate, SourceUpdate


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
        source = Source(
            **data.model_dump(mode="json", exclude={"url", "rss_url"}),
            url=str(data.url),
            rss_url=str(data.rss_url),
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def update(self, source: Source, data: SourceUpdate) -> Source:
        values = data.model_dump(exclude_unset=True)
        for field in ("url", "rss_url"):
            if field in values:
                values[field] = str(values[field])
        for key, value in values.items():
            setattr(source, key, value)
        await self.session.flush()
        return source

    async def deactivate(self, source: Source) -> None:
        source.active = False
        await self.session.flush()
