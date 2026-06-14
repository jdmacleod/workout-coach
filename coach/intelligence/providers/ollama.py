from __future__ import annotations

import httpx

from coach.intelligence.exceptions import InferenceError
from coach.intelligence.provider import InferenceProvider, InferenceRequest, InferenceResponse


class OllamaProvider(InferenceProvider):
    """Calls the Ollama OpenAI-compatible REST endpoint."""

    def provider_name(self) -> str:
        return "ollama"

    def display_name(self) -> str:
        return f"ollama / {self.config.llm.ollama.model}"

    def is_available(self) -> bool:
        try:
            httpx.get(
                f"{self.config.llm.ollama.base_url}/api/tags",
                timeout=3,
            ).raise_for_status()
            return True
        except Exception:
            return False

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        effective_max_tokens = min(request.max_tokens, self.config.llm.ollama.max_tokens)
        payload = {
            "model": self.config.llm.ollama.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "max_tokens": effective_max_tokens,
            "temperature": request.temperature,
            "stream": False,
            "options": {"num_ctx": self.config.llm.ollama.num_ctx},
        }
        try:
            r = httpx.post(
                f"{self.config.llm.ollama.base_url}/v1/chat/completions",
                json=payload,
                timeout=180,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise InferenceError(f"Ollama request failed: {e}") from e
        return InferenceResponse(
            text=r.json()["choices"][0]["message"]["content"],
            provider="ollama",
            model=self.config.llm.ollama.model,
        )
