from __future__ import annotations

from typing import Optional

import httpx

from agile_team.llm.base import LLMFactory, LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        api_key: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", self.temperature),
                    "num_predict": kwargs.get("max_tokens", self.max_tokens),
                },
            }
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json()["response"]

    async def chat(
        self, messages: list[dict[str, str]], system_prompt: str = "", **kwargs
    ) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", self.temperature),
                    "num_predict": kwargs.get("max_tokens", self.max_tokens),
                },
            }
            if system_prompt:
                payload["messages"] = [{"role": "system", "content": system_prompt}] + messages
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def vision(self, prompt: str, image_path: str, **kwargs) -> str:
        import base64
        from pathlib import Path

        img_bytes = Path(image_path).read_bytes()
        img_b64 = base64.b64encode(img_bytes).decode()

        async with httpx.AsyncClient(timeout=120) as client:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [img_b64],
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", self.temperature),
                },
            }
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json()["response"]


LLMFactory.register("ollama", OllamaProvider)
