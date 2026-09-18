from html import escape
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder

from app.models.generated_post import GeneratedPost

X_POST_MAX_LENGTH = 280
X_URL_LENGTH = 23


def build_application(token: str) -> Application:
    return ApplicationBuilder().token(token).build()


def approval_keyboard(post_id: int, *, edited: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("✅ Onayla", callback_data=f"approve:{post_id}"),
            InlineKeyboardButton("❌ Reddet", callback_data=f"reject:{post_id}"),
        ]
    ]
    if not edited:
        rows.append(
            [
                InlineKeyboardButton("✏️ Düzenle", callback_data=f"edit:{post_id}"),
                InlineKeyboardButton(
                    "📋 Metni Göster", callback_data=f"show:{post_id}"
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


def notification_text(post: GeneratedPost) -> str:
    article = post.article
    source = article.source
    return (
        "🚨 <b>YENİ HABER</b>\n\n"
        f"<b>Başlık:</b>\n{escape(article.title)}\n\n"
        f"<b>Kaynak:</b>\n{escape(source.name)}\n\n"
        f"<b>Güvenilirlik:</b>\n{article.credibility_score}/10\n\n"
        f"<b>AI Gönderisi:</b>\n\n{escape(post.final_text or post.text)}\n\n"
        f'<b>Haber:</b>\n<a href="{escape(article.url, quote=True)}">Haberi aç</a>'
    )
