"""6-week usability simulation using the live LLM provider.

A faster alternative to the full 13-week run: covers base building (W1–W3),
deload (W4), and early progression (W5–W6). Runs in roughly half the time.

Run with:
    uv run pytest tests/usability/test_simulation_live_short.py -m usability_live -v -s
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from coach.commands.assess import _run_assess
from coach.commands.plan import _run_plan
from coach.commands.report import _run_report
from coach.commands.status import _run_status
from coach.config import load_config
from tests.notes.mock_client import MockNotesClient
from tests.usability.analysis import Collector, generate_report
from tests.usability.conftest import make_sim_config
from tests.usability.synthetic_data import (
    TRAINING_INFO,
    WEEK_PROFILES,
    simulate_completions,
)
from tests.usability.synthetic_llm import (
    compute_base_monday,
    week_str_for_monday,
)

OUTPUT_DIR = Path(__file__).parent.parent.parent / "usability-output" / "live-short"

SHORT_PROFILES = WEEK_PROFILES[:6]
N_WEEKS = len(SHORT_PROFILES)


def _make_live_config(tmp: Path) -> object:
    cfg = make_sim_config(tmp)
    try:
        real = load_config()
        cfg.llm = real.llm
        cfg.search = real.search
    except Exception:
        pass
    return cfg


@pytest.mark.usability_live
def test_6_week_simulation_live(sim_tmp_live: Path) -> None:
    """Run a 6-week coaching loop with the live LLM provider.

    Covers base building → deload → early progression. Faster than the full
    13-week run while still exercising all commands and the plan→assess→status loop.
    """
    workouts_dir = sim_tmp_live / "workouts"
    plans_dir = sim_tmp_live / "plans"
    assessments_dir = sim_tmp_live / "assessments"
    workouts_dir.mkdir(exist_ok=True)
    plans_dir.mkdir(exist_ok=True)
    assessments_dir.mkdir(exist_ok=True)

    training_info_path = sim_tmp_live / "training-info.md"
    training_info_path.write_text(TRAINING_INFO)

    cfg = _make_live_config(sim_tmp_live)
    notes_client = MockNotesClient()
    collector = Collector()

    base_monday = compute_base_monday()

    for profile in SHORT_PROFILES:
        week_num = profile["week_num"]
        monday = base_monday + datetime.timedelta(weeks=week_num - 1)
        week_str = week_str_for_monday(monday)

        print(f"\n{'=' * 60}")
        print(f"Week {week_num}/{N_WEEKS} — {week_str} ({profile['theme']})")
        print(f"{'=' * 60}")

        # ── Plan ─────────────────────────────────────────────────────────────
        plan_ok = False
        try:
            with patch("coach.commands.plan.load_config", return_value=cfg):
                _run_plan(
                    week=week_str,
                    focus=None,
                    dry_run=False,
                    overwrite=False,
                    no_calendar=True,
                    notes_client=notes_client,
                    inference_provider=None,
                )
            assert (plans_dir / f"{week_str}.md").exists(), f"Plan file missing for {week_str}"
            plan_ok = True
        except Exception as exc:
            print(f"[FAIL] plan week {week_num}: {exc}")

        # ── Simulate completions ──────────────────────────────────────────────
        simulate_completions(profile, workouts_dir, monday)

        # ── Count sessions ────────────────────────────────────────────────────
        n_sessions = _count_sessions_for_week(workouts_dir, monday)
        print(f"Sessions to assess: {n_sessions}")

        # ── Assess ────────────────────────────────────────────────────────────
        assess_ok = False
        try:
            with patch("coach.commands.assess.load_config", return_value=cfg):
                _run_assess(
                    workout_title=None,
                    week=week_str,
                    dry_run=False,
                    notes_client=notes_client,
                    inference_provider=None,
                )
            assert (assessments_dir / f"{week_str}.md").exists(), (
                f"Assessment file missing for {week_str}"
            )
            assess_ok = True
        except Exception as exc:
            print(f"[FAIL] assess week {week_num}: {exc}")

        # ── Status ────────────────────────────────────────────────────────────
        status_ok = False
        try:
            with patch("coach.commands.status.load_config", return_value=cfg):
                _run_status(week=week_str)
            status_ok = True
        except SystemExit as exc:
            status_ok = exc.code == 0
        except Exception as exc:
            print(f"[FAIL] status week {week_num}: {exc}")

        # ── Report ────────────────────────────────────────────────────────────
        report_output = ""
        report_ran = week_num >= 2
        if report_ran:
            all_workouts = _load_all_workouts(workouts_dir)
            captured: list[str] = []

            def _capture(*a: object, _out: list[str] = captured, **k: object) -> None:
                _out.append(" ".join(str(x) for x in a) + "\n")

            try:
                with patch("coach.commands.report.console") as mock_console:
                    mock_console.print.side_effect = _capture
                    _run_report(
                        subcommand="summary",
                        weeks=week_num,
                        format="json",
                        type_filter=None,
                        workouts=all_workouts,  # type: ignore[arg-type]
                    )
                report_output = "".join(captured)
            except Exception:
                report_output = ""

        # ── Collect ───────────────────────────────────────────────────────────
        collector.record(
            week_num=week_num,
            week_str=week_str,
            focus=profile["focus"],
            volume=profile["volume"],
            theme=profile["theme"],
            n_completed_target=profile["n_completed"],
            plan_ok=plan_ok,
            assess_ok=assess_ok,
            status_ok=status_ok,
            workouts_dir=workouts_dir,
            assessments_dir=assessments_dir,
            report_output=report_output,
            report_ran=report_ran,
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_md = generate_report(collector)
    (OUTPUT_DIR / "report.md").write_text(report_md)
    (OUTPUT_DIR / "simulation.json").write_text(collector.as_json())
    print(f"\nReport written to {OUTPUT_DIR}/report.md")

    failed_plans = [r for r in collector.results if not r.plan_ok]
    failed_assesses = [r for r in collector.results if not r.assess_ok]
    failed_statuses = [r for r in collector.results if not r.status_ok]

    assert not failed_plans, f"Plan failed for: {[r.week_str for r in failed_plans]}"
    assert not failed_assesses, f"Assess failed for: {[r.week_str for r in failed_assesses]}"
    assert not failed_statuses, f"Status failed for: {[r.week_str for r in failed_statuses]}"

    rpe_ok = sum(1 for r in collector.results if r.avg_rpe_extracted is not None)
    assert rpe_ok >= 5, f"Only {rpe_ok}/{N_WEEKS} assessments have avg_rpe extracted"

    notes_ok = sum(1 for r in collector.results if r.next_week_notes_len >= 20)
    assert notes_ok >= 5, f"Only {notes_ok}/{N_WEEKS} assessments have meaningful next-week notes"


def _count_sessions_for_week(workouts_dir: Path, monday: datetime.date) -> int:
    from coach.notes.parser import workout_from_note

    sunday = monday + datetime.timedelta(days=6)
    count = 0
    for path in workouts_dir.glob("*.md"):
        try:
            w = workout_from_note(path.read_text(), path.stem)
            if monday <= w.date <= sunday:
                count += 1
        except Exception:
            continue
    return count


def _load_all_workouts(workouts_dir: Path) -> list[object]:
    from coach.models.workout import Workout
    from coach.notes.parser import workout_from_note

    workouts: list[Workout] = []
    for path in sorted(workouts_dir.glob("*.md")):
        try:
            w = workout_from_note(path.read_text(), path.stem)
            workouts.append(w)
        except Exception:
            continue
    return workouts  # type: ignore[return-value]
