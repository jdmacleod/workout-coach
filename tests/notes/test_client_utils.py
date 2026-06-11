"""Unit tests for pure-Python helpers in coach/notes/client.py"""

from coach.notes.client import _escape_for_applescript, _strip_html


def test_escape_quotes():
    assert _escape_for_applescript('say "hello"') == 'say \\"hello\\"'


def test_escape_newlines():
    assert _escape_for_applescript("line1\nline2") == "line1\\nline2"


def test_escape_backslash():
    assert _escape_for_applescript("path\\to\\file") == "path\\\\to\\\\file"


def test_strip_html_basic():
    assert _strip_html("<p>Hello</p>") == "Hello"


def test_strip_html_br():
    result = _strip_html("line1<br/>line2")
    assert result == "line1\nline2"


def test_strip_html_entities():
    result = _strip_html("a &amp; b &lt;c&gt; &nbsp;d")
    assert result == "a & b <c>  d"


def test_strip_html_empty():
    assert _strip_html("") == ""
