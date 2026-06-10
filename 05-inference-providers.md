# Inference Provider Spec

## Overview

All LLM inference flows through a single abstract interface. The provider is
resolved once from config at command startup and injected into commands that need
it. Commands never call a specific provider directly.

---

## Architecture

```
coach/intelligence/
├── provider.py           # ABC, factory, InferenceRequest/Response
├── prompts.py            # Prompt templates for each task
└── providers/
    ├── swift.py          # Foundation Models binary
    ├── apple.py          # Apple Shortcuts
    ├── ollama.py         # Ollama REST
    ├── llamacpp.py       # llama.cpp REST
    └── anthropic.py      # Anthropic SDK
```

---

## Core Interface

```python
# coach/intelligence/provider.py

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class InferenceRequest:
    system: str
    user: str
    max_tokens: int = 1024
    temperature: float = 0.4   # Low: structured output tasks need consistency

@dataclass
class InferenceResponse:
    text: str
    provider: str
    model: str | None = None

class InferenceProvider(ABC):

    @abstractmethod
    def infer(self, request: InferenceRequest) -> InferenceResponse:
        """Run inference. Raises InferenceError on failure."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is configured and reachable."""
        ...

    @abstractmethod
    def provider_name(self) -> str:
        ...
```

```python
# Factory

def get_provider(config: Config) -> InferenceProvider:
    providers = {
        "swift":     SwiftInferenceProvider,
        "apple":     AppleIntelligenceProvider,
        "ollama":    OllamaProvider,
        "llamacpp":  LlamaCppProvider,
        "anthropic": AnthropicProvider,
    }
    cls = providers.get(config.llm.provider)
    if cls is None:
        raise ConfigError(f"Unknown provider: {config.llm.provider}")
    provider = cls(config)
    if not provider.is_available():
        raise InferenceError(
            f"Provider '{config.llm.provider}' is not available. "
            "Run 'coach setup' to check provider status."
        )
    return provider
```

---

## Provider: Swift (Foundation Models)

**File:** `coach/intelligence/providers/swift.py`

**Requirements:** macOS 26+, `coach-infer` binary built and present.

The Swift binary accepts a JSON object on stdin and writes a JSON object to stdout.

```python
class SwiftInferenceProvider(InferenceProvider):

    def is_available(self) -> bool:
        import platform
        ver_str = platform.mac_ver()[0]
        if not ver_str:
            return False  # Not macOS
        try:
            major = int(ver_str.split(".")[0])
        except (ValueError, IndexError):
            return False
        return major >= 26 and self._binary_path().exists()

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        import json, subprocess
        payload = json.dumps({
            "system": request.system,
            "user": request.user,
            "max_tokens": request.max_tokens,
        })
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
            raise InferenceParseError(f"coach-infer returned invalid JSON: {e}")
        return InferenceResponse(
            text=data["text"],
            provider="swift",
            model=data.get("model"),
        )

    def _binary_path(self) -> Path:
        return (PROJECT_ROOT / self.config.llm.swift.binary).expanduser()
```

### Swift binary (`swift/Sources/CoachInfer/main.swift`)

```swift
import Foundation
import FoundationModels

struct Request: Decodable {
    let system: String
    let user: String
    let maxTokens: Int

    enum CodingKeys: String, CodingKey {
        case system, user
        case maxTokens = "max_tokens"
    }
}

struct Response: Encodable {
    let text: String
    let model: String
}

let inputData = FileHandle.standardInput.readDataToEndOfFile()
let request = try JSONDecoder().decode(Request.self, from: inputData)

let session = LanguageModelSession(instructions: request.system)
let result = try await session.respond(
    to: request.user,
    options: GenerationOptions(maximumResponseTokens: request.maxTokens)
)

let response = Response(text: result.content, model: "apple/on-device")
FileHandle.standardOutput.write(try JSONEncoder().encode(response))
```

### `swift/Package.swift`

```swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CoachInfer",
    platforms: [.macOS(.v26)],
    targets: [
        .executableTarget(
            name: "CoachInfer",
            path: "Sources/CoachInfer"
        )
    ]
)
```

### Build instructions (run by `coach setup`)

```bash
cd swift
swift build -c release
cp .build/release/CoachInfer ~/.local/bin/coach-infer   # or project-relative path
```

---

## Provider: Apple Intelligence (Shortcuts)

**File:** `coach/intelligence/providers/apple.py`

**Requirements:** macOS 15+, Apple Intelligence enabled, Shortcuts installed.

Three Shortcuts are distributed with the project in `shortcuts/`:
- `EC-Generate` — plan generation
- `EC-Assess` — workout assessment extraction
- `EC-Summarize` — weekly narrative

```python
class AppleIntelligenceProvider(InferenceProvider):

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        # Shortcuts receive input as text via stdin using the `shortcuts` CLI
        combined = f"SYSTEM:\n{request.system}\n\nUSER:\n{request.user}"
        result = subprocess.run(
            ["shortcuts", "run", self._shortcut_name(request), "--input-path", "-"],
            input=combined.encode(),
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise InferenceError(f"Shortcut failed: {result.stderr.decode()}")
        return InferenceResponse(
            text=result.stdout.decode().strip(),
            provider="apple",
            model="apple-intelligence",
        )

    def is_available(self) -> bool:
        # Check that the shortcuts CLI exists and at least one EC- shortcut is installed
        try:
            result = subprocess.run(
                ["shortcuts", "list"], capture_output=True, text=True, timeout=10
            )
            return any(
                line.startswith(self.config.llm.apple.shortcut_prefix)
                for line in result.stdout.splitlines()
            )
        except FileNotFoundError:
            return False
```

---

## Provider: Ollama

**File:** `coach/intelligence/providers/ollama.py`

**Requirements:** Ollama running locally. Default URL: `http://localhost:11434`.

Uses Ollama's OpenAI-compatible `/v1/chat/completions` endpoint.

```python
class OllamaProvider(InferenceProvider):

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        import httpx
        payload = {
            "model": self.config.llm.ollama.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user",   "content": request.user},
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
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

    def is_available(self) -> bool:
        try:
            httpx.get(
                f"{self.config.llm.ollama.base_url}/api/tags", timeout=3
            ).raise_for_status()
            return True
        except Exception:
            return False
```

---

## Provider: llama.cpp

**File:** `coach/intelligence/providers/llamacpp.py`

Identical structure to Ollama. Uses the llama.cpp server's OpenAI-compatible endpoint.

```python
class LlamaCppProvider(InferenceProvider):

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        # Same as Ollama — OpenAI-compatible /v1/chat/completions
        # base_url default: http://localhost:8080
        ...

    def is_available(self) -> bool:
        try:
            httpx.get(f"{self.config.llm.llamacpp.server_url}/health", timeout=3)
            return True
        except Exception:
            return False
```

---

## Provider: Anthropic

**File:** `coach/intelligence/providers/anthropic.py`

**Requirements:** `ANTHROPIC_API_KEY` environment variable set. Internet access.

```python
class AnthropicProvider(InferenceProvider):

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        import anthropic as sdk
        client = sdk.Anthropic()   # reads ANTHROPIC_API_KEY from env
        message = client.messages.create(
            model=self.config.llm.anthropic.model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=[{"role": "user", "content": request.user}],
        )
        return InferenceResponse(
            text=message.content[0].text,
            provider="anthropic",
            model=self.config.llm.anthropic.model,
        )

    def is_available(self) -> bool:
        import os
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
```

---

## Prompt Templates (`coach/intelligence/prompts.py`)

All prompts are defined as module-level constants. They include explicit JSON
schema specifications so structured output tasks are reliable across providers.

```python
PLAN_GENERATION_SYSTEM = """
You are a personal fitness coach generating a weekly training plan.
Respond only with a valid JSON object matching the schema provided.
Do not include any explanation, preamble, or markdown formatting.
""".strip()

PLAN_GENERATION_USER = """
## User Profile
{config_note}
Days per week: {profile_days_per_week}
Primary goal: {profile_primary_goal}
Injury notes: {profile_injury_notes}

## Next Week Notes (from last assessment — highest priority context)
{next_week_notes}

## Training Philosophy and Example Workouts
{training_info}

## Recent History (last 4 weeks)
{history_summary}

## Fixed Sessions This Week
{external_sessions}

## Available Days
{available_days}

## Constraints
- No high-intensity session the day after a session with recovery_cost >= 3
- At least 1 full rest day per week
- Match weekly volume to recent history (avoid >10% load increase)

## Response Schema
{plan_schema}
""".strip()

ASSESS_SYSTEM = """
You are a fitness coach extracting structured data from a completed workout log.
Respond only with a valid JSON object matching the schema provided.
Do not include any explanation, preamble, or markdown formatting.
""".strip()

ASSESS_USER = """
## Workout Metadata
{metadata}

## Completed Section
{completed}

## How It Went
{how_it_went}

## Response Schema
{assess_schema}
""".strip()

WEEKLY_SUMMARY_SYSTEM = """
You are a fitness coach writing a concise weekly training summary.
Write 2–3 sentences in plain English. No bullet points. No headers.
Mention overall performance, any notable highs or lows, and one forward-looking note.
""".strip()

WEEKLY_SUMMARY_USER = """
## Week: {week}
## Sessions: {sessions_completed} of {sessions_planned} completed
## Average RPE: {avg_rpe}
## Total Duration: {total_duration_min} min

## Session Details
{session_details}
""".strip()
```

---

## Provider Comparison Table

| Provider | Privacy | macOS req | Internet | Quality | Setup effort | Default |
|---|---|---|---|---|---|---|
| Swift (Foundation Models) | On-device | 26+ | No | Good | Medium (build binary) | **Yes (macOS 26+)** |
| Apple Intelligence (Shortcuts) | On-device | 15+ (AI) | No | Good | Low (import shortcuts) | No |
| Ollama | Local | Any | No | Model-dependent | Low (brew install) | No |
| llama.cpp | Local | Any | No | Model-dependent | Medium (compile/serve) | No |
| Anthropic API | Cloud | Any | Yes | Excellent | Low (API key) | No |

---

## Error Types

```python
# coach/intelligence/exceptions.py

class InferenceError(Exception):
    """Raised when inference fails for any reason."""

class InferenceTimeoutError(InferenceError):
    """Raised when the provider exceeds the response timeout."""

class InferenceParseError(InferenceError):
    """Raised when the provider response cannot be parsed as expected JSON."""
```

JSON parse errors from structured output tasks are caught and retried once with
an appended correction prompt before raising `InferenceParseError`.
