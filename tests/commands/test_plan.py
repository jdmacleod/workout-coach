"""Unit tests for coach plan command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from coach.config import Config, DataConfig, NotesConfig
from coach.notes.schema import FOLDER_PLANS
from tests.intelligence.mock_provider import MockInferenceProvider
from tests.notes.mock_client import MockNotesClient

MOCK_PLAN_RESPONSE = json.dumps(
    {
        "training_focus": "strength",
        "weekly_volume": "moderate",
        "generation_notes": "Balanced week for intermediate lifter.",
        "sessions": [
            {
                "day": "Mon",
                "type": "strength",
                "subtype": "upper",
                "duration_minutes": 55,
                "title": "Upper Body Push",
                "planned_content": "Bench 4x5, OHP 3x8",
                "rationale": "Push focus day",
            },
            {
                "day": "Wed",
                "type": "cardio",
                "subtype": "zone2",
                "duration_minutes": 45,
                "title": "Zone 2 Run",
                "planned_content": "Easy 45 min run",
                "rationale": "Aerobic base",
            },
            {
                "day": "Fri",
                "type": "rest",
                "subtype": "",
                "duration_minutes": 0,
                "title": "Rest",
                "planned_content": "",
                "rationale": "Recovery",
            },
        ],
    }
)


def _make_config(tmp_dir: str) -> Config:
    cfg = Config()
    cfg.data = DataConfig(
        training_info=str(Path(tmp_dir) / "training-info.md"),
        workouts_dir=str(Path(tmp_dir) / "workouts") + "/",
        plans_dir=str(Path(tmp_dir) / "plans") + "/",
        assessments_dir=str(Path(tmp_dir) / "assessments") + "/",
    )
    cfg.notes = NotesConfig()
    return cfg


def test_plan_dry_run_prints_table_and_writes_nothing(tmp_path, capsys):
    """coach plan --dry-run prints a plan table without writing files or Notes."""
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)

    # Pre-populate prior assessment with Next Week Notes
    from coach.notes.schema import FOLDER_ASSESSMENTS

    mock_client.create_note(
        FOLDER_ASSESSMENTS, "Assessment 2026-W22", "## Next Week Notes\nFocus on recovery."
    )

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=True,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # No plan files written
    assert not (tmp_path / "plans" / "2026-W23.md").exists()
    # No workout files written
    assert not (tmp_path / "workouts").exists() or not list((tmp_path / "workouts").glob("*.md"))
    # Notes unchanged (only the pre-existing assessment)
    assert mock_client.list_notes(FOLDER_PLANS) == []


def test_plan_live_writes_local_files_then_notes(tmp_path):
    """coach plan writes local files before pushing to Notes."""
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # Local plan file written
    assert (tmp_path / "plans" / "2026-W23.md").exists()

    # Apple Notes updated
    notes = mock_client.list_notes(FOLDER_PLANS)
    assert any("W23" in n for n in notes)


def test_plan_overwrite_creates_missing_workout_notes(tmp_path):
    """coach plan --overwrite creates workout notes missing from Apple Notes without re-running the LLM."""
    from coach.commands.plan import _run_plan
    from coach.notes.schema import FOLDER_WORKOUTS

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")

    # First run: generate plan + write everything
    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    workout_notes_before = mock_client.list_notes(FOLDER_WORKOUTS)
    assert len(workout_notes_before) > 0

    # Simulate Notes losing one workout note
    lost_title = workout_notes_before[0]
    mock_client.delete_note(FOLDER_WORKOUTS, lost_title)
    assert lost_title not in mock_client.list_notes(FOLDER_WORKOUTS)

    # Second run with --overwrite: should recreate missing note without calling the LLM
    provider2 = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=True,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider2,
        )

    # LLM was NOT called on overwrite (uses local files)
    assert len(provider2.calls) == 0

    # The missing workout note was recreated
    assert lost_title in mock_client.list_notes(FOLDER_WORKOUTS)


def test_plan_overwrite_updates_plan_note_as_html(tmp_path):
    """coach plan --overwrite updates the plan note in Apple Notes using HTML rendering."""
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")

    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # Overwrite: re-push with no LLM call
    provider2 = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=True,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider2,
        )

    plan_notes = mock_client.list_notes(FOLDER_PLANS)
    assert any("W23" in n for n in plan_notes)
    # Plan note should be HTML (contains h1 or h2 marker after strip)
    plan_title = next(n for n in plan_notes if "W23" in n)
    body = mock_client._store[(FOLDER_PLANS, plan_title)]
    assert "<h2>Schedule</h2>" in body  # raw stored body is HTML


def test_plan_next_week_notes_injected_from_prior_assessment(tmp_path):
    """coach plan injects Next Week Notes from the prior assessment into the prompt."""
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    mock_client = MockNotesClient()

    # Put a prior assessment with Next Week Notes
    prior_assessment_body = """---
week: 2026-W22
---

## Next Week Notes
Focus on recovery this week.
"""
    from coach.notes.schema import FOLDER_ASSESSMENTS

    mock_client.create_note(FOLDER_ASSESSMENTS, "Assessment 2026-W22", prior_assessment_body)

    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=True,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # Verify the provider received a prompt containing the Next Week Notes text
    assert len(provider.calls) >= 1
    prompt_text = provider.calls[0].user
    assert "Focus on recovery this week." in prompt_text


def test_plan_first_time_use_no_prior_assessment(tmp_path):
    """coach plan succeeds on first run with no prior assessment or history."""
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    # Empty Notes store — no folders, no assessments, no history
    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # Plan was written to local disk
    assert (tmp_path / "plans" / "2026-W23.md").exists()
    # Plan note was written to Notes despite no prior state
    notes = mock_client.list_notes(FOLDER_PLANS)
    assert any("W23" in n for n in notes)

    # LLM received the first-week placeholder, not an error
    prompt_text = provider.calls[0].user
    assert "none yet" in prompt_text.lower() or "first week" in prompt_text.lower()


def test_plan_first_time_use_injects_first_week_placeholder(tmp_path):
    """On first use, the planning prompt receives '(none yet — first week)'."""
    from coach.commands.plan import _load_next_week_notes

    cfg = _make_config(str(tmp_path))
    mock_client = MockNotesClient()  # empty — no assessments

    with patch("coach.commands.plan.load_config", return_value=cfg):
        result = _load_next_week_notes(cfg, "2026-W23", mock_client)

    assert result == "(none yet — first week)"


def test_infer_with_retry_strips_json_code_fence():
    """_infer_with_retry succeeds when the LLM wraps JSON in markdown code fences."""
    from coach.commands.plan import _infer_with_retry

    fenced_response = f"```json\n{MOCK_PLAN_RESPONSE}\n```"
    provider = MockInferenceProvider(response_text=fenced_response)
    result = _infer_with_retry(provider, "sys", "user", "{}")
    assert result == MOCK_PLAN_RESPONSE


def test_infer_with_retry_strips_bare_code_fence():
    """_infer_with_retry succeeds when the LLM wraps JSON in bare ``` fences."""
    from coach.commands.plan import _infer_with_retry

    fenced_response = f"```\n{MOCK_PLAN_RESPONSE}\n```"
    provider = MockInferenceProvider(response_text=fenced_response)
    result = _infer_with_retry(provider, "sys", "user", "{}")
    assert result == MOCK_PLAN_RESPONSE


def test_infer_with_retry_raises_on_double_failure():
    """_infer_with_retry raises InferenceParseError if both attempts return non-JSON."""
    import pytest

    from coach.commands.plan import _infer_with_retry
    from coach.intelligence.exceptions import InferenceParseError

    provider = MockInferenceProvider(response_text="This is not JSON at all.")
    with pytest.raises(InferenceParseError, match="after retry"):
        _infer_with_retry(provider, "sys", "user", "{}")


def test_plan_live_handles_fenced_llm_response(tmp_path):
    """coach plan succeeds when the LLM wraps its JSON in markdown code fences."""
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    mock_client = MockNotesClient()
    fenced_response = f"```json\n{MOCK_PLAN_RESPONSE}\n```"
    provider = MockInferenceProvider(response_text=fenced_response)

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    assert (tmp_path / "plans" / "2026-W23.md").exists()
    notes = mock_client.list_notes(FOLDER_PLANS)
    assert any("W23" in n for n in notes)


def test_safe_slug_strips_path_separators():
    """safe_slug removes '/' so LLM-generated titles like 'Mobility / Recovery' don't crash file writes."""
    from coach.notes.schema import safe_slug

    assert "/" not in safe_slug("Mobility / Recovery")
    assert safe_slug("Mobility / Recovery") == "mobility-recovery"


def test_safe_slug_replaces_em_dash():
    """safe_slug replaces em dash with hyphen instead of deleting it (avoids double hyphens)."""
    from coach.notes.schema import safe_slug

    result = safe_slug("Upper Body — Push")
    assert "--" not in result
    assert result == "upper-body-push"


def test_safe_slug_strips_leading_trailing_hyphens():
    """safe_slug never produces a slug that starts or ends with a hyphen."""
    from coach.notes.schema import safe_slug

    result = safe_slug("2026-06-17 Mobility — Mobility / Recovery")
    assert not result.startswith("-")
    assert not result.endswith("-")


def test_plan_live_writes_file_for_slash_in_title(tmp_path):
    """coach plan writes workout files when LLM returns a title containing '/' (regression for FileNotFoundError)."""
    import json
    from unittest.mock import patch

    from coach.commands.plan import _run_plan
    from tests.intelligence.mock_provider import MockInferenceProvider
    from tests.notes.mock_client import MockNotesClient

    slash_plan = json.dumps(
        {
            "training_focus": "mobility",
            "weekly_volume": "low",
            "generation_notes": "Easy week.",
            "sessions": [
                {
                    "day": "Wed",
                    "type": "mobility",
                    "subtype": "recovery",
                    "duration_minutes": 30,
                    "title": "Mobility / Recovery",
                    "planned_content": "Light stretching",
                    "rationale": "Active recovery",
                }
            ],
        }
    )

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=slash_plan)

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W26",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    written = list((tmp_path / "workouts").glob("*.md"))
    assert len(written) == 1, f"Expected 1 workout file, got: {written}"
    assert "/" not in written[0].name, f"Filename contains '/': {written[0].name}"
