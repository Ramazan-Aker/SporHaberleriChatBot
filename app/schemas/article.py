from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.article import ArticleStatus
from app.schemas.generated_post import GeneratedPostRead


class ArticleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    title: str
    description: str | None
    url: str
    published_at: datetime | None
    fetched_at: datetime
    content_hash: str
    status: ArticleStatus
    credibility_score: int
    processing_attempts: int
    last_error: str | None
    extracted_facts: dict[str, object] | None
    fact_confidence: float | None
    source_similarity: float | None


class ArticleDetail(ArticleRead):
    generated_posts: list[GeneratedPostRead]
