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


class MisreadingTransferAI:
    model = "mock-model"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, system_prompt: str, user_prompt: str):
        self.calls += 1
        if self.calls == 1:
            return GeneratedPostContent(
                post_text=(
                    "Nijerya ile anlaşmaya varıldı: Osimhen'in Galatasaray'a "
                    "transferi tamamlandı."
                ),
                category=PostCategory.TRANSFER,
                confidence=0.9,
            )
        return GeneratedPostContent(
            post_text=(
                "Nijerya, sakatlığı süren Osimhen'i milli takım kadrosuna çağırdı."
            ),
            category=PostCategory.GENERAL,
            confidence=0.85,
        )


async def test_content_generator_retries_unsupported_transfer_claim() -> None:
    ai = MisreadingTransferAI()
    generator = ContentGenerator(ai, max_length=100, max_attempts=2)

    result = await generator.generate(
        ContentInput(
            title="Nijerya'dan Galatasaray'a Victor Osimhen şoku",
            description=(
                "Osimhen'in milli takım kampına katılmaması konusunda federasyonla "
                "anlaşıldığı haberlerinin ardından oyuncu kadroya çağrıldı."
            ),
            source_name="A Spor",
            url="https://example.com/osimhen",
            published_at=None,
            credibility_score=7,
        )
    )

    assert result.category == PostCategory.GENERAL
    assert "milli takım" in result.post_text
    assert ai.calls == 2


class PrematureMatchResultAI:
    model = "mock-model"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, system_prompt: str, user_prompt: str):
        self.calls += 1
        if self.calls == 1:
            return GeneratedPostContent(
                post_text="Orduspor 1967, rakibini 8-0 yenerek galibiyet elde etti.",
                category=PostCategory.MATCH_RESULT,
                confidence=0.9,
            )
        return GeneratedPostContent(
            post_text="60. dakikada gelen golle skor Orduspor 1967 lehine 8-0 oldu.",
            category=PostCategory.GENERAL,
            confidence=0.8,
        )


async def test_content_generator_retries_premature_match_result_claim() -> None:
    ai = PrematureMatchResultAI()
    generator = ContentGenerator(ai, max_length=100, max_attempts=2)

    result = await generator.generate(
        ContentInput(
            title="GOL | Orduspor 1967 8-0 Torul Belediye Spor",
            description="60. dakikada Atakan Aybastı topu ağlara gönderdi.",
            source_name="A Spor",
            url="https://example.com/live-goal",
            published_at=None,
            credibility_score=7,
        )
    )

    assert result.category == PostCategory.GENERAL
    assert "skor" in result.post_text
    assert ai.calls == 2


class ExcessiveHashtagAI:
    model = "mock-model"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, system_prompt: str, user_prompt: str):
        self.calls += 1
        hashtags = "#Futbol #Spor #Gundem" if self.calls == 1 else "#SuperLig"
        return GeneratedPostContent(
            post_text=f"Takım yeni sezon hazırlıklarına başladı. {hashtags}",
            category=PostCategory.GENERAL,
            confidence=0.8,
        )


async def test_content_generator_retries_more_than_two_hashtags() -> None:
    ai = ExcessiveHashtagAI()
    generator = ContentGenerator(ai, max_length=100, max_attempts=2)

    result = await generator.generate(
        ContentInput(
            title="Takım yeni sezon hazırlıklarına başladı",
            description="Takım ilk antrenmanını bugün gerçekleştirdi.",
            source_name="Spor Kaynağı",
            url="https://example.com/training",
            published_at=None,
            credibility_score=7,
        )
    )

    assert result.post_text.endswith("#SuperLig")
    assert ai.calls == 2


class VerbatimCopyAI:
    model = "mock-model"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, system_prompt: str, user_prompt: str):
        self.calls += 1
        if self.calls == 1:
            return GeneratedPostContent(
                post_text=(
                    "Takım yeni sezon hazırlıkları kapsamında bugün tesislerde "
                    "ilk antrenmanını teknik ekip yönetiminde gerçekleştirdi."
                ),
                category=PostCategory.GENERAL,
                confidence=0.8,
            )
        return GeneratedPostContent(
            post_text="Yeni sezon mesaisi bugün yapılan çalışmayla başladı. #Futbol",
            category=PostCategory.GENERAL,
            confidence=0.8,
        )


async def test_content_generator_retries_long_verbatim_copy() -> None:
    ai = VerbatimCopyAI()
    generator = ContentGenerator(ai, max_length=120, max_attempts=2)

    result = await generator.generate(
        ContentInput(
            title="Kulüp yeni sezon çalışmalarına başladı",
            description=(
                "Takım yeni sezon hazırlıkları kapsamında bugün tesislerde ilk "
                "antrenmanını teknik ekip yönetiminde gerçekleştirdi."
            ),
            source_name="Spor Kaynağı",
            url="https://example.com/training",
            published_at=None,
            credibility_score=7,
        )
    )

    assert result.post_text.startswith("Yeni sezon mesaisi")
    assert ai.calls == 2
