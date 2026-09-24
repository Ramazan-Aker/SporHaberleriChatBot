from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.opportunity_post import OpportunityPost, OpportunityPostStatus
from app.models.price_history import PriceHistory
from app.models.product import Product
from app.models.product_listing import ProductListing
from app.models.store import Store


class CommerceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_store_by_slug(self, slug: str) -> Store | None:
        return await self.session.scalar(select(Store).where(Store.slug == slug))

    async def list_stores(self, *, active_only: bool = False) -> list[Store]:
        statement = select(Store).order_by(Store.name)
        if active_only:
            statement = statement.where(Store.active.is_(True))
        return list((await self.session.scalars(statement)).all())

    async def get_listing(
        self, store_id: int, external_product_id: str
    ) -> ProductListing | None:
        return await self.session.scalar(
            select(ProductListing).where(
                ProductListing.store_id == store_id,
                ProductListing.external_product_id == external_product_id,
            )
        )

    async def get_product(self, product_id: int) -> Product | None:
        return await self.session.get(Product, product_id)

    async def list_products(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        category: str | None = None,
        store_slug: str | None = None,
    ) -> list[Product]:
        statement: Select[tuple[Product]] = select(Product).distinct()
        if category:
            statement = statement.where(Product.category == category)
        if store_slug:
            statement = (
                statement.join(Product.listings)
                .join(ProductListing.store)
                .where(Store.slug == store_slug)
            )
        statement = statement.order_by(Product.id).offset(offset).limit(limit)
        return list((await self.session.scalars(statement)).all())

    async def list_listings(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        store_slug: str | None = None,
        category: str | None = None,
    ) -> list[ProductListing]:
        statement: Select[tuple[ProductListing]] = select(ProductListing).options(
            selectinload(ProductListing.product), selectinload(ProductListing.store)
        )
        if store_slug:
            statement = statement.join(ProductListing.store).where(
                Store.slug == store_slug
            )
        if category:
            statement = statement.join(ProductListing.product).where(
                Product.category == category
            )
        statement = statement.order_by(ProductListing.id).offset(offset).limit(limit)
        return list((await self.session.scalars(statement)).all())

    async def price_history(
        self, product_id: int, *, offset: int = 0, limit: int = 200
    ) -> list[PriceHistory]:
        statement = (
            select(PriceHistory)
            .join(PriceHistory.listing)
            .where(ProductListing.product_id == product_id)
            .order_by(PriceHistory.captured_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def get_opportunity(
        self, opportunity_id: int, *, full: bool = False
    ) -> Opportunity | None:
        if not full:
            return await self.session.get(Opportunity, opportunity_id)
        statement = (
            select(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .options(
                selectinload(Opportunity.product),
                selectinload(Opportunity.store),
                selectinload(Opportunity.listing),
                selectinload(Opportunity.posts),
            )
        )
        return await self.session.scalar(statement)

    async def list_opportunities(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        store_slug: str | None = None,
        category: str | None = None,
        min_score: float | None = None,
        status: OpportunityStatus | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[Opportunity]:
        statement: Select[tuple[Opportunity]] = select(Opportunity)
        if store_slug:
            statement = statement.join(Opportunity.store).where(
                Store.slug == store_slug
            )
        if category:
            statement = statement.join(Opportunity.product).where(
                Product.category == category
            )
        if min_score is not None:
            statement = statement.where(Opportunity.opportunity_score >= min_score)
        if status:
            statement = statement.where(Opportunity.status == status)
        if date_from:
            statement = statement.where(Opportunity.detected_at >= date_from)
        if date_to:
            statement = statement.where(Opportunity.detected_at <= date_to)
        statement = (
            statement.order_by(Opportunity.detected_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def duplicate_opportunity_exists(
        self,
        *,
        listing_id: int,
        price: Decimal,
        cooldown_hours: int,
        now: datetime,
    ) -> bool:
        cutoff = now - timedelta(hours=cooldown_hours)
        statement = select(Opportunity.id).where(
            Opportunity.product_listing_id == listing_id,
            Opportunity.current_price == price,
            Opportunity.detected_at >= cutoff,
        )
        return await self.session.scalar(statement) is not None

    async def expire_stale_opportunities(
        self, listing_id: int, current_price: Decimal
    ) -> int:
        statement = select(Opportunity).where(
            Opportunity.product_listing_id == listing_id,
            Opportunity.status.in_(
                [
                    OpportunityStatus.DETECTED,
                    OpportunityStatus.READY,
                    OpportunityStatus.TELEGRAM_SENT,
                ]
            ),
            Opportunity.current_price != current_price,
        )
        opportunities = list((await self.session.scalars(statement)).all())
        for opportunity in opportunities:
            opportunity.status = OpportunityStatus.EXPIRED
        return len(opportunities)

    async def create_post(
        self, opportunity_id: int, text: str, template_name: str
    ) -> OpportunityPost:
        version = (
            await self.session.scalar(
                select(func.coalesce(func.max(OpportunityPost.version), 0)).where(
                    OpportunityPost.opportunity_id == opportunity_id
                )
            )
        ) + 1
        post = OpportunityPost(
            opportunity_id=opportunity_id,
            version=version,
            text=text,
            template_name=template_name,
        )
        self.session.add(post)
        await self.session.flush()
        return post

    async def get_post(
        self, post_id: int, *, full: bool = False
    ) -> OpportunityPost | None:
        if not full:
            return await self.session.get(OpportunityPost, post_id)
        statement = (
            select(OpportunityPost)
            .where(OpportunityPost.id == post_id)
            .options(
                selectinload(OpportunityPost.opportunity).selectinload(
                    Opportunity.product
                ),
                selectinload(OpportunityPost.opportunity).selectinload(
                    Opportunity.store
                ),
                selectinload(OpportunityPost.opportunity).selectinload(
                    Opportunity.listing
                ),
            )
        )
        return await self.session.scalar(statement)

    async def pending_posts(self, limit: int = 50) -> list[OpportunityPost]:
        now = datetime.now(UTC)
        statement = (
            select(OpportunityPost)
            .where(
                OpportunityPost.status == OpportunityPostStatus.READY,
                OpportunityPost.telegram_sent_at.is_(None),
                (
                    OpportunityPost.next_notification_at.is_(None)
                    | (OpportunityPost.next_notification_at <= now)
                ),
            )
            .order_by(OpportunityPost.created_at)
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())
