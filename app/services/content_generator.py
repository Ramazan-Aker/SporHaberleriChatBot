import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from app.models.generated_post import PostCategory
from app.models.source import SourceType
from app.schemas.facts import ClaimCertainty, EventType, ExtractedFacts
from app.schemas.generated_post import GeneratedPostContent, GeneratedPostValidation

SYSTEM_PROMPT = """Sen Türkçe yayın yapan bağımsız bir spor haber editörüsün.
Sana verilen FACT verilerini kullanarak tamamen yeni bir spor gönderisi yaz.
Kaynak metni yeniden yazma, paraphrase etme veya başlığı taklit etme.
Yalnız doğrulanabilir FACT verilerini kullan ve yeni bilgi uydurma.
Kesin olmayan bilgileri kesinmiş gibi yazma. Gerektiğinde 'iddia edildi',
'bildiriliyor', 'görüşmeler sürüyor' veya 'henüz resmi açıklama yapılmadı' de.
Resmi kaynak ile gazeteci veya haber kaynağının iddiasını birbirinden ayır.
Kaynağın yorumunu kendi yorumun gibi sunma ve doğrudan alıntı üretme.
Kaynak adı kullanacaksan yalnız verilen gerçek source_name değerini kullan; başka
bir yayın, gazeteci veya kurum adı uydurma. Her gönderide kaynak adı kullanma.
Gönderi özgün, doğal, kısa ve X'te paylaşılabilir olmalı.
transfer_rumor temkinli, official_transfer yalnız official=true ise kesin dille
yazılabilir. injury yalnız açıklanan bilgileri, statistics sayıları aynen,
statement ise açıklamanın fact-level özetini kullanmalıdır. Bir skorun varlığı
maçın bittiğini kanıtlamaz; yalnız event_type=match_result ise sonuç dili kullan.
Gerekiyorsa 1-2 uygun emoji ve en fazla iki ilgili hashtag kullan. Kaynak URL'sini
post metnine ekleme. Verilen karakter sınırını kesinlikle aşma.
"""

HASHTAG_PATTERN = re.compile(r"(?<!\w)#\w+")
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")
CAUTIOUS_TERMS = (
    "iddia",
    "bildiril",
    "öne sür",
    "görüşme",
    "resmi açıklama",
    "henüz kesinleş",
    "gündeminde",
)
FINAL_RESULT_TERMS = (
    "maç sonucu",
    "kazandı",
    "mağlup etti",
    "galip",
    " yendi",
    "sona erdi",
)
TRANSFER_CONTEXT_TERMS = (
    "transfer",
    "bonservis",
    "kiralık",
    "kulübüne kat",
    "kadrosuna kat",
    "sözleşme imza",
    "transfer görüşme",
)
TRANSFER_COMPLETION_PHRASES = (
    "transferi tamamlandı",
    "transfer tamamlandı",
    "resmen transfer",
    "kadrosuna kattı",
    "imza attı",
)
MATCH_FINAL_EVIDENCE_TERMS = (
    "maç sonucu",
    "karşılaşma sona erdi",
    "mücadele sona erdi",
    "maç sona erdi",
    "son düdük",
    "maçı kazandı",
    "galibiyet elde etti",
    "mağlup etti",
    " yendi",
)
WORD_PATTERN = re.compile(r"\w+")


def _contains_verbatim_sequence(output: str, source: str, length: int = 10) -> bool:
    output_words = WORD_PATTERN.findall(output.casefold())
    source_words = WORD_PATTERN.findall(source.casefold())
    if min(len(output_words), len(source_words)) < length:
        return False
    sequences = {
        tuple(source_words[index : index + length])
        for index in range(len(source_words) - length + 1)
    }
    return any(
        tuple(output_words[index : index + length]) in sequences
        for index in range(len(output_words) - length + 1)
    )


EVENT_CATEGORY = {
    EventType.TRANSFER: PostCategory.TRANSFER,
    EventType.TRANSFER_RUMOR: PostCategory.TRANSFER_RUMOR,
    EventType.OFFICIAL_TRANSFER: PostCategory.OFFICIAL_TRANSFER,
    EventType.INJURY: PostCategory.INJURY,
    EventType.MATCH_RESULT: PostCategory.MATCH_RESULT,
    EventType.LINEUP: PostCategory.LINEUP,
    EventType.STATEMENT: PostCategory.STATEMENT,
    EventType.STATISTICS: PostCategory.STATISTICS,
    EventType.DISCIPLINARY: PostCategory.DISCIPLINARY,
    EventType.BREAKING_NEWS: PostCategory.BREAKING_NEWS,
    EventType.GENERAL: PostCategory.GENERAL,
}


@dataclass(slots=True)
class ContentInput:
    title: str
    description: str | None
    source_name: str
    url: str
    published_at: datetime | None
    credibility_score: int
    facts: ExtractedFacts | None = None
    source_type: SourceType = SourceType.NEWS


class AIClient(Protocol):
    model: str

    async def generate(
        self, *, system_prompt: str, user_prompt: str
    ) -> GeneratedPostContent: ...


class ContentGenerator:
    def __init__(
        self,
        ai_client: AIClient,
        *,
        max_length: int = 260,
        max_attempts: int = 3,
        min_request_interval_seconds: float = 0,
        allow_direct_quotes: bool = False,
    ) -> None:
        self.ai_client = ai_client
        self.max_length = max_length
        self.max_attempts = max_attempts
        self.min_request_interval_seconds = min_request_interval_seconds
        self.allow_direct_quotes = allow_direct_quotes
        self._request_lock = asyncio.Lock()
        self._last_request_at: float | None = None

    async def wait_for_request_slot(self) -> None:
        async with self._request_lock:
            if self._last_request_at is not None:
                elapsed = time.monotonic() - self._last_request_at
                delay = self.min_request_interval_seconds - elapsed
                if delay > 0:
                    await asyncio.sleep(delay)
            self._last_request_at = time.monotonic()

    def _validate_fact_grounding(
        self, result: GeneratedPostContent, data: ContentInput
    ) -> None:
        facts = data.facts
        if facts is None:
            return
        expected_category = EVENT_CATEGORY[facts.event_type]
        if result.category != expected_category:
            raise ValueError("AI category does not match extracted event type")

        output = result.post_text.casefold()
        uncertain = facts.event_type == EventType.TRANSFER_RUMOR or any(
            claim.certainty
            in {ClaimCertainty.REPORTED, ClaimCertainty.RUMOR, ClaimCertainty.UNKNOWN}
            for claim in facts.claims
        )
        if uncertain and not any(term in output for term in CAUTIOUS_TERMS):
            raise ValueError("AI removed uncertainty from a reported claim")
        if facts.event_type == EventType.OFFICIAL_TRANSFER and (
            not facts.official or data.source_type != SourceType.OFFICIAL
        ):
            raise ValueError("Official transfer requires an official source")
        if facts.event_type != EventType.MATCH_RESULT and any(
            term in output for term in FINAL_RESULT_TERMS
        ):
            raise ValueError("AI added an unsupported final match result")

        allowed_numbers = set(
            NUMBER_PATTERN.findall(
                str(facts.model_dump(exclude={"confidence"}, mode="json"))
            )
        )
        output_numbers = set(NUMBER_PATTERN.findall(result.post_text))
        if not output_numbers.issubset(allowed_numbers):
            raise ValueError("AI changed or invented a numeric value")

    def _validate_output(
        self, result: GeneratedPostContent, data: ContentInput
    ) -> None:
        if len(HASHTAG_PATTERN.findall(result.post_text)) > 2:
            raise ValueError("AI added more than two hashtags")
        if not self.allow_direct_quotes and any(
            mark in result.post_text for mark in ('"', "“", "”")
        ):
            raise ValueError("Direct quotation is disabled")
        if data.facts is not None:
            self._validate_fact_grounding(result, data)
        else:
            self._validate_legacy_grounding(result, data)

    @staticmethod
    def _validate_legacy_grounding(
        result: GeneratedPostContent, data: ContentInput
    ) -> None:
        source_text = f"{data.title} {data.description or ''}".casefold()
        output_text = result.post_text.casefold()
        has_transfer_context = any(
            term in source_text for term in TRANSFER_CONTEXT_TERMS
        )
        if result.category == PostCategory.TRANSFER and not has_transfer_context:
            raise ValueError("AI classified a non-transfer source as a transfer")
        if (
            any(phrase in output_text for phrase in TRANSFER_COMPLETION_PHRASES)
            and not has_transfer_context
        ):
            raise ValueError("AI added an unsupported completed transfer claim")
        has_final_evidence = any(
            term in source_text for term in MATCH_FINAL_EVIDENCE_TERMS
        )
        if result.category == PostCategory.MATCH_RESULT and not has_final_evidence:
            raise ValueError("AI classified an unfinished match update as a result")
        if (
            any(term in output_text for term in FINAL_RESULT_TERMS)
            and not has_final_evidence
        ):
            raise ValueError("AI added an unsupported final match result")
        if any(
            _contains_verbatim_sequence(result.post_text, source)
            for source in (data.title, data.description or "")
        ):
            raise ValueError("AI copied a long verbatim sequence from the source")

    def _user_prompt(self, data: ContentInput) -> str:
        if data.facts is not None:
            return (
                f"FACT_DATA:\n{data.facts.model_dump_json(indent=2)}\n\n"
                f"Kaynak adi: {data.source_name}\n"
                f"Kaynak turu: {data.source_type.value}\n"
                f"Kaynak guvenilirligi: {data.credibility_score}/10\n"
                f"Yayin zamani: "
                f"{data.published_at.isoformat() if data.published_at else 'Bilinmiyor'}\n"
                f"Maksimum post uzunlugu: {self.max_length} karakter"
            )
        # Backward-compatible path for existing callers; production uses FACT_DATA.
        return (
            f"FACT_DATA:\n"
            f"- {data.title}\n"
            f"- {data.description or 'Ek doğrulanmış bilgi yok'}\n"
            f"Kaynak adi: {data.source_name}\n"
            f"Kaynak guvenilirligi: {data.credibility_score}/10\n"
            f"Maksimum post uzunlugu: {self.max_length} karakter"
        )

    async def generate(self, data: ContentInput) -> GeneratedPostContent:
        user_prompt = self._user_prompt(data)
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            reraise=True,
        ):
            with attempt:
                await self.wait_for_request_slot()
                result = await self.ai_client.generate(
                    system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt
                )
                validated = GeneratedPostValidation(
                    text=result.post_text, max_length=self.max_length
                )
                result.post_text = validated.text
                self._validate_output(result, data)
                return result
        raise RuntimeError("Content generation retry loop ended unexpectedly")
