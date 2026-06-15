"""Tests for workout variation engine functions in coach/commands/plan.py."""

from __future__ import annotations

import datetime
from pathlib import Path

from coach.commands.plan import (
    _build_overload_hints,
    _build_periodization_directive,
    _check_deload_signal,
    _extract_exercise_sets_reps,
    _load_recent_workouts,
    _notes_already_mention,
    _parse_exercise_front_matter,
    _sample_exercise_library,
)
from coach.config import Config, DataConfig, NotesConfig
from coach.models.workout import Workout


def _make_workout(
    *,
    date: datetime.date,
    wtype: str = "strength",
    rpe: float | None = None,
    completed_content: str | None = None,
) -> Workout:
    return Workout(
        id=f"wrk-{date.isoformat().replace('-', '')}",
        date=date,
        type=wtype,
        status="completed",
        source="generated",
        rpe=rpe,
        completed_content=completed_content,
    )


def _make_config(tmp_dir: Path) -> Config:
    cfg = Config()
    cfg.data = DataConfig(
        training_info=str(tmp_dir / "training-info.md"),
        workouts_dir=str(tmp_dir / "workouts") + "/",
        plans_dir=str(tmp_dir / "plans") + "/",
        assessments_dir=str(tmp_dir / "assessments") + "/",
        exercise_library=str(tmp_dir / "exercise-library") + "/",
    )
    cfg.notes = NotesConfig()
    return cfg


# ── _notes_already_mention ────────────────────────────────────────────────────


def test_notes_already_mention_found():
    assert _notes_already_mention("Focus on deload this week", "deload") is True


def test_notes_already_mention_case_insensitive():
    assert _notes_already_mention("Recovery week ahead", "recovery week") is True


def test_notes_already_mention_not_found():
    assert _notes_already_mention("Push hard this week", "deload") is False


def test_notes_already_mention_multiple_keywords():
    assert _notes_already_mention("Try progressive overload", "deload", "progressive") is True


def test_notes_already_mention_empty_notes():
    assert _notes_already_mention("", "deload") is False


# ── _check_deload_signal ──────────────────────────────────────────────────────


def test_check_deload_signal_no_history():
    assert _check_deload_signal([]) == ""


def test_check_deload_signal_insufficient_sessions():
    today = datetime.date.today()
    workouts = [
        _make_workout(date=today - datetime.timedelta(days=3), rpe=9.0),
        _make_workout(date=today - datetime.timedelta(days=6), rpe=9.0),
    ]
    assert _check_deload_signal(workouts) == ""


def test_check_deload_signal_high_rpe_triggers():
    today = datetime.date.today()
    workouts = [
        _make_workout(date=today - datetime.timedelta(days=2), rpe=9.0),
        _make_workout(date=today - datetime.timedelta(days=5), rpe=9.0),
        _make_workout(date=today - datetime.timedelta(days=8), rpe=9.0),
    ]
    result = _check_deload_signal(workouts)
    assert "Deload signal" in result
    assert "9.0" in result


def test_check_deload_signal_moderate_rpe_no_trigger():
    today = datetime.date.today()
    workouts = [
        _make_workout(date=today - datetime.timedelta(days=2), rpe=7.0),
        _make_workout(date=today - datetime.timedelta(days=5), rpe=7.5),
        _make_workout(date=today - datetime.timedelta(days=8), rpe=7.0),
    ]
    assert _check_deload_signal(workouts) == ""


def test_check_deload_signal_old_sessions_ignored():
    today = datetime.date.today()
    workouts = [
        _make_workout(date=today - datetime.timedelta(weeks=4), rpe=9.5),
        _make_workout(date=today - datetime.timedelta(weeks=5), rpe=9.5),
        _make_workout(date=today - datetime.timedelta(weeks=6), rpe=9.5),
    ]
    assert _check_deload_signal(workouts) == ""


# ── _build_periodization_directive ───────────────────────────────────────────


def test_periodization_directive_empty_history():
    assert _build_periodization_directive([]) == ""


def test_periodization_directive_insufficient_sessions():
    today = datetime.date.today()
    assert _build_periodization_directive([_make_workout(date=today)]) == ""


def test_periodization_directive_4_weeks_triggers_overload():
    today = datetime.date.today()
    workouts = []
    for week_offset in range(4):
        for day_offset in [0, 2, 4]:
            workouts.append(
                _make_workout(
                    date=today - datetime.timedelta(weeks=week_offset, days=day_offset),
                    rpe=7.0,
                )
            )
    result = _build_periodization_directive(workouts)
    assert "progressive overload" in result.lower() or "periodization" in result.lower()


def test_periodization_directive_high_rpe_fatigue():
    today = datetime.date.today()
    workouts = []
    for week_offset in range(3):
        for day_offset in [0, 2, 4]:
            workouts.append(
                _make_workout(
                    date=today - datetime.timedelta(weeks=week_offset, days=day_offset),
                    rpe=8.5,
                )
            )
    result = _build_periodization_directive(workouts)
    assert "fatigue" in result.lower() or "volume reduction" in result.lower()


# ── _build_overload_hints ─────────────────────────────────────────────────────


def test_overload_hints_empty_history():
    assert _build_overload_hints([]) == ""


def test_overload_hints_no_completed_content():
    today = datetime.date.today()
    workouts = [_make_workout(date=today)]
    assert _build_overload_hints(workouts) == ""


def test_overload_hints_single_session_no_hint():
    today = datetime.date.today()
    workouts = [
        _make_workout(date=today, completed_content="- Floor Press: 4x5 @ 60kg"),
    ]
    assert _build_overload_hints(workouts) == ""


def test_overload_hints_consistent_load_emits_hint():
    today = datetime.date.today()
    workouts = [
        _make_workout(
            date=today - datetime.timedelta(weeks=2),
            completed_content="- Floor Press: 4x5 @ 55kg",
        ),
        _make_workout(
            date=today - datetime.timedelta(weeks=1),
            completed_content="- Floor Press: 4x5 @ 60kg",
        ),
    ]
    result = _build_overload_hints(workouts)
    assert "floor press" in result.lower()
    assert "60.0 kg" in result


def test_overload_hints_bodyweight_exercise_ignored():
    today = datetime.date.today()
    workouts = [
        _make_workout(
            date=today - datetime.timedelta(weeks=2), completed_content="- Pull-ups: 4x8"
        ),
        _make_workout(
            date=today - datetime.timedelta(weeks=1), completed_content="- Pull-ups: 4x9"
        ),
    ]
    assert _build_overload_hints(workouts) == ""


# ── _parse_exercise_front_matter ──────────────────────────────────────────────


def test_parse_exercise_front_matter_basic():
    content = """\
---
name: Floor Press
equipment: [barbell, bumper_plates]
type: strength-push
difficulty: intermediate
---
## Notes
Some notes here.
"""
    fm = _parse_exercise_front_matter(content)
    assert fm["name"] == "Floor Press"
    assert fm["equipment"] == ["barbell", "bumper_plates"]
    assert fm["type"] == "strength-push"


def test_parse_exercise_front_matter_empty_equipment():
    content = """\
---
name: Push-up
equipment: []
type: strength-push
---
"""
    fm = _parse_exercise_front_matter(content)
    assert fm["equipment"] == []


def test_parse_exercise_front_matter_no_front_matter():
    assert _parse_exercise_front_matter("Just some content") == {}


# ── _extract_exercise_sets_reps ───────────────────────────────────────────────


def test_extract_sets_reps_basic():
    content = """\
## Sets / Reps
- Strength: 4x4-6 @ 75-85% 1RM
- Volume: 3x8-10

## Cues
Keep tight.
"""
    result = _extract_exercise_sets_reps(content)
    assert result == "Strength: 4x4-6 @ 75-85% 1RM"


def test_extract_sets_reps_duration_section():
    content = """\
## Duration / Intensity
- Standard: 30-60 min

## Cues
Conversational pace.
"""
    result = _extract_exercise_sets_reps(content)
    assert result == "Standard: 30-60 min"


def test_extract_sets_reps_missing_section():
    content = "## Notes\nSome notes."
    assert _extract_exercise_sets_reps(content) == ""


# ── _sample_exercise_library ──────────────────────────────────────────────────


def _write_exercise(path: Path, name: str, equipment: list[str], category: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{name.lower().replace(' ', '-')}.md").write_text(
        f"""\
---
name: {name}
equipment: [{", ".join(equipment)}]
type: {category}
difficulty: beginner
---
## Sets / Reps
- Volume: 3x10
"""
    )


def test_sample_exercise_library_no_directory(tmp_path):
    cfg = _make_config(tmp_path)
    result = _sample_exercise_library([], cfg)
    assert result == ""


def test_sample_exercise_library_filters_by_equipment(tmp_path):
    cfg = _make_config(tmp_path)
    lib_dir = tmp_path / "exercise-library" / "strength-push"
    _write_exercise(lib_dir, "Floor Press", ["barbell", "bumper_plates"], "strength-push")
    _write_exercise(lib_dir, "Push-up", [], "strength-push")

    # Only barbell + bumper_plates available → Floor Press eligible; Push-up also eligible (no equip)
    result = _sample_exercise_library(["barbell", "bumper_plates"], cfg)
    assert "strength-push" in result


def test_sample_exercise_library_empty_equipment_gets_bodyweight_only(tmp_path):
    cfg = _make_config(tmp_path)
    lib_dir = tmp_path / "exercise-library" / "strength-push"
    _write_exercise(lib_dir, "Floor Press", ["barbell", "bumper_plates"], "strength-push")
    _write_exercise(lib_dir, "Push-up", [], "strength-push")

    # No equipment → only bodyweight exercises eligible
    result = _sample_exercise_library([], cfg)
    assert "Push-up" in result
    # Floor Press should NOT appear (requires equipment user doesn't have)
    assert "Floor Press" not in result


def test_sample_exercise_library_reproducible_per_week(tmp_path):
    cfg = _make_config(tmp_path)
    lib_dir = tmp_path / "exercise-library" / "strength-push"
    for i in range(5):
        _write_exercise(lib_dir, f"Exercise {i}", [], "strength-push")

    result1 = _sample_exercise_library([], cfg)
    result2 = _sample_exercise_library([], cfg)
    assert result1 == result2


# ── _load_recent_workouts ─────────────────────────────────────────────────────


def test_load_recent_workouts_empty_dir(tmp_path):
    cfg = _make_config(tmp_path)
    assert _load_recent_workouts(cfg) == []


def test_load_recent_workouts_missing_dir(tmp_path):
    cfg = _make_config(tmp_path)
    assert _load_recent_workouts(cfg) == []


def test_load_recent_workouts_returns_within_cutoff(tmp_path):
    from coach.notes.parser import render_workout_note

    cfg = _make_config(tmp_path)
    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir()

    today = datetime.date.today()
    recent_w = _make_workout(date=today - datetime.timedelta(weeks=2))
    old_w = _make_workout(date=today - datetime.timedelta(weeks=10))

    (workouts_dir / f"{recent_w.date.isoformat()}-session.md").write_text(
        render_workout_note(recent_w)
    )
    (workouts_dir / f"{old_w.date.isoformat()}-session.md").write_text(render_workout_note(old_w))

    result = _load_recent_workouts(cfg, weeks=5)
    assert len(result) == 1
    assert result[0].date == recent_w.date
