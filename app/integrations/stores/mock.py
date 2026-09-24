from decimal import Decimal

from app.integrations.stores.base import StoreAdapter, StoreProduct
from app.models.store import DataSourceType


class MockAmazonAdapter(StoreAdapter):
    """Deterministic local fixture; never used when mock mode is disabled."""

    slug = "amazon-tr"
    name = "Amazon Türkiye"
    base_url = "https://www.amazon.com.tr"
    adapter_type = "mock_amazon"
    data_source_type = DataSourceType.MANUAL
    terms_url = "https://gelirortakligi.amazon.com.tr"
    notes = "Development fixture; no external request is made."
    affiliate_enabled = True

    def __init__(self, partner_tag: str | None = None) -> None:
        self.partner_tag = partner_tag
        self._cursor = 0
        self._prices = [Decimal("8499"), Decimal("7999"), Decimal("6999")]

    def _fixture(self, price: Decimal) -> StoreProduct:
        original = Decimal("9999")
        return StoreProduct(
            external_product_id="B0MOCK990PRO2TB",
            title="Samsung 990 PRO 2TB NVMe M.2 SSD",
            current_price=price,
            original_price=original,
            product_url="https://www.amazon.com.tr/dp/B0MOCK990PRO2TB",
            affiliate_url=(
                f"https://www.amazon.com.tr/dp/B0MOCK990PRO2TB?tag={self.partner_tag}"
                if self.partner_tag
                else None
            ),
            seller_name="Amazon Türkiye",
            seller_score=0.98,
            stock_status="in_stock",
            brand="Samsung",
            model="MZ-V9P2T0BW",
            category="SSD",
            mpn="MZ-V9P2T0BW",
            popularity_score=0.95,
        )

    async def fetch_products(self) -> list[StoreProduct]:
        price = self._prices[min(self._cursor, len(self._prices) - 1)]
        self._cursor += 1
        return [self._fixture(price)]

    async def get_product(self, external_id: str) -> StoreProduct | None:
        if external_id != "B0MOCK990PRO2TB":
            return None
        price = self._prices[min(max(self._cursor - 1, 0), len(self._prices) - 1)]
        return self._fixture(price)

    async def build_product_url(self, external_id: str) -> str:
        return f"{self.base_url}/dp/{external_id}"

    async def build_affiliate_url(self, product_url: str) -> str | None:
        if not self.partner_tag:
            return None
        separator = "&" if "?" in product_url else "?"
        return f"{product_url}{separator}tag={self.partner_tag}"
