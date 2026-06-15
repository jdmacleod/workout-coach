from __future__ import annotations

from typing import Any

import httpx

from coach.intelligence.exceptions import InferenceError
from coach.intelligence.provider import InferenceProvider, InferenceRequest, InferenceResponse


class OllamaProvider(InferenceProvider):
    """Calls the Ollama OpenAI-compatible REST endpoint."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        # Native context window for the configured model, lazily populated from /api/tags.
        # Ollama's per-request num_ctx override isn't always honored when the model is
        # already loaded with a different context size. We use the native ceiling to clamp
        # num_ctx and the post-response usage.prompt_tokens to detect actual truncation.
        self._native_ctx: int | None = None

    def provider_name(self) -> str:
        return "ollama"

    def display_name(self) -> str:
        return f"ollama / {self.config.llm.ollama.model}"

    def is_available(self) -> bool:
        try:
            r = httpx.get(
                f"{self.config.llm.ollama.base_url}/api/tags",
                timeout=3,
            )
            r.raise_for_status()
            self._cache_native_ctx(r.json())
            return True
        except Exception:
            return False

    def _cache_native_ctx(self, tags_data: dict[str, Any]) -> None:
        """Extract and cache the model's native context window from /api/tags payload."""
        model_name = self.config.llm.ollama.model
        for m in tags_data.get("models", []):
            if m.get("model") == model_name or m.get("name") == model_name:
                ctx = m.get("details", {}).get("context_length")
                if isinstance(ctx, int) and ctx > 0:
                    self._native_ctx = ctx
                    return

    def _get_native_ctx(self) -> int:
        """Return the model's native context ceiling, querying /api/tags if not yet cached.

        Falls back to the configured num_ctx if the API is unreachable or the model
        is not found in the response.
        """
        if self._native_ctx is not None:
            return self._native_ctx
        try:
            r = httpx.get(
                f"{self.config.llm.ollama.base_url}/api/tags",
                timeout=3,
            )
            r.raise_for_status()
            self._cache_native_ctx(r.json())
        except Exception:
            pass
        return self._native_ctx or self.config.llm.ollama.num_ctx

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        native_ctx = self._get_native_ctx()
        # Clamp num_ctx to the model's native ceiling — sending a value above it is a no-op
        # at best and causes a model-reload penalty at worst.
        num_ctx = min(self.config.llm.ollama.num_ctx, native_ctx)
        effective_max_tokens = min(request.max_tokens, self.config.llm.ollama.max_tokens)
        payload: dict[str, object] = {
            "model": self.config.llm.ollama.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "max_tokens": effective_max_tokens,
            "temperature": request.temperature,
            "stream": False,
            "options": {"num_ctx": num_ctx},
        }
        if request.schema is not None:
            # Force JSON output mode — reduces parse failures without requiring
            # a full JSON Schema (which Ollama supports but varies by model).
            payload["format"] = "json"
        try:
            r = httpx.post(
                f"{self.config.llm.ollama.base_url}/v1/chat/completions",
                json=payload,
                timeout=180,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise InferenceError(f"Ollama request failed: {e}") from e

        data = r.json()

        # Defensive overflow check: Ollama reports the actual number of prompt tokens
        # consumed. If prompt_tokens >= num_ctx, the prompt was silently truncated and
        # the model's output is unreliable. Raise rather than return bad results.
        usage = data.get("usage", {})
        actual_prompt_tokens = usage.get("prompt_tokens", 0)
        if actual_prompt_tokens > 0 and actual_prompt_tokens >= num_ctx:
            raise InferenceError(
                f"Ollama context overflow: prompt consumed {actual_prompt_tokens} tokens "
                f"but num_ctx={num_ctx} (model native max: {native_ctx}). "
                "Increase [llm.ollama] num_ctx in config.toml to resolve."
            )

        return InferenceResponse(
            text=data["choices"][0]["message"]["content"],
            provider="ollama",
            model=self.config.llm.ollama.model,
        )
