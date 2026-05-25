from __future__ import annotations

import httpx

from agile_team.llm.base import LLMFactory, LLMProvider


class DeepSeekProvider(LLMProvider):
    """Provider for DeepSeek models via OpenAI-compatible API."""

    def __init__(
        self,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        api_key: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def provider_name(self) -> str:
        return "deepseek"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(messages, **kwargs)

    async def chat(
        self, messages: list[dict[str, str]], system_prompt: str = "", **kwargs
    ) -> str:
        msgs = list(messages)
        if system_prompt:
            msgs.insert(0, {"role": "system", "content": system_prompt})

        async with httpx.AsyncClient(timeout=120) as client:
            payload = {
                "model": self.model,
                "messages": msgs,
                "temperature": kwargs.get("temperature", self.temperature),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "stream": False,
            }
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class OpenAICompatibleProvider(DeepSeekProvider):
    """Generic provider for any OpenAI-compatible API (vLLM, LiteLLM, local models)."""

    @property
    def provider_name(self) -> str:
        return "openai_compatible"


LLMFactory.register("deepseek", DeepSeekProvider)
LLMFactory.register("openai_compatible", OpenAICompatibleProvider)
