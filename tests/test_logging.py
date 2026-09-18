from app.core.logging import redact_secrets, safe_error


def test_redact_secrets_removes_credentials_from_log_text() -> None:
    telegram_token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
    openai_key = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    database_password = "super-secret-password"
    message = (
        f"POST https://api.telegram.org/bot{telegram_token}/getUpdates "
        f"Authorization: Bearer {openai_key} "
        f"postgresql+asyncpg://user:{database_password}@db.internal/app"
    )

    redacted = redact_secrets(message)

    assert telegram_token not in redacted
    assert openai_key not in redacted
    assert database_password not in redacted
    assert "https://api.telegram.org/bot<redacted>/getUpdates" in redacted


def test_safe_error_redacts_secret_in_exception_message() -> None:
    token = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"

    message = safe_error(RuntimeError(f"request failed for bot token {token}"))

    assert token not in message
    assert "<redacted-telegram-token>" in message
