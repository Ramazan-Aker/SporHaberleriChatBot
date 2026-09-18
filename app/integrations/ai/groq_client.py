from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.schemas.generated_post import GeneratedPostContent

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class GroqClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        reasoning_effort: str = "low",
        max_completion_tokens: int = 512,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_completion_tokens = max_completion_tokens
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def generate(
        self, *, system_prompt: str, user_prompt: str
    ) -> GeneratedPostContent:
        return await self.parse(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=GeneratedPostContent,
        )

    async def parse(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            reasoning_effort=self.reasoning_effort,
            max_completion_tokens=self.max_completion_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__.lower(),
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq did not return parseable structured output")
        return response_model.model_validate_json(content)
