from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app.integrations.telegram.telegram_bot import (
    approval_keyboard,
    blocked_source_text,
    build_application,
    notification_text,
    x_share_keyboard,
    x_share_text,
)
from app.models.article import ArticleStatus
from app.models.generated_post import GeneratedPost, PostStatus
from app.repositories.article_repository import ArticleRepository
from app.repositories.post_repository import PostRepository
from app.schemas.generated_post import GeneratedPostValidation
from app.services.content_workflow import ContentWorkflow

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
        max_source_similarity: float = 0.55,
        content_workflow: ContentWorkflow | None = None,
    ) -> None:
        self.chat_id = chat_id
        self.allowed_user_id = allowed_user_id
        self.session_factory = session_factory
        self.max_post_length = max_post_length
        self.max_source_similarity = max_source_similarity
        self.content_workflow = content_workflow
        self.application = build_application(token)
        self.application.add_handler(
            CallbackQueryHandler(
                self._on_callback,
                pattern=r"^(approve|reject|edit|show|regenerate):\d+$",
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
            if post is None or post.status not in {
                PostStatus.READY,
                PostStatus.REVIEW_REQUIRED,
            }:
                return
            try:
                message = await self.application.bot.send_message(
                    chat_id=self.chat_id,
                    text=notification_text(
                        post, max_source_similarity=self.max_source_similarity
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=approval_keyboard(
                        post.id,
                        source_url=post.article.url,
                        review_required=post.status == PostStatus.REVIEW_REQUIRED,
                    ),
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

    async def notify_blocked_article(self, article_id: int) -> None:
        async with self.session_factory() as session:
            article = await ArticleRepository(session).get(article_id, with_source=True)
            if article is None:
                return
            await self.application.bot.send_message(
                chat_id=self.chat_id,
                text=blocked_source_text(article),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

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
        elif action == "regenerate":
            await self._regenerate(update, post_id)

    async def _regenerate(self, update: Update, post_id: int) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        if self.content_workflow is None:
            await query.message.reply_text("Yeniden yazma servisi etkin değil.")
            return
        async with self.session_factory() as session:
            post = await PostRepository(session).get(post_id, with_article=True)
            if post is None:
                await query.message.reply_text("Gönderi bulunamadı.")
                return
            article_id = post.article_id
        await query.message.reply_text(
            "🔄 Kayıtlı bilgilerden yeni metin hazırlanıyor."
        )
        try:
            result = await self.content_workflow.regenerate(article_id)
            if result.post_id is None:
                await query.message.reply_text("Yeni metin üretilemedi.")
                return
            await self.notify_post(result.post_id)
            await query.message.reply_text("Yeni sürüm Telegram'a gönderildi.")
        except Exception as error:
            logger.exception(
                "telegram_regeneration_failed",
                post_id=post_id,
                article_id=article_id,
                operation="regenerate",
                error=f"{type(error).__name__}: {error}",
            )
            await query.message.reply_text("Yeniden yazma sırasında hata oluştu.")

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
            elif post.status == PostStatus.REVIEW_REQUIRED:
                message = (
                    "Bu gönderi içerik incelemesi gerektiriyor. Önce düzenleyin "
                    "veya yeniden yazın."
                )
            else:
                siblings = await session.scalars(
                    select(GeneratedPost).where(
                        GeneratedPost.article_id == post.article_id,
                        GeneratedPost.id != post.id,
                        GeneratedPost.status.in_(
                            [PostStatus.READY, PostStatus.REVIEW_REQUIRED]
                        ),
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
                        GeneratedPost.status.in_(
                            [PostStatus.READY, PostStatus.REVIEW_REQUIRED]
                        ),
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
            post = await PostRepository(session).get(int(post_id), with_article=True)
            if post is None or post.status not in {
                PostStatus.READY,
                PostStatus.REVIEW_REQUIRED,
            }:
                context.user_data.pop("editing_post_id", None)
                await update.message.reply_text("Düzenlenebilir gönderi bulunamadı.")
                return
            post.final_text = validated.text
            post.edited_by_user = True
            post.status = PostStatus.READY
            post.article.status = ArticleStatus.READY
            await session.commit()
        context.user_data.pop("editing_post_id", None)
        await update.message.reply_text(
            "Metin kaydedildi:\n\n" + validated.text,
            reply_markup=approval_keyboard(
                int(post_id),
                source_url=post.article.url,
                edited=True,
            ),
        )
