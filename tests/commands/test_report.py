"""Unit tests for coach report and coach status commands."""
from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from coach.config import Config, DataConfig
from coach.models.workout import Workout


def _make_workouts(n: int = 4) -> list[Workout]:
    workouts = []
    base = datetime.date(2026, 6, 1)
    types = ["strength", "cardio", "hiit", "mobility"]
    for i in range(n):
        workouts.append(Workout(
            id=f"wrk-{i}",
            date=base + datetime.timedelta(days=i),
            type=types[i % len(types)],
            status="completed",
            source="generated",
            duration_actual=45 + i * 5,
            rpe=6.0 + i * 0.5,
        ))
    return workouts


def test_report_summary_table(capsys):
    from coach.commands.report import _run_report

    workouts = _make_workouts(4)
    _run_report(subcommand="summary", weeks=4, format="table", type_filter=None, workouts=workouts)
    # No exception = pass; summary table output expected


def test_report_summary_json():
    from coach.commands.report import _run_report
    import json as json_mod

    workouts = _make_workouts(4)
    output_lines = []
    with patch("coach.commands.report.console") as mock_console:
        mock_console.print.side_effect = lambda x: output_lines.append(str(x))
        _run_report(subcommand="summary", weeks=4, format="json", type_filter=None, workouts=workouts)

    output = "\n".join(output_lines)
    parsed = json_mod.loads(output)
    assert isinstance(parsed, list)


def test_report_rpe():
    from coach.commands.report import _run_report

    workouts = _make_workouts(4)
    _run_report(subcommand="rpe", weeks=4, format="table", type_filter=None, workouts=workouts)


def test_report_streak():
    from coach.commands.report import _run_report

    workouts = _make_workouts(4)
    _run_report(subcommand="streak", weeks=4, format="table", type_filter=None, workouts=workouts)


def test_report_type_filter():
    from coach.commands.report import _run_report

    workouts = _make_workouts(8)
    # Should not raise
    _run_report(subcommand="summary", weeks=8, format="table", type_filter="strength", workouts=workouts)
