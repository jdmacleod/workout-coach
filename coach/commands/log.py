"""coach log — quick ad hoc workout entry."""

from __future__ import annotations

import datetime
from typing import Annotated

import typer
from rich.console import Console

from coach.config import ConfigNotFoundError, load_config, resolve_data_path
from coach.models.workout import Workout
from coach.notes.client import NotesClient
from coach.notes.exceptions import NotesClientError
from coach.notes.parser import render_workout_note, render_workout_note_html
from coach.notes.schema import FOLDER_WORKOUTS, workout_note_title

console = Console()
err_console = Console(stderr=True, style="bold red")


def run(
    date: Annotated[
        str | None, typer.Option("--date", help="Date of workout YYYY-MM-DD (default: today)")
    ] = None,
    type: Annotated[str | None, typer.Option("--type", help="Workout type")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Short title")] = None,
) -> None:
    """Quick interactive entry for ad hoc workouts not in the weekly plan."""
    try:
        _run_log(date_str=date, workout_type=type, title=title)
    except ConfigNotFoundError:
        err_console.print("No config found. Run 'coach setup' first.")
        raise typer.Exit(code=1)
    except NotesClientError as e:
        err_console.print(f"Apple Notes error: {e}")
        err_console.print("Is Notes running? Try opening Notes.app and retrying.")
        raise typer.Exit(code=1)


def _run_log(
    *,
    date_str: str | None,
    workout_type: str | None,
    title: str | None,
    notes_client: NotesClient | None = None,
) -> None:
    """Core logic for coach log, injectable for testing."""
    cfg = load_config()

    # Resolve date
    if date_str:
        try:
            workout_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            err_console.print(f"Invalid date format: {date_str!r}. Use YYYY-MM-DD.")
            raise typer.Exit(code=1)
    else:
        workout_date = datetime.date.today()

    # Collect remaining fields interactively if not provided
    if workout_type is None:
        workout_type = typer.prompt(
            "Workout type (strength/cardio/hiit/mobility/rest)",
            default="strength",
        )
    if title is None:
        title = typer.prompt("Short title (e.g. 'Upper Body', 'Zone 2 Run')")

    duration_str = typer.prompt("Duration in minutes", default="")
    duration = int(duration_str) if duration_str.strip().isdigit() else None

    description = typer.prompt("Brief description (optional)", default="")

    rpe_str = typer.prompt("RPE 1–10 (optional)", default="")
    rpe = float(rpe_str) if rpe_str.strip() else None

    how_it_went = typer.prompt("How did it go? (optional — free text)", default="")

    # Build workout object
    slug = title.lower().replace(" ", "-").replace("'", "")
    note_id = f"wrk-{workout_date.isoformat().replace('-', '')}-log"
    note_title = workout_note_title(
        workout_date.isoformat(),
        title,
    )

    workout = Workout(
        id=note_id,
        date=workout_date,
        type=workout_type,  # type: ignore[arg-type]
        status="completed",
        source="manual",
        duration_actual=duration,
        rpe=rpe,
        planned_content=description if description else None,
        completed_content=description if description else None,
        how_it_went=how_it_went if how_it_went else None,
        note_title=note_title,
    )

    body = render_workout_note(workout)

    # Write to Apple Notes (HTML for human-readable display)
    client = notes_client or NotesClient(account=cfg.notes.account, root_folder=cfg.notes.folder)
    client.ensure_folder(FOLDER_WORKOUTS)
    client.create_note(FOLDER_WORKOUTS, note_title, render_workout_note_html(workout))

    # Write local file (plaintext YAML + Markdown as source of truth)
    filename = f"{workout_date.isoformat()}-{slug}.md"
    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    workouts_dir.mkdir(parents=True, exist_ok=True)
    local_path = workouts_dir / filename
    local_path.write_text(body)

    console.print(f"\n[green]Logged:[/green] [bold]{note_title}[/bold]")
    console.print(f"  Notes: Exercise Coach/Workouts/{note_title}")
    console.print(f"  Local: {local_path}")
    console.print(
        f'\nTip: run [bold]coach assess --workout "{note_title}"[/bold] to extract full metrics.'
    )
