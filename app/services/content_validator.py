from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

from pydantic import BaseModel
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from app.schemas.facts import ClaimValidationResult, ExtractedFacts

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)

VALIDATION_PROMPT = """Verilen spor gönderisini yalnız FACT verilerine göre denetle.
FACT listesinde desteklenmeyen kişi, kulüp, skor, sayı, tarih, transfer, sakatlık,
sonuç veya kesinlik iddiasını unsupported_claims listesine yaz. Üslup farklarını
hata sayma. Şüphedeysen valid=false döndür. Yeni metin üretme.
"""


class ValidationAIClient(Protocol):
    async def parse(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel: ...


class ContentValidator:
    def __init__(
        self,
        ai_client: ValidationAIClient,
        *,
        max_attempts: int = 3,
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.ai_client = ai_client
        self.max_attempts = max_attempts
        self.before_request = before_request

    async def validate(
        self, *, facts: ExtractedFacts, generated_post: str
    ) -> ClaimValidationResult:
        user_prompt = (
            f"FACT_DATA:\n{facts.model_dump_json(indent=2)}\n\n"
            f"GENERATED_POST:\n{generated_post}"
        )
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            reraise=True,
        ):
            with attempt:
                if self.before_request:
                    await self.before_request()
                result = await self.ai_client.parse(
                    system_prompt=VALIDATION_PROMPT,
                    user_prompt=user_prompt,
                    response_model=ClaimValidationResult,
                )
                if result.valid and result.unsupported_claims:
                    raise ValueError("Valid result cannot contain unsupported claims")
                if not result.valid and not result.unsupported_claims:
                    raise ValueError("Invalid result must explain unsupported claims")
                return result
        raise RuntimeError("Content validation retry loop ended unexpectedly")
