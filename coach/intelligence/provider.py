from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from coach.config import Config, ConfigError
from coach.intelligence.exceptions import InferenceError


@dataclass
class InferenceRequest:
    system: str
    user: str
    max_tokens: int = 1024
    temperature: float = 0.4
    schema: dict[str, Any] | None = field(default=None, compare=False)


@dataclass
class InferenceResponse:
    text: str
    provider: str
    model: str | None = None


class InferenceProvider(ABC):
    def __init__(self, config: Config) -> None:
        self.config = config

    @abstractmethod
    def infer(self, request: InferenceRequest) -> InferenceResponse:
        """Run inference. Raises InferenceError on failure."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and reachable."""
        ...

    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def display_name(self) -> str:
        """Human-readable label shown in console output, e.g. 'anthropic / claude-3-5-sonnet'."""
        ...


def get_provider(config: Config) -> InferenceProvider:
    """Resolve the configured provider and verify it is available."""
    from coach.intelligence.providers.anthropic import AnthropicProvider
    from coach.intelligence.providers.apple import AppleIntelligenceProvider
    from coach.intelligence.providers.llamacpp import LlamaCppProvider
    from coach.intelligence.providers.ollama import OllamaProvider
    from coach.intelligence.providers.swift import SwiftInferenceProvider

    providers: dict[str, type[InferenceProvider]] = {
        "swift": SwiftInferenceProvider,
        "apple": AppleIntelligenceProvider,
        "ollama": OllamaProvider,
        "llamacpp": LlamaCppProvider,
        "anthropic": AnthropicProvider,
    }
    cls = providers.get(config.llm.provider)
    if cls is None:
        raise ConfigError(f"Unknown provider: {config.llm.provider!r}")
    provider = cls(config)
    if not provider.is_available():
        raise InferenceError(
            f"Provider '{config.llm.provider}' is not available. "
            "Run 'coach setup' to check provider status."
        )
    return provider
