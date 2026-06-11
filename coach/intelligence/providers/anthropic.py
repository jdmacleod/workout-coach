from __future__ import annotations

import os

from coach.intelligence.exceptions import InferenceError
from coach.intelligence.provider import InferenceProvider, InferenceRequest, InferenceResponse


class AnthropicProvider(InferenceProvider):
    """Calls the Anthropic Messages API (cloud fallback)."""

    def provider_name(self) -> str:
        return "anthropic"

    def display_name(self) -> str:
        return f"anthropic / {self.config.llm.anthropic.model}"

    def is_available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        import anthropic as sdk

        try:
            client = sdk.Anthropic()
            message = client.messages.create(
                model=self.config.llm.anthropic.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
            )
        except sdk.AuthenticationError as e:
            raise InferenceError(f"Inference error: invalid API key — {e}") from e
        except sdk.RateLimitError as e:
            raise InferenceError(f"Inference error: rate limit exceeded — {e}") from e
        except sdk.APIError as e:
            raise InferenceError(f"Inference error: Anthropic API error — {e}") from e

        from anthropic.types import TextBlock

        text_blocks = [b for b in message.content if isinstance(b, TextBlock)]
        if not text_blocks:
            raise InferenceError("Anthropic returned no text content")
        return InferenceResponse(
            text=text_blocks[0].text,
            provider="anthropic",
            model=self.config.llm.anthropic.model,
        )
