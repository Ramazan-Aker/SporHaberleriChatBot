from openai import AsyncOpenAI

from app.schemas.generated_post import GeneratedPostContent


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
        response = await self._client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text_format=GeneratedPostContent,
            store=False,
        )
        if response.output_parsed is None:
            raise ValueError("OpenAI did not return a parseable post")
        return response.output_parsed
