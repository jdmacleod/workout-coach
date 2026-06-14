"""Unit tests for _load_week_workouts exception logging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_load_week_workouts_logs_bad_file(tmp_path: Path) -> None:
    """A malformed workout file produces a console warning instead of silent skip."""
    from coach.commands.assess import _load_week_workouts

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir()
    # Write a file with invalid UTF-8 so read_text() raises UnicodeDecodeError
    (workouts_dir / "2026-06-08-bad.md").write_bytes(b"\xff\xfd binary garbage")

    with patch("coach.commands.assess.console") as mock_console:
        result = _load_week_workouts(workouts_dir, "2026-W24")

    assert result == []
    mock_console.print.assert_called_once()
    warning_text = mock_console.print.call_args[0][0]
    assert "2026-06-08-bad.md" in warning_text
    assert "Warning" in warning_text
