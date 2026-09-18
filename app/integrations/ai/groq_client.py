from openai import AsyncOpenAI

from app.schemas.generated_post import GeneratedPostContent


class GroqClient:
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
            base_url="https://api.groq.com/openai/v1",
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def generate(
        self, *, system_prompt: str, user_prompt: str
    ) -> GeneratedPostContent:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "generated_post",
                    "strict": True,
                    "schema": GeneratedPostContent.model_json_schema(),
                },
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq did not return a parseable post")
        return GeneratedPostContent.model_validate_json(content)
