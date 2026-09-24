from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.models.opportunity import Opportunity


def format_try(value: Decimal | None) -> str:
    if value is None:
        return "Yeterli veri yok"
    rendered = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if rendered.endswith(",00"):
        rendered = rendered[:-3]
    return f"{rendered} TL"


@dataclass(slots=True, frozen=True)
class GeneratedOpportunityText:
    text: str
    template_name: str


class OpportunityPostGenerator:
    def __init__(self, affiliate_disclosure: str = "#reklam") -> None:
        self.affiliate_disclosure = affiliate_disclosure.strip()

    def generate(
        self, opportunity: Opportunity, *, product_name: str | None = None
    ) -> GeneratedOpportunityText:
        product = opportunity.product
        listing = opportunity.listing
        store = opportunity.store
        link = listing.affiliate_url or listing.product_url
        disclosure = (
            f"\n\n{self.affiliate_disclosure}"
            if listing.affiliate_url and self.affiliate_disclosure
            else ""
        )
        real_discount = opportunity.discount_from_30d
        discount_line = (
            f"\n📉 30 günlük ortalamaya göre %{real_discount:.1f} daha ucuz"
            if real_discount is not None
            else "\n📊 Fiyat geçmişi henüz sınırlı"
        )
        if (
            opportunity.low_90d is not None
            and opportunity.current_price <= opportunity.low_90d * Decimal("1.02")
        ):
            template = "near_90d_low"
            text = (
                "🚨 Son 90 günün en düşük fiyatlarından biri!\n\n"
                f"{product_name or product.canonical_name}\n\n"
                f"💰 {format_try(opportunity.current_price)}\n"
                f"30 günlük ortalama: {format_try(opportunity.average_30d)}"
                f"{discount_line}\n\n"
                f"⭐ Fırsat skoru: {opportunity.opportunity_score:.0f}/100\n"
                f"🛒 {store.name}{disclosure}\n\n🔗 {link}"
            )
        else:
            template = "price_drop"
            previous = (
                f"❌ Önceki: {format_try(opportunity.previous_price)}\n"
                if opportunity.previous_price is not None
                else ""
            )
            text = (
                "🔥 Fiyat düştü!\n\n"
                f"{product_name or product.canonical_name}\n\n"
                f"{previous}✅ Şimdi: {format_try(opportunity.current_price)}"
                f"{discount_line}\n"
                f"⭐ Fırsat skoru: {opportunity.opportunity_score:.0f}/100\n\n"
                f"🛒 {store.name}{disclosure}\n\n🔗 {link}"
            )
        return GeneratedOpportunityText(text=text, template_name=template)
