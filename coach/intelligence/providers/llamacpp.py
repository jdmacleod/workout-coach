from __future__ import annotations

import httpx

from coach.intelligence.exceptions import InferenceError
from coach.intelligence.provider import InferenceProvider, InferenceRequest, InferenceResponse


class LlamaCppProvider(InferenceProvider):
    """Calls the llama.cpp server's OpenAI-compatible REST endpoint."""

    def provider_name(self) -> str:
        return "llamacpp"

    def display_name(self) -> str:
        return "llamacpp / local"

    def is_available(self) -> bool:
        try:
            httpx.get(
                f"{self.config.llm.llamacpp.server_url}/health",
                timeout=3,
            )
            return True
        except Exception:
            return False

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        payload = {
            "model": "local",
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        try:
            r = httpx.post(
                f"{self.config.llm.llamacpp.server_url}/v1/chat/completions",
                json=payload,
                timeout=180,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise InferenceError(f"llama.cpp request failed: {e}") from e
        return InferenceResponse(
            text=r.json()["choices"][0]["message"]["content"],
            provider="llamacpp",
            model="local",
        )
