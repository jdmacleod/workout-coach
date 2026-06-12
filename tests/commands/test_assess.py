"""Unit tests for coach assess command."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import patch

from coach.config import Config, DataConfig, NotesConfig
from coach.notes.schema import FOLDER_ASSESSMENTS
from tests.intelligence.mock_provider import MockInferenceProvider
from tests.notes.mock_client import MockNotesClient

MOCK_ASSESS_RESPONSE = json.dumps(
    {
        "status": "completed",
        "duration_actual": 55,
        "rpe": 7.5,
        "mood": "good",
        "soreness": "mild",
        "prs": [],
        "deviations": [],
        "summary": "Solid session.",
    }
)

MOCK_SUMMARY_RESPONSE = "Good week overall. Strength was up. Keep the load similar next week."
MOCK_NEXT_WEEK_NOTES = "Good week. Keep volume steady. Watch shoulder on pressing days."


def _make_config(tmp_dir: str) -> Config:
    cfg = Config()
    cfg.data = DataConfig(
        workouts_dir=str(Path(tmp_dir) / "workouts") + "/",
        plans_dir=str(Path(tmp_dir) / "plans") + "/",
        assessments_dir=str(Path(tmp_dir) / "assessments") + "/",
    )
    cfg.notes = NotesConfig()
    return cfg


def _write_workout(workouts_dir: Path, date_str: str, title: str, status: str = "planned") -> Path:
    """Write a minimal workout file for testing. Returns the path written."""
    workouts_dir.mkdir(parents=True, exist_ok=True)
    slug = title.lower().replace(" ", "-")
    note_title = f"{date_str} {title}"
    content = f"""---
id: wrk-{date_str.replace("-", "")}-001
date: {date_str}
type: strength
subtype: upper
status: {status}
note_title: {note_title}
duration_planned: 55
source: generated
---

## Planned

Bench Press: 4x5

## Completed

Done all sets.

## How It Went

Felt strong.
"""
    path = workouts_dir / f"{date_str}-{slug}.md"
    path.write_text(content)
    return path


def test_assess_week_produces_assessment_note_with_next_week_notes(tmp_path):
    """assess --week produces an Assessment note with a non-empty ## Next Week Notes section."""
    from coach.commands.assess import _run_assess

    cfg = _make_config(str(tmp_path))
    mock_client = MockNotesClient()
    provider_responses = [
        MOCK_ASSESS_RESPONSE,  # for the workout assessment
        MOCK_SUMMARY_RESPONSE,  # weekly summary
        MOCK_NEXT_WEEK_NOTES,  # next week notes
    ]
    provider = MockInferenceProvider(available=True)
    call_idx = [0]

    def mock_infer(req):
        from coach.intelligence.provider import InferenceResponse

        resp = provider_responses[min(call_idx[0], len(provider_responses) - 1)]
        call_idx[0] += 1
        return InferenceResponse(text=resp, provider="mock", model="mock")

    provider.infer = mock_infer

    workouts_dir = tmp_path / "workouts"
    today = datetime.date.today()
    iso = today.isocalendar()
    week_str = f"{iso.year}-W{iso.week:02d}"
    jan4 = datetime.date(iso.year, 1, 4)
    monday = jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=iso.week - 1)
    _write_workout(workouts_dir, monday.isoformat(), "Upper Body")

    with patch("coach.commands.assess.load_config", return_value=cfg):
        _run_assess(
            workout_title=None,
            week=week_str,
            dry_run=False,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # Assessment note was created
    notes = mock_client.list_notes(FOLDER_ASSESSMENTS)
    assert len(notes) == 1
    assert week_str in notes[0]

    # Note body contains ## Next Week Notes
    body = mock_client.get_note(FOLDER_ASSESSMENTS, notes[0])
    assert "## Next Week Notes" in body
    assert MOCK_NEXT_WEEK_NOTES in body


def test_find_local_workout_by_title_finds_matching_workout(tmp_path):
    """_find_local_workout_by_title returns a Workout when a local file matches the title."""
    from coach.commands.assess import _find_local_workout_by_title

    workouts_dir = tmp_path / "workouts"
    _write_workout(workouts_dir, "2026-06-16", "Upper Body")
    # note_title stored by _write_workout is "{date} {short_title}"
    title = "2026-06-16 Upper Body"

    result = _find_local_workout_by_title(workouts_dir, title)
    assert result is not None
    assert result.note_title == title


def test_find_local_workout_by_title_returns_none_for_missing(tmp_path):
    """_find_local_workout_by_title returns None when no matching local file exists."""
    from coach.commands.assess import _find_local_workout_by_title

    workouts_dir = tmp_path / "workouts"
    result = _find_local_workout_by_title(workouts_dir, "2026-06-16 Nothing Here")
    assert result is None


def test_assess_single_merges_local_metadata_with_notes_content(tmp_path):
    """_assess_single reads user edits from Apple Notes and structured metadata from local file."""
    import dataclasses

    from coach.commands.assess import _run_assess
    from coach.notes.parser import render_workout_note_html, workout_from_note
    from coach.notes.schema import FOLDER_WORKOUTS

    cfg = _make_config(str(tmp_path))
    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=MOCK_ASSESS_RESPONSE)

    workouts_dir = tmp_path / "workouts"
    local_path = _write_workout(workouts_dir, "2026-06-16", "Upper Body")
    title = "2026-06-16 Upper Body"  # matches note_title stored in FM by _write_workout

    # Simulate user filling in "How It Went" directly in the Apple Notes HTML note
    base_workout = workout_from_note(local_path.read_text(), local_path.stem)
    edited = dataclasses.replace(base_workout, how_it_went="Great session, hit all PRs.")
    mock_client.create_note(FOLDER_WORKOUTS, title, render_workout_note_html(edited))

    with patch("coach.commands.assess.load_config", return_value=cfg):
        _run_assess(
            workout_title=title,
            week=None,
            dry_run=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # Verify the provider received the user's completion content from Notes
    assert len(provider.calls) >= 1
    prompt_text = provider.calls[0].user
    assert "Great session, hit all PRs." in prompt_text


def test_assess_week_writes_local_assessment_file(tmp_path):
    """assess --week writes data/assessments/YYYY-Www.md."""
    from coach.commands.assess import _run_assess

    cfg = _make_config(str(tmp_path))
    mock_client = MockNotesClient()
    provider_responses = [MOCK_ASSESS_RESPONSE, MOCK_SUMMARY_RESPONSE, MOCK_NEXT_WEEK_NOTES]
    provider = MockInferenceProvider(available=True)
    call_idx = [0]

    def mock_infer(req):
        from coach.intelligence.provider import InferenceResponse

        resp = provider_responses[min(call_idx[0], len(provider_responses) - 1)]
        call_idx[0] += 1
        return InferenceResponse(text=resp, provider="mock", model="mock")

    provider.infer = mock_infer

    workouts_dir = tmp_path / "workouts"
    today = datetime.date.today()
    iso = today.isocalendar()
    week_str = f"{iso.year}-W{iso.week:02d}"
    jan4 = datetime.date(iso.year, 1, 4)
    monday = jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=iso.week - 1)
    _write_workout(workouts_dir, monday.isoformat(), "Upper Body")

    with patch("coach.commands.assess.load_config", return_value=cfg):
        _run_assess(
            workout_title=None,
            week=week_str,
            dry_run=False,
            notes_client=mock_client,
            inference_provider=provider,
        )

    assessment_file = tmp_path / "assessments" / f"{week_str}.md"
    assert assessment_file.exists()
    content = assessment_file.read_text()
    assert "## Next Week Notes" in content
