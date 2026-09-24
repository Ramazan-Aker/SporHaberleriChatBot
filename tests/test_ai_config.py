import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_groq_provider_requires_key_when_ai_polish_is_enabled() -> None:
    with pytest.raises(ValidationError, match="GROQ_API_KEY"):
        Settings(
            _env_file=None,
            ai_provider="groq",
            scheduler_enabled=True,
            enable_ai_post_polish=True,
            groq_api_key=None,
        )


def test_groq_provider_accepts_key_and_default_model() -> None:
    settings = Settings(
        _env_file=None,
        ai_provider="groq",
        scheduler_enabled=True,
        enable_ai_post_polish=True,
        groq_api_key="gsk_test-key-for-validation",
    )

    assert settings.groq_model == "openai/gpt-oss-20b"
    assert settings.groq_reasoning_effort == "low"
    assert settings.groq_max_completion_tokens == 512
    assert settings.ai_min_request_interval_seconds == 12
    assert settings.max_source_similarity == 0.55
    assert settings.allow_external_media is False
    assert settings.allow_direct_quotes is False
    assert settings.enable_claim_validation is True
    assert settings.enable_source_policy_check is True


def test_production_amazon_requires_creators_api_credentials() -> None:
    with pytest.raises(ValidationError, match="AMAZON_CREDENTIAL_ID"):
        Settings(
            _env_file=None,
            scheduler_enabled=True,
            use_mock_store_data=False,
        )
