"""coach report — display workout trends and statistics."""
from __future__ import annotations

import datetime
import json
from collections import defaultdict
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from coach.config import ConfigNotFoundError, load_config, resolve_data_path
from coach.intelligence.load_workouts import load_workouts
from coach.models.workout import Workout

console = Console()
err_console = Console(stderr=True, style="bold red")

SUBCOMMANDS = {"summary", "volume", "rpe", "prs", "streak"}


def run(
    subcommand: Annotated[str, typer.Argument(help="Subcommand: summary | volume | rpe | prs | streak")] = "summary",
    weeks: Annotated[int, typer.Option("--weeks", help="Lookback window in weeks")] = 8,
    format: Annotated[str, typer.Option("--format", help="Output format: table | json | csv")] = "table",
    type: Annotated[Optional[str], typer.Option("--type", help="Filter by workout type")] = None,
) -> None:
    """Display workout trends and statistics. No Apple Notes access required."""
    try:
        _run_report(subcommand=subcommand, weeks=weeks, format=format, type_filter=type)
    except ConfigNotFoundError:
        err_console.print("No config found. Run 'coach setup' first.")
        raise typer.Exit(code=1)


def _run_report(
    *,
    subcommand: str,
    weeks: int,
    format: str,
    type_filter: str | None,
    workouts: list[Workout] | None = None,  # injectable for testing
) -> None:
    if subcommand not in SUBCOMMANDS:
        err_console.print(f"Unknown subcommand: {subcommand!r}. Use: {', '.join(sorted(SUBCOMMANDS))}")
        raise typer.Exit(code=1)

    if workouts is None:
        cfg = load_config()
        workouts_dir = resolve_data_path(cfg, "workouts_dir")
        workouts = load_workouts(workouts_dir, weeks=weeks)

    if type_filter:
        workouts = [w for w in workouts if w.type == type_filter]

    dispatch = {
        "summary": _report_summary,
        "volume": _report_volume,
        "rpe": _report_rpe,
        "prs": _report_prs,
        "streak": _report_streak,
    }
    dispatch[subcommand](workouts, format=format)


def _group_by_week(workouts: list[Workout]) -> dict[str, list[Workout]]:
    by_week: dict[str, list[Workout]] = defaultdict(list)
    for w in workouts:
        iso = w.date.isocalendar()
        week_key = f"{iso.year}-W{iso.week:02d}"
        by_week[week_key].append(w)
    return dict(sorted(by_week.items()))


def _report_summary(workouts: list[Workout], *, format: str) -> None:
    by_week = _group_by_week(workouts)
    rows = []
    for week, ws in by_week.items():
        total = len(ws)
        completed = sum(1 for w in ws if w.status == "completed")
        rpes = [w.rpe for w in ws if w.rpe is not None]
        avg_rpe = sum(rpes) / len(rpes) if rpes else None
        total_min = sum((w.duration_actual or w.duration_planned or 0) for w in ws)
        focus = next((w.type for w in ws if w.status == "completed"), "—")
        rows.append({
            "week": week,
            "sessions": total,
            "completed": f"{completed} ({completed/total:.0%})" if total else "0",
            "avg_rpe": f"{avg_rpe:.1f}" if avg_rpe else "—",
            "total_min": total_min,
            "focus": focus,
        })

    if format == "json":
        console.print(json.dumps(rows, indent=2))
        return
    if format == "csv":
        console.print("week,sessions,completed,avg_rpe,total_min,focus")
        for r in rows:
            console.print(f"{r['week']},{r['sessions']},{r['completed']},{r['avg_rpe']},{r['total_min']},{r['focus']}")
        return

    table = Table(title="Workout Summary", show_header=True)
    table.add_column("Week")
    table.add_column("Sessions", justify="right")
    table.add_column("Completed")
    table.add_column("Avg RPE", justify="right")
    table.add_column("Total Min", justify="right")
    table.add_column("Focus")
    for r in rows:
        table.add_row(r["week"], str(r["sessions"]), r["completed"], r["avg_rpe"], str(r["total_min"]), r["focus"])
    console.print(table)


def _report_volume(workouts: list[Workout], *, format: str) -> None:
    by_week = _group_by_week(workouts)
    rows = []
    for week, ws in by_week.items():
        by_type: dict[str, int] = defaultdict(int)
        for w in ws:
            by_type[w.type] += w.duration_actual or w.duration_planned or 0
        rows.append({"week": week, **dict(by_type)})

    if format == "json":
        console.print(json.dumps(rows, indent=2))
        return

    table = Table(title="Volume by Week", show_header=True)
    table.add_column("Week")
    for t in ("strength", "cardio", "hiit", "mobility"):
        table.add_column(t.capitalize(), justify="right")
    for r in rows:
        table.add_row(r["week"], *(str(r.get(t, 0)) + " min" for t in ("strength", "cardio", "hiit", "mobility")))
    console.print(table)


def _report_rpe(workouts: list[Workout], *, format: str) -> None:
    rows = [
        {"date": w.date.isoformat(), "type": w.type, "rpe": w.rpe}
        for w in workouts
        if w.rpe is not None
    ]
    if format == "json":
        console.print(json.dumps(rows, indent=2))
        return

    table = Table(title="RPE Trend", show_header=True)
    table.add_column("Date")
    table.add_column("Type")
    table.add_column("RPE", justify="right")
    for r in rows:
        table.add_row(r["date"], r["type"], str(r["rpe"]))
    console.print(table)


def _report_prs(workouts: list[Workout], *, format: str) -> None:
    console.print("[dim]PR tracking not yet implemented — requires assess phase.[/dim]")


def _report_streak(workouts: list[Workout], *, format: str) -> None:
    completed_dates = sorted({w.date for w in workouts if w.status == "completed"})
    if not completed_dates:
        console.print("No completed workouts found.")
        return

    current_streak = 1
    longest_streak = 1
    tmp = 1
    for i in range(1, len(completed_dates)):
        if (completed_dates[i] - completed_dates[i - 1]).days <= 2:
            tmp += 1
            longest_streak = max(longest_streak, tmp)
        else:
            tmp = 1

    # Check if streak is current (last completed within 2 days)
    today = datetime.date.today()
    if (today - completed_dates[-1]).days <= 2:
        current_streak = tmp
    else:
        current_streak = 0

    if format == "json":
        console.print(json.dumps({"current": current_streak, "longest": longest_streak}))
        return

    console.print(f"Current streak: [bold]{current_streak}[/bold] session(s)")
    console.print(f"Longest streak: [bold]{longest_streak}[/bold] session(s)")
