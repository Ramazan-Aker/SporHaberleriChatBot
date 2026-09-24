from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.integrations.stores.base import StoreProduct

_SELLER_WORDS = {
    "amazon",
    "trendyol",
    "hepsiburada",
    "resmi",
    "magaza",
    "mağaza",
    "garantili",
    "ucretsiz",
    "ücretsiz",
    "kargo",
}
_GENERIC_WORDS = {"pcie", "nvme", "ssd", "m2", "disk", "dahili"}


@dataclass(slots=True, frozen=True)
class NormalizedProduct:
    canonical_name: str
    normalized_title: str
    normalized_key: str
    brand: str | None
    model: str | None
    gtin: str | None
    ean: str | None
    upc: str | None
    mpn: str | None


class ProductNormalizer:
    @staticmethod
    def _ascii(value: str) -> str:
        replacements = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
        value = value.translate(replacements)
        return "".join(
            character
            for character in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(character)
        )

    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = cls._ascii(value).lower()
        value = re.sub(r"(\d+)\s*(tera\s*byte|tb)\b", r"\1tb", value)
        value = re.sub(r"(\d+)\s*(giga\s*byte|gb)\b", r"\1gb", value)
        value = re.sub(r"m[.\s-]*2\b", "m2", value)
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return " ".join(value.split())

    def normalize(self, item: StoreProduct) -> NormalizedProduct:
        normalized = self.normalize_text(item.title)
        tokens = [token for token in normalized.split() if token not in _SELLER_WORDS]
        clean_title = " ".join(tokens)
        key_tokens = [token for token in tokens if token not in _GENERIC_WORDS]
        brand = self.normalize_text(item.brand) if item.brand else None
        model = self.normalize_text(item.model) if item.model else None
        if brand and brand not in key_tokens:
            key_tokens.insert(0, brand)
        if model:
            for token in model.split():
                if token not in key_tokens:
                    key_tokens.append(token)
        identifier_key = next(
            (
                f"{name}:{self.normalize_text(value)}"
                for name, value in (
                    ("gtin", item.gtin),
                    ("ean", item.ean),
                    ("upc", item.upc),
                    ("mpn", item.mpn),
                )
                if value
            ),
            None,
        )
        return NormalizedProduct(
            canonical_name=item.title.strip(),
            normalized_title=clean_title,
            normalized_key=identifier_key or " ".join(key_tokens),
            brand=brand,
            model=model,
            gtin=item.gtin,
            ean=item.ean,
            upc=item.upc,
            mpn=item.mpn,
        )
