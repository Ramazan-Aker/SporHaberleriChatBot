from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.services.product_normalizer import NormalizedProduct


@dataclass(slots=True, frozen=True)
class ProductMatch:
    matched: bool
    product_id: int | None
    confidence: float
    method: str
    manual_review_required: bool = False


class ProductMatcher:
    def __init__(self, session: AsyncSession, fuzzy_threshold: float = 0.92) -> None:
        self.session = session
        self.fuzzy_threshold = fuzzy_threshold

    async def match(self, candidate: NormalizedProduct) -> ProductMatch:
        identifiers = [candidate.gtin, candidate.ean, candidate.upc]
        identifiers = [value for value in identifiers if value]
        if identifiers:
            product = await self.session.scalar(
                select(Product).where(
                    or_(
                        Product.gtin.in_(identifiers),
                        Product.ean.in_(identifiers),
                        Product.upc.in_(identifiers),
                    )
                )
            )
            if product:
                return ProductMatch(True, product.id, 1.0, "ean")
        if candidate.mpn:
            statement = select(Product).where(Product.mpn == candidate.mpn)
            if candidate.brand:
                statement = statement.where(Product.brand == candidate.brand)
            product = await self.session.scalar(statement)
            if product:
                return ProductMatch(True, product.id, 0.99, "mpn")
        if candidate.brand and candidate.model:
            product = await self.session.scalar(
                select(Product).where(
                    Product.brand == candidate.brand, Product.model == candidate.model
                )
            )
            if product:
                return ProductMatch(True, product.id, 0.97, "brand_model")
        product = await self.session.scalar(
            select(Product).where(Product.normalized_key == candidate.normalized_key)
        )
        if product:
            return ProductMatch(True, product.id, 0.94, "normalized_key")

        candidates = list((await self.session.scalars(select(Product))).all())
        best: Product | None = None
        best_ratio = 0.0
        for product in candidates:
            if candidate.brand and product.brand and candidate.brand != product.brand:
                continue
            if self._conflicting_capacity(
                candidate.normalized_key, product.normalized_key
            ):
                ratio = SequenceMatcher(
                    None, candidate.normalized_key, product.normalized_key
                ).ratio()
                if ratio > best_ratio:
                    best, best_ratio = product, min(ratio, self.fuzzy_threshold - 0.01)
                continue
            ratio = SequenceMatcher(
                None, candidate.normalized_key, product.normalized_key
            ).ratio()
            if ratio > best_ratio:
                best, best_ratio = product, ratio
        if best and best_ratio >= self.fuzzy_threshold:
            return ProductMatch(True, best.id, best_ratio, "fuzzy")
        if best and best_ratio >= 0.75:
            return ProductMatch(False, best.id, best_ratio, "fuzzy", True)
        return ProductMatch(False, None, best_ratio, "none")

    @staticmethod
    def _conflicting_capacity(left: str, right: str) -> bool:
        pattern = re.compile(r"\b\d+(?:\.\d+)?(?:tb|gb)\b")
        left_values = set(pattern.findall(left))
        right_values = set(pattern.findall(right))
        return bool(left_values and right_values and left_values != right_values)
