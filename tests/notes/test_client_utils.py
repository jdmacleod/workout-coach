"""Unit tests for pure-Python helpers in coach/notes/client.py"""

from unittest.mock import patch

from coach.notes.client import NotesClient, _escape_for_applescript, _strip_html


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


# ── ensure_folder AppleScript generation ──────────────────────────────────────


def test_ensure_folder_flat_uses_account_level() -> None:
    """A single-component path creates a top-level folder at the account."""
    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with patch("coach.notes.client._run_applescript") as mock_run:
        client.ensure_folder("Exercise Coach")
    assert mock_run.call_count == 1
    script = mock_run.call_args[0][0]
    assert 'make new folder at acct with properties {name:"Exercise Coach"}' in script
    # No leaf should be created at currentParent for a flat path
    assert "make new folder at currentParent" not in script


def test_ensure_folder_nested_uses_parent_ref() -> None:
    """A two-component path creates the leaf at the parent folder, not at acct."""
    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with patch("coach.notes.client._run_applescript") as mock_run:
        client.ensure_folder("Exercise Coach/Plans")
    assert mock_run.call_count == 1
    script = mock_run.call_args[0][0]
    # Parent created at account level with leaf name only
    assert 'make new folder at acct with properties {name:"Exercise Coach"}' in script
    # Child created at parent reference with leaf name only
    assert 'make new folder at currentParent with properties {name:"Plans"}' in script
    # The full slash-path must NOT appear as a folder name
    assert '"Exercise Coach/Plans"' not in script


def test_ensure_folder_nested_no_slash_in_name() -> None:
    """Regression: ensure_folder must never pass a slash-containing string as a name."""
    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with patch("coach.notes.client._run_applescript") as mock_run:
        for folder in ("Exercise Coach", "Exercise Coach/Plans", "Exercise Coach/Workouts"):
            client.ensure_folder(folder)
    for c in mock_run.call_args_list:
        script = c[0][0]
        # No name argument should ever contain a forward slash
        import re

        for m in re.finditer(r'name:"([^"]*)"', script):
            assert "/" not in m.group(1), f"slash in name argument: {m.group(1)!r}"


def test_ensure_folder_empty_path_is_noop() -> None:
    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with patch("coach.notes.client._run_applescript") as mock_run:
        client.ensure_folder("")
    mock_run.assert_not_called()
