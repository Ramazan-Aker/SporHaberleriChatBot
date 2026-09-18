from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.telegram.telegram_bot import approval_keyboard
from app.models.article import ArticleStatus
from app.models.generated_post import PostCategory, PostStatus
from app.repositories.article_repository import ArticleRepository
from app.repositories.post_repository import PostRepository
from app.repositories.source_repository import SourceRepository
from app.schemas.source import SourceCreate
from app.services.duplicate_detector import make_content_hash
from app.services.telegram_service import TelegramService


def test_keyboard_contains_expected_actions() -> None:
    keyboard = approval_keyboard(42)
    callbacks = [
        button.callback_data for row in keyboard.inline_keyboard for button in row
    ]
    assert callbacks == ["approve:42", "reject:42", "edit:42", "show:42"]


def test_telegram_authorization_requires_user_and_chat(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    service = TelegramService(
        token="123456:TEST_TOKEN",
        chat_id=100,
        allowed_user_id=200,
        session_factory=session_factory,
        max_post_length=260,
    )
    allowed = SimpleNamespace(
        effective_user=SimpleNamespace(id=200), effective_chat=SimpleNamespace(id=100)
    )
    wrong_user = SimpleNamespace(
        effective_user=SimpleNamespace(id=201), effective_chat=SimpleNamespace(id=100)
    )
    wrong_chat = SimpleNamespace(
        effective_user=SimpleNamespace(id=200), effective_chat=SimpleNamespace(id=101)
    )
    assert service._authorized(allowed)
    assert not service._authorized(wrong_user)
    assert not service._authorized(wrong_chat)


@pytest.mark.asyncio
async def test_approve_flow_updates_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        source = await SourceRepository(session).create(
            SourceCreate(
                name="Telegram Source",
                url="https://example.com",
                rss_url="https://example.com/telegram-feed",
                category="football",
                source_type="news",
                credibility_score=8,
            )
        )
        await session.flush()
        article = await ArticleRepository(session).create(
            source_id=source.id,
            title="Telegram akışı için yeterince uzun haber",
            description="Açıklama",
            url="https://example.com/telegram-news",
            published_at=None,
            content_hash=make_content_hash("Telegram akışı için yeterince uzun haber"),
            credibility_score=8,
            status=ArticleStatus.READY,
        )
        await session.flush()
        post = await PostRepository(session).create(
            article_id=article.id,
            text="İlk metin",
            ai_model="mock-model",
            category=PostCategory.GENERAL,
            confidence=0.9,
        )
        await session.commit()
        post_id = post.id

    service = TelegramService(
        token="123456:TEST_TOKEN",
        chat_id=100,
        allowed_user_id=200,
        session_factory=session_factory,
        max_post_length=260,
    )
    reply_text = AsyncMock()
    update = SimpleNamespace(
        callback_query=SimpleNamespace(message=SimpleNamespace(reply_text=reply_text))
    )
    await service._approve(update, post_id)

    async with session_factory() as session:
        loaded = await PostRepository(session).get(post_id, with_article=True)
        assert loaded is not None
        assert loaded.status == PostStatus.APPROVED
        assert loaded.article.status == ArticleStatus.APPROVED
