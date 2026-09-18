from html import escape
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder

from app.models.generated_post import GeneratedPost
from app.models.source import CommercialUseStatus, RSSUsageStatus
from app.schemas.facts import EventType, ExtractedFacts

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
