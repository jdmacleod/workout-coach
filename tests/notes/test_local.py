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

    imported, _ = _sync_notes(cfg, client, verbose=False)
    assert imported == 1
    workouts_dir = tmp_path / "workouts"
    assert (workouts_dir / "2026-06-12-hotel-gym.md").exists()


def test_sync_no_notes(tmp_path: Path) -> None:
    """list_notes() returns [] → imported=0."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()

    imported, _ = _sync_notes(cfg, client, verbose=False)
    assert imported == 0


def test_sync_already_local(tmp_path: Path) -> None:
    """File already exists locally with status completed → skip update gate, no change."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-10 Bench Press"
    _put_note(client, title, _yaml_note("2026-06-10", "Bench Press"))

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    # Write a completed local file so the performance gate fires
    local_content = _yaml_note("2026-06-10", "Bench Press")  # status: completed
    (workouts_dir / "2026-06-10-bench-press.md").write_text(local_content)

    imported, updated = _sync_notes(cfg, client, verbose=False)
    assert imported == 0
    assert updated == 0


def test_sync_comma_title_works(tmp_path: Path) -> None:
    """Comma in title is supported (newline delimiter fix in list_notes means commas don't split titles)."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-11 Yoga, Flow"
    _put_note(client, title, _yaml_note("2026-06-11", "Yoga, Flow"))

    imported, _ = _sync_notes(cfg, client, verbose=False)
    assert imported == 1
    workouts_dir = tmp_path / "workouts"
    files = list(workouts_dir.glob("2026-06-11-*.md"))
    assert len(files) == 1


def test_sync_no_date_prefix_skipped(tmp_path: Path) -> None:
    """Note without date prefix is skipped."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "Morning Run", "some content")

    imported, _ = _sync_notes(cfg, client, verbose=False)
    assert imported == 0
    workouts_dir = tmp_path / "workouts"
    assert not workouts_dir.exists() or not any(workouts_dir.glob("*.md"))


def test_sync_since_filter(tmp_path: Path) -> None:
    """--since filters notes before the cutoff date."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "2026-05-30 Old Session", _yaml_note("2026-05-30", "Old Session"))
    _put_note(client, "2026-06-10 New Session", _yaml_note("2026-06-10", "New Session"))

    imported, _ = _sync_notes(cfg, client, since=datetime.date(2026, 6, 1), verbose=False)
    assert imported == 1
    workouts_dir = tmp_path / "workouts"
    assert not (workouts_dir / "2026-05-30-old-session.md").exists()
    assert (workouts_dir / "2026-06-10-new-session.md").exists()


def test_sync_dry_run(tmp_path: Path) -> None:
    """--dry-run reports count but writes nothing."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "2026-06-12 Hotel Gym", _yaml_note("2026-06-12", "Hotel Gym"))

    imported, _ = _sync_notes(cfg, client, verbose=False, dry_run=True)
    assert imported == 1
    workouts_dir = tmp_path / "workouts"
    assert not workouts_dir.exists() or not any(workouts_dir.glob("*.md"))


def test_sync_idempotent(tmp_path: Path) -> None:
    """Running sync twice writes nothing on the second run."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "2026-06-12 Hotel Gym", _yaml_note("2026-06-12", "Hotel Gym"))

    first_imported, _ = _sync_notes(cfg, client, verbose=False)
    second_imported, _ = _sync_notes(cfg, client, verbose=False)
    assert first_imported == 1
    assert second_imported == 0


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

    imported, _ = _sync_notes(cfg, client, verbose=False)
    assert imported == 2
    workouts_dir = tmp_path / "workouts"
    files = sorted(workouts_dir.glob("2026-06-15-*.md"))
    assert len(files) == 2


def test_sync_empty_content_skipped(tmp_path: Path) -> None:
    """Empty note body is skipped."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    _put_note(client, "2026-06-12 Empty", "")

    imported, _ = _sync_notes(cfg, client, verbose=False)
    assert imported == 0


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
        imported, _ = _sync_notes(cfg, client, verbose=False)

    assert imported == 1
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

    imported, _ = _sync_notes(cfg, client, verbose=False, provider=provider)
    assert imported == 1
    workouts_dir = tmp_path / "workouts"
    written = list(workouts_dir.glob("2026-06-12-*.md"))
    assert len(written) == 1
    content = written[0].read_text()
    assert "strength" in content
    # Provider was called
    assert len(provider.calls) == 1


def test_sync_llm_parse_preserves_structured_sections(tmp_path: Path) -> None:
    """Ad-hoc note with ## Planned/## Completed + LLM provider → sections kept, status flips."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-12 Hotel Gym"
    _put_note(
        client,
        title,
        "## Planned\n\nSquats 5x5, push-ups 3x10.\n\n"
        "## Completed\n\nSquats 5x5 @ 185lb, push-ups 3x10.\n\n"
        "## How It Went\n\nFelt great, hit all reps.\n",
    )

    llm_response = json.dumps(
        {"type": "strength", "duration_actual": 40, "rpe": 6.5, "description": "Hotel gym session"}
    )
    provider = MockInferenceProvider(response_text=llm_response)

    imported, _ = _sync_notes(cfg, client, verbose=False, provider=provider)
    assert imported == 1
    workouts_dir = tmp_path / "workouts"
    written = list(workouts_dir.glob("2026-06-12-*.md"))
    assert len(written) == 1
    content = written[0].read_text()

    # The user's own Planned/Completed/How It Went content must survive, not be
    # clobbered by the LLM's narrow extraction.
    assert "Squats 5x5, push-ups 3x10." in content
    assert "Squats 5x5 @ 185lb, push-ups 3x10." in content
    assert "Felt great, hit all reps." in content
    # Real completed content present → status should flip from the default "planned".
    assert "status: completed" in content


def test_sync_llm_fallback(tmp_path: Path) -> None:
    """LLM returns invalid JSON → falls back to workout_from_note, raw text preserved."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-12 Hotel Gym"
    _put_note(client, title, "Did some squats and push-ups.")

    provider = MockInferenceProvider(response_text="not valid json at all")

    imported, _ = _sync_notes(cfg, client, verbose=False, provider=provider)
    assert imported == 1
    workouts_dir = tmp_path / "workouts"
    written = list(workouts_dir.glob("2026-06-12-*.md"))
    assert len(written) == 1
    content = written[0].read_text()
    # The ad-hoc note has no ## headers, so the fallback must not drop the raw text.
    assert "Did some squats and push-ups." in content


def test_sync_no_provider_fallback(tmp_path: Path) -> None:
    """Free-form note + provider=None → best-effort parse, no LLM attempt, raw text preserved."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    title = "2026-06-12 Hotel Gym"
    _put_note(client, title, "Did squats and lunges for 30 minutes.")

    imported, _ = _sync_notes(cfg, client, verbose=False, provider=None)
    assert imported == 1
    workouts_dir = tmp_path / "workouts"
    written = list(workouts_dir.glob("2026-06-12-*.md"))
    assert len(written) == 1
    content = written[0].read_text()
    # Date from title should be used, not 1970-01-01
    assert "2026-06-12" in content
    # No headers in the raw note, so the fallback must preserve the text rather
    # than silently dropping it.
    assert "Did squats and lunges for 30 minutes." in content


def test_sync_invalid_calendar_date_skipped(tmp_path: Path) -> None:
    """Note with regex-valid but calendar-invalid date (month 13) is skipped."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    # Passes \d{4}-\d{2}-\d{2} regex but fromisoformat raises ValueError (month 13)
    _put_note(client, "2026-13-01 Bad Month", "some content")

    imported, _ = _sync_notes(cfg, client, verbose=False)
    assert imported == 0
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
        imported, _ = _sync_notes(cfg, client, verbose=True)
    finally:
        local_mod.console = orig_console

    output = string_io.getvalue()
    assert imported == 0
    assert "Morning Run" in output
    assert "skipped" in output


# ── Smart sync gate (iPhone edit detection) ───────────────────────────────────


def _planned_local_note(date_str: str, title: str) -> str:
    """Local .md file written by render_workout_note with placeholder Completed/How It Went."""
    from coach.notes.parser import workout_from_note

    note_title = f"{date_str} {title}"
    bare = f"""---
id: wrk-{date_str.replace("-", "")}-001
date: {date_str}
type: strength
status: planned
note_title: {note_title}
duration_planned: 55
source: generated
---

## Planned

Bench Press: 4x5
"""
    # Round-trip through render_workout_note to get proper placeholders
    from coach.notes.parser import render_workout_note

    workout = workout_from_note(bare, note_title)
    return render_workout_note(workout)


def _notes_html_with_completion(date_str: str, title: str, completed: str, how_went: str) -> str:
    """Simulates Apple Notes HTML content after a user has filled in completion fields."""
    import dataclasses

    from coach.notes.parser import render_workout_note_html, workout_from_note

    note_title = f"{date_str} {title}"
    bare = f"""---
id: wrk-{date_str.replace("-", "")}-001
date: {date_str}
type: strength
status: planned
note_title: {note_title}
duration_planned: 55
source: generated
---

## Planned

Bench Press: 4x5
"""
    workout = workout_from_note(bare, note_title)
    filled = dataclasses.replace(workout, completed_content=completed, how_it_went=how_went)
    return render_workout_note_html(filled)


# ── _is_placeholder_or_empty ──────────────────────────────────────────────────


def test_placeholder_detection_md_completed_variant(tmp_path: Path) -> None:
    """MD HTML-comment Completed placeholder is detected as placeholder."""
    from coach.notes.local import _is_placeholder_or_empty
    from coach.notes.parser import _COMPLETED_PLACEHOLDER_MD

    assert _is_placeholder_or_empty(_COMPLETED_PLACEHOLDER_MD)


def test_placeholder_detection_md_how_went_variant(tmp_path: Path) -> None:
    """MD HTML-comment How It Went placeholder is detected as placeholder."""
    from coach.notes.local import _is_placeholder_or_empty
    from coach.notes.parser import _HOW_WENT_PLACEHOLDER_MD

    assert _is_placeholder_or_empty(_HOW_WENT_PLACEHOLDER_MD)


def test_placeholder_detection_notes_completed_variant(tmp_path: Path) -> None:
    """Notes-stripped Completed placeholder is detected as placeholder."""
    from coach.notes.local import _is_placeholder_or_empty
    from coach.notes.parser import _COMPLETED_PLACEHOLDER_NOTES

    assert _is_placeholder_or_empty(_COMPLETED_PLACEHOLDER_NOTES)


def test_placeholder_detection_notes_how_went_variant(tmp_path: Path) -> None:
    """Notes-stripped How It Went placeholder is detected as placeholder."""
    from coach.notes.local import _is_placeholder_or_empty
    from coach.notes.parser import _HOW_WENT_PLACEHOLDER_NOTES

    assert _is_placeholder_or_empty(_HOW_WENT_PLACEHOLDER_NOTES)


def test_placeholder_detection_real_content(tmp_path: Path) -> None:
    """Real user content is NOT detected as placeholder."""
    from coach.notes.local import _is_placeholder_or_empty

    assert not _is_placeholder_or_empty("Bench 4x5 done")
    assert not _is_placeholder_or_empty("Felt strong today, hit all reps.")


def test_placeholder_detection_none_and_empty(tmp_path: Path) -> None:
    """None and empty string are both treated as empty (placeholder)."""
    from coach.notes.local import _is_placeholder_or_empty

    assert _is_placeholder_or_empty(None)
    assert _is_placeholder_or_empty("")
    assert _is_placeholder_or_empty("   ")


def test_placeholder_detection_legacy_how_went_md(tmp_path: Path) -> None:
    """Pre-T12 How It Went MD placeholder text is still recognised (backward compat)."""
    from coach.notes.local import _is_placeholder_or_empty

    old_placeholder = "<!-- Free text. The assessor will parse this for RPE, PRs, notes. -->"
    assert _is_placeholder_or_empty(old_placeholder)


def test_placeholder_detection_md_variants_derive_from_notes_variants() -> None:
    """MD placeholder strings are HTML-comment-wrapped versions of the Notes strings."""
    from coach.notes.parser import (
        _COMPLETED_PLACEHOLDER_MD,
        _COMPLETED_PLACEHOLDER_NOTES,
        _HOW_WENT_PLACEHOLDER_MD,
        _HOW_WENT_PLACEHOLDER_NOTES,
    )

    assert f"<!-- {_COMPLETED_PLACEHOLDER_NOTES} -->" == _COMPLETED_PLACEHOLDER_MD
    assert f"<!-- {_HOW_WENT_PLACEHOLDER_NOTES} -->" == _HOW_WENT_PLACEHOLDER_MD


# ── _maybe_update_local ───────────────────────────────────────────────────────


def test_update_gate_fires_when_notes_has_completion(tmp_path: Path) -> None:
    """Notes has real Completed content, local has placeholder → update fires."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    local_file = workouts_dir / "2026-06-14-upper-body.md"
    local_file.write_text(_planned_local_note(date_str, "Upper Body"))

    notes_content = _notes_html_with_completion(
        date_str, "Upper Body", "Bench 4x5 done.", "Felt great, hit all sets."
    )
    _put_note(client, title, notes_content)

    imported, updated = _sync_notes(cfg, client, verbose=False)
    assert imported == 0
    assert updated == 1

    content = local_file.read_text()
    assert "Bench 4x5 done." in content


def test_update_gate_skips_when_local_has_real_content(tmp_path: Path) -> None:
    """Local already has real completed content → no update (local wins)."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    local_file = workouts_dir / "2026-06-14-upper-body.md"
    # Local already has real content (status=planned but completed_content filled)
    local_file.write_text(
        _yaml_note(date_str, "Upper Body").replace("status: completed", "status: planned")
    )

    notes_content = _notes_html_with_completion(
        date_str, "Upper Body", "Different content from iPhone.", "Felt OK."
    )
    _put_note(client, title, notes_content)

    imported, updated = _sync_notes(cfg, client, verbose=False)
    assert imported == 0
    assert updated == 0


def test_update_gate_skips_status_completed(tmp_path: Path) -> None:
    """Local has status:completed → performance gate fires, get_note never called."""
    from unittest.mock import MagicMock, patch

    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    (workouts_dir / "2026-06-14-upper-body.md").write_text(
        _yaml_note(date_str, "Upper Body")  # status: completed
    )
    _put_note(client, title, _yaml_note(date_str, "Upper Body"))

    mock_get = MagicMock(wraps=client.get_note)
    with patch.object(client, "get_note", mock_get):
        imported, updated = _sync_notes(cfg, client, verbose=False)

    assert imported == 0
    assert updated == 0
    mock_get.assert_not_called()


def test_update_dry_run_no_write(tmp_path: Path) -> None:
    """dry_run=True → update detected but no file write."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    local_file = workouts_dir / "2026-06-14-upper-body.md"
    original_content = _planned_local_note(date_str, "Upper Body")
    local_file.write_text(original_content)

    notes_content = _notes_html_with_completion(
        date_str, "Upper Body", "Bench 4x5 done.", "Felt strong."
    )
    _put_note(client, title, notes_content)

    imported, updated = _sync_notes(cfg, client, verbose=False, dry_run=True)
    assert imported == 0
    assert updated == 1
    # File must NOT be modified in dry-run
    assert local_file.read_text() == original_content


def test_update_note_not_found_warns_continues(tmp_path: Path) -> None:
    """NoteNotFoundError during update → warning printed, update skipped, sync continues."""
    from unittest.mock import patch

    from coach.notes.exceptions import NoteNotFoundError
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"
    title2 = f"{date_str} Lower Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    # First note: local planned → triggers update gate → raises NoteNotFoundError
    (workouts_dir / "2026-06-14-upper-body.md").write_text(
        _planned_local_note(date_str, "Upper Body")
    )
    _put_note(client, title, _yaml_note(date_str, "Upper Body"))

    # Second note: new → import path should still succeed
    _put_note(client, title2, _yaml_note(date_str, "Lower Body"))

    original_get = client.get_note

    def raise_on_upper(folder: str, t: str) -> str:
        if "Upper Body" in t:
            raise NoteNotFoundError("gone")
        return original_get(folder, t)

    with patch.object(client, "get_note", side_effect=raise_on_upper):
        imported, updated = _sync_notes(cfg, client, verbose=False)

    assert imported == 1
    assert updated == 0
    assert (workouts_dir / "2026-06-14-lower-body.md").exists()


def test_e1_status_set_completed_on_update(tmp_path: Path) -> None:
    """After iPhone edit is synced, status is set to completed (E1)."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    local_file = workouts_dir / "2026-06-14-upper-body.md"
    local_file.write_text(_planned_local_note(date_str, "Upper Body"))

    notes_content = _notes_html_with_completion(
        date_str, "Upper Body", "Bench 4x5 done.", "Felt great."
    )
    _put_note(client, title, notes_content)

    _sync_notes(cfg, client, verbose=False)

    content = local_file.read_text()
    assert "status: completed" in content


def test_e2_updated_counter_in_sync_result(tmp_path: Path) -> None:
    """_sync_notes returns (imported=0, updated=1) when update path fires."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    (workouts_dir / "2026-06-14-upper-body.md").write_text(
        _planned_local_note(date_str, "Upper Body")
    )
    notes_content = _notes_html_with_completion(
        date_str, "Upper Body", "Bench 4x5 done.", "Felt great."
    )
    _put_note(client, title, notes_content)

    imported, updated = _sync_notes(cfg, client, verbose=False)
    assert imported == 0
    assert updated == 1


def test_e3_verbose_already_current_count(tmp_path: Path) -> None:
    """verbose=True prints 'N already current' when local matches Notes."""
    from io import StringIO

    from rich.console import Console

    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    # Local planned with placeholder — Notes also has placeholder (no real content)
    (workouts_dir / "2026-06-14-upper-body.md").write_text(
        _planned_local_note(date_str, "Upper Body")
    )
    # Notes has no completion content either (both sides are empty/placeholder)
    _put_note(client, title, _planned_local_note(date_str, "Upper Body"))

    string_io = StringIO()
    import coach.notes.local as local_mod

    orig_console = local_mod.console
    local_mod.console = Console(file=string_io, highlight=False)
    try:
        _sync_notes(cfg, client, verbose=True)
    finally:
        local_mod.console = orig_console

    output = string_io.getvalue()
    assert "already current" in output


def test_performance_gate_oserror_skips_gracefully(tmp_path: Path) -> None:
    """When local file is unreadable (OSError), update gate is skipped (treated as assessed)."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    local_file = workouts_dir / "2026-06-14-upper-body.md"
    local_file.write_text(_planned_local_note(date_str, "Upper Body"))

    notes_content = _notes_html_with_completion(
        date_str, "Upper Body", "Bench 4x5 done.", "Felt great."
    )
    _put_note(client, title, notes_content)

    local_file.chmod(0o000)
    try:
        # PermissionError (OSError subclass) → local_status = "completed" → update gate skipped
        imported, updated = _sync_notes(cfg, client, verbose=False)
        assert imported == 0
        assert updated == 0
    finally:
        local_file.chmod(0o644)


def test_update_only_how_went_preserves_planned_status(tmp_path: Path) -> None:
    """How It Went updated from iPhone with placeholder Completed → status stays planned (E1 only fires on completed_content)."""
    from coach.notes.local import _sync_notes

    cfg = _make_cfg(tmp_path)
    client = MockNotesClient()
    date_str = "2026-06-14"
    title = f"{date_str} Upper Body"

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir(parents=True)
    local_file = workouts_dir / "2026-06-14-upper-body.md"
    local_file.write_text(_planned_local_note(date_str, "Upper Body"))

    # Notes: Completed = placeholder (""), How It Went = real content
    notes_content = _notes_html_with_completion(
        date_str, "Upper Body", "", "Felt strong, hit all reps."
    )
    _put_note(client, title, notes_content)

    imported, updated = _sync_notes(cfg, client, verbose=False)
    assert imported == 0
    assert updated == 1

    content = local_file.read_text()
    assert "Felt strong, hit all reps." in content
    assert "status: planned" in content  # E1 requires completed_content — not triggered here
