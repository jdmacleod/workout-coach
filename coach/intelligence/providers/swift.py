from __future__ import annotations

import json
import subprocess
import time
import warnings
from pathlib import Path
from typing import Any

from coach.config import PROJECT_ROOT
from coach.intelligence.exceptions import (
    InferenceError,
    InferenceParseError,
    InferenceTimeoutError,
)
from coach.intelligence.provider import InferenceProvider, InferenceRequest, InferenceResponse


class SwiftInferenceProvider(InferenceProvider):
    """Calls the coach-infer Swift binary via subprocess."""

    def provider_name(self) -> str:
        return "swift"

    def display_name(self) -> str:
        return "swift / on-device"

    def is_available(self) -> bool:
        import platform

        ver_str = platform.mac_ver()[0]
        if not ver_str:
            return False
        try:
            major = int(ver_str.split(".")[0])
        except (ValueError, IndexError):
            return False
        return major >= 26 and self._binary_path().exists()

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        last_error: InferenceError | None = None
        for attempt in range(3):
            if attempt > 0:
                time.sleep(attempt)  # 1s after first failure, 2s after second
            try:
                return self._do_infer(request)
            except InferenceTimeoutError:
                raise  # timeouts already burned 120s each — never retry
            except InferenceError as e:
                last_error = e
        assert last_error is not None
        raise last_error

    def _do_infer(self, request: InferenceRequest) -> InferenceResponse:
        effective_max_tokens = min(request.max_tokens, self.config.llm.swift.max_tokens)
        context_window = self.config.llm.swift.context_window
        estimated_input_tokens = (len(request.system) + len(request.user)) // 4
        if estimated_input_tokens + effective_max_tokens > context_window:
            available_input_chars = (context_window - effective_max_tokens) * 4 - len(
                request.system
            )
            available_input_chars = max(0, available_input_chars)
            truncated_user = request.user[:available_input_chars]
            if truncated_user != request.user:
                warnings.warn(
                    f"swift: user prompt truncated from {len(request.user)} to {len(truncated_user)} chars "
                    f"to fit {context_window}-token context window",
                    stacklevel=2,
                )
            user = truncated_user
        else:
            user = request.user
        payload_dict: dict[str, Any] = {
            "system": request.system,
            "user": user,
            "max_tokens": effective_max_tokens,
        }
        if request.schema is not None:
            payload_dict["schema"] = request.schema
        if request.enable_search:
            payload_dict["enable_search"] = True
            keys: dict[str, str] = {}
            if self.config.search.brave_search_api_key:
                keys["brave_search_api_key"] = self.config.search.brave_search_api_key
            if self.config.search.exa_api_key:
                keys["exa_api_key"] = self.config.search.exa_api_key
            if self.config.search.tavily_api_key:
                keys["tavily_api_key"] = self.config.search.tavily_api_key
            if keys:
                payload_dict["search_api_keys"] = keys
        payload = json.dumps(payload_dict)
        try:
            result = subprocess.run(
                [str(self._binary_path())],
                input=payload.encode(),
                capture_output=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            raise InferenceTimeoutError("coach-infer timed out after 120s")
        if result.returncode != 0:
            raise InferenceError(f"coach-infer failed: {result.stderr.decode()}")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise InferenceParseError(f"coach-infer returned invalid JSON: {e}") from e
        if data.get("error"):
            # Include stderr diagnostic detail (domain/code/userInfo) when present
            stderr_detail = result.stderr.decode().strip()
            msg = data["error"]
            if stderr_detail and stderr_detail not in msg:
                msg = f"{msg} | stderr: {stderr_detail}"
            raise InferenceError(f"coach-infer model error: {msg}")
        return InferenceResponse(
            text=data["text"],
            provider="swift",
            model=data.get("model"),
        )

    def _binary_path(self) -> Path:
        return (PROJECT_ROOT / self.config.llm.swift.binary).expanduser()
