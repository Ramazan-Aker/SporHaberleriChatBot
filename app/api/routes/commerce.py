from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_session
from app.models.opportunity import OpportunityStatus
from app.models.product import Product
from app.repositories.commerce_repository import CommerceRepository
from app.schemas.commerce import (
    ListingRead,
    OpportunityRead,
    PriceHistoryRead,
    ProductDetail,
    ProductRead,
    StoreRead,
)

router = APIRouter(tags=["commerce"])


@router.get("/stores", response_model=list[StoreRead])
async def list_stores(
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[StoreRead]:
    stores = await CommerceRepository(session).list_stores(active_only=active_only)
    return [StoreRead.model_validate(store) for store in stores]


@router.get("/products", response_model=list[ProductRead])
async def list_products(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    store: str | None = None,
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ProductRead]:
    products = await CommerceRepository(session).list_products(
        offset=offset, limit=limit, category=category, store_slug=store
    )
    return [ProductRead.model_validate(product) for product in products]


@router.get("/products/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: int, session: AsyncSession = Depends(get_session)
) -> ProductDetail:
    product = await session.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(selectinload(Product.listings))
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductDetail.model_validate(product)


@router.get("/products/{product_id}/prices", response_model=list[PriceHistoryRead])
async def product_prices(
    product_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[PriceHistoryRead]:
    if await session.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    rows = await CommerceRepository(session).price_history(
        product_id, offset=offset, limit=limit
    )
    return [PriceHistoryRead.model_validate(row) for row in rows]


@router.get("/listings", response_model=list[ListingRead])
async def list_listings(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    store: str | None = None,
    category: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ListingRead]:
    listings = await CommerceRepository(session).list_listings(
        offset=offset, limit=limit, store_slug=store, category=category
    )
    return [ListingRead.model_validate(listing) for listing in listings]


@router.get("/opportunities", response_model=list[OpportunityRead])
async def list_opportunities(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    store: str | None = None,
    category: str | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    status: OpportunityStatus | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[OpportunityRead]:
    opportunities = await CommerceRepository(session).list_opportunities(
        offset=offset,
        limit=limit,
        store_slug=store,
        category=category,
        min_score=min_score,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return [OpportunityRead.model_validate(value) for value in opportunities]


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
async def get_opportunity(
    opportunity_id: int, session: AsyncSession = Depends(get_session)
) -> OpportunityRead:
    opportunity = await CommerceRepository(session).get_opportunity(opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return OpportunityRead.model_validate(opportunity)
