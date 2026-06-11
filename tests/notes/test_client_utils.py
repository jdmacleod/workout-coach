"""Unit tests for pure-Python helpers in coach/notes/client.py"""

from unittest.mock import patch

from coach.notes.client import (
    NotesClient,
    _escape_for_applescript,
    _folder_script_lines,
    _is_not_found_error,
    _strip_html,
)


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


# ── _folder_script_lines helper ───────────────────────────────────────────────


def test_folder_script_lines_flat() -> None:
    """Single-component path sets targetFolder directly off acct."""
    lines = _folder_script_lines("Exercise Coach", "iCloud")
    joined = "\n".join(lines)
    assert 'set acct to account "iCloud"' in joined
    assert 'set targetFolder to folder "Exercise Coach" of acct' in joined
    assert "targetFolder" in joined
    assert "Exercise Coach/Plans" not in joined


def test_folder_script_lines_nested_two_levels() -> None:
    """Two-component path walks acct → root → leaf, never using a slash name."""
    lines = _folder_script_lines("Exercise Coach/Assessments", "iCloud")
    joined = "\n".join(lines)
    assert 'set targetFolder to folder "Exercise Coach" of acct' in joined
    assert 'set targetFolder to folder "Assessments" of targetFolder' in joined
    assert '"Exercise Coach/Assessments"' not in joined


def test_folder_script_lines_three_levels() -> None:
    """Three-component path produces three sequential set statements."""
    lines = _folder_script_lines("A/B/C", "iCloud")
    assert len(lines) == 4  # acct line + 3 folder traversals
    assert 'set targetFolder to folder "A" of acct' in lines[1]
    assert 'set targetFolder to folder "B" of targetFolder' in lines[2]
    assert 'set targetFolder to folder "C" of targetFolder' in lines[3]


# ── note operations use nested folder traversal ───────────────────────────────


def test_get_note_nested_folder_no_slash_in_script() -> None:
    """get_note must not embed 'Exercise Coach/Assessments' as a flat folder name."""
    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with patch("coach.notes.client._run_applescript", return_value="<p>hi</p>") as mock_run:
        result = client.get_note("Exercise Coach/Assessments", "Assessment 2026-W23")
    assert result == "hi"
    script = mock_run.call_args[0][0]
    assert '"Exercise Coach/Assessments"' not in script
    assert 'set targetFolder to folder "Exercise Coach" of acct' in script
    assert 'set targetFolder to folder "Assessments" of targetFolder' in script
    assert "targetFolder" in script


def test_note_exists_nested_folder() -> None:
    """note_exists must use nested traversal for slash-separated folder paths."""
    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with patch("coach.notes.client._run_applescript", return_value="true") as mock_run:
        result = client.note_exists("Exercise Coach/Plans", "Week Plan")
    assert result is True
    script = mock_run.call_args[0][0]
    assert '"Exercise Coach/Plans"' not in script
    assert 'set targetFolder to folder "Plans" of targetFolder' in script


def test_list_notes_nested_folder() -> None:
    """list_notes must traverse nested folders rather than using a slash-path."""
    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with patch("coach.notes.client._run_applescript", return_value="Note A, Note B") as mock_run:
        titles = client.list_notes("Exercise Coach/Workouts")
    assert titles == ["Note A", "Note B"]
    script = mock_run.call_args[0][0]
    assert '"Exercise Coach/Workouts"' not in script
    assert 'set targetFolder to folder "Workouts" of targetFolder' in script


# ── _is_not_found_error helper ────────────────────────────────────────────────


def test_is_not_found_error_can_get() -> None:
    from coach.notes.exceptions import NotesClientError

    assert _is_not_found_error(
        NotesClientError('AppleScript failed (exit 1): Can\'t get folder "X".')
    )


def test_is_not_found_error_doesnt_exist() -> None:
    from coach.notes.exceptions import NotesClientError

    assert _is_not_found_error(NotesClientError("AppleScript failed (exit 1): item doesn't exist"))


def test_is_not_found_error_cant_find() -> None:
    """macOS 16+ Notes may return 'Can't find item' instead of 'Can't get'."""
    from coach.notes.exceptions import NotesClientError

    assert _is_not_found_error(
        NotesClientError('AppleScript failed (exit 1): Can\'t find item "X".')
    )


def test_is_not_found_error_was_not_found() -> None:
    """macOS 16+ Notes may return 'was not found' phrasing."""
    from coach.notes.exceptions import NotesClientError

    assert _is_not_found_error(
        NotesClientError('AppleScript failed (exit 1): folder "X" was not found. (-1728)')
    )


def test_is_not_found_error_numeric_code() -> None:
    """(-1728) numeric code alone is sufficient to classify as not-found."""
    from coach.notes.exceptions import NotesClientError

    assert _is_not_found_error(
        NotesClientError("AppleScript failed (exit 1): unknown phrase. (-1728)")
    )


def test_is_not_found_error_other_error() -> None:
    """Connection errors must not be misclassified as not-found."""
    from coach.notes.exceptions import NotesClientError

    assert not _is_not_found_error(
        NotesClientError("AppleScript failed (exit 1): connection is invalid. (-609)")
    )


# ── list_notes — folder-not-found returns empty list ──────────────────────────


def test_list_notes_returns_empty_when_folder_missing() -> None:
    """list_notes returns [] when the folder itself doesn't exist."""
    from coach.notes.exceptions import NotesClientError

    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with patch(
        "coach.notes.client._run_applescript",
        side_effect=NotesClientError(
            'AppleScript failed (exit 1): Can\'t get folder "Workouts" of folder "Exercise Coach" of account "iCloud".'
        ),
    ):
        result = client.list_notes("Exercise Coach/Workouts")
    assert result == []


def test_list_notes_propagates_non_folder_errors() -> None:
    """list_notes re-raises NotesClientError that isn't a missing-item error."""
    import pytest

    from coach.notes.exceptions import NotesClientError

    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with (
        patch(
            "coach.notes.client._run_applescript",
            side_effect=NotesClientError("AppleScript failed (exit 1): permission denied"),
        ),
        pytest.raises(NotesClientError),
    ):
        client.list_notes("Exercise Coach/Workouts")


# ── note_exists — folder-not-found returns False ─────────────────────────────


def test_note_exists_returns_false_when_folder_missing() -> None:
    """note_exists returns False when the folder itself doesn't exist (first-time-use)."""
    from coach.notes.exceptions import NotesClientError

    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with patch(
        "coach.notes.client._run_applescript",
        side_effect=NotesClientError(
            "AppleScript failed (exit 1): "
            'Can\'t get folder "Assessments" of folder "Exercise Coach" of account "iCloud".'
        ),
    ):
        result = client.note_exists("Exercise Coach/Assessments", "Assessment 2026-W22")
    assert result is False


def test_note_exists_propagates_non_folder_errors() -> None:
    """note_exists re-raises NotesClientError that isn't a missing-item error."""
    import pytest

    from coach.notes.exceptions import NotesClientError

    client = NotesClient(account="iCloud", root_folder="Exercise Coach")
    with (
        patch(
            "coach.notes.client._run_applescript",
            side_effect=NotesClientError("AppleScript failed (exit 1): permission denied"),
        ),
        pytest.raises(NotesClientError),
    ):
        client.note_exists("Exercise Coach/Assessments", "Any Note")
