import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from app.models.source import SourceType
from app.schemas.facts import EventType, ExtractedFacts

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)

FACT_EXTRACTION_PROMPT = """Sen bir spor haberinden yalnız doğrulanabilir olguları
çıkaran veri editörüsün. Yeni gönderi yazma ve kaynak metni yeniden anlatma.
Başlık ile kısa RSS açıklamasındaki açık bilgileri structured alanlara ayır.
Çıkarım, yorum, abartı, doğrudan alıntı veya kaynakta bulunmayan bilgi ekleme.
Kesinlik düzeylerini confirmed, reported, rumor veya unknown olarak koru.
Bir haber kaynağının aktardığı iddia confirmed değildir. source_type yalnız official
ise official=true olabilir. Canlı skor veya gol girdisini match_result sayma; maçın
bittiği açıkça belirtilmelidir. Sayıları ve özel değerleri değiştirmeden numbers
alanına metin olarak yaz. Bilgi yoksa ilgili sayı alanını null bırak.
"""


class StructuredAIClient(Protocol):
    model: str

    async def parse(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel: ...


@dataclass(slots=True)
class FactExtractionInput:
    title: str
    description: str | None
    source_name: str
    source_type: SourceType
    published_at: datetime | None


class FactExtractor:
    def __init__(
        self,
        ai_client: StructuredAIClient,
        *,
        max_attempts: int = 3,
        allow_direct_quotes: bool = False,
        before_request: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.ai_client = ai_client
        self.max_attempts = max_attempts
        self.allow_direct_quotes = allow_direct_quotes
        self.before_request = before_request

    def _validate(self, result: ExtractedFacts, data: FactExtractionInput) -> None:
        if data.source_type != SourceType.OFFICIAL and result.official:
            raise ValueError("A non-official source was marked official")
        if (
            result.event_type == EventType.OFFICIAL_TRANSFER
            and data.source_type != SourceType.OFFICIAL
        ):
            raise ValueError("A non-official source claimed an official transfer")
        if not self.allow_direct_quotes:
            text = " ".join(result.facts + [claim.text for claim in result.claims])
            if any(mark in text for mark in ('"', "“", "”")):
                raise ValueError("Direct quotation is disabled")

        source_numbers = set(
            re.findall(r"\d+(?:[.,]\d+)?", f"{data.title} {data.description or ''}")
        )
        fact_payload = result.model_dump(exclude={"confidence"})
        extracted_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", str(fact_payload)))
        if not extracted_numbers.issubset(source_numbers):
            raise ValueError("Extracted numeric data is not present in the source")

    async def extract(self, data: FactExtractionInput) -> ExtractedFacts:
        user_prompt = (
            f"Baslik: {data.title}\n"
            f"Kisa RSS ozeti: {data.description or 'Yok'}\n"
            f"Kaynak adi: {data.source_name}\n"
            f"Kaynak turu: {data.source_type.value}\n"
            f"Yayin zamani: "
            f"{data.published_at.isoformat() if data.published_at else 'Bilinmiyor'}"
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
                    system_prompt=FACT_EXTRACTION_PROMPT,
                    user_prompt=user_prompt,
                    response_model=ExtractedFacts,
                )
                self._validate(result, data)
                return result
        raise RuntimeError("Fact extraction retry loop ended unexpectedly")
