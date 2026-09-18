import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_groq_provider_requires_key_when_scheduler_is_enabled() -> None:
    with pytest.raises(ValidationError, match="GROQ_API_KEY"):
        Settings(
            _env_file=None,
            ai_provider="groq",
            scheduler_enabled=True,
            groq_api_key=None,
        )


def test_groq_provider_accepts_key_and_default_model() -> None:
    settings = Settings(
        _env_file=None,
        ai_provider="groq",
        scheduler_enabled=True,
        groq_api_key="gsk_test-key-for-validation",
    )

    assert settings.groq_model == "openai/gpt-oss-20b"
    assert settings.groq_reasoning_effort == "low"
    assert settings.groq_max_completion_tokens == 512
    assert settings.ai_min_request_interval_seconds == 12
