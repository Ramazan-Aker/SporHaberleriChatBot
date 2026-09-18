from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app.integrations.telegram.telegram_bot import (
    approval_keyboard,
    build_application,
    notification_text,
    x_share_keyboard,
    x_share_text,
)
from app.models.article import ArticleStatus
from app.models.generated_post import GeneratedPost, PostStatus
from app.repositories.post_repository import PostRepository
from app.schemas.generated_post import GeneratedPostValidation

logger = structlog.get_logger(__name__)


class TelegramService:
    def __init__(
        self,
        *,
        token: str,
        chat_id: int,
        allowed_user_id: int,
        session_factory: async_sessionmaker[AsyncSession],
        max_post_length: int,
    ) -> None:
        self.chat_id = chat_id
        self.allowed_user_id = allowed_user_id
        self.session_factory = session_factory
        self.max_post_length = max_post_length
        self.application = build_application(token)
        self.application.add_handler(
            CallbackQueryHandler(
                self._on_callback,
                pattern=r"^(approve|reject|edit|show):\d+$",
            )
        )
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text)
        )

    async def start(self) -> None:
        await self.application.initialize()
        await self.application.start()
        if self.application.updater is None:
            raise RuntimeError("Telegram updater is unavailable")
        await self.application.updater.start_polling(drop_pending_updates=False)
        logger.info("telegram_started", operation="telegram_polling")

    async def stop(self) -> None:
        if self.application.updater and self.application.updater.running:
            await self.application.updater.stop()
        if self.application.running:
            await self.application.stop()
        await self.application.shutdown()
        logger.info("telegram_stopped", operation="telegram_polling")

    def _authorized(self, update: Update) -> bool:
        return bool(
            update.effective_user
            and update.effective_chat
            and update.effective_user.id == self.allowed_user_id
            and update.effective_chat.id == self.chat_id
        )

    async def notify_post(self, post_id: int) -> None:
        async with self.session_factory() as session:
            post = await PostRepository(session).get(post_id, with_article=True)
            if post is None or post.status != PostStatus.READY:
                return
            try:
                message = await self.application.bot.send_message(
                    chat_id=self.chat_id,
                    text=notification_text(post),
                    parse_mode=ParseMode.HTML,
                    reply_markup=approval_keyboard(post.id),
                    disable_web_page_preview=True,
                )
                post.telegram_message_id = message.message_id
                post.telegram_sent_at = datetime.now(UTC)
                post.telegram_error = None
                post.next_notification_at = None
            except Exception as error:
                post.notification_attempts += 1
                delay = min(60 * (2 ** (post.notification_attempts - 1)), 3600)
                post.next_notification_at = datetime.now(UTC) + timedelta(seconds=delay)
                post.telegram_error = f"{type(error).__name__}: {error}"[:2000]
                logger.exception(
                    "telegram_notification_failed",
                    post_id=post.id,
                    article_id=post.article_id,
                    operation="telegram_send",
                    error=post.telegram_error,
                )
            await session.commit()

    async def retry_pending(self) -> None:
        async with self.session_factory() as session:
            post_ids = [
                post.id
                for post in await PostRepository(session).pending_notifications()
            ]
        for post_id in post_ids:
            await self.notify_post(post_id)

    async def _on_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if query is None:
            return
        if not self._authorized(update):
            await query.answer("Bu işlem için yetkiniz yok.", show_alert=True)
            return
        await query.answer()
        action, raw_post_id = (query.data or "").split(":", maxsplit=1)
        post_id = int(raw_post_id)
        if action == "show":
            await self._show_post(update, post_id)
        elif action == "edit":
            context.user_data["editing_post_id"] = post_id
            if query.message:
                await query.message.reply_text("Yeni gönderi metnini gönderin.")
        elif action == "approve":
            await self._approve(update, post_id)
        elif action == "reject":
            await self._reject(update, post_id)

    async def _show_post(self, update: Update, post_id: int) -> None:
        query = update.callback_query
        async with self.session_factory() as session:
            post = await PostRepository(session).get(post_id, with_article=True)
            if query and query.message:
                if post is None:
                    await query.message.reply_text("Gönderi bulunamadı.")
                else:
                    await query.message.reply_text(
                        x_share_text(post) + "\n" + post.article.url,
                        reply_markup=x_share_keyboard(post),
                        disable_web_page_preview=True,
                    )

    async def _approve(self, update: Update, post_id: int) -> None:
        query = update.callback_query
        async with self.session_factory() as session:
            post = await PostRepository(session).get(post_id, with_article=True)
            reply_markup = None
            if post is None:
                message = "Gönderi bulunamadı."
            elif post.status == PostStatus.APPROVED:
                message = "Bu gönderi zaten onaylandı."
                reply_markup = x_share_keyboard(post)
            elif post.status == PostStatus.REJECTED:
                message = "Bu gönderi daha önce reddedildi."
            else:
                siblings = await session.scalars(
                    select(GeneratedPost).where(
                        GeneratedPost.article_id == post.article_id,
                        GeneratedPost.id != post.id,
                        GeneratedPost.status == PostStatus.READY,
                    )
                )
                now = datetime.now(UTC)
                for sibling in siblings:
                    sibling.status = PostStatus.REJECTED
                    sibling.rejected_at = now
                post.status = PostStatus.APPROVED
                post.approved_at = now
                post.article.status = ArticleStatus.APPROVED
                await session.commit()
                message = "✅ Gönderi onaylandı. X paylaşım ekranını açabilirsiniz."
                reply_markup = x_share_keyboard(post)
            if query and query.message:
                await query.message.reply_text(message, reply_markup=reply_markup)

    async def _reject(self, update: Update, post_id: int) -> None:
        query = update.callback_query
        async with self.session_factory() as session:
            post = await PostRepository(session).get(post_id, with_article=True)
            if post is None:
                message = "Gönderi bulunamadı."
            elif post.status == PostStatus.REJECTED:
                message = "Bu gönderi zaten reddedildi."
            elif post.status == PostStatus.APPROVED:
                message = "Bu gönderi daha önce onaylandı."
            else:
                post.status = PostStatus.REJECTED
                post.rejected_at = datetime.now(UTC)
                remaining = await session.scalar(
                    select(GeneratedPost.id).where(
                        GeneratedPost.article_id == post.article_id,
                        GeneratedPost.id != post.id,
                        GeneratedPost.status == PostStatus.READY,
                    )
                )
                if remaining is None:
                    post.article.status = ArticleStatus.REJECTED
                await session.commit()
                message = "❌ Gönderi reddedildi."
            if query and query.message:
                await query.message.reply_text(message)

    async def _on_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._authorized(update) or update.message is None:
            return
        post_id = context.user_data.get("editing_post_id")
        if post_id is None:
            return
        try:
            validated = GeneratedPostValidation(
                text=update.message.text or "", max_length=self.max_post_length
            )
        except ValueError as error:
            await update.message.reply_text(
                f"Metin geçersiz: {error}. Lütfen yeni metni tekrar gönderin."
            )
            return

        async with self.session_factory() as session:
            post = await PostRepository(session).get(int(post_id))
            if post is None or post.status != PostStatus.READY:
                context.user_data.pop("editing_post_id", None)
                await update.message.reply_text("Düzenlenebilir gönderi bulunamadı.")
                return
            post.final_text = validated.text
            post.edited_by_user = True
            await session.commit()
        context.user_data.pop("editing_post_id", None)
        await update.message.reply_text(
            "Metin kaydedildi:\n\n" + validated.text,
            reply_markup=approval_keyboard(int(post_id), edited=True),
        )
