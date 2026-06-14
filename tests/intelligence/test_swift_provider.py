"""Unit tests for SwiftInferenceProvider payload construction."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from unittest.mock import patch

from coach.config import Config, LLMConfig, LLMSwiftConfig, SearchConfig
from coach.intelligence.provider import InferenceRequest


def _make_config(**search_kwargs: str) -> Config:
    cfg = Config()
    cfg.llm = LLMConfig(provider="swift")
    cfg.llm.swift = LLMSwiftConfig(binary="swift/.build/release/CoachInfer")
    cfg.search = SearchConfig(**search_kwargs)
    return cfg


def _capture_payload(cfg: Config, request: InferenceRequest) -> dict:
    """Run SwiftInferenceProvider.infer() with a fake binary and capture the stdin payload."""
    import subprocess

    from coach.intelligence.providers.swift import SwiftInferenceProvider

    provider = SwiftInferenceProvider(cfg)
    captured: list[bytes] = []

    def fake_run(cmd: list, *, input: bytes, capture_output: bool, timeout: int):
        captured.append(input)
        response = json.dumps({"text": "{}", "model": "apple/on-device"})
        result = subprocess.CompletedProcess(cmd, 0)
        result.stdout = response.encode()
        result.stderr = b""
        return result

    with (
        patch.object(provider, "_binary_path", return_value=Path("/fake/CoachInfer")),
        patch("coach.intelligence.providers.swift.subprocess.run", side_effect=fake_run),
        contextlib.suppress(Exception),
    ):
        provider.infer(request)

    return json.loads(captured[0])


def test_enable_search_flag_in_payload() -> None:
    cfg = _make_config()
    req = InferenceRequest(system="sys", user="usr", max_tokens=512, enable_search=True)
    payload = _capture_payload(cfg, req)
    assert payload["enable_search"] is True


def test_enable_search_absent_when_false() -> None:
    cfg = _make_config()
    req = InferenceRequest(system="sys", user="usr", max_tokens=512, enable_search=False)
    payload = _capture_payload(cfg, req)
    assert "enable_search" not in payload


def test_search_api_keys_included_when_configured() -> None:
    cfg = _make_config(
        brave_search_api_key="brave-key-123",
        exa_api_key="exa-key-456",
        tavily_api_key="tvly-key-789",
    )
    req = InferenceRequest(system="sys", user="usr", max_tokens=512, enable_search=True)
    payload = _capture_payload(cfg, req)
    assert payload.get("search_api_keys") == {
        "brave_search_api_key": "brave-key-123",
        "exa_api_key": "exa-key-456",
        "tavily_api_key": "tvly-key-789",
    }


def test_search_keys_absent_when_empty() -> None:
    cfg = _make_config(brave_search_api_key="", exa_api_key="")
    req = InferenceRequest(system="sys", user="usr", max_tokens=512, enable_search=True)
    payload = _capture_payload(cfg, req)
    assert "search_api_keys" not in payload


def test_partial_search_keys_only_non_empty() -> None:
    cfg = _make_config(brave_search_api_key="brave-key", exa_api_key="")
    req = InferenceRequest(system="sys", user="usr", max_tokens=512, enable_search=True)
    payload = _capture_payload(cfg, req)
    keys = payload.get("search_api_keys", {})
    assert "brave_search_api_key" in keys
    assert "exa_api_key" not in keys
