from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.schemas.generated_post import GeneratedPostContent

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class OpenAIClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
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
        response = await self._client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=response_model,
            store=False,
        )
        if response.output_parsed is None:
            raise ValueError("OpenAI did not return parseable structured output")
        return response.output_parsed
