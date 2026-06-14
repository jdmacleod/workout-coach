"""Unit tests for _load_history_summary (weekly rollup) and rest session filtering."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import patch

from coach.commands.plan import _run_plan
from coach.config import Config, DataConfig, NotesConfig
from tests.intelligence.mock_provider import MockInferenceProvider
from tests.notes.mock_client import MockNotesClient


def _make_config(tmp_dir: Path) -> Config:
    cfg = Config()
    cfg.data = DataConfig(
        training_info=str(tmp_dir / "training-info.md"),
        workouts_dir=str(tmp_dir / "workouts") + "/",
        plans_dir=str(tmp_dir / "plans") + "/",
        assessments_dir=str(tmp_dir / "assessments") + "/",
    )
    cfg.notes = NotesConfig()
    return cfg


def _write_workout_file(
    workouts_dir: Path,
    date_str: str,
    wtype: str = "strength",
    rpe: float | None = None,
    duration_actual: int | None = None,
) -> None:
    workouts_dir.mkdir(parents=True, exist_ok=True)
    rpe_line = f"rpe: {rpe}" if rpe is not None else ""
    dur_line = f"duration_actual: {duration_actual}" if duration_actual is not None else ""
    content = f"""---
id: wrk-{date_str.replace("-", "")}-tst
date: {date_str}
type: {wtype}
status: completed
note_title: {date_str} Test Session
duration_planned: 45
source: generated
{rpe_line}
{dur_line}
---

## Planned

Test exercise.
"""
    slug = f"{wtype}-session"
    (workouts_dir / f"{date_str}-{slug}.md").write_text(content)


def test_history_rollup_format(tmp_path: Path) -> None:
    """_load_history_summary produces one line per ISO week, not one per session."""
    from coach.commands.plan import _load_history_summary

    workouts_dir = tmp_path / "workouts"
    today = datetime.date.today()
    # Two weeks ago Monday and Wednesday (2 sessions in one week)
    last_monday = today - datetime.timedelta(days=today.weekday() + 7)
    this_monday = today - datetime.timedelta(days=today.weekday())

    d_w1_a = last_monday
    d_w1_b = last_monday + datetime.timedelta(days=2)
    d_w2 = this_monday

    _write_workout_file(workouts_dir, d_w1_a.isoformat(), "strength", rpe=7.5, duration_actual=45)
    _write_workout_file(workouts_dir, d_w1_b.isoformat(), "cardio", rpe=6.0, duration_actual=30)
    _write_workout_file(workouts_dir, d_w2.isoformat(), "strength", rpe=8.0, duration_actual=45)

    cfg = _make_config(tmp_path)
    summary = _load_history_summary(cfg)

    lines = [ln for ln in summary.splitlines() if ln.strip()]
    # Must be 2 lines (one per ISO week), NOT 3 lines (one per session)
    assert len(lines) == 2, f"Expected 2 rollup lines, got {len(lines)}:\n{summary}"

    w1_iso = f"{last_monday.isocalendar().year}-W{last_monday.isocalendar().week:02d}"
    w2_iso = f"{this_monday.isocalendar().year}-W{this_monday.isocalendar().week:02d}"
    assert w1_iso in lines[0], f"Week 1 ISO not in first line: {lines[0]}"
    assert w2_iso in lines[1], f"Week 2 ISO not in second line: {lines[1]}"
    # Week 1 should show 2 sessions
    assert "2 sessions" in lines[0]
    # Week 2 should show 1 session
    assert "1 sessions" in lines[1]


def test_history_excludes_rest_type(tmp_path: Path) -> None:
    """_load_history_summary omits rest-type sessions from the rollup."""
    from coach.commands.plan import _load_history_summary

    workouts_dir = tmp_path / "workouts"
    today = datetime.date.today()
    this_monday = today - datetime.timedelta(days=today.weekday())

    _write_workout_file(
        workouts_dir, this_monday.isoformat(), "strength", rpe=7.0, duration_actual=45
    )
    _write_workout_file(
        workouts_dir, (this_monday + datetime.timedelta(days=1)).isoformat(), "rest"
    )
    _write_workout_file(
        workouts_dir,
        (this_monday + datetime.timedelta(days=2)).isoformat(),
        "cardio",
        rpe=6.0,
        duration_actual=30,
    )

    cfg = _make_config(tmp_path)
    summary = _load_history_summary(cfg)

    lines = [ln for ln in summary.splitlines() if ln.strip()]
    assert len(lines) == 1
    # 2 sessions (strength + cardio), rest excluded
    assert "2 sessions" in lines[0]
    assert "rest" not in lines[0]


def test_rest_sessions_not_written_to_disk(tmp_path: Path) -> None:
    """_run_plan does not write local files for rest-type sessions."""
    plan_with_rest = json.dumps(
        {
            "training_focus": "strength",
            "weekly_volume": "moderate",
            "generation_notes": "Test plan.",
            "sessions": [
                {
                    "day": "Mon",
                    "type": "strength",
                    "subtype": "upper",
                    "duration_minutes": 45,
                    "title": "Upper Push",
                    "planned_content": "Pull-ups 3x8",
                    "rationale": "Push day",
                },
                {
                    "day": "Wed",
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

    cfg = _make_config(tmp_path)
    (tmp_path / "training-info.md").write_text("# Training\nGeneral fitness.")
    provider = MockInferenceProvider(response_text=plan_with_rest)
    client = MockNotesClient()

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W23",
            focus=None,
            dry_run=False,
            overwrite=False,
            no_calendar=True,
            notes_client=client,
            inference_provider=provider,
        )

    workouts_dir = tmp_path / "workouts"
    written = list(workouts_dir.glob("*.md"))
    assert len(written) == 1, f"Expected 1 file (rest excluded), got {len(written)}: {written}"
    assert "rest" not in written[0].name.lower()
