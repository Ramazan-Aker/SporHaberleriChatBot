from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder

from app.models.generated_post import GeneratedPost


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
