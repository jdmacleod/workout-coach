"""Tests for per-provider max_tokens, context_window, and num_ctx enforcement."""

from __future__ import annotations

import contextlib
import json
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from coach.config import (
    Config,
    ConfigError,
    LLMAnthropicConfig,
    LLMAppleConfig,
    LLMConfig,
    LLMLlamaCppConfig,
    LLMOllamaConfig,
    LLMSwiftConfig,
    _validate_max_tokens,
)
from coach.intelligence.provider import InferenceRequest

# ── Config helpers ────────────────────────────────────────────────────────────


def _swift_config(max_tokens: int = 2048, context_window: int = 4096) -> Config:
    cfg = Config()
    cfg.llm = LLMConfig(provider="swift")
    cfg.llm.swift = LLMSwiftConfig(max_tokens=max_tokens, context_window=context_window)
    return cfg


def _ollama_config(max_tokens: int = 2048, num_ctx: int = 2048) -> Config:
    cfg = Config()
    cfg.llm = LLMConfig(provider="ollama")
    cfg.llm.ollama = LLMOllamaConfig(max_tokens=max_tokens, num_ctx=num_ctx)
    return cfg


def _llamacpp_config(max_tokens: int = 2048) -> Config:
    cfg = Config()
    cfg.llm = LLMConfig(provider="llamacpp")
    cfg.llm.llamacpp = LLMLlamaCppConfig(max_tokens=max_tokens)
    return cfg


def _anthropic_config(max_tokens: int = 4096) -> Config:
    cfg = Config()
    cfg.llm = LLMConfig(provider="anthropic")
    cfg.llm.anthropic = LLMAnthropicConfig(max_tokens=max_tokens)
    return cfg


# ── Payload capture helpers ───────────────────────────────────────────────────


def _capture_swift_payload(cfg: Config, request: InferenceRequest) -> dict:
    import subprocess

    from coach.intelligence.providers.swift import SwiftInferenceProvider

    provider = SwiftInferenceProvider(cfg)
    captured: list[bytes] = []

    def fake_run(cmd: list, *, input: bytes, capture_output: bool, timeout: int):
        captured.append(input)
        result = subprocess.CompletedProcess(cmd, 0)
        result.stdout = json.dumps({"text": "{}", "model": "apple/on-device"}).encode()
        result.stderr = b""
        return result

    with (
        patch.object(provider, "_binary_path", return_value=Path("/fake/CoachInfer")),
        patch("coach.intelligence.providers.swift.subprocess.run", side_effect=fake_run),
        contextlib.suppress(Exception),
    ):
        provider.infer(request)

    return json.loads(captured[0])


def _make_ollama_get_mock(model_name: str, context_length: int = 32768):
    """Return a fake httpx.get response for Ollama's /api/tags endpoint."""
    from unittest.mock import MagicMock

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "models": [
            {
                "name": model_name,
                "model": model_name,
                "details": {"context_length": context_length},
            }
        ]
    }
    return mock_resp


def _capture_ollama_payload(
    cfg: Config,
    request: InferenceRequest,
    *,
    native_ctx: int = 32768,
    prompt_tokens: int = 5,
) -> dict:
    from unittest.mock import MagicMock

    from coach.intelligence.providers.ollama import OllamaProvider

    provider = OllamaProvider(cfg)
    captured: list[dict] = []

    def fake_post(url: str, *, json: dict, timeout: int):
        captured.append(json)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 1,
                "total_tokens": prompt_tokens + 1,
            },
        }
        return mock_resp

    def fake_get(url: str, timeout: int):
        return _make_ollama_get_mock(cfg.llm.ollama.model, native_ctx)

    with (
        patch("coach.intelligence.providers.ollama.httpx.post", side_effect=fake_post),
        patch("coach.intelligence.providers.ollama.httpx.get", side_effect=fake_get),
    ):
        provider.infer(request)

    return captured[0]


def _capture_llamacpp_payload(cfg: Config, request: InferenceRequest) -> dict:
    from unittest.mock import MagicMock

    from coach.intelligence.providers.llamacpp import LlamaCppProvider

    provider = LlamaCppProvider(cfg)
    captured: list[dict] = []

    def fake_post(url: str, *, json: dict, timeout: int):
        captured.append(json)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        return mock_resp

    with patch("coach.intelligence.providers.llamacpp.httpx.post", side_effect=fake_post):
        provider.infer(request)

    return captured[0]


# ── Test 1: max_tokens fields exist on dataclasses with correct defaults ──────


def test_config_defaults_swift() -> None:
    cfg = LLMSwiftConfig()
    assert cfg.max_tokens == 2048
    assert cfg.context_window == 4096


def test_config_defaults_ollama() -> None:
    cfg = LLMOllamaConfig()
    assert cfg.max_tokens == 2048
    assert cfg.num_ctx == 8192


def test_config_defaults_llamacpp() -> None:
    cfg = LLMLlamaCppConfig()
    assert cfg.max_tokens == 2048


def test_config_defaults_anthropic() -> None:
    cfg = LLMAnthropicConfig()
    assert cfg.max_tokens == 4096


# ── Test 2: defaults survive when absent from TOML (_dc filtering) ────────────


def test_swift_config_defaults_when_not_in_toml() -> None:
    from coach.config import _parse_config

    raw = {"llm": {"provider": "swift", "swift": {"binary": "foo"}}}
    cfg = _parse_config(raw)
    assert cfg.llm.swift.max_tokens == 2048
    assert cfg.llm.swift.context_window == 4096


def test_ollama_config_defaults_when_not_in_toml() -> None:
    from coach.config import _parse_config

    raw = {"llm": {"provider": "ollama", "ollama": {"model": "llama3.2"}}}
    cfg = _parse_config(raw)
    assert cfg.llm.ollama.max_tokens == 2048
    assert cfg.llm.ollama.num_ctx == 8192


# ── Tests 3-4: _validate_max_tokens raises ConfigError for invalid values ──────


def test_validate_rejects_zero_swift_max_tokens() -> None:
    cfg = _swift_config(max_tokens=0)
    with pytest.raises(ConfigError, match="llm.swift.max_tokens"):
        _validate_max_tokens(cfg)


def test_validate_rejects_negative_swift_max_tokens() -> None:
    cfg = _swift_config(max_tokens=-1)
    with pytest.raises(ConfigError, match="llm.swift.max_tokens"):
        _validate_max_tokens(cfg)


def test_validate_rejects_zero_context_window() -> None:
    cfg = _swift_config(context_window=0)
    with pytest.raises(ConfigError, match="llm.swift.context_window"):
        _validate_max_tokens(cfg)


def test_validate_rejects_zero_ollama_max_tokens() -> None:
    cfg = _ollama_config(max_tokens=0)
    with pytest.raises(ConfigError, match="llm.ollama.max_tokens"):
        _validate_max_tokens(cfg)


def test_validate_rejects_zero_num_ctx() -> None:
    cfg = _ollama_config(num_ctx=0)
    with pytest.raises(ConfigError, match="llm.ollama.num_ctx"):
        _validate_max_tokens(cfg)


def test_validate_rejects_zero_llamacpp_max_tokens() -> None:
    cfg = _llamacpp_config(max_tokens=0)
    with pytest.raises(ConfigError, match="llm.llamacpp.max_tokens"):
        _validate_max_tokens(cfg)


def test_validate_rejects_zero_anthropic_max_tokens() -> None:
    cfg = _anthropic_config(max_tokens=0)
    with pytest.raises(ConfigError, match="llm.anthropic.max_tokens"):
        _validate_max_tokens(cfg)


# ── Tests 5-7: Swift provider output clamping ─────────────────────────────────


def test_swift_clamps_request_above_config_limit() -> None:
    cfg = _swift_config(max_tokens=512, context_window=4096)
    payload = _capture_swift_payload(cfg, InferenceRequest(system="s", user="u", max_tokens=2048))
    assert payload["max_tokens"] == 512


def test_swift_passes_through_request_below_config_limit() -> None:
    cfg = _swift_config(max_tokens=2048, context_window=4096)
    payload = _capture_swift_payload(cfg, InferenceRequest(system="s", user="u", max_tokens=512))
    assert payload["max_tokens"] == 512


def test_swift_uses_exact_value_when_equal() -> None:
    cfg = _swift_config(max_tokens=1024, context_window=4096)
    payload = _capture_swift_payload(cfg, InferenceRequest(system="s", user="u", max_tokens=1024))
    assert payload["max_tokens"] == 1024


# ── Tests 8-9: Swift prompt truncation ────────────────────────────────────────


def test_swift_truncates_long_user_prompt_and_warns() -> None:
    # context_window=200 tokens, max_tokens=100 → 100 tokens left for input
    # 100 tokens * 4 chars/token = 400 chars budget minus system len
    system = "System prompt."  # 14 chars ≈ 3 tokens
    # User prompt: 2000 chars → estimated 500 tokens, which overflows 200-token window
    user = "x" * 2000
    cfg = _swift_config(max_tokens=100, context_window=200)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        payload = _capture_swift_payload(
            cfg, InferenceRequest(system=system, user=user, max_tokens=100)
        )

    truncation_warnings = [w for w in caught if "truncated" in str(w.message).lower()]
    assert len(truncation_warnings) >= 1, "Expected a truncation warning"
    assert len(payload["user"]) < len(user), "User prompt should be truncated in payload"


def test_swift_does_not_truncate_short_prompt() -> None:
    system = "S"
    user = "short prompt"  # trivially fits in any reasonable context window
    cfg = _swift_config(max_tokens=256, context_window=4096)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        payload = _capture_swift_payload(
            cfg, InferenceRequest(system=system, user=user, max_tokens=256)
        )

    truncation_warnings = [w for w in caught if "truncated" in str(w.message).lower()]
    assert len(truncation_warnings) == 0, "No warning expected for short prompt"
    assert payload["user"] == user, "User prompt should be unchanged"


# ── Test 10: Ollama num_ctx appears in API payload options ────────────────────


def test_ollama_num_ctx_in_payload_options() -> None:
    cfg = _ollama_config(max_tokens=512, num_ctx=8192)
    payload = _capture_ollama_payload(cfg, InferenceRequest(system="s", user="u", max_tokens=512))
    assert payload.get("options", {}).get("num_ctx") == 8192


def test_ollama_clamps_request_above_config_limit() -> None:
    cfg = _ollama_config(max_tokens=512, num_ctx=2048)
    payload = _capture_ollama_payload(cfg, InferenceRequest(system="s", user="u", max_tokens=2048))
    assert payload["max_tokens"] == 512


# ── Ollama context window discovery and overflow detection ────────────────────


def test_ollama_native_ctx_cached_from_api_tags() -> None:
    """_cache_native_ctx populates _native_ctx from /api/tags details.context_length."""

    from coach.intelligence.providers.ollama import OllamaProvider

    cfg = _ollama_config(num_ctx=8192)
    provider = OllamaProvider(cfg)
    assert provider._native_ctx is None

    mock_resp = _make_ollama_get_mock(cfg.llm.ollama.model, context_length=32768)
    with patch("coach.intelligence.providers.ollama.httpx.get", return_value=mock_resp):
        available = provider.is_available()

    assert available is True
    assert provider._native_ctx == 32768


def test_ollama_native_ctx_falls_back_to_num_ctx_when_api_unavailable() -> None:
    """_get_native_ctx falls back to configured num_ctx when /api/tags is unreachable."""
    from coach.intelligence.providers.ollama import OllamaProvider

    cfg = _ollama_config(num_ctx=4096)
    provider = OllamaProvider(cfg)

    with patch(
        "coach.intelligence.providers.ollama.httpx.get",
        side_effect=Exception("connection refused"),
    ):
        ctx = provider._get_native_ctx()

    assert ctx == 4096


def test_ollama_num_ctx_clamped_to_native_ceiling() -> None:
    """num_ctx in the payload never exceeds the model's native context length."""
    # Configure num_ctx=16384 but the model only supports 8192
    cfg = _ollama_config(max_tokens=512, num_ctx=16384)
    payload = _capture_ollama_payload(
        cfg,
        InferenceRequest(system="s", user="u", max_tokens=512),
        native_ctx=8192,
    )
    assert payload["options"]["num_ctx"] == 8192


def test_ollama_raises_inference_error_on_context_overflow() -> None:
    """InferenceError is raised when actual prompt_tokens >= num_ctx (overflow detected)."""
    from unittest.mock import MagicMock

    from coach.intelligence.exceptions import InferenceError
    from coach.intelligence.providers.ollama import OllamaProvider

    cfg = _ollama_config(max_tokens=512, num_ctx=1024)
    provider = OllamaProvider(cfg)

    def fake_post(url: str, *, json: dict, timeout: int):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        # prompt_tokens equals num_ctx — overflow occurred
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "truncated"}}],
            "usage": {"prompt_tokens": 1024, "completion_tokens": 5, "total_tokens": 1029},
        }
        return mock_resp

    with (
        patch(
            "coach.intelligence.providers.ollama.httpx.get",
            return_value=_make_ollama_get_mock(cfg.llm.ollama.model, 32768),
        ),
        patch("coach.intelligence.providers.ollama.httpx.post", side_effect=fake_post),
        pytest.raises(InferenceError, match="context overflow"),
    ):
        provider.infer(InferenceRequest(system="s", user="u", max_tokens=512))


def test_ollama_no_overflow_error_when_usage_absent() -> None:
    """No error is raised when the response lacks a usage field (older Ollama versions)."""
    from unittest.mock import MagicMock

    from coach.intelligence.providers.ollama import OllamaProvider

    cfg = _ollama_config(max_tokens=512, num_ctx=2048)
    provider = OllamaProvider(cfg)

    def fake_post(url: str, *, json: dict, timeout: int):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        return mock_resp

    with (
        patch(
            "coach.intelligence.providers.ollama.httpx.get",
            return_value=_make_ollama_get_mock(cfg.llm.ollama.model, 32768),
        ),
        patch("coach.intelligence.providers.ollama.httpx.post", side_effect=fake_post),
    ):
        resp = provider.infer(InferenceRequest(system="s", user="u", max_tokens=512))

    assert resp.text == "ok"


def test_ollama_no_overflow_error_when_prompt_tokens_below_num_ctx() -> None:
    """No error is raised when prompt_tokens is safely below num_ctx."""
    cfg = _ollama_config(max_tokens=512, num_ctx=4096)
    # prompt_tokens=100 is well below num_ctx=4096 → no overflow
    payload = _capture_ollama_payload(
        cfg,
        InferenceRequest(system="s", user="u", max_tokens=512),
        native_ctx=32768,
        prompt_tokens=100,
    )
    # If we get here without an exception, the test passes
    assert payload["options"]["num_ctx"] == 4096


# ── llamacpp clamping ──────────────────────────────────────────────────────────


def test_llamacpp_clamps_request_above_config_limit() -> None:
    cfg = _llamacpp_config(max_tokens=256)
    payload = _capture_llamacpp_payload(
        cfg, InferenceRequest(system="s", user="u", max_tokens=1024)
    )
    assert payload["max_tokens"] == 256


# ── Test 11: Apple provider regression — no max_tokens attr on LLMAppleConfig ─


def test_apple_config_has_no_max_tokens_attr() -> None:
    """LLMAppleConfig must not have max_tokens — the provider can't enforce it."""
    assert not hasattr(LLMAppleConfig(), "max_tokens"), (
        "LLMAppleConfig should NOT have max_tokens: the apple provider passes prompts "
        "to a Shortcut via subprocess and cannot enforce an output token limit."
    )
