from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from app.models.store import DataSourceType


class StoreError(RuntimeError):
    """Base error for isolated store failures."""


class StoreConfigurationError(StoreError):
    """Raised when an enabled adapter lacks an approved data source or credentials."""


class StoreRateLimitError(StoreError):
    """Raised after rate-limit retries are exhausted."""


@dataclass(slots=True, frozen=True)
class StoreProduct:
    external_product_id: str
    title: str
    current_price: Decimal
    currency: str = "TRY"
    original_price: Decimal | None = None
    product_url: str | None = None
    affiliate_url: str | None = None
    seller_name: str | None = None
    seller_score: float | None = None
    stock_status: str = "unknown"
    shipping_cost: Decimal | None = None
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    sub_category: str | None = None
    gtin: str | None = None
    ean: str | None = None
    upc: str | None = None
    mpn: str | None = None
    image_url: str | None = None
    popularity_score: float = 0.5


class StoreAdapter(ABC):
    slug: str
    name: str
    base_url: str
    adapter_type: str
    data_source_type: DataSourceType
    terms_url: str | None = None
    notes: str | None = None
    affiliate_enabled: bool = False

    @abstractmethod
    async def fetch_products(self) -> list[StoreProduct]: ...

    @abstractmethod
    async def get_product(self, external_id: str) -> StoreProduct | None: ...

    async def get_current_price(self, external_id: str) -> Decimal | None:
        product = await self.get_product(external_id)
        return product.current_price if product else None

    async def get_stock(self, external_id: str) -> str:
        product = await self.get_product(external_id)
        return product.stock_status if product else "unknown"

    @abstractmethod
    async def build_product_url(self, external_id: str) -> str: ...

    async def build_affiliate_url(self, product_url: str) -> str | None:
        return None

    async def close(self) -> None:
        return None
