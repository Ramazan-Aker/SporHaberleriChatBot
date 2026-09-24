from html import escape
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder

from app.models.generated_post import GeneratedPost
from app.models.opportunity_post import OpportunityPost
from app.models.source import CommercialUseStatus, RSSUsageStatus
from app.schemas.facts import EventType, ExtractedFacts
from app.services.opportunity_post_generator import format_try

X_POST_MAX_LENGTH = 280
X_URL_LENGTH = 23


def build_application(token: str) -> Application:
    return ApplicationBuilder().token(token).build()


def approval_keyboard(
    post_id: int,
    *,
    source_url: str | None = None,
    edited: bool = False,
    review_required: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if not review_required:
        rows.append(
            [
                InlineKeyboardButton("✅ Onayla", callback_data=f"approve:{post_id}"),
                InlineKeyboardButton("❌ Reddet", callback_data=f"reject:{post_id}"),
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton("❌ Reddet", callback_data=f"reject:{post_id}")]
        )
    if not edited:
        rows.append(
            [
                InlineKeyboardButton("✏️ Düzenle", callback_data=f"edit:{post_id}"),
                InlineKeyboardButton(
                    "🔄 Yeniden Yaz", callback_data=f"regenerate:{post_id}"
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("📋 Metni Göster", callback_data=f"show:{post_id}"),
            *(
                [InlineKeyboardButton("🔗 Kaynağı Aç", url=source_url)]
                if source_url
                else []
            ),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    shortened = text[: max_length - 1].rsplit(" ", maxsplit=1)[0].rstrip()
    return (shortened or text[: max_length - 1]).rstrip() + "…"


def x_share_text(post: GeneratedPost) -> str:
    source_name = _truncate_text(post.article.source.name, 40)
    attribution = f"\n\nKaynak: {source_name}"
    # X wraps every HTTP(S) link to a fixed-length t.co URL. Leave one character
    # for the space before the separately supplied news URL.
    available = X_POST_MAX_LENGTH - X_URL_LENGTH - 1 - len(attribution)
    post_text = _truncate_text(post.final_text or post.text, available)
    return post_text + attribution


def x_share_url(post: GeneratedPost) -> str:
    query = urlencode({"text": x_share_text(post), "url": post.article.url})
    return f"https://twitter.com/intent/tweet?{query}"


def x_share_keyboard(post: GeneratedPost) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("𝕏'te Paylaş", url=x_share_url(post))]]
    )


def opportunity_keyboard(
    post_id: int, *, product_url: str, edited: bool = False
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("✅ Onayla", callback_data=f"deal_approve:{post_id}"),
            InlineKeyboardButton("❌ Reddet", callback_data=f"deal_reject:{post_id}"),
        ]
    ]
    if not edited:
        rows.append(
            [
                InlineKeyboardButton("✏️ Düzenle", callback_data=f"deal_edit:{post_id}"),
                InlineKeyboardButton(
                    "🔄 Yeniden Oluştur",
                    callback_data=f"deal_regenerate:{post_id}",
                ),
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    "📋 Metni Göster", callback_data=f"deal_show:{post_id}"
                ),
                InlineKeyboardButton("🔗 Ürünü Aç", url=product_url),
            ],
            [
                InlineKeyboardButton(
                    "📊 Fiyat Geçmişi", callback_data=f"deal_history:{post_id}"
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(rows)


def opportunity_x_share_url(post: OpportunityPost) -> str:
    opportunity = post.opportunity
    text = post.final_text or post.text
    link = opportunity.listing.affiliate_url or opportunity.listing.product_url
    available = X_POST_MAX_LENGTH - X_URL_LENGTH - 1
    body = text.replace(f"\n\n🔗 {link}", "").rstrip()
    if opportunity.listing.affiliate_url and "\n\n" in body:
        prefix, disclosure = body.rsplit("\n\n", maxsplit=1)
        prefix = _truncate_text(prefix, available - len(disclosure) - 2)
        body = f"{prefix}\n\n{disclosure}"
    else:
        body = _truncate_text(body, available)
    query = urlencode({"text": body, "url": link})
    return f"https://twitter.com/intent/tweet?{query}"


def opportunity_x_share_keyboard(post: OpportunityPost) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("𝕏'te Paylaş", url=opportunity_x_share_url(post))]]
    )


def opportunity_notification_text(post: OpportunityPost) -> str:
    opportunity = post.opportunity
    product = opportunity.product
    listing = opportunity.listing
    store = opportunity.store
    warning = (
        "\n⚠️ <b>Bu fırsat artık geçerli olmayabilir.</b>\n"
        if opportunity.status.value == "expired"
        else ""
    )
    discount = (
        f"%{opportunity.discount_from_30d:.1f} daha ucuz"
        if opportunity.discount_from_30d is not None
        else "Yeterli veri yok"
    )
    return (
        "🔥 <b>YENİ FIRSAT</b>\n\n"
        f"<b>📦 Ürün:</b>\n{escape(product.canonical_name)}\n\n"
        f"<b>🏪 Mağaza:</b>\n{escape(store.name)}\n\n"
        f"<b>💰 Güncel fiyat:</b>\n{format_try(opportunity.current_price)}\n\n"
        f"<b>↩️ Önceki fiyat:</b>\n{format_try(opportunity.previous_price)}\n\n"
        f"<b>📊 30 günlük ortalama:</b>\n{format_try(opportunity.average_30d)}\n\n"
        f"<b>📉 30 günlük ortalamaya göre:</b>\n{discount}\n\n"
        f"<b>🏆 90 günlük en düşük:</b>\n{format_try(opportunity.low_90d)}\n\n"
        f"<b>⭐ Fırsat skoru:</b>\n{opportunity.opportunity_score:.0f}/100\n\n"
        f"<b>📦 Stok:</b>\n{escape(listing.stock_status)}\n\n"
        f"<b>👤 Satıcı:</b>\n{escape(listing.seller_name or 'Bilinmiyor')}\n"
        f"{warning}\n"
        "<b>HAZIRLANAN GÖNDERİ:</b>\n\n"
        f"{escape(post.final_text or post.text)}\n\n"
        f'<b>🔗 Ürün:</b>\n<a href="{escape(listing.product_url, quote=True)}">'
        "Ürünü aç</a>"
    )


def notification_text(
    post: GeneratedPost, *, max_source_similarity: float = 0.55
) -> str:
    article = post.article
    source = article.source
    facts = (
        ExtractedFacts.model_validate(article.extracted_facts)
        if article.extracted_facts
        else None
    )
    event_labels = {
        EventType.TRANSFER: "Transfer",
        EventType.TRANSFER_RUMOR: "Transfer İddiası",
        EventType.OFFICIAL_TRANSFER: "Resmî Transfer",
        EventType.INJURY: "Sakatlık",
        EventType.MATCH_RESULT: "Maç Sonucu",
        EventType.LINEUP: "Kadro",
        EventType.STATEMENT: "Açıklama",
        EventType.STATISTICS: "İstatistik",
        EventType.DISCIPLINARY: "Disiplin",
        EventType.BREAKING_NEWS: "Son Dakika",
        EventType.GENERAL: "Genel",
    }
    commercial_labels = {
        CommercialUseStatus.UNKNOWN: "Bilinmiyor",
        CommercialUseStatus.ALLOWED: "İzinli",
        CommercialUseStatus.RESTRICTED: "Kısıtlı",
        CommercialUseStatus.PROHIBITED: "Yasak",
    }
    rss_labels = {
        RSSUsageStatus.UNKNOWN: "Bilinmiyor",
        RSSUsageStatus.ALLOWED: "İzinli",
        RSSUsageStatus.RESTRICTED: "Kısıtlı",
    }
    header = (
        "⚠️ <b>İÇERİK İNCELEMESİ GEREKİYOR</b>"
        if post.status.value == "review_required"
        else "🚨 <b>YENİ HABER</b>"
    )
    fact_lines = (
        "\n".join(f"• {escape(fact)}" for fact in (facts.facts[:6] if facts else []))
        or "• Structured FACT verisi bulunamadı"
    )
    similarity = (post.source_similarity or 0) * 100
    warning = ""
    if source.commercial_use_status == CommercialUseStatus.RESTRICTED:
        warning = "\n⚠️ Bu kaynağın ticari kullanım koşullarını kontrol et.\n"
    elif source.commercial_use_status == CommercialUseStatus.UNKNOWN:
        warning = "\n⚠️ Bu kaynağın ticari kullanım izni bilinmiyor.\n"
    review_reasons = ""
    if post.status.value == "review_required" and post.unsupported_claims:
        reasons = "\n".join(f"• {escape(reason)}" for reason in post.unsupported_claims)
        review_reasons = f"\n<b>İnceleme nedenleri:</b>\n{reasons}\n"
    return (
        f"{header}\n\n"
        f"<b>Tür:</b>\n{event_labels.get(facts.event_type, 'Genel') if facts else 'Genel'}\n\n"
        f"<b>Başlık:</b>\n{escape(article.title)}\n\n"
        f"<b>📰 Kaynak:</b>\n{escape(source.name)}\n\n"
        f"<b>⭐ Güvenilirlik:</b>\n{article.credibility_score}/10\n\n"
        f"<b>⚖️ Ticari Kullanım:</b>\n"
        f"{commercial_labels[source.commercial_use_status]}\n\n"
        f"<b>📡 RSS Kullanımı:</b>\n{rss_labels[source.rss_usage_status]}\n"
        f"{warning}\n"
        f"<b>🤖 AI Güven:</b>\n%{round(post.confidence * 100)}\n\n"
        f"<b>🔍 Kaynak Benzerliği:</b>\n%{round(similarity)}\n\n"
        f"<b>Benzerlik Limiti:</b>\n%{round(max_source_similarity * 100)}\n"
        f"{review_reasons}\n"
        f"<b>DOĞRULANAN BİLGİLER:</b>\n\n{fact_lines}\n\n"
        f"<b>HAZIRLANAN X GÖNDERİSİ:</b>\n\n"
        f"{escape(post.final_text or post.text)}\n\n"
        f'<b>🔗 Orijinal Haber:</b>\n<a href="{escape(article.url, quote=True)}">'
        "Kaynağı aç</a>"
    )


def blocked_source_text(article) -> str:
    source = article.source
    return (
        "⛔ <b>KAYNAK KULLANIM KISITLAMASI</b>\n\n"
        f"<b>Başlık:</b>\n{escape(article.title)}\n\n"
        f"<b>Kaynak:</b>\n{escape(source.name)}\n\n"
        f"<b>Ticari kullanım:</b>\n{source.commercial_use_status.value}\n\n"
        f"<b>RSS kullanımı:</b>\n{source.rss_usage_status.value}\n\n"
        "Bu haber için AI içeriği üretilmedi. Kaynak koşullarını manuel inceleyin.\n\n"
        f'<a href="{escape(article.url, quote=True)}">Orijinal haberi aç</a>'
    )
