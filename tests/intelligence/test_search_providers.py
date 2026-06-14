"""
Smoke tests for the external search provider APIs used by the Swift web search tool.

Each test mirrors the HTTP call made by WebSearchTool in main.swift and verifies
that the provider returns non-empty content for a representative fitness query.

Run:
    uv run pytest tests/intelligence/test_search_providers.py -m search -v

Keys are read from environment variables first, then from config/config.toml:

    Provider       Env var                  Config key
    ─────────────  ───────────────────────  ─────────────────────
    Brave Search   BRAVE_SEARCH_API_KEY     search.brave_search_api_key
    Exa            EXA_API_KEY              search.exa_api_key
    Tavily         TAVILY_API_KEY           search.tavily_api_key
    DuckDuckGo     (no key required)        —

Keyed providers are automatically skipped when no key is found.
DuckDuckGo always runs but is marked xfail when it returns nothing, since
its Instant Answer API has limited fitness coverage.
"""

from __future__ import annotations

import os

import httpx
import pytest

from coach.config import ConfigNotFoundError, load_config

# Representative query that all four providers should handle reasonably well.
SMOKE_QUERY = "pull-up bar bodyweight exercises for strength training"


def _get_key(config_attr: str) -> str | None:
    """Return an API key from the matching env var or config/config.toml, or None."""
    env_name = config_attr.upper()
    if val := os.environ.get(env_name):
        return val
    try:
        return getattr(load_config().search, config_attr, "") or None
    except (ConfigNotFoundError, Exception):
        return None


# ── Provider implementations (mirrors swift/Sources/CoachInfer/main.swift) ──


def _call_brave(query: str, api_key: str) -> str:
    resp = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": 5},
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        timeout=20,
    )
    resp.raise_for_status()
    results = resp.json().get("web", {}).get("results", [])
    return "\n".join(
        f"{r['title']}: {r.get('description', '')}" for r in results[:3] if r.get("title")
    )


def _call_exa(query: str, api_key: str) -> str:
    resp = httpx.post(
        "https://api.exa.ai/search",
        json={"query": query, "numResults": 3, "contents": {"highlights": {"numSentences": 2}}},
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        timeout=20,
    )
    resp.raise_for_status()
    snippets: list[str] = []
    for r in (resp.json().get("results") or [])[:3]:
        if r.get("title"):
            snippets.append(r["title"])
        snippets.extend(r.get("highlights") or [])
    return "\n".join(snippets)


def _call_tavily(query: str, api_key: str) -> str:
    resp = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "search_depth": "basic", "max_results": 5},
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    snippets: list[str] = []
    if data.get("answer"):
        snippets.append(data["answer"])
    for r in (data.get("results") or [])[:3]:
        title, content = r.get("title", ""), r.get("content", "")
        if title or content:
            snippets.append(f"{title}: {content}" if title else content)
    return "\n".join(snippets)


def _call_duckduckgo(query: str) -> str:
    resp = httpx.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1", "no_redirect": "1"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    parts = [data.get("Answer", ""), data.get("AbstractText", "")]
    parts += [t.get("Text", "") for t in (data.get("RelatedTopics") or [])[:5]]
    return "\n".join(p for p in parts if p)


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.search
def test_brave_search_returns_results() -> None:
    key = _get_key("brave_search_api_key")
    if not key:
        pytest.skip(
            "Brave Search key not found (set BRAVE_SEARCH_API_KEY or search.brave_search_api_key in config.toml)"
        )
    result = _call_brave(SMOKE_QUERY, key)
    print(f"\n[Brave] {result[:300]}")
    assert result, "Brave Search returned empty content for smoke query"


@pytest.mark.search
def test_exa_search_returns_results() -> None:
    key = _get_key("exa_api_key")
    if not key:
        pytest.skip("Exa key not found (set EXA_API_KEY or search.exa_api_key in config.toml)")
    result = _call_exa(SMOKE_QUERY, key)
    print(f"\n[Exa] {result[:300]}")
    assert result, "Exa returned empty content for smoke query"


@pytest.mark.search
def test_tavily_search_returns_results() -> None:
    key = _get_key("tavily_api_key")
    if not key:
        pytest.skip(
            "Tavily key not found (set TAVILY_API_KEY or search.tavily_api_key in config.toml)"
        )
    result = _call_tavily(SMOKE_QUERY, key)
    print(f"\n[Tavily] {result[:300]}")
    assert result, "Tavily returned empty content for smoke query"


@pytest.mark.search
def test_duckduckgo_search_returns_results() -> None:
    """DuckDuckGo Instant Answer API requires no API key and is always the final fallback.

    The DDG API returns Wikipedia abstracts and related topics, not general web results.
    It responds to concept/topic queries that map to Wikipedia articles (e.g. "calisthenics",
    "strength training") but returns nothing for specific multi-word exercise phrases.
    This test uses a topic query to validate the API call and response parsing, not
    SMOKE_QUERY which is too specific for DDG to match.
    """
    # "calisthenics" reliably maps to a Wikipedia article DDG can return.
    result = _call_duckduckgo("calisthenics")
    print(f"\n[DuckDuckGo] {result[:300]}")
    assert result, "DuckDuckGo returned empty content for 'calisthenics' — unexpected for a Wikipedia topic"
