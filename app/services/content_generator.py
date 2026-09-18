import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import structlog
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from app.models.generated_post import PostCategory
from app.schemas.generated_post import GeneratedPostContent, GeneratedPostValidation

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """Sen Türkçe yayın yapan profesyonel bir spor haber editörüsün.
Yalnızca kullanıcı mesajında verilen haber kaynağındaki bilgileri kullan.
Bilgi uydurma, haberi kopyalama, yanıltıcı veya abartılı clickbait kullanma.
Transfer iddialarını kesinleşmiş gibi yazma; 'iddia ediliyor', 'bildiriliyor'
veya 'görüşmeler sürüyor' gibi kaynaktaki belirsizliği koruyan ifadeler kullan.
Başlıktaki kelimelerden olayın bağlamını tahmin etme. Kim, kiminle, hangi konuda
anlaştı bilgisini açıklamadan aynen doğrula. Bir kulübün oyuncuyu milli takıma
göndermemek için federasyonla anlaşması, transfer anlaşması değildir.
Kaynak açıkça transfer, bonservis, kulüpler arası geçiş veya imza sürecinden
bahsetmiyorsa kategori 'transfer' olamaz; 'transfer tamamlandı', 'imza attı',
'kadrosuna kattı' veya benzeri kesin ifadeler kullanma.
Kaynakta yalnız iddia, beklenti, haber veya belirsizlik varsa bunu kesin olay gibi
yazma. Açıklama yetersizse yalnız doğrulanabilen başlık bilgisini temkinli aktar ve
confidence değerini düşür.
Bir skorun yazılması maçın bittiğini göstermez. Kaynak açıkça 'maç sonucu',
'sona erdi', 'son düdük', 'kazandı' veya eşdeğer bir bitiş bilgisi vermiyorsa
'yendi', 'galibiyet elde etti' ya da 'maç sonucu' yazma. GOL, canlı anlatım,
devre arası ve dakika güncellemelerini kesin maç sonucu olarak sunma.
Kısa, doğal ve özgün bir X gönderisi yaz. Gerekiyorsa 1-2 uygun emoji kullan.
Kaynak URL'sini post metnine ekleme. Verilen karakter sınırını aşma.
Kategori değeri izin verilen kategorilerden biri, confidence ise 0-1 arasında olsun.
"""

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
MATCH_FINAL_CLAIM_TERMS = MATCH_FINAL_EVIDENCE_TERMS + (
    "finali tamamladı",
    "galip ayrıldı",
)


@dataclass(slots=True)
class ContentInput:
    title: str
    description: str | None
    source_name: str
    url: str
    published_at: datetime | None
    credibility_score: int


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
    ) -> None:
        self.ai_client = ai_client
        self.max_length = max_length
        self.max_attempts = max_attempts
        self.min_request_interval_seconds = min_request_interval_seconds
        self._request_lock = asyncio.Lock()
        self._last_request_at: float | None = None

    async def _wait_for_request_slot(self) -> None:
        async with self._request_lock:
            if self._last_request_at is not None:
                elapsed = time.monotonic() - self._last_request_at
                delay = self.min_request_interval_seconds - elapsed
                if delay > 0:
                    await asyncio.sleep(delay)
            self._last_request_at = time.monotonic()

    @staticmethod
    def _validate_source_grounding(
        result: GeneratedPostContent, data: ContentInput
    ) -> None:
        source_text = f"{data.title} {data.description or ''}".casefold()
        output_text = result.post_text.casefold()
        has_transfer_context = any(
            term in source_text for term in TRANSFER_CONTEXT_TERMS
        )
        claims_completed_transfer = any(
            phrase in output_text for phrase in TRANSFER_COMPLETION_PHRASES
        )
        if result.category == PostCategory.TRANSFER and not has_transfer_context:
            raise ValueError("AI classified a non-transfer source as a transfer")
        if claims_completed_transfer and not has_transfer_context:
            raise ValueError("AI added an unsupported completed transfer claim")
        has_final_result_evidence = any(
            term in source_text for term in MATCH_FINAL_EVIDENCE_TERMS
        )
        claims_final_result = any(
            term in output_text for term in MATCH_FINAL_CLAIM_TERMS
        )
        if (
            result.category == PostCategory.MATCH_RESULT
            and not has_final_result_evidence
        ):
            raise ValueError("AI classified an unfinished match update as a result")
        if claims_final_result and not has_final_result_evidence:
            raise ValueError("AI added an unsupported final match result")

    async def generate(self, data: ContentInput) -> GeneratedPostContent:
        user_prompt = (
            f"Baslik: {data.title}\n"
            f"Aciklama: {data.description or 'Yok'}\n"
            f"Kaynak: {data.source_name}\n"
            f"Haber URL: {data.url}\n"
            f"Yayin zamani: {data.published_at.isoformat() if data.published_at else 'Bilinmiyor'}\n"
            f"Kaynak guvenilirligi: {data.credibility_score}/10\n"
            f"Maksimum post uzunlugu: {self.max_length} karakter"
        )
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            reraise=True,
        ):
            with attempt:
                await self._wait_for_request_slot()
                result = await self.ai_client.generate(
                    system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt
                )
                validated = GeneratedPostValidation(
                    text=result.post_text, max_length=self.max_length
                )
                result.post_text = validated.text
                self._validate_source_grounding(result, data)
                return result
        raise RuntimeError("Content generation retry loop ended unexpectedly")
