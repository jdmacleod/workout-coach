"""Unit tests for the provider factory and MockInferenceProvider."""

import pytest

from coach.config import Config, ConfigError, LLMConfig
from coach.intelligence.exceptions import InferenceError
from coach.intelligence.provider import InferenceRequest, get_provider
from tests.intelligence.mock_provider import MockInferenceProvider


def _config_with_provider(name: str) -> Config:
    cfg = Config()
    cfg.llm = LLMConfig(provider=name)
    return cfg


def test_mock_provider_returns_configured_text():
    provider = MockInferenceProvider(response_text='{"hello": "world"}')
    req = InferenceRequest(system="sys", user="usr")
    resp = provider.infer(req)
    assert resp.text == '{"hello": "world"}'
    assert resp.provider == "mock"


def test_mock_provider_records_calls():
    provider = MockInferenceProvider()
    req = InferenceRequest(system="sys", user="usr")
    provider.infer(req)
    provider.infer(req)
    assert len(provider.calls) == 2


def test_mock_provider_available():
    assert MockInferenceProvider(available=True).is_available() is True
    assert MockInferenceProvider(available=False).is_available() is False


def test_get_provider_unknown_name_raises_config_error():
    cfg = _config_with_provider("nonexistent_provider_xyz")
    with pytest.raises(ConfigError, match="Unknown provider"):
        get_provider(cfg)


def test_get_provider_unavailable_raises_inference_error(monkeypatch):
    """get_provider raises InferenceError when is_available() returns False."""
    from coach.intelligence.providers import ollama as ollama_mod

    monkeypatch.setattr(ollama_mod.OllamaProvider, "is_available", lambda self: False)

    cfg = _config_with_provider("ollama")
    with pytest.raises(InferenceError, match="not available"):
        get_provider(cfg)
