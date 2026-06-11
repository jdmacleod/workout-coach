from __future__ import annotations

import json
import subprocess
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
        payload_dict: dict[str, Any] = {
            "system": request.system,
            "user": request.user,
            "max_tokens": request.max_tokens,
        }
        if request.schema is not None:
            payload_dict["schema"] = request.schema
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
            raise InferenceError(f"coach-infer model error: {data['error']}")
        return InferenceResponse(
            text=data["text"],
            provider="swift",
            model=data.get("model"),
        )

    def _binary_path(self) -> Path:
        return (PROJECT_ROOT / self.config.llm.swift.binary).expanduser()
