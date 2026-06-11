"""Unit tests for coach/intelligence/prompts.py utilities."""

from coach.intelligence.prompts import extract_json_text


def test_extract_json_plain():
    assert extract_json_text('{"a": 1}') == '{"a": 1}'


def test_extract_json_strips_json_fence():
    text = '```json\n{"a": 1}\n```'
    assert extract_json_text(text) == '{"a": 1}'


def test_extract_json_strips_bare_fence():
    text = '```\n{"a": 1}\n```'
    assert extract_json_text(text) == '{"a": 1}'


def test_extract_json_strips_surrounding_whitespace():
    assert extract_json_text('  {"a": 1}  ') == '{"a": 1}'


def test_extract_json_multiline_object():
    text = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
    result = extract_json_text(text)
    import json

    assert json.loads(result) == {"a": 1, "b": 2}


def test_extract_json_preserves_non_fence_text():
    assert extract_json_text("Here is some text") == "Here is some text"
