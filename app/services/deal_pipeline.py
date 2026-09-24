from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.stores.base import StoreAdapter, StoreProduct
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.product_listing import ProductListing
from app.models.store import Store
from app.repositories.commerce_repository import CommerceRepository
from app.services.affiliate_service import AffiliateService
from app.services.opportunity_ai_polisher import OpportunityAIPolisher
from app.services.opportunity_detector import OpportunityDetector
from app.services.opportunity_post_generator import OpportunityPostGenerator
from app.services.opportunity_scorer import OpportunityScorer
from app.services.price_tracker import PriceTracker
from app.services.product_matcher import ProductMatcher
from app.services.product_normalizer import ProductNormalizer

logger = structlog.get_logger(__name__)


class OpportunityNotifier(Protocol):
    async def notify_opportunity_post(self, post_id: int) -> None: ...

    async def retry_pending_opportunities(self) -> None: ...


class DealPipeline:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        adapters: list[StoreAdapter],
        scorer: OpportunityScorer,
        post_generator: OpportunityPostGenerator,
        notifier: OpportunityNotifier | None,
        min_score: float = 75,
        cooldown_hours: int = 24,
        snapshot_hours: int = 24,
        active_categories: list[str] | None = None,
        ai_polisher: OpportunityAIPolisher | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.adapters = adapters
        self.scorer = scorer
        self.post_generator = post_generator
        self.notifier = notifier
        self.min_score = min_score
        self.cooldown_hours = cooldown_hours
        self.snapshot_hours = snapshot_hours
        self.active_categories = {
            category.casefold() for category in (active_categories or [])
        }
        self.ai_polisher = ai_polisher
        self.normalizer = ProductNormalizer()
        self.detector = OpportunityDetector()
        self.affiliate = AffiliateService()

    async def run(self) -> None:
        if self.notifier:
            await self.notifier.retry_pending_opportunities()
        for adapter in self.adapters:
            try:
                products = await adapter.fetch_products()
            except Exception as error:
                logger.exception(
                    "store_fetch_failed",
                    store=adapter.slug,
                    operation="fetch_products",
                    error=f"{type(error).__name__}: {error}",
                )
                continue
            for item in products:
                if not self._category_enabled(item.category):
                    continue
                try:
                    post_id = await self._process_item(adapter, item)
                    if post_id and self.notifier:
                        await self.notifier.notify_opportunity_post(post_id)
                except Exception as error:
                    logger.exception(
                        "product_pipeline_failed",
                        store=adapter.slug,
                        external_product_id=item.external_product_id,
                        operation="process_listing",
                        price=str(item.current_price),
                        error=f"{type(error).__name__}: {error}",
                    )

    def _category_enabled(self, category: str | None) -> bool:
        return not self.active_categories or bool(
            category and category.casefold() in self.active_categories
        )

    async def _process_item(
        self, adapter: StoreAdapter, item: StoreProduct
    ) -> int | None:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            repository = CommerceRepository(session)
            store = await self._upsert_store(session, repository, adapter)
            normalized = self.normalizer.normalize(item)
            match = await ProductMatcher(session).match(normalized)
            manual_review = match.manual_review_required
            product = (
                await session.get(Product, match.product_id)
                if match.matched and match.product_id
                else None
            )
            if product is None:
                product = Product(
                    canonical_name=normalized.canonical_name,
                    brand=normalized.brand,
                    model=normalized.model,
                    category=item.category,
                    sub_category=item.sub_category,
                    gtin=normalized.gtin,
                    ean=normalized.ean,
                    upc=normalized.upc,
                    mpn=normalized.mpn,
                    normalized_key=normalized.normalized_key,
                    image_url=item.image_url,
                    popularity_score=item.popularity_score,
                )
                session.add(product)
                await session.flush()
            listing = await repository.get_listing(store.id, item.external_product_id)
            product_url = item.product_url or await adapter.build_product_url(
                item.external_product_id
            )
            affiliate_url = item.affiliate_url
            if affiliate_url is None:
                affiliate_url = await self.affiliate.build_url(adapter, product_url)
            if listing is None:
                listing = ProductListing(
                    product_id=product.id,
                    store_id=store.id,
                    external_product_id=item.external_product_id,
                    title=item.title,
                    product_url=product_url,
                    affiliate_url=affiliate_url,
                    seller_name=item.seller_name,
                    seller_score=item.seller_score,
                    current_price=item.current_price,
                    currency=item.currency,
                    original_price=item.original_price,
                    discount_percent=self._advertised_discount(item),
                    stock_status=item.stock_status,
                    shipping_cost=item.shipping_cost,
                    last_seen_at=now,
                )
                session.add(listing)
                await session.flush()
            else:
                listing.product_id = product.id
                listing.title = item.title
                listing.product_url = product_url
                listing.affiliate_url = affiliate_url
                listing.seller_name = item.seller_name
                listing.seller_score = item.seller_score
                listing.discount_percent = self._advertised_discount(item)
                listing.shipping_cost = item.shipping_cost
                listing.active = True

            await repository.expire_stale_opportunities(listing.id, item.current_price)
            tracked = await PriceTracker(
                session, snapshot_hours=self.snapshot_hours
            ).record(
                listing,
                price=item.current_price,
                original_price=item.original_price,
                currency=item.currency,
                stock_status=item.stock_status,
                captured_at=now,
            )
            if not tracked.price_changed or item.stock_status != "in_stock":
                await session.commit()
                return None

            history = list(
                (
                    await session.scalars(
                        select(PriceHistory).where(
                            PriceHistory.product_listing_id == listing.id,
                            PriceHistory.captured_at < now,
                        )
                    )
                ).all()
            )
            metrics = self.detector.analyze(
                current_price=item.current_price,
                previous_price=tracked.previous_price,
                original_price=item.original_price,
                history=history,
                now=now,
            )
            score = self.scorer.score(
                metrics,
                popularity=product.popularity_score,
                seller_quality=item.seller_score,
                stock_status=item.stock_status,
            )
            if score.total < self.min_score:
                await session.commit()
                return None
            if await repository.duplicate_opportunity_exists(
                listing_id=listing.id,
                price=item.current_price,
                cooldown_hours=self.cooldown_hours,
                now=now,
            ):
                await session.commit()
                return None
            bucket = int(now.timestamp() // (self.cooldown_hours * 3600))
            opportunity = Opportunity(
                product=product,
                listing=listing,
                store=store,
                current_price=metrics.current_price,
                previous_price=metrics.previous_price,
                average_7d=metrics.average_7d,
                average_30d=metrics.average_30d,
                average_90d=metrics.average_90d,
                low_30d=metrics.low_30d,
                low_90d=metrics.low_90d,
                historical_low=metrics.historical_low,
                historical_high=metrics.historical_high,
                advertised_discount=metrics.advertised_discount,
                discount_from_30d=metrics.real_discount_30d,
                discount_from_90d=metrics.real_discount_90d,
                price_drop_amount=metrics.price_drop_amount,
                price_drop_percent=metrics.price_drop_percent,
                opportunity_score=score.total,
                reason=self._reason(metrics.real_discount_30d, score.total),
                status=(
                    OpportunityStatus.REVIEW_REQUIRED
                    if manual_review
                    else OpportunityStatus.READY
                ),
                duplicate_key=f"{listing.id}:{item.current_price}:{bucket}",
                detected_at=now,
            )
            session.add(opportunity)
            await session.flush()
            product_name = None
            if self.ai_polisher is not None:
                try:
                    product_name = await self.ai_polisher.shorten_name(
                        {
                            "product_name": product.canonical_name,
                            "brand": product.brand,
                            "category": product.category,
                            "store": store.name,
                            "current_price": float(opportunity.current_price),
                            "previous_price": (
                                float(opportunity.previous_price)
                                if opportunity.previous_price is not None
                                else None
                            ),
                            "average_30d": (
                                float(opportunity.average_30d)
                                if opportunity.average_30d is not None
                                else None
                            ),
                            "historical_low": (
                                float(opportunity.historical_low)
                                if opportunity.historical_low is not None
                                else None
                            ),
                            "opportunity_score": opportunity.opportunity_score,
                        }
                    )
                except Exception as error:
                    logger.warning(
                        "opportunity_ai_polish_failed",
                        store=store.slug,
                        product_id=product.id,
                        opportunity_id=opportunity.id,
                        operation="ai_polish",
                        error=f"{type(error).__name__}: {error}",
                    )
            generated = self.post_generator.generate(
                opportunity, product_name=product_name
            )
            post = await repository.create_post(
                opportunity.id, generated.text, generated.template_name
            )
            await session.commit()
            logger.info(
                "opportunity_created",
                store=store.slug,
                external_product_id=item.external_product_id,
                product_id=product.id,
                listing_id=listing.id,
                opportunity_id=opportunity.id,
                operation="detect_opportunity",
                price=str(item.current_price),
                score=score.total,
            )
            return post.id

    @staticmethod
    async def _upsert_store(
        session: AsyncSession,
        repository: CommerceRepository,
        adapter: StoreAdapter,
    ) -> Store:
        store = await repository.get_store_by_slug(adapter.slug)
        if store is None:
            store = Store(
                name=adapter.name,
                slug=adapter.slug,
                base_url=adapter.base_url,
                active=True,
                adapter_type=adapter.adapter_type,
                affiliate_enabled=adapter.affiliate_enabled,
                data_source_type=adapter.data_source_type,
                terms_url=adapter.terms_url,
                notes=adapter.notes,
            )
            session.add(store)
            await session.flush()
        else:
            store.name = adapter.name
            store.base_url = adapter.base_url
            store.adapter_type = adapter.adapter_type
            store.affiliate_enabled = adapter.affiliate_enabled
            store.data_source_type = adapter.data_source_type
            store.terms_url = adapter.terms_url
            store.notes = adapter.notes
            store.active = True
        return store

    @staticmethod
    def _advertised_discount(item: StoreProduct) -> float | None:
        if not item.original_price or item.original_price <= 0:
            return None
        return round(
            max(
                0,
                float(
                    (item.original_price - item.current_price)
                    / item.original_price
                    * 100
                ),
            ),
            2,
        )

    @staticmethod
    def _reason(discount_30d: float | None, score: float) -> str:
        if discount_30d is None:
            return f"Fiyat düşüşü ve kalite sinyalleri; skor {score:.1f}/100"
        return f"30 günlük ortalamadan %{discount_30d:.1f} düşük; skor {score:.1f}/100"

    async def close(self) -> None:
        for adapter in self.adapters:
            await adapter.close()
