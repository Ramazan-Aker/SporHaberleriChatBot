from app.core.config import Settings
from app.integrations.ai.groq_client import GroqClient
from app.integrations.ai.openai_client import OpenAIClient


def create_ai_client(settings: Settings) -> OpenAIClient | GroqClient:
    if settings.ai_provider == "groq":
        return GroqClient(
            api_key=settings.groq_api_key or "",
            model=settings.groq_model,
            timeout_seconds=settings.http_timeout_seconds,
        )
    return OpenAIClient(
        api_key=settings.openai_api_key or "",
        model=settings.openai_model or "",
        timeout_seconds=settings.http_timeout_seconds,
    )
