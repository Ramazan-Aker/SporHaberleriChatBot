from app.integrations.stores.base import StoreAdapter


class AffiliateService:
    async def build_url(self, adapter: StoreAdapter, original_url: str) -> str | None:
        if not adapter.affiliate_enabled:
            return None
        return await adapter.build_affiliate_url(original_url)
