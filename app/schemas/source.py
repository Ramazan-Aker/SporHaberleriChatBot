from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.models.source import SourceType


class SourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: AnyHttpUrl
    rss_url: AnyHttpUrl
    category: str = Field(min_length=1, max_length=100)
    source_type: SourceType
    credibility_score: int = Field(ge=1, le=10)
    active: bool = True


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: AnyHttpUrl | None = None
    rss_url: AnyHttpUrl | None = None
    category: str | None = Field(default=None, min_length=1, max_length=100)
    source_type: SourceType | None = None
    credibility_score: int | None = Field(default=None, ge=1, le=10)
    active: bool | None = None


class SourceRead(SourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None
