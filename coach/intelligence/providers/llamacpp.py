from __future__ import annotations

import re

import httpx

from coach.intelligence.exceptions import InferenceError
from coach.intelligence.provider import InferenceProvider, InferenceRequest, InferenceResponse


def _strip_reasoning_channel(text: str) -> str:
    """Strip <|channel|>...<|end|> reasoning wrapper emitted by gpt-oss and similar models.

    Three cases:
    1. <|end|> present with content after it → take that content (the real output).
    2. <|channel|> present but no <|end|> (response cut off mid-reasoning) → fall back
       to the first JSON object or array found anywhere in the text.
    3. No channel tokens → return as-is.

    Also strips markdown code fences that the model sometimes wraps around output.
    """
    if "<|end|>" in text:
        text = text.split("<|end|>", 1)[1].strip()
    elif "<|channel|>" in text:
        # Response was cut off before <|end|>; try to salvage inline JSON from reasoning.
        m = re.search(r"[{\[]", text)
        text = text[m.start() :] if m else ""
    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if m:
        text = m.group(1).strip()
    return text


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
        effective_max_tokens = min(request.max_tokens, self.config.llm.llamacpp.max_tokens)
        payload = {
            "model": "local",
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "max_tokens": effective_max_tokens,
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
        text = r.json()["choices"][0]["message"]["content"]
        text = _strip_reasoning_channel(text)
        return InferenceResponse(
            text=text,
            provider="llamacpp",
            model="local",
        )
