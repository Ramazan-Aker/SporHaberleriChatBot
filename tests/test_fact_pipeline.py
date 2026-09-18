from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.telegram.telegram_bot import notification_text
from app.models.article import ArticleStatus
from app.models.generated_post import PostCategory, PostStatus
from app.models.source import (
    CommercialUseStatus,
    RSSUsageStatus,
    SourceType,
)
from app.repositories.article_repository import ArticleRepository
from app.repositories.post_repository import PostRepository
from app.repositories.source_repository import SourceRepository
from app.schemas.facts import (
    ClaimCertainty,
    ClaimValidationResult,
    EventType,
    ExtractedFacts,
    FactClaim,
    FactEntities,
    FactNumbers,
)
from app.schemas.generated_post import GeneratedPostContent
from app.schemas.source import SourceCreate
from app.services.content_generator import ContentGenerator, ContentInput
from app.services.content_safety_service import ContentSafetyService
from app.services.content_validator import ContentValidator
from app.services.content_workflow import ContentWorkflow
from app.services.duplicate_detector import make_content_hash
from app.services.fact_extractor import FactExtractionInput, FactExtractor


def transfer_facts(*, official: bool = False) -> ExtractedFacts:
    return ExtractedFacts(
        event_type=(
            EventType.OFFICIAL_TRANSFER if official else EventType.TRANSFER_RUMOR
        ),
        entities=FactEntities(
            team="Galatasaray",
            player="Örnek Oyuncu",
            other_team=None,
            person=None,
            organization=None,
            opponent=None,
            competition=None,
        ),
        facts=["Galatasaray oyuncuyla ilgileniyor."],
        claims=[
            FactClaim(
                text="20 milyon euro teklif bildiriliyor.",
                certainty=(
                    ClaimCertainty.CONFIRMED if official else ClaimCertainty.REPORTED
                ),
            )
        ],
        numbers=FactNumbers(
            fee="20",
            currency="euro",
            contract_years=None,
            goals=None,
            assists=None,
            score=None,
            minute=None,
            date=None,
            age=None,
        ),
        official=official,
        confidence=0.88,
    )


class QueueStructuredAI:
    model = "mock-model"

    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls = 0

    async def parse(self, *, system_prompt, user_prompt, response_model):
        response = self.responses[self.calls]
        self.calls += 1
        return response_model.model_validate(response)


class QueuePostAI:
    model = "mock-model"

    def __init__(self, responses: list[GeneratedPostContent]) -> None:
        self.responses = responses
        self.calls = 0
        self.prompts: list[str] = []

    async def generate(self, *, system_prompt: str, user_prompt: str):
        self.prompts.append(user_prompt)
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response.model_copy(deep=True)


async def test_fact_extractor_retries_invalid_official_claim() -> None:
    invalid = transfer_facts(official=True).model_dump()
    valid = transfer_facts(official=False).model_dump()
    ai = QueueStructuredAI([invalid, valid])
    extractor = FactExtractor(ai, max_attempts=2)

    result = await extractor.extract(
        FactExtractionInput(
            title="Galatasaray için 20 milyon euro iddiası",
            description="Oyuncu için 20 milyon euro teklif bildiriliyor.",
            source_name="Haber Kaynağı",
            source_type=SourceType.NEWS,
            published_at=None,
        )
    )

    assert result.event_type == EventType.TRANSFER_RUMOR
    assert result.numbers.fee == "20"
    assert ai.calls == 2


async def test_content_validator_returns_unsupported_claims() -> None:
    ai = QueueStructuredAI(
        [
            {
                "valid": False,
                "unsupported_claims": ["Oyuncunun sözleşme imzaladığı iddiası"],
                "confidence": 0.96,
            }
        ]
    )
    validator = ContentValidator(ai, max_attempts=1)

    result = await validator.validate(
        facts=transfer_facts(),
        generated_post="Oyuncu sözleşme imzaladı.",
    )

    assert not result.valid
    assert result.unsupported_claims


def test_similarity_detects_source_like_content() -> None:
    safety = ContentSafetyService(max_similarity=0.55)
    copied = safety.evaluate(
        generated_text="Galatasaray oyuncuyla görüşmelere başladı",
        source_title="Galatasaray oyuncuyla görüşmelere başladı",
        source_summary=None,
    )
    original = safety.evaluate(
        generated_text="Sarı-kırmızılıların transfer gündeminde yeni bir isim var.",
        source_title="Galatasaray oyuncuyla görüşmelere başladı",
        source_summary=None,
    )

    assert not copied.safe
    assert original.score < copied.score


async def test_rumor_wording_and_number_preservation() -> None:
    ai = QueuePostAI(
        [
            GeneratedPostContent(
                post_text="Galatasaray 30 milyon euro teklif yaptı. #Galatasaray",
                category=PostCategory.TRANSFER_RUMOR,
                confidence=0.8,
            ),
            GeneratedPostContent(
                post_text=(
                    "Galatasaray'ın 20 milyon euro teklif yaptığı bildiriliyor. "
                    "#Galatasaray"
                ),
                category=PostCategory.TRANSFER_RUMOR,
                confidence=0.85,
            ),
        ]
    )
    generator = ContentGenerator(ai, max_attempts=2, max_length=150)

    result = await generator.generate(
        ContentInput(
            title="Ham başlık AI'a gönderilmemeli",
            description="Ham açıklama AI'a gönderilmemeli",
            source_name="Haber Kaynağı",
            url="https://example.com/news",
            published_at=None,
            credibility_score=8,
            facts=transfer_facts(),
            source_type=SourceType.NEWS,
        )
    )

    assert "20 milyon" in result.post_text
    assert "bildiriliyor" in result.post_text
    assert "Ham başlık" not in ai.prompts[-1]
    assert ai.calls == 2


async def test_official_source_allows_official_transfer_language() -> None:
    ai = QueuePostAI(
        [
            GeneratedPostContent(
                post_text="Galatasaray, Örnek Oyuncu transferini açıkladı. #Galatasaray",
                category=PostCategory.OFFICIAL_TRANSFER,
                confidence=0.95,
            )
        ]
    )
    generator = ContentGenerator(ai, max_attempts=1, max_length=150)

    result = await generator.generate(
        ContentInput(
            title="Transfer açıklaması",
            description=None,
            source_name="Galatasaray",
            url="https://example.com/official",
            published_at=None,
            credibility_score=10,
            facts=transfer_facts(official=True),
            source_type=SourceType.OFFICIAL,
        )
    )

    assert result.category == PostCategory.OFFICIAL_TRANSFER


class FakeExtractor:
    def __init__(self, facts: ExtractedFacts) -> None:
        self.facts = facts
        self.calls = 0

    async def extract(self, data):
        self.calls += 1
        return self.facts


class FakeGenerator:
    ai_client = SimpleNamespace(model="mock-model")

    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.calls = 0

    async def generate(self, data):
        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return GeneratedPostContent(
            post_text=text,
            category=PostCategory.TRANSFER_RUMOR,
            confidence=0.9,
        )


class FakeValidator:
    def __init__(self, valid: bool = True) -> None:
        self.valid = valid
        self.calls = 0

    async def validate(self, *, facts, generated_post):
        self.calls += 1
        return ClaimValidationResult(
            valid=self.valid,
            unsupported_claims=[] if self.valid else ["Desteksiz iddia"],
            confidence=0.97,
        )


class QueueValidator:
    def __init__(self, results: list[bool]) -> None:
        self.results = results
        self.calls = 0

    async def validate(self, *, facts, generated_post):
        valid = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return ClaimValidationResult(
            valid=valid,
            unsupported_claims=[] if valid else ["FACT listesinde olmayan iddia"],
            confidence=0.96,
        )


async def create_article(
    factory: async_sessionmaker[AsyncSession],
    *,
    commercial_status: CommercialUseStatus = CommercialUseStatus.ALLOWED,
) -> int:
    async with factory() as session:
        source = await SourceRepository(session).create(
            SourceCreate(
                name="Test Kaynağı",
                url="https://example.com",
                rss_url="https://example.com/facts.xml",
                category="football",
                source_type=SourceType.NEWS,
                credibility_score=8,
                commercial_use_status=commercial_status,
                rss_usage_status=RSSUsageStatus.ALLOWED,
            )
        )
        await session.flush()
        article = await ArticleRepository(session).create(
            source_id=source.id,
            title="Galatasaray için transfer iddiası gündemde",
            description="20 milyon euro teklif yapıldığı bildiriliyor.",
            url="https://example.com/fact-news",
            published_at=datetime.now(UTC),
            content_hash=make_content_hash(
                "Galatasaray için transfer iddiası gündemde"
            ),
            credibility_score=8,
            status=ArticleStatus.PROCESSING,
        )
        await session.commit()
        return article.id


def build_workflow(
    factory: async_sessionmaker[AsyncSession],
    extractor: FakeExtractor,
    generator: FakeGenerator,
    validator: FakeValidator,
    *,
    similarity: float = 0.95,
) -> ContentWorkflow:
    return ContentWorkflow(
        session_factory=factory,
        fact_extractor=extractor,
        content_generator=generator,
        safety_service=ContentSafetyService(similarity),
        content_validator=validator,
        enable_claim_validation=True,
        enable_source_policy_check=True,
    )


async def test_workflow_regenerate_uses_stored_facts_and_keeps_versions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    article_id = await create_article(session_factory)
    extractor = FakeExtractor(transfer_facts())
    generator = FakeGenerator(
        [
            "Transfer görüşmelerinin sürdüğü bildiriliyor. #Galatasaray",
            "Oyuncu için temasların devam ettiği bildiriliyor. #Galatasaray",
        ]
    )
    workflow = build_workflow(session_factory, extractor, generator, FakeValidator())

    first = await workflow.process_article(article_id)
    second = await workflow.regenerate(article_id)

    async with session_factory() as session:
        article = await ArticleRepository(session).get(article_id, with_posts=True)
        assert article is not None
        assert [post.version for post in article.generated_posts] == [1, 2]
    assert first.post_id != second.post_id
    assert extractor.calls == 1


async def test_workflow_marks_persistent_similarity_for_review(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    article_id = await create_article(session_factory)
    workflow = build_workflow(
        session_factory,
        FakeExtractor(transfer_facts()),
        FakeGenerator(["Galatasaray için transfer iddiası gündemde"]),
        FakeValidator(),
        similarity=0.55,
    )

    result = await workflow.process_article(article_id)

    async with session_factory() as session:
        post = await PostRepository(session).get(result.post_id or 0)
        article = await ArticleRepository(session).get(article_id)
    assert post is not None and post.status == PostStatus.REVIEW_REQUIRED
    assert (
        article is not None and article.status == ArticleStatus.CONTENT_REVIEW_REQUIRED
    )


async def test_unsupported_claim_causes_one_regeneration(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    article_id = await create_article(session_factory)
    generator = FakeGenerator(
        [
            "Temasların sürdüğü bildiriliyor. #Galatasaray",
            "Görüşmelerin devam ettiği bildiriliyor. #Galatasaray",
        ]
    )
    validator = QueueValidator([False, True])
    workflow = ContentWorkflow(
        session_factory=session_factory,
        fact_extractor=FakeExtractor(transfer_facts()),
        content_generator=generator,
        safety_service=ContentSafetyService(0.95),
        content_validator=validator,
        enable_claim_validation=True,
        enable_source_policy_check=True,
    )

    result = await workflow.process_article(article_id)

    async with session_factory() as session:
        post = await PostRepository(session).get(result.post_id or 0)
    assert post is not None and post.status == PostStatus.READY
    assert generator.calls == 2
    assert validator.calls == 2


async def test_workflow_blocks_prohibited_source_before_ai(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    article_id = await create_article(
        session_factory, commercial_status=CommercialUseStatus.PROHIBITED
    )
    extractor = FakeExtractor(transfer_facts())
    workflow = build_workflow(
        session_factory, extractor, FakeGenerator(["Kullanılmamalı"]), FakeValidator()
    )

    result = await workflow.process_article(article_id)

    assert result.post_id is None
    assert result.article_status == ArticleStatus.BLOCKED_SOURCE
    assert extractor.calls == 0


def test_telegram_message_contains_safety_information() -> None:
    facts = transfer_facts()
    source = SimpleNamespace(
        name="Örnek Kaynak",
        commercial_use_status=CommercialUseStatus.UNKNOWN,
        rss_usage_status=RSSUsageStatus.ALLOWED,
    )
    article = SimpleNamespace(
        title="Transfer haberi",
        url="https://example.com/news",
        credibility_score=8,
        extracted_facts=facts.model_dump(mode="json"),
        source=source,
    )
    post = SimpleNamespace(
        article=article,
        status=PostStatus.READY,
        source_similarity=0.24,
        confidence=0.91,
        unsupported_claims=None,
        final_text=None,
        text="Görüşmelerin sürdüğü bildiriliyor.",
    )

    message = notification_text(post)

    assert "DOĞRULANAN BİLGİLER" in message
    assert "%24" in message
    assert "%91" in message
    assert "Ticari Kullanım" in message
