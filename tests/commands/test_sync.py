"""Unit tests for coach sync CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from coach.cli import app
from coach.config import Config, DataConfig, NotesConfig
from tests.notes.mock_client import MockNotesClient

FOLDER_WORKOUTS = "Exercise Coach/Workouts"

runner = CliRunner()


def _yaml_note(date_str: str, title_suffix: str = "Session") -> str:
    return f"""---
id: wrk-{date_str.replace("-", "")}-001
date: {date_str}
type: strength
status: completed
note_title: {date_str} {title_suffix}
duration_actual: 45
rpe: 7.0
---

## Completed

Some exercises.

## How It Went

Good.
"""


def _make_cfg(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.data = DataConfig(
        workouts_dir=str(tmp_path / "workouts") + "/",
        plans_dir=str(tmp_path / "plans") + "/",
        assessments_dir=str(tmp_path / "assessments") + "/",
    )
    cfg.notes = NotesConfig()
    return cfg


def test_sync_cli_no_notes(tmp_path: Path) -> None:
    """coach sync with no notes reports 0 unsynced."""
    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()

    with (
        patch("coach.commands.sync.load_config", return_value=cfg),
        patch("coach.commands.sync.NotesClient", return_value=client),
        patch("coach.commands.sync.get_provider", side_effect=Exception("no provider")),
    ):
        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "0 new, 0 updated" in result.output


def test_sync_cli_happy_path(tmp_path: Path) -> None:
    """coach sync writes a local file and reports synced."""
    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    client.create_note(
        FOLDER_WORKOUTS, "2026-06-12 Hotel Gym", _yaml_note("2026-06-12", "Hotel Gym")
    )

    with (
        patch("coach.commands.sync.load_config", return_value=cfg),
        patch("coach.commands.sync.NotesClient", return_value=client),
        patch("coach.commands.sync.get_provider", side_effect=Exception("no provider")),
    ):
        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "1 new" in result.output
    assert (tmp_path / "workouts" / "2026-06-12-hotel-gym.md").exists()


def test_sync_cli_dry_run(tmp_path: Path) -> None:
    """coach sync --dry-run labels notes as 'would sync' but writes nothing."""
    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    client.create_note(
        FOLDER_WORKOUTS, "2026-06-12 Hotel Gym", _yaml_note("2026-06-12", "Hotel Gym")
    )

    with (
        patch("coach.commands.sync.load_config", return_value=cfg),
        patch("coach.commands.sync.NotesClient", return_value=client),
        patch("coach.commands.sync.get_provider", side_effect=Exception("no provider")),
    ):
        result = runner.invoke(app, ["sync", "--dry-run"])

    assert result.exit_code == 0
    assert "would sync" in result.output
    assert not (tmp_path / "workouts").exists() or not any((tmp_path / "workouts").glob("*.md"))


def test_sync_cli_since_flag(tmp_path: Path) -> None:
    """coach sync --since filters out older notes."""
    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    client.create_note(FOLDER_WORKOUTS, "2026-05-01 Old", _yaml_note("2026-05-01", "Old"))
    client.create_note(FOLDER_WORKOUTS, "2026-06-10 New", _yaml_note("2026-06-10", "New"))

    with (
        patch("coach.commands.sync.load_config", return_value=cfg),
        patch("coach.commands.sync.NotesClient", return_value=client),
        patch("coach.commands.sync.get_provider", side_effect=Exception("no provider")),
    ):
        result = runner.invoke(app, ["sync", "--since", "2026-06-01"])

    assert result.exit_code == 0
    assert "1 new" in result.output
    workouts_dir = tmp_path / "workouts"
    assert not (workouts_dir / "2026-05-01-old.md").exists()
    assert (workouts_dir / "2026-06-10-new.md").exists()


def test_sync_cli_invalid_since(tmp_path: Path) -> None:
    """coach sync --since with bad date exits with error."""
    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()

    with (
        patch("coach.commands.sync.load_config", return_value=cfg),
        patch("coach.commands.sync.NotesClient", return_value=client),
        patch("coach.commands.sync.get_provider", side_effect=Exception("no provider")),
    ):
        result = runner.invoke(app, ["sync", "--since", "not-a-date"])

    assert result.exit_code == 1


def test_sync_cli_config_not_found() -> None:
    """coach sync exits 1 when no config exists."""
    from coach.config import ConfigNotFoundError

    with patch("coach.commands.sync.load_config", side_effect=ConfigNotFoundError("no config")):
        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 1


def test_sync_cli_notes_client_error(tmp_path: Path) -> None:
    """coach sync exits 1 when Apple Notes is unavailable."""
    from unittest.mock import MagicMock

    from coach.notes.exceptions import NotesClientError

    cfg = _make_cfg(tmp_path)
    bad_client = MagicMock()
    bad_client.list_notes.side_effect = NotesClientError("Notes unavailable")

    with (
        patch("coach.commands.sync.load_config", return_value=cfg),
        patch("coach.commands.sync.NotesClient", return_value=bad_client),
        patch("coach.commands.sync.get_provider", side_effect=Exception("no provider")),
    ):
        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 1
