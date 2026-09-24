from app.integrations.stores.base import (
    StoreAdapter,
    StoreConfigurationError,
    StoreProduct,
)
from app.models.store import DataSourceType


class HepsiburadaAdapter(StoreAdapter):
    slug = "hepsiburada"
    name = "Hepsiburada"
    base_url = "https://www.hepsiburada.com"
    adapter_type = "hepsiburada"
    data_source_type = DataSourceType.OTHER
    affiliate_enabled = False
    notes = "DISABLED UNTIL DATA SOURCE IS CONFIGURED"

    @staticmethod
    def _disabled() -> StoreConfigurationError:
        return StoreConfigurationError(
            "Hepsiburada requires an approved official API, affiliate feed or supplied data source"
        )

    async def fetch_products(self) -> list[StoreProduct]:
        raise self._disabled()

    async def get_product(self, external_id: str) -> StoreProduct | None:
        raise self._disabled()

    async def build_product_url(self, external_id: str) -> str:
        raise self._disabled()
