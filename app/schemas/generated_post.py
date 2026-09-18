from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.generated_post import PostCategory, PostStatus


class GeneratedPostContent(BaseModel):
    post_text: str = Field(min_length=1)
    category: PostCategory
    confidence: float = Field(ge=0, le=1)


class GeneratedPostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    article_id: int
    version: int
    text: str
    final_text: str | None
    ai_model: str
    status: PostStatus
    category: PostCategory
    confidence: float
    created_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None
    edited_by_user: bool
    telegram_sent_at: datetime | None


class GeneratedPostValidation(BaseModel):
    text: str
    max_length: int = Field(default=260, ge=1)

    @model_validator(mode="after")
    def validate_text(self) -> "GeneratedPostValidation":
        normalized = self.text.strip()
        if not normalized:
            raise ValueError("Post text cannot be empty")
        if len(normalized) > self.max_length:
            raise ValueError(f"Post text cannot exceed {self.max_length} characters")
        self.text = normalized
        return self
