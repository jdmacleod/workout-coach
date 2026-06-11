"""coach status — week-at-a-glance from local files only."""

from __future__ import annotations

import datetime
from typing import Annotated

import typer
from rich.console import Console

from coach.config import ConfigNotFoundError, load_config, resolve_data_path

console = Console()
err_console = Console(stderr=True, style="bold red")


def run(
    week: Annotated[
        str | None, typer.Option("--week", help="Target week in YYYY-Www format (default: current)")
    ] = None,
) -> None:
    """Week-at-a-glance summary. Reads local files only — no Apple Notes access."""
    try:
        _run_status(week=week)
    except ConfigNotFoundError:
        err_console.print("No config found. Run 'coach setup' first.")
        raise typer.Exit(code=1)


def _run_status(*, week: str | None = None) -> None:
    cfg = load_config()

    today = datetime.date.today()
    if week:
        year_str, week_str = week.split("-W")
        iso_year, iso_week = int(year_str), int(week_str)
        jan4 = datetime.date(iso_year, 1, 4)
        current_monday = (
            jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=iso_week - 1)
        )
        display_week = week
    else:
        iso = today.isocalendar()
        iso_year, iso_week = iso.year, iso.week
        display_week = f"{iso_year}-W{iso_week:02d}"
        jan4 = datetime.date(iso_year, 1, 4)
        current_monday = (
            jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=iso_week - 1)
        )

    current_sunday = current_monday + datetime.timedelta(days=6)

    # Check for plan file
    plans_dir = resolve_data_path(cfg, "plans_dir")
    plan_file = plans_dir / f"{display_week}.md"
    if not plan_file.exists():
        console.print("No plan for current week. Run [bold]coach plan[/bold] to generate one.")
        raise typer.Exit(0)

    # Load workouts for the week
    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    week_workouts = []
    if workouts_dir.exists():
        for path in sorted(workouts_dir.glob("*.md")):
            try:
                from coach.notes.parser import workout_from_note

                content = path.read_text()
                w = workout_from_note(content, path.stem)
                if current_monday <= w.date <= current_sunday:
                    week_workouts.append(w)
            except Exception:
                continue

    total = len(week_workouts)
    completed = sum(1 for w in week_workouts if w.status == "completed")

    # Find today's workout
    today_workouts = [w for w in week_workouts if w.date == today]

    if not today_workouts:
        today_str = "Rest day"
    else:
        w = today_workouts[0]
        for candidate in today_workouts:
            if candidate.status != "completed":
                w = candidate
                break
        title = w.note_title or f"{w.type.capitalize()}"
        status_label = w.status
        today_str = f"{title} ({status_label})"

    console.print(
        f"Week {display_week} | Today: {today_str} | This week: {completed}/{total} completed"
    )
