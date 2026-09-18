from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.article import ArticleStatus
from app.models.generated_post import PostStatus
from app.repositories.article_repository import ArticleRepository
from app.repositories.post_repository import PostRepository
from app.schemas.facts import ClaimValidationResult, ExtractedFacts
from app.services.content_generator import ContentGenerator, ContentInput
from app.services.content_safety_service import ContentSafetyService
from app.services.content_validator import ContentValidator
from app.services.fact_extractor import FactExtractionInput, FactExtractor
from app.services.source_usage_policy import source_policy_blocks_processing


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    post_id: int | None
    article_status: ArticleStatus


class ContentWorkflow:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        fact_extractor: FactExtractor,
        content_generator: ContentGenerator,
        safety_service: ContentSafetyService,
        content_validator: ContentValidator | None,
        enable_claim_validation: bool = True,
        enable_source_policy_check: bool = True,
    ) -> None:
        self.session_factory = session_factory
        self.fact_extractor = fact_extractor
        self.content_generator = content_generator
        self.safety_service = safety_service
        self.content_validator = content_validator
        self.enable_claim_validation = enable_claim_validation
        self.enable_source_policy_check = enable_source_policy_check

    async def _load_article(self, article_id: int):
        async with self.session_factory() as session:
            return await ArticleRepository(session).get(article_id, with_source=True)

    async def _facts_for_article(self, article_id: int) -> ExtractedFacts:
        article = await self._load_article(article_id)
        if article is None:
            raise ValueError("Article not found")
        if article.extracted_facts:
            return ExtractedFacts.model_validate(article.extracted_facts)

        facts = await self.fact_extractor.extract(
            FactExtractionInput(
                title=article.title,
                description=article.description,
                source_name=article.source.name,
                source_type=article.source.source_type,
                published_at=article.published_at,
            )
        )
        async with self.session_factory() as session:
            stored = await ArticleRepository(session).get(article_id)
            if stored is None:
                raise ValueError("Article disappeared during fact extraction")
            stored.extracted_facts = facts.model_dump(mode="json")
            stored.fact_confidence = facts.confidence
            await session.commit()
        return facts

    async def process_article(self, article_id: int) -> WorkflowResult:
        try:
            article = await self._load_article(article_id)
            if article is None:
                raise ValueError("Article not found")
            if self.enable_source_policy_check and source_policy_blocks_processing(
                article.source.commercial_use_status,
                article.source.rss_usage_status,
            ):
                async with self.session_factory() as session:
                    stored = await ArticleRepository(session).get(article_id)
                    if stored:
                        stored.status = ArticleStatus.BLOCKED_SOURCE
                        stored.last_error = "Source policy blocks content generation"
                        await session.commit()
                return WorkflowResult(None, ArticleStatus.BLOCKED_SOURCE)

            facts = await self._facts_for_article(article_id)
            return await self._generate(article_id, facts)
        except Exception as error:
            async with self.session_factory() as session:
                article = await ArticleRepository(session).get(article_id)
                if article:
                    article.processing_attempts += 1
                    article.status = ArticleStatus.PROCESSING_FAILED
                    article.last_error = f"{type(error).__name__}: {error}"[:2000]
                    await session.commit()
            raise

    async def regenerate(self, article_id: int) -> WorkflowResult:
        facts = await self._facts_for_article(article_id)
        return await self._generate(article_id, facts)

    async def _generate(self, article_id: int, facts: ExtractedFacts) -> WorkflowResult:
        article = await self._load_article(article_id)
        if article is None:
            raise ValueError("Article not found")

        final_generated = None
        final_similarity = None
        final_validation = ClaimValidationResult(
            valid=True, unsupported_claims=[], confidence=1.0
        )
        for _ in range(2):
            generated = await self.content_generator.generate(
                ContentInput(
                    title=article.title,
                    description=article.description,
                    source_name=article.source.name,
                    url=article.url,
                    published_at=article.published_at,
                    credibility_score=article.credibility_score,
                    facts=facts,
                    source_type=article.source.source_type,
                )
            )
            similarity = self.safety_service.evaluate(
                generated_text=generated.post_text,
                source_title=article.title,
                source_summary=article.description,
            )
            validation = ClaimValidationResult(
                valid=True, unsupported_claims=[], confidence=1.0
            )
            if similarity.safe and self.enable_claim_validation:
                if self.content_validator is None:
                    raise RuntimeError(
                        "Claim validation is enabled without a validator"
                    )
                validation = await self.content_validator.validate(
                    facts=facts, generated_post=generated.post_text
                )
            final_generated = generated
            final_similarity = similarity
            final_validation = validation
            if similarity.safe and validation.valid:
                break

        if final_generated is None or final_similarity is None:
            raise RuntimeError("Content workflow did not produce a candidate")
        ready = final_similarity.safe and final_validation.valid
        post_status = PostStatus.READY if ready else PostStatus.REVIEW_REQUIRED
        article_status = (
            ArticleStatus.READY if ready else ArticleStatus.CONTENT_REVIEW_REQUIRED
        )
        unsupported = list(final_validation.unsupported_claims)
        if not final_similarity.safe:
            unsupported.append("Kaynak metinle benzerlik limiti aşıldı")

        async with self.session_factory() as session:
            stored = await ArticleRepository(session).get(article_id)
            if stored is None:
                raise ValueError("Article disappeared during content generation")
            stored.processing_attempts += 1
            stored.status = article_status
            stored.last_error = None
            stored.source_similarity = final_similarity.score
            post = await PostRepository(session).create(
                article_id=article_id,
                text=final_generated.post_text,
                ai_model=self.content_generator.ai_client.model,
                category=final_generated.category,
                confidence=final_generated.confidence,
                status=post_status,
                source_similarity=final_similarity.score,
                validation_confidence=final_validation.confidence,
                unsupported_claims=unsupported,
            )
            await session.commit()
            post_id = post.id
        return WorkflowResult(post_id, article_status)
