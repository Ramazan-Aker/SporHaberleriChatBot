from __future__ import annotations

import json
import re
from typing import Protocol, TypeVar

from pydantic import BaseModel, Field

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class StructuredAIClient(Protocol):
    async def parse(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel: ...


class PolishedProductName(BaseModel):
    short_name: str = Field(min_length=3, max_length=100)


class OpportunityAIPolisher:
    """Optional, bounded AI step that can only shorten the supplied product name."""

    system_prompt = """Sen Türkiye'de fiyat düşüşlerini paylaşan bir hesap için
ürün adını kısaltıyorsun. Yalnız verilen structured veriyi kullan. Marka, model,
kapasite veya ürün özelliği uydurma. Fiyat, yüzde, mağaza veya tanıtım metni ekleme.
Yalnız kısa ürün adını structured JSON alanında döndür."""

    def __init__(self, client: StructuredAIClient) -> None:
        self.client = client

    async def shorten_name(self, structured_data: dict[str, object]) -> str:
        original = str(structured_data["product_name"])
        result = await self.client.parse(
            system_prompt=self.system_prompt,
            user_prompt=json.dumps(structured_data, ensure_ascii=False),
            response_model=PolishedProductName,
        )
        candidate = result.short_name.strip()
        original_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", original))
        candidate_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", candidate))
        if not candidate_numbers.issubset(original_numbers):
            raise ValueError("AI product name introduced an unsupported number")
        return candidate
