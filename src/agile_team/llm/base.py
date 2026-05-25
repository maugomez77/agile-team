from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        """Generate a text completion from a prompt."""

    @abstractmethod
    async def chat(
        self, messages: list[dict[str, str]], system_prompt: str = "", **kwargs
    ) -> str:
        """Generate a response from chat messages."""

    async def vision(self, prompt: str, image_path: str, **kwargs) -> str:
        """Describe/analyze an image. Default raises if not supported."""
        raise NotImplementedError(f"Vision not supported by {self.__class__.__name__}")

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier."""


class LLMFactory:
    """Factory to create LLM providers from configuration."""

    _registry: dict[str, type[LLMProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_cls: type[LLMProvider]) -> None:
        cls._registry[name] = provider_cls

    @classmethod
    def create(cls, provider: str, model: str, base_url: str = "", api_key: str = "", **kwargs: Any) -> LLMProvider:
        if provider not in cls._registry:
            raise ValueError(
                f"Unknown provider '{provider}'. Available: {list(cls._registry)}"
            )
        provider_cls = cls._registry[provider]
        return provider_cls(model=model, base_url=base_url, api_key=api_key, **kwargs)  # pyright: ignore[reportCallIssue]
