"""Unit tests for coach plan command."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import patch

from coach.config import Config, DataConfig, NotesConfig, ProfileConfig
from coach.intelligence.provider import InferenceRequest, InferenceResponse
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


def test_plan_overwrite_includes_note_links(tmp_path):
    """coach plan --overwrite includes applenotes:// links in the plan note when plan_note_links=True."""
    from unittest.mock import patch

    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path))
    cfg.notes.plan_note_links = True
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")

    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    with (
        patch("coach.commands.plan.load_config", return_value=cfg),
        patch("coach.notes.sqlite.lookup_uuids", return_value={}),
    ):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # Overwrite: re-push plan with no LLM call
    provider2 = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    with (
        patch("coach.commands.plan.load_config", return_value=cfg),
        patch("coach.notes.sqlite.lookup_uuids", return_value={}),
    ):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=True,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider2,
        )

    assert len(provider2.calls) == 0  # no LLM on overwrite
    plan_title = next(n for n in mock_client.list_notes(FOLDER_PLANS) if "W23" in n)
    body = mock_client._store[(FOLDER_PLANS, plan_title)]
    assert "applenotes://showNote?identifier=" in body


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


def test_normalize_promotes_plain_items_in_section():
    """_normalize_planned_content promotes plain-text items under section headings to list items."""
    from coach.commands.plan import _normalize_planned_content

    content = (
        "### Main Lifts:\n"
        "- Back Squat: 3x5 @ 80% 1RM\n"
        "Romanian Deadlift: 3x8\n"
        "### Accessories:\n"
        "- Bulgarian Split Squat: 3x8 per leg\n"
        "Nordic Curl or Leg Curl: 3x10\n"
        "Calf Raises: 3x15\n"
        "Notes: Rest 3 min between main lift sets."
    )
    result = _normalize_planned_content(content, "strength")
    lines = result.splitlines()
    assert "- Back Squat: 3x5 @ 80% 1RM" in lines
    assert "- Romanian Deadlift: 3x8" in lines
    assert "- Bulgarian Split Squat: 3x8 per leg" in lines
    assert "- Nordic Curl or Leg Curl: 3x10" in lines
    assert "- Calf Raises: 3x15" in lines
    # Notes: is not a list item
    assert "Notes: Rest 3 min between main lift sets." in lines
    assert "- Notes: Rest 3 min between main lift sets." not in lines


def test_normalize_preserves_already_bulleted_items():
    """_normalize_planned_content does not double-bullet items that already have '- ' prefix."""
    from coach.commands.plan import _normalize_planned_content

    content = "### Warm-up:\n- arm circles\n- band pull-aparts\n"
    result = _normalize_planned_content(content, "strength")
    assert "- - arm circles" not in result
    assert "- arm circles" in result


def test_normalize_noop_for_non_strength():
    """_normalize_planned_content returns content unchanged for non-strength workout types."""
    from coach.commands.plan import _normalize_planned_content

    content = "Zone 2 run\n30 minutes easy"
    assert _normalize_planned_content(content, "cardio") == content
    assert _normalize_planned_content(content, "mobility") == content


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


def test_plan_reassigns_same_day_sessions_to_open_day(tmp_path):
    """When the LLM returns two sessions on the same day, the extra is moved to an
    open day in the week rather than dropped, so fitness_days_per_week is honored."""
    from coach.commands.plan import _run_plan
    from coach.notes.schema import FOLDER_WORKOUTS

    duplicate_day_plan = json.dumps(
        {
            "training_focus": "strength",
            "weekly_volume": "moderate",
            "generation_notes": "Test plan with duplicate Monday.",
            "sessions": [
                {
                    "day": "Mon",
                    "type": "strength",
                    "subtype": "upper",
                    "duration_minutes": 55,
                    "title": "Upper Body Push",
                    "planned_content": "Bench 4x5",
                    "rationale": "",
                },
                {
                    "day": "Mon",
                    "type": "strength",
                    "subtype": "lower",
                    "duration_minutes": 55,
                    "title": "Lower Body",
                    "planned_content": "Squat 4x5",
                    "rationale": "",
                },
                {
                    "day": "Wed",
                    "type": "cardio",
                    "subtype": "zone2",
                    "duration_minutes": 45,
                    "title": "Zone 2 Run",
                    "planned_content": "Easy run",
                    "rationale": "",
                },
            ],
        }
    )

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=duplicate_day_plan)

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W25",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    workout_files = list((tmp_path / "workouts").glob("*.md"))
    workout_notes = mock_client.list_notes(FOLDER_WORKOUTS)

    # All 3 sessions should be kept, just spread across distinct days.
    assert len(workout_files) == 3, f"Expected 3 workout files, got: {workout_files}"
    assert len(workout_notes) == 3, f"Expected 3 workout notes, got: {workout_notes}"

    # Mon still has Upper Body Push (first claim on that date).
    mon_files = [f for f in workout_files if "2026-06-15" in f.name]
    assert len(mon_files) == 1
    assert "upper-body-push" in mon_files[0].name

    # Lower Body was moved off Monday to the next open day (Tuesday), not dropped.
    lower_body_files = [f for f in workout_files if "lower-body" in f.name]
    assert len(lower_body_files) == 1
    assert "2026-06-15" not in lower_body_files[0].name
    assert "2026-06-16" in lower_body_files[0].name

    # Wed keeps its original session, untouched by the collision.
    wed_files = [f for f in workout_files if "2026-06-17" in f.name]
    assert len(wed_files) == 1
    assert "zone-2-run" in wed_files[0].name


def test_plan_collision_reassignment_respects_available_days(tmp_path):
    """A collision should skip days excluded by training-info.md's Schedule
    Constraints 'Available days' line, not just the nearest chronological day."""
    from coach.commands.plan import _run_plan
    from coach.notes.schema import FOLDER_WORKOUTS

    duplicate_day_plan = json.dumps(
        {
            "training_focus": "strength",
            "weekly_volume": "moderate",
            "generation_notes": "Test plan with duplicate Monday.",
            "sessions": [
                {
                    "day": "Mon",
                    "type": "strength",
                    "subtype": "upper",
                    "duration_minutes": 55,
                    "title": "Upper Body Push",
                    "planned_content": "Bench 4x5",
                    "rationale": "",
                },
                {
                    "day": "Mon",
                    "type": "strength",
                    "subtype": "lower",
                    "duration_minutes": 55,
                    "title": "Lower Body",
                    "planned_content": "Squat 4x5",
                    "rationale": "",
                },
            ],
        }
    )

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text(
        "# Training Info\n\n"
        "## Schedule Constraints\n\n"
        "- Available days: Monday, Wednesday, Thursday, Saturday, Sunday\n"
    )
    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=duplicate_day_plan)

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W25",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    workout_files = list((tmp_path / "workouts").glob("*.md"))
    workout_notes = mock_client.list_notes(FOLDER_WORKOUTS)

    assert len(workout_files) == 2, f"Expected 2 workout files, got: {workout_files}"
    assert len(workout_notes) == 2

    # Lower Body must skip Tuesday (2026-06-16, not in Available days) and land
    # on Wednesday (2026-06-17, the next day that *is* available).
    lower_body_files = [f for f in workout_files if "lower-body" in f.name]
    assert len(lower_body_files) == 1
    assert "2026-06-16" not in lower_body_files[0].name
    assert "2026-06-17" in lower_body_files[0].name


def test_plan_collision_reassignment_avoids_recurring_class_day(tmp_path):
    """A collision should prefer skipping days with a recurring external class
    over the nearest chronological day, when another open day exists."""
    from coach.commands.plan import _run_plan
    from coach.notes.schema import FOLDER_WORKOUTS

    duplicate_day_plan = json.dumps(
        {
            "training_focus": "strength",
            "weekly_volume": "moderate",
            "generation_notes": "Test plan with duplicate Monday.",
            "sessions": [
                {
                    "day": "Mon",
                    "type": "strength",
                    "subtype": "upper",
                    "duration_minutes": 55,
                    "title": "Upper Body Push",
                    "planned_content": "Bench 4x5",
                    "rationale": "",
                },
                {
                    "day": "Mon",
                    "type": "strength",
                    "subtype": "lower",
                    "duration_minutes": 55,
                    "title": "Lower Body",
                    "planned_content": "Squat 4x5",
                    "rationale": "",
                },
            ],
        }
    )

    cfg = _make_config(str(tmp_path))
    (tmp_path / "training-info.md").write_text(
        "# Training Info\n\n## Recurring External Classes\n\n- Tuesday 6pm: Pilates class\n"
    )
    mock_client = MockNotesClient()
    provider = MockInferenceProvider(response_text=duplicate_day_plan)

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W25",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    workout_files = list((tmp_path / "workouts").glob("*.md"))
    workout_notes = mock_client.list_notes(FOLDER_WORKOUTS)

    assert len(workout_files) == 2, f"Expected 2 workout files, got: {workout_files}"
    assert len(workout_notes) == 2

    # Lower Body should skip Tuesday (recurring Pilates class) and land on
    # Wednesday instead, since no Schedule Constraints restrict availability.
    lower_body_files = [f for f in workout_files if "lower-body" in f.name]
    assert len(lower_body_files) == 1
    assert "2026-06-16" not in lower_body_files[0].name
    assert "2026-06-17" in lower_body_files[0].name


# ── T8: Equipment constraint correction pass ──────────────────────────────────


class _MultiResponseProvider:
    """Test provider that returns different responses per call."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[InferenceRequest] = []

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        self.calls.append(request)
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return InferenceResponse(text=self.responses[idx], provider="mock", model="mock")

    def is_available(self) -> bool:
        return True

    def provider_name(self) -> str:
        return "mock"

    def display_name(self) -> str:
        return "mock / mock"


_VIOLATING_PLAN = json.dumps(
    {
        "training_focus": "strength",
        "weekly_volume": "moderate",
        "generation_notes": "Using cable machines.",
        "sessions": [
            {
                "day": "Mon",
                "type": "strength",
                "subtype": "upper",
                "duration_minutes": 45,
                "title": "Cable Machine Upper",
                "planned_content": "Cable machine rows: 4x12, cable machine press: 3x10",
                "rationale": "Upper body with cable machine",
            },
            {
                "day": "Wed",
                "type": "cardio",
                "subtype": "zone2",
                "duration_minutes": 30,
                "title": "Cardio",
                "planned_content": "Easy run 30 min",
                "rationale": "Aerobic base",
            },
        ],
    }
)


def _make_config_with_equipment(tmp_dir: str, equipment: list[str]) -> Config:
    cfg = _make_config(tmp_dir)
    cfg.profile = ProfileConfig(available_equipment=equipment)
    return cfg


def test_correction_pass_fires_on_equipment_violation(tmp_path: Path) -> None:
    """When the LLM generates a plan violating equipment constraints, the correction
    pass calls the provider a second time and the final plan uses only allowed gear."""
    from coach.commands.plan import _run_plan

    cfg = _make_config_with_equipment(str(tmp_path), ["dumbbells"])
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    mock_client = MockNotesClient()

    # First call: violating plan (cable machine). Second call: corrected plan (no violations).
    provider = _MultiResponseProvider([_VIOLATING_PLAN, MOCK_PLAN_RESPONSE])

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

    # Correction pass fired — provider was called at least twice
    assert len(provider.calls) >= 2

    # Final workout files don't reference cable machine
    for path in (tmp_path / "workouts").glob("*.md"):
        content = path.read_text().lower()
        assert "cable machine" not in content, f"Equipment violation in {path.name}"


def test_no_correction_pass_without_equipment_constraint(tmp_path: Path) -> None:
    """When no equipment is configured, the correction pass is skipped entirely."""
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path))  # no equipment in profile
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

    # Only one LLM call — no correction pass
    assert len(provider.calls) == 1


# ── T6: Month-range glob optimisation ────────────────────────────────────────


def test_load_recent_workouts_only_returns_files_within_cutoff(tmp_path: Path) -> None:
    """_load_recent_workouts returns only workouts within the N-week window
    and ignores older files, regardless of how many historical files exist."""
    from coach.commands.plan import _load_recent_workouts

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir()

    cfg = _make_config(str(tmp_path))

    today = datetime.date.today()

    # Write a file that falls within the window
    recent_date = today - datetime.timedelta(days=7)
    recent_content = f"---\nid: wrk-recent\ndate: {recent_date.isoformat()}\ntype: strength\nstatus: completed\nsource: manual\nnote_title: Recent Workout\nduration_planned: \nduration_actual: \ndistance_km: \navg_hr: \nrpe: \nmood: \nsoreness: \ntags: \n---\n\n## Planned\n\nTest\n\n## Completed\n\nDone\n\n## How It Went\n\nGood"
    (workouts_dir / f"{recent_date.isoformat()}-strength.md").write_text(recent_content)

    # Write a file that falls outside the window (6+ weeks ago)
    old_date = today - datetime.timedelta(weeks=6, days=1)
    old_content = f"---\nid: wrk-old\ndate: {old_date.isoformat()}\ntype: strength\nstatus: completed\nsource: manual\nnote_title: Old Workout\nduration_planned: \nduration_actual: \ndistance_km: \navg_hr: \nrpe: \nmood: \nsoreness: \ntags: \n---\n\n## Planned\n\nTest\n\n## Completed\n\nDone\n\n## How It Went\n\nGood"
    (workouts_dir / f"{old_date.isoformat()}-strength.md").write_text(old_content)

    result = _load_recent_workouts(cfg, weeks=5)

    # Only the recent workout is returned
    assert len(result) == 1
    assert result[0].date == recent_date


def test_load_recent_workouts_excludes_rest_type(tmp_path: Path) -> None:
    """Rest-type workouts are excluded even when within the date window."""
    from coach.commands.plan import _load_recent_workouts

    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir()

    cfg = _make_config(str(tmp_path))
    today = datetime.date.today()
    recent_date = today - datetime.timedelta(days=3)

    rest_content = f"---\nid: wrk-rest\ndate: {recent_date.isoformat()}\ntype: rest\nstatus: planned\nsource: generated\nnote_title: Rest Day\nduration_planned: \nduration_actual: \ndistance_km: \navg_hr: \nrpe: \nmood: \nsoreness: \ntags: \n---\n\n## Planned\n\nRest\n\n## Completed\n\n## How It Went\n\n"
    (workouts_dir / f"{recent_date.isoformat()}-rest.md").write_text(rest_content)

    result = _load_recent_workouts(cfg, weeks=5)
    assert result == []
