from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.integrations.ai.groq_client import GroqClient
from app.models.generated_post import PostCategory


async def test_groq_client_requests_strict_structured_output() -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"post_text":"Kısa haber",'
                            '"category":"general","confidence":0.9}'
                        )
                    )
                )
            ]
        )
    )
    client = GroqClient(
        api_key="gsk_test-key", model="openai/gpt-oss-20b", timeout_seconds=15
    )
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    result = await client.generate(system_prompt="Sistem", user_prompt="Haber")

    assert result.post_text == "Kısa haber"
    assert result.category == PostCategory.GENERAL
    kwargs = create.await_args.kwargs
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["max_completion_tokens"] == 512
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert (
        kwargs["response_format"]["json_schema"]["schema"]["additionalProperties"]
        is False
    )
