from app.models.generated_post import PostCategory
from app.schemas.generated_post import GeneratedPostContent
from app.services.content_generator import ContentGenerator, ContentInput


class RetryingAI:
    model = "mock-model"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, system_prompt: str, user_prompt: str):
        self.calls += 1
        text = "x" * 40 if self.calls == 1 else "Geçerli kısa gönderi"
        return GeneratedPostContent(
            post_text=text, category=PostCategory.GENERAL, confidence=0.9
        )


async def test_content_generator_retries_invalid_length() -> None:
    ai = RetryingAI()
    generator = ContentGenerator(ai, max_length=30, max_attempts=2)
    result = await generator.generate(
        ContentInput(
            title="Haber",
            description="Açıklama",
            source_name="Kaynak",
            url="https://example.com/news",
            published_at=None,
            credibility_score=8,
        )
    )
    assert result.post_text == "Geçerli kısa gönderi"
    assert ai.calls == 2
