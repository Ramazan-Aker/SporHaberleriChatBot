from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import httpx

from app.integrations.stores.base import (
    StoreAdapter,
    StoreConfigurationError,
    StoreProduct,
    StoreRateLimitError,
)
from app.models.store import DataSourceType


class AmazonAdapter(StoreAdapter):
    """Amazon Creators API adapter using its official OAuth 2.0 interface."""

    slug = "amazon-tr"
    name = "Amazon Türkiye"
    base_url = "https://www.amazon.com.tr"
    adapter_type = "amazon_creators_api"
    data_source_type = DataSourceType.AFFILIATE_API
    terms_url = "https://affiliate-program.amazon.com/creatorsapi/docs"
    notes = "Official Creators API. PA-API access-key credentials are deprecated."
    affiliate_enabled = True
    api_url = "https://creatorsapi.amazon"
    token_url = "https://api.amazon.co.uk/auth/o2/token"

    def __init__(
        self,
        *,
        credential_id: str,
        credential_secret: str,
        partner_tag: str,
        marketplace: str = "www.amazon.com.tr",
        item_ids: list[str] | None = None,
        search_keywords: list[str] | None = None,
        timeout_seconds: float = 15,
        max_retries: int = 3,
        requests_per_second: float = 1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not credential_id or not credential_secret or not partner_tag:
            raise StoreConfigurationError(
                "Amazon Creators API credential ID, credential secret and partner "
                "tag are required"
            )
        self.credential_id = credential_id
        self.credential_secret = credential_secret
        self.partner_tag = partner_tag
        self.marketplace = marketplace.removeprefix("https://")
        self.item_ids = item_ids or []
        self.search_keywords = search_keywords or []
        self.max_retries = max_retries
        self.requests_per_second = requests_per_second
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._last_request_at = 0.0

    async def _token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expires_at - 60:
            return self._access_token
        response = await self.client.post(
            self.token_url,
            json={
                "grant_type": "client_credentials",
                "client_id": self.credential_id,
                "client_secret": self.credential_secret,
                "scope": "creatorsapi::default",
            },
        )
        response.raise_for_status()
        payload = response.json()
        self._access_token = str(payload["access_token"])
        self._token_expires_at = time.monotonic() + int(payload.get("expires_in", 3600))
        return self._access_token

    async def _post(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_response: httpx.Response | None = None
        for attempt in range(self.max_retries):
            wait_for = (1 / self.requests_per_second) - (
                time.monotonic() - self._last_request_at
            )
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            token = await self._token()
            response = await self.client.post(
                f"{self.api_url}/catalog/v1/{operation}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "x-marketplace": self.marketplace,
                },
                json=payload,
            )
            self._last_request_at = time.monotonic()
            last_response = response
            if response.status_code == 401 and attempt == 0:
                self._access_token = None
                continue
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 30)
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        if last_response is not None and last_response.status_code == 429:
            raise StoreRateLimitError("Amazon Creators API rate limit exhausted")
        if last_response is not None:
            last_response.raise_for_status()
        raise RuntimeError("Amazon Creators API request failed")

    async def fetch_products(self) -> list[StoreProduct]:
        products: list[StoreProduct] = []
        for start in range(0, len(self.item_ids), 10):
            payload = await self._post(
                "getItems",
                {
                    "itemIds": self.item_ids[start : start + 10],
                    "itemIdType": "ASIN",
                    "marketplace": self.marketplace,
                    "partnerTag": self.partner_tag,
                    "resources": self._resources(),
                },
            )
            products.extend(
                self._parse_items(payload.get("itemsResult", {}).get("items", []))
            )
        for keyword in self.search_keywords:
            payload = await self._post(
                "searchItems",
                {
                    "keywords": keyword,
                    "searchIndex": "Electronics",
                    "itemCount": 10,
                    "marketplace": self.marketplace,
                    "partnerTag": self.partner_tag,
                    "resources": self._resources(),
                },
            )
            products.extend(
                self._parse_items(payload.get("searchResult", {}).get("items", []))
            )
        return list(
            {product.external_product_id: product for product in products}.values()
        )

    async def get_product(self, external_id: str) -> StoreProduct | None:
        payload = await self._post(
            "getItems",
            {
                "itemIds": [external_id],
                "itemIdType": "ASIN",
                "marketplace": self.marketplace,
                "partnerTag": self.partner_tag,
                "resources": self._resources(),
            },
        )
        products = self._parse_items(payload.get("itemsResult", {}).get("items", []))
        return products[0] if products else None

    @staticmethod
    def _resources() -> list[str]:
        return [
            "itemInfo.title",
            "itemInfo.byLineInfo",
            "itemInfo.externalIds",
            "itemInfo.manufactureInfo",
            "images.primary.medium",
            "offersV2.listings.price",
            "offersV2.listings.merchantInfo",
            "offersV2.listings.availability",
        ]

    @classmethod
    def _parse_items(cls, items: list[dict[str, Any]]) -> list[StoreProduct]:
        products: list[StoreProduct] = []
        for item in items:
            listing = ((item.get("offersV2") or {}).get("listings") or [{}])[0]
            price_data = listing.get("price") or {}
            amount = price_data.get("amount")
            if amount is None:
                continue
            try:
                price = Decimal(str(amount))
            except InvalidOperation:
                continue
            info = item.get("itemInfo") or {}
            title = (info.get("title") or {}).get("displayValue")
            if not title:
                continue
            byline = info.get("byLineInfo") or {}
            external = info.get("externalIds") or {}
            merchant = listing.get("merchantInfo") or {}
            availability = listing.get("availability") or {}
            saving = price_data.get("savingBasis") or {}
            image_url = (
                ((item.get("images") or {}).get("primary") or {}).get("medium") or {}
            ).get("url")
            products.append(
                StoreProduct(
                    external_product_id=str(item.get("asin")),
                    title=str(title),
                    current_price=price,
                    currency=str(price_data.get("currency", "TRY")),
                    original_price=(
                        Decimal(str(saving["amount"])) if saving.get("amount") else None
                    ),
                    product_url=item.get("detailPageURL"),
                    affiliate_url=item.get("detailPageURL"),
                    seller_name=merchant.get("displayName"),
                    stock_status=(
                        "in_stock"
                        if availability.get("type") != "OutOfStock"
                        else "out_of_stock"
                    ),
                    brand=(byline.get("brand") or {}).get("displayValue"),
                    ean=cls._first_external_id(external, "eaNs", "eans"),
                    upc=cls._first_external_id(external, "upCs", "upcs"),
                    image_url=image_url,
                )
            )
        return products

    @staticmethod
    def _first_external_id(data: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            values = (data.get(key) or {}).get("displayValues") or data.get(key)
            if isinstance(values, list) and values:
                return str(values[0])
        return None

    async def build_product_url(self, external_id: str) -> str:
        return f"{self.base_url}/dp/{external_id}"

    async def build_affiliate_url(self, product_url: str) -> str:
        separator = "&" if "?" in product_url else "?"
        return f"{product_url}{separator}{urlencode({'tag': self.partner_tag})}"

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
