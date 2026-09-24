from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app.integrations.stores.base import StoreAdapter
from app.integrations.telegram.telegram_bot import (
    approval_keyboard,
    blocked_source_text,
    build_application,
    notification_text,
    opportunity_keyboard,
    opportunity_notification_text,
    opportunity_x_share_keyboard,
    x_share_keyboard,
    x_share_text,
)
from app.models.article import ArticleStatus
from app.models.generated_post import GeneratedPost, PostStatus
from app.models.opportunity import OpportunityStatus
from app.models.opportunity_post import OpportunityPost, OpportunityPostStatus
from app.models.price_history import PriceHistory
from app.repositories.article_repository import ArticleRepository
from app.repositories.commerce_repository import CommerceRepository
from app.repositories.post_repository import PostRepository
from app.schemas.generated_post import GeneratedPostValidation
from app.services.content_workflow import ContentWorkflow
from app.services.opportunity_detector import OpportunityDetector
from app.services.opportunity_post_generator import OpportunityPostGenerator, format_try

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
        affiliate_disclosure: str = "#reklam",
        store_adapters: list[StoreAdapter] | None = None,
    ) -> None:
        self.chat_id = chat_id
        self.allowed_user_id = allowed_user_id
        self.session_factory = session_factory
        self.max_post_length = max_post_length
        self.max_source_similarity = max_source_similarity
        self.content_workflow = content_workflow
        self.affiliate_disclosure = affiliate_disclosure
        self.store_adapters = {
            adapter.slug: adapter for adapter in (store_adapters or [])
        }
        self.application = build_application(token)
        self.application.add_handler(
            CallbackQueryHandler(
                self._on_callback,
                pattern=(
                    r"^(approve|reject|edit|show|regenerate|deal_approve|"
                    r"deal_reject|deal_edit|deal_show|deal_regenerate|"
                    r"deal_history):\d+$"
                ),
            )
        )
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text)
        )

    def set_store_adapters(self, adapters: list[StoreAdapter]) -> None:
        self.store_adapters = {adapter.slug: adapter for adapter in adapters}

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

    async def notify_opportunity_post(self, post_id: int) -> None:
        async with self.session_factory() as session:
            post = await CommerceRepository(session).get_post(post_id, full=True)
            if post is None or post.status != OpportunityPostStatus.READY:
                return
            opportunity = post.opportunity
            if opportunity.status not in {
                OpportunityStatus.READY,
                OpportunityStatus.REVIEW_REQUIRED,
            }:
                return
            try:
                message = await self.application.bot.send_message(
                    chat_id=self.chat_id,
                    text=opportunity_notification_text(post),
                    parse_mode=ParseMode.HTML,
                    reply_markup=opportunity_keyboard(
                        post.id, product_url=opportunity.listing.product_url
                    ),
                    disable_web_page_preview=True,
                )
                post.telegram_message_id = message.message_id
                post.telegram_sent_at = datetime.now(UTC)
                post.telegram_error = None
                post.next_notification_at = None
                if opportunity.status == OpportunityStatus.READY:
                    opportunity.status = OpportunityStatus.TELEGRAM_SENT
            except Exception as error:
                post.notification_attempts += 1
                delay = min(60 * (2 ** (post.notification_attempts - 1)), 3600)
                post.next_notification_at = datetime.now(UTC) + timedelta(seconds=delay)
                post.telegram_error = f"{type(error).__name__}: {error}"[:2000]
                logger.exception(
                    "opportunity_notification_failed",
                    post_id=post.id,
                    opportunity_id=opportunity.id,
                    listing_id=opportunity.product_listing_id,
                    store=opportunity.store.slug,
                    operation="telegram_send",
                    error=post.telegram_error,
                )
            await session.commit()

    async def retry_pending_opportunities(self) -> None:
        async with self.session_factory() as session:
            post_ids = [
                post.id for post in await CommerceRepository(session).pending_posts()
            ]
        for post_id in post_ids:
            await self.notify_opportunity_post(post_id)

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
        if action.startswith("deal_"):
            await self._on_opportunity_callback(
                update, context, action.removeprefix("deal_"), post_id
            )
            return
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

    async def _on_opportunity_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        action: str,
        post_id: int,
    ) -> None:
        query = update.callback_query
        if action == "show":
            await self._show_opportunity_post(update, post_id)
        elif action == "edit":
            context.user_data["editing_opportunity_post_id"] = post_id
            if query and query.message:
                await query.message.reply_text(
                    "Yeni fırsat gönderisi metnini gönderin."
                )
        elif action == "approve":
            await self._approve_opportunity(update, post_id)
        elif action == "reject":
            await self._reject_opportunity(update, post_id)
        elif action == "regenerate":
            await self._regenerate_opportunity(update, post_id)
        elif action == "history":
            await self._show_price_history(update, post_id)

    async def _show_opportunity_post(self, update: Update, post_id: int) -> None:
        query = update.callback_query
        async with self.session_factory() as session:
            post = await CommerceRepository(session).get_post(post_id, full=True)
            if query and query.message:
                if post is None:
                    await query.message.reply_text("Fırsat gönderisi bulunamadı.")
                else:
                    await query.message.reply_text(
                        post.final_text or post.text,
                        reply_markup=opportunity_x_share_keyboard(post),
                        disable_web_page_preview=True,
                    )

    async def _approve_opportunity(self, update: Update, post_id: int) -> None:
        query = update.callback_query
        async with self.session_factory() as session:
            repository = CommerceRepository(session)
            post = await repository.get_post(post_id, full=True)
            if post is not None:
                adapter = self.store_adapters.get(post.opportunity.store.slug)
                if adapter is not None:
                    try:
                        live_price = await adapter.get_current_price(
                            post.opportunity.listing.external_product_id
                        )
                        if live_price is not None:
                            post.opportunity.listing.current_price = live_price
                    except Exception as error:
                        logger.warning(
                            "opportunity_live_price_check_failed",
                            store=post.opportunity.store.slug,
                            opportunity_id=post.opportunity.id,
                            listing_id=post.opportunity.product_listing_id,
                            operation="approval_price_check",
                            error=f"{type(error).__name__}: {error}",
                        )
            reply_markup = None
            if post is None:
                message = "Fırsat gönderisi bulunamadı."
            elif post.status == OpportunityPostStatus.APPROVED:
                message = "Bu fırsat zaten onaylandı."
                reply_markup = opportunity_x_share_keyboard(post)
            elif post.status == OpportunityPostStatus.REJECTED:
                message = "Bu fırsat daha önce reddedildi."
            elif post.opportunity.status == OpportunityStatus.EXPIRED:
                message = "⚠️ Bu fırsat artık geçerli değil; onaylanmadı."
            elif (
                post.opportunity.listing.current_price != post.opportunity.current_price
            ):
                old_price = post.opportunity.current_price
                new_price = post.opportunity.listing.current_price
                post.opportunity.status = OpportunityStatus.EXPIRED
                await session.commit()
                message = (
                    "⚠️ Fiyat değişti.\n\n"
                    f"Eski fiyat: {format_try(old_price)}\n"
                    f"Yeni fiyat: {format_try(new_price)}\n\n"
                    "Fırsat expired yapıldı ve onaylanmadı."
                )
            elif post.opportunity.status == OpportunityStatus.REVIEW_REQUIRED:
                message = (
                    "Bu ürün eşleşmesi manuel inceleme gerektiriyor. "
                    "Önce metni düzenleyin veya ürünü doğrulayın."
                )
            else:
                now = datetime.now(UTC)
                siblings = await session.scalars(
                    select(OpportunityPost).where(
                        OpportunityPost.opportunity_id == post.opportunity_id,
                        OpportunityPost.id != post.id,
                        OpportunityPost.status == OpportunityPostStatus.READY,
                    )
                )
                for sibling in siblings:
                    sibling.status = OpportunityPostStatus.REJECTED
                    sibling.rejected_at = now
                post.status = OpportunityPostStatus.APPROVED
                post.approved_at = now
                post.opportunity.status = OpportunityStatus.APPROVED
                post.opportunity.approved_at = now
                await session.commit()
                message = "✅ Fırsat onaylandı. X paylaşım ekranını açabilirsiniz."
                reply_markup = opportunity_x_share_keyboard(post)
            if query and query.message:
                await query.message.reply_text(message, reply_markup=reply_markup)

    async def _reject_opportunity(self, update: Update, post_id: int) -> None:
        query = update.callback_query
        async with self.session_factory() as session:
            post = await CommerceRepository(session).get_post(post_id, full=True)
            if post is None:
                message = "Fırsat gönderisi bulunamadı."
            elif post.status == OpportunityPostStatus.REJECTED:
                message = "Bu fırsat zaten reddedildi."
            elif post.status == OpportunityPostStatus.APPROVED:
                message = "Bu fırsat daha önce onaylandı."
            else:
                now = datetime.now(UTC)
                post.status = OpportunityPostStatus.REJECTED
                post.rejected_at = now
                post.opportunity.status = OpportunityStatus.REJECTED
                post.opportunity.rejected_at = now
                await session.commit()
                message = "❌ Fırsat reddedildi."
            if query and query.message:
                await query.message.reply_text(message)

    async def _regenerate_opportunity(self, update: Update, post_id: int) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        async with self.session_factory() as session:
            repository = CommerceRepository(session)
            post = await repository.get_post(post_id, full=True)
            if post is None:
                await query.message.reply_text("Fırsat gönderisi bulunamadı.")
                return
            generated = OpportunityPostGenerator(self.affiliate_disclosure).generate(
                post.opportunity
            )
            new_post = await repository.create_post(
                post.opportunity_id, generated.text, generated.template_name
            )
            await session.commit()
            new_post_id = new_post.id
        await self.notify_opportunity_post(new_post_id)
        await query.message.reply_text(
            "Yeni sürüm kayıtlı fırsat verisinden oluşturuldu."
        )

    async def _show_price_history(self, update: Update, post_id: int) -> None:
        query = update.callback_query
        async with self.session_factory() as session:
            repository = CommerceRepository(session)
            post = await repository.get_post(post_id, full=True)
            if post is None:
                message = "Fırsat gönderisi bulunamadı."
            else:
                rows = list(
                    (
                        await session.scalars(
                            select(PriceHistory).where(
                                PriceHistory.product_listing_id
                                == post.opportunity.product_listing_id
                            )
                        )
                    ).all()
                )
                metrics = OpportunityDetector().analyze(
                    current_price=post.opportunity.listing.current_price,
                    previous_price=None,
                    original_price=None,
                    history=rows,
                )
                message = (
                    f"{post.opportunity.product.canonical_name}\n\n"
                    f"7 gün ortalama: {format_try(metrics.average_7d)}\n"
                    f"30 gün ortalama: {format_try(metrics.average_30d)}\n"
                    f"90 gün ortalama: {format_try(metrics.average_90d)}\n\n"
                    f"30 gün en düşük: {format_try(metrics.low_30d)}\n"
                    f"90 gün en düşük: {format_try(metrics.low_90d)}\n\n"
                    f"Mevcut: {format_try(metrics.current_price)}"
                )
            if query and query.message:
                await query.message.reply_text(message)

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
        opportunity_post_id = context.user_data.get("editing_opportunity_post_id")
        if opportunity_post_id is not None:
            await self._edit_opportunity_post(update, context, int(opportunity_post_id))
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

    async def _edit_opportunity_post(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        post_id: int,
    ) -> None:
        assert update.message is not None
        text = (update.message.text or "").strip()
        if not text or len(text) > 1000:
            await update.message.reply_text(
                "Metin boş olamaz ve 1.000 karakteri geçemez. Tekrar gönderin."
            )
            return
        async with self.session_factory() as session:
            post = await CommerceRepository(session).get_post(post_id, full=True)
            if post is None or post.status != OpportunityPostStatus.READY:
                context.user_data.pop("editing_opportunity_post_id", None)
                await update.message.reply_text("Düzenlenebilir fırsat bulunamadı.")
                return
            post.final_text = text
            post.edited_by_user = True
            if post.opportunity.status == OpportunityStatus.REVIEW_REQUIRED:
                post.opportunity.status = OpportunityStatus.READY
            product_url = post.opportunity.listing.product_url
            await session.commit()
        context.user_data.pop("editing_opportunity_post_id", None)
        await update.message.reply_text(
            "Metin kaydedildi:\n\n" + text,
            reply_markup=opportunity_keyboard(
                post_id, product_url=product_url, edited=True
            ),
        )
