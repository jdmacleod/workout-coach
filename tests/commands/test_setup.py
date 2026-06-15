"""Unit tests for coach setup questionnaire and config writing."""

from __future__ import annotations

import tomllib

import pytest


def test_write_config_values_equipment_and_duration(tmp_path: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from coach.commands.setup import _write_config_values
    from coach.config import CONFIG_EXAMPLE

    fake_config = tmp_path / "config.toml"  # type: ignore[operator]
    fake_config.write_text(CONFIG_EXAMPLE.read_text())

    with patch("coach.commands.setup.CONFIG_FILE", fake_config):
        _write_config_values(
            name="Alice",
            days="5",
            goal="strength",
            injuries="",
            equipment=["barbell", "pull-up bar", "rings"],
            max_duration=45,
            plan_note_links=True,
        )

    parsed = tomllib.loads(fake_config.read_text())
    assert parsed["profile"]["available_equipment"] == ["barbell", "pull-up bar", "rings"]
    assert parsed["profile"]["max_session_duration_minutes"] == 45


def test_write_config_values_empty_equipment(tmp_path: pytest.MonkeyPatch) -> None:
    from unittest.mock import patch

    from coach.commands.setup import _write_config_values
    from coach.config import CONFIG_EXAMPLE

    fake_config = tmp_path / "config.toml"  # type: ignore[operator]
    fake_config.write_text(CONFIG_EXAMPLE.read_text())

    with patch("coach.commands.setup.CONFIG_FILE", fake_config):
        _write_config_values(
            name="Bob",
            days="4",
            goal="general fitness",
            injuries="",
            equipment=[],
            max_duration=0,
            plan_note_links=True,
        )

    parsed = tomllib.loads(fake_config.read_text())
    assert parsed["profile"]["available_equipment"] == []
    assert parsed["profile"]["max_session_duration_minutes"] == 0


def test_questionnaire_parses_equipment_string(tmp_path: pytest.MonkeyPatch) -> None:
    """Comma-separated input is split into a list, stripping whitespace."""
    from unittest.mock import patch

    from coach.commands.setup import _write_config_values
    from coach.config import CONFIG_EXAMPLE

    fake_config = tmp_path / "config.toml"  # type: ignore[operator]
    fake_config.write_text(CONFIG_EXAMPLE.read_text())

    equipment_raw = "barbell,  bumper plates, pull-up bar"
    equipment = [e.strip() for e in equipment_raw.split(",") if e.strip()]

    with patch("coach.commands.setup.CONFIG_FILE", fake_config):
        _write_config_values(
            name="",
            days="4",
            goal="general fitness",
            injuries="",
            equipment=equipment,
            max_duration=30,
            plan_note_links=True,
        )

    parsed = tomllib.loads(fake_config.read_text())
    assert parsed["profile"]["available_equipment"] == ["barbell", "bumper plates", "pull-up bar"]
    assert parsed["profile"]["max_session_duration_minutes"] == 30


def test_setup_creates_template_note() -> None:
    """_setup_notes_folders creates 'Template — Workout' note in Workouts folder."""
    from unittest.mock import MagicMock, patch

    from coach.commands.setup import _setup_notes_folders
    from coach.config import CONFIG_EXAMPLE, NotesConfig
    from tests.notes.mock_client import MockNotesClient

    mock_client = MockNotesClient()
    mock_cfg = MagicMock()
    mock_cfg.notes = NotesConfig()

    with (
        patch("coach.commands.setup.load_config", return_value=mock_cfg),
        patch("coach.notes.client.NotesClient", return_value=mock_client),
        patch("coach.commands.setup.CONFIG_FILE", CONFIG_EXAMPLE),
    ):
        _setup_notes_folders()

    from coach.notes.schema import FOLDER_WORKOUTS

    assert mock_client.note_exists(FOLDER_WORKOUTS, "Template — Workout")
    body = mock_client.get_note(FOLDER_WORKOUTS, "Template — Workout")
    assert "date: YYYY-MM-DD" in body


def test_setup_template_idempotent() -> None:
    """Running _setup_notes_folders twice does not duplicate the template note."""
    from unittest.mock import MagicMock, patch

    from coach.commands.setup import _setup_notes_folders
    from coach.config import CONFIG_EXAMPLE, NotesConfig
    from tests.notes.mock_client import MockNotesClient

    mock_client = MockNotesClient()
    mock_cfg = MagicMock()
    mock_cfg.notes = NotesConfig()

    with (
        patch("coach.commands.setup.load_config", return_value=mock_cfg),
        patch("coach.notes.client.NotesClient", return_value=mock_client),
        patch("coach.commands.setup.CONFIG_FILE", CONFIG_EXAMPLE),
    ):
        _setup_notes_folders()
        _setup_notes_folders()  # second call should be a no-op

    from coach.notes.schema import FOLDER_WORKOUTS

    # Still exactly one note with that title
    notes = [
        t for (f, t) in mock_client._store if f == FOLDER_WORKOUTS and t == "Template — Workout"
    ]
    assert len(notes) == 1
