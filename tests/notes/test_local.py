"""Unit tests for coach/notes/local.py — _sync_notes and _write_local_workout."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from coach.config import Config, DataConfig, NotesConfig
from coach.notes.exceptions import NotesClientError
from tests.intelligence.mock_provider import MockInferenceProvider
from tests.notes.mock_client import MockNotesClient

FOLDER_WORKOUTS = "Exercise Coach/Workouts"


def _make_cfg(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.data = DataConfig(
        workouts_dir=str(tmp_path / "workouts") + "/",
        plans_dir=str(tmp_path / "plans") + "/",
        assessments_dir=str(tmp_path / "assessments") + "/",
    )
    cfg.notes = NotesConfig()
    return cfg


def _yaml_note(date_str: str, title: str = "") -> str:
    note_title = f"{date_str} {title}" if title else date_str
    return f"""---
id: wrk-{date_str.replace("-", "")}-001
date: {date_str}
type: strength
status: completed
note_title: {note_title}
duration_actual: 45
rpe: 7.0
---

## Completed

Bench press 4x5.

## How It Went

Felt strong.
"""


def _put_note(client: MockNotesClient, title: str, body: str) -> None:
    client.create_note(FOLDER_WORKOUTS, title, body)


# ── _write_local_workout ──────────────────────────────────────────────────────


def test_write_local_workout_creates_file(tmp_path: Path) -> None:
    from coach.notes.local import _write_local_workout
    from coach.notes.parser import workout_from_note

    workouts_dir = tmp_path / "workouts"
    content = _yaml_note("2026-06-10", "Bench Press Day")
    workout = workout_from_note(content, "2026-06-10 Bench Press Day")
    _write_local_workout(workouts_dir, workout)
    assert (workouts_dir / "2026-06-10-bench-press-day.md").exists()


def test_write_local_workout_slug_truncated(tmp_path: Path) -> None:
    from coach.notes.local import _write_local_workout
    from coach.notes.parser import workout_from_note

    workouts_dir = tmp_path / "workouts"
    long_title = "2026-06-10 " + "A" * 60
    content = _yaml_note("2026-06-10", "A" * 60)
    workout = workout_from_note(content, long_title)
    _write_local_workout(workouts_dir, workout)
    files = list(workouts_dir.glob("*.md"))
    assert len(files) == 1
    assert len(files[0].stem) <= len("2026-06-10-") + 40


# ── _sync_notes happy paths ───────────────────────────────────────────────────


def test_sync_happy_path_yaml(tmp_path: Path) -> None:
    """A note with YAML front matter is written to local file."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-12 Hotel Gym"
    _put_note(client, title, _yaml_note("2026-06-12", "Hotel Gym"))

    synced = _sync_notes(cfg, client, verbose=False)
    assert synced == 1
    workouts_dir = tmp_path / "workouts"
    assert (workouts_dir / "2026-06-12-hotel-gym.md").exists()


def test_sync_no_notes(tmp_path: Path) -> None:
    """list_notes() returns [] → synced=0."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()

    synced = _sync_notes(cfg, client, verbose=False)
    assert synced == 0


def test_sync_already_local(tmp_path: Path) -> None:
    """File already exists locally → skip, synced=0."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-10 Bench Press"
    _put_note(client, title, _yaml_note("2026-06-10", "Bench Press"))

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    (workouts_dir / "2026-06-10-bench-press.md").write_text("existing")

    synced = _sync_notes(cfg, client, verbose=False)
    assert synced == 0
    # original file not overwritten
    assert (workouts_dir / "2026-06-10-bench-press.md").read_text() == "existing"


def test_sync_comma_title_works(tmp_path: Path) -> None:
    """Comma in title is supported (newline delimiter fix in list_notes means commas don't split titles)."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-11 Yoga, Flow"
    _put_note(client, title, _yaml_note("2026-06-11", "Yoga, Flow"))

    synced = _sync_notes(cfg, client, verbose=False)
    assert synced == 1
    workouts_dir = tmp_path / "workouts"
    files = list(workouts_dir.glob("2026-06-11-*.md"))
    assert len(files) == 1


def test_sync_no_date_prefix_skipped(tmp_path: Path) -> None:
    """Note without date prefix is skipped."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "Morning Run", "some content")

    synced = _sync_notes(cfg, client, verbose=False)
    assert synced == 0
    workouts_dir = tmp_path / "workouts"
    assert not workouts_dir.exists() or not any(workouts_dir.glob("*.md"))


def test_sync_since_filter(tmp_path: Path) -> None:
    """--since filters notes before the cutoff date."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "2026-05-30 Old Session", _yaml_note("2026-05-30", "Old Session"))
    _put_note(client, "2026-06-10 New Session", _yaml_note("2026-06-10", "New Session"))

    synced = _sync_notes(cfg, client, since=datetime.date(2026, 6, 1), verbose=False)
    assert synced == 1
    workouts_dir = tmp_path / "workouts"
    assert not (workouts_dir / "2026-05-30-old-session.md").exists()
    assert (workouts_dir / "2026-06-10-new-session.md").exists()


def test_sync_dry_run(tmp_path: Path) -> None:
    """--dry-run reports count but writes nothing."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "2026-06-12 Hotel Gym", _yaml_note("2026-06-12", "Hotel Gym"))

    synced = _sync_notes(cfg, client, verbose=False, dry_run=True)
    assert synced == 1
    workouts_dir = tmp_path / "workouts"
    assert not workouts_dir.exists() or not any(workouts_dir.glob("*.md"))


def test_sync_idempotent(tmp_path: Path) -> None:
    """Running sync twice writes nothing on the second run."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "2026-06-12 Hotel Gym", _yaml_note("2026-06-12", "Hotel Gym"))

    first = _sync_notes(cfg, client, verbose=False)
    second = _sync_notes(cfg, client, verbose=False)
    assert first == 1
    assert second == 0


def test_sync_slug_collision(tmp_path: Path) -> None:
    """Two notes producing the same slug get distinct filenames."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    long = "A" * 41
    title1 = f"2026-06-15 {long}X"
    title2 = f"2026-06-15 {long}Y"
    _put_note(client, title1, _yaml_note("2026-06-15", long + "X"))
    _put_note(client, title2, _yaml_note("2026-06-15", long + "Y"))

    synced = _sync_notes(cfg, client, verbose=False)
    assert synced == 2
    workouts_dir = tmp_path / "workouts"
    files = sorted(workouts_dir.glob("2026-06-15-*.md"))
    assert len(files) == 2


def test_sync_empty_content_skipped(tmp_path: Path) -> None:
    """Empty note body is skipped."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "2026-06-12 Empty", "")

    synced = _sync_notes(cfg, client, verbose=False)
    assert synced == 0


def test_sync_per_note_error_continues(tmp_path: Path) -> None:
    """NotesClientError on one note does not abort sync; other notes still synced."""
    from unittest.mock import patch

    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "2026-06-10 Bench Press", _yaml_note("2026-06-10", "Bench Press"))
    _put_note(client, "2026-06-11 Yoga", _yaml_note("2026-06-11", "Yoga"))

    original_get = client.get_note

    def failing_get(folder: str, title: str) -> str:
        if "Bench Press" in title:
            raise NotesClientError("note disappeared")
        return original_get(folder, title)

    with patch.object(client, "get_note", side_effect=failing_get):
        synced = _sync_notes(cfg, client, verbose=False)

    assert synced == 1
    workouts_dir = tmp_path / "workouts"
    assert (workouts_dir / "2026-06-11-yoga.md").exists()


# ── LLM parse paths ───────────────────────────────────────────────────────────


def test_sync_llm_parse(tmp_path: Path) -> None:
    """Free-form note with provider → LLM parse path → workout written."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-12 Hotel Gym"
    _put_note(client, title, "Did some squats and push-ups. Felt great.")

    llm_response = json.dumps(
        {"type": "strength", "duration_actual": 40, "rpe": 6.5, "description": "Hotel gym session"}
    )
    provider = MockInferenceProvider(response_text=llm_response)

    synced = _sync_notes(cfg, client, verbose=False, provider=provider)
    assert synced == 1
    workouts_dir = tmp_path / "workouts"
    written = list(workouts_dir.glob("2026-06-12-*.md"))
    assert len(written) == 1
    content = written[0].read_text()
    assert "strength" in content
    # Provider was called
    assert len(provider.calls) == 1


def test_sync_llm_fallback(tmp_path: Path) -> None:
    """LLM returns invalid JSON → falls back to workout_from_note."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-12 Hotel Gym"
    _put_note(client, title, "Did some squats and push-ups.")

    provider = MockInferenceProvider(response_text="not valid json at all")

    synced = _sync_notes(cfg, client, verbose=False, provider=provider)
    assert synced == 1
    workouts_dir = tmp_path / "workouts"
    assert any(workouts_dir.glob("2026-06-12-*.md"))


def test_sync_no_provider_fallback(tmp_path: Path) -> None:
    """Free-form note + provider=None → best-effort parse, no LLM attempt."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-12 Hotel Gym"
    _put_note(client, title, "Did squats and lunges for 30 minutes.")

    synced = _sync_notes(cfg, client, verbose=False, provider=None)
    assert synced == 1
    workouts_dir = tmp_path / "workouts"
    written = list(workouts_dir.glob("2026-06-12-*.md"))
    assert len(written) == 1
    content = written[0].read_text()
    # Date from title should be used, not 1970-01-01
    assert "2026-06-12" in content


def test_sync_invalid_calendar_date_skipped(tmp_path: Path) -> None:
    """Note with regex-valid but calendar-invalid date (month 13) is skipped."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    # Passes \d{4}-\d{2}-\d{2} regex but fromisoformat raises ValueError (month 13)
    _put_note(client, "2026-13-01 Bad Month", "some content")

    synced = _sync_notes(cfg, client, verbose=False)
    assert synced == 0
    workouts_dir = tmp_path / "workouts"
    assert not workouts_dir.exists() or not any(workouts_dir.glob("*.md"))


def test_sync_verbose_no_path_rows(tmp_path: Path, capsys: object) -> None:
    """verbose=True with a no-date-prefix note prints a row without a path arrow."""
    from io import StringIO

    from rich.console import Console

    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "Morning Run", "some content")

    # Capture rich output via redirect
    string_io = StringIO()
    import coach.notes.local as local_mod

    orig_console = local_mod.console
    local_mod.console = Console(file=string_io, highlight=False)
    try:
        synced = _sync_notes(cfg, client, verbose=True)
    finally:
        local_mod.console = orig_console

    output = string_io.getvalue()
    assert synced == 0
    assert "Morning Run" in output
    assert "skipped" in output
