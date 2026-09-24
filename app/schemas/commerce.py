from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.opportunity import OpportunityStatus
from app.models.store import DataSourceType


class StoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    base_url: str
    active: bool
    adapter_type: str
    affiliate_enabled: bool
    data_source_type: DataSourceType
    terms_url: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical_name: str
    brand: str | None
    model: str | None
    category: str | None
    sub_category: str | None
    gtin: str | None
    ean: str | None
    upc: str | None
    mpn: str | None
    normalized_key: str
    image_url: str | None
    popularity_score: float
    active: bool
    created_at: datetime
    updated_at: datetime


class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    store_id: int
    external_product_id: str
    title: str
    product_url: str
    affiliate_url: str | None
    seller_name: str | None
    seller_score: float | None
    current_price: Decimal
    currency: str
    original_price: Decimal | None
    discount_percent: float | None
    stock_status: str
    shipping_cost: Decimal | None
    last_seen_at: datetime
    active: bool
    created_at: datetime
    updated_at: datetime


class ProductDetail(ProductRead):
    listings: list[ListingRead]


class PriceHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_listing_id: int
    price: Decimal
    original_price: Decimal | None
    currency: str
    stock_status: str
    captured_at: datetime


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product_listing_id: int
    store_id: int
    current_price: Decimal
    previous_price: Decimal | None
    average_7d: Decimal | None
    average_30d: Decimal | None
    average_90d: Decimal | None
    low_30d: Decimal | None
    low_90d: Decimal | None
    historical_low: Decimal | None
    historical_high: Decimal | None
    advertised_discount: float | None
    discount_from_30d: float | None
    discount_from_90d: float | None
    price_drop_amount: Decimal | None
    price_drop_percent: float | None
    opportunity_score: float
    reason: str
    status: OpportunityStatus
    detected_at: datetime
    approved_at: datetime | None
    rejected_at: datetime | None
    published_at: datetime | None
