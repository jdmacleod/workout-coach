from __future__ import annotations

import subprocess

from coach.intelligence.exceptions import InferenceError
from coach.intelligence.provider import InferenceProvider, InferenceRequest, InferenceResponse


class AppleIntelligenceProvider(InferenceProvider):
    """Runs inference via Apple Shortcuts (Apple Intelligence)."""

    SHORTCUT_NAME = "EC-Generate"

    def provider_name(self) -> str:
        return "apple"

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ["shortcuts", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            prefix = self.config.llm.apple.shortcut_prefix
            return any(line.startswith(prefix) for line in result.stdout.splitlines())
        except FileNotFoundError:
            return False

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        combined = f"SYSTEM:\n{request.system}\n\nUSER:\n{request.user}"
        try:
            result = subprocess.run(
                ["shortcuts", "run", self.SHORTCUT_NAME, "--input-path", "-"],
                input=combined.encode(),
                capture_output=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            from coach.intelligence.exceptions import InferenceTimeoutError

            raise InferenceTimeoutError("Apple Intelligence shortcut timed out after 120s")
        if result.returncode != 0:
            raise InferenceError(f"Shortcut failed: {result.stderr.decode()}")
        return InferenceResponse(
            text=result.stdout.decode().strip(),
            provider="apple",
            model="apple-intelligence",
        )
