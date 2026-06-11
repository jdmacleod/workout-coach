"""Unit tests for coach log command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from coach.config import Config, DataConfig, NotesConfig
from coach.notes.schema import FOLDER_WORKOUTS
from tests.notes.mock_client import MockNotesClient


def _make_config(tmp_dir: str) -> Config:
    cfg = Config()
    cfg.data = DataConfig(workouts_dir=str(Path(tmp_dir) / "workouts") + "/")
    cfg.notes = NotesConfig()
    return cfg


def test_log_creates_note_and_local_file(tmp_path):
    """coach log creates a note in MockNotesClient and writes a local .md file."""
    from coach.commands.log import _run_log

    cfg = _make_config(str(tmp_path))
    mock_client = MockNotesClient()

    inputs = iter(["strength", "Upper Body", "50", "Barbell work", "7", "Felt great"])

    with (
        patch("coach.commands.log.load_config", return_value=cfg),
        patch("typer.prompt", side_effect=lambda msg, default="": next(inputs)),
    ):
        _run_log(
            date_str="2026-06-09",
            workout_type=None,
            title=None,
            notes_client=mock_client,
        )

    # Note created in Apple Notes mock
    notes = mock_client.list_notes(FOLDER_WORKOUTS)
    assert len(notes) == 1
    assert "2026-06-09" in notes[0]
    assert "Upper Body" in notes[0]

    # Local file written
    workouts_dir = tmp_path / "workouts"
    local_files = list(workouts_dir.glob("2026-06-09-*.md"))
    assert len(local_files) == 1
    content = local_files[0].read_text()
    assert "date: 2026-06-09" in content
    assert "status: completed" in content


def test_log_with_flags_skips_type_and_title_prompts(tmp_path):
    """When --type and --title are passed, no prompts for those fields."""
    from coach.commands.log import _run_log

    cfg = _make_config(str(tmp_path))
    mock_client = MockNotesClient()

    inputs = iter(["45", "", "", ""])  # duration, description, rpe, how_it_went

    with (
        patch("coach.commands.log.load_config", return_value=cfg),
        patch("typer.prompt", side_effect=lambda msg, default="": next(inputs)),
    ):
        _run_log(
            date_str="2026-06-10",
            workout_type="cardio",
            title="Zone 2 Run",
            notes_client=mock_client,
        )

    notes = mock_client.list_notes(FOLDER_WORKOUTS)
    assert any("Zone 2 Run" in n for n in notes)
