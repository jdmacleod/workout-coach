"""coach assess — parse completed workout notes and generate weekly assessment."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console

from coach.config import Config, ConfigNotFoundError, load_config, resolve_data_path
from coach.intelligence.exceptions import InferenceError, InferenceParseError
from coach.intelligence.prompts import (
    ASSESS_SCHEMA,
    ASSESS_SYSTEM,
    ASSESS_USER,
    JSON_PARSE_CORRECTION,
    NEXT_WEEK_NOTES_SYSTEM,
    NEXT_WEEK_NOTES_USER,
    WEEKLY_SUMMARY_SYSTEM,
    WEEKLY_SUMMARY_USER,
)
from coach.intelligence.provider import InferenceProvider, InferenceRequest, get_provider
from coach.models.workout import Workout
from coach.notes.client import NotesClient
from coach.notes.exceptions import NoteNotFoundError, NotesClientError
from coach.notes.parser import render_workout_note, workout_from_note
from coach.notes.schema import (
    FOLDER_ASSESSMENTS,
    FOLDER_WORKOUTS,
    assessment_note_title,
)

console = Console()
err_console = Console(stderr=True, style="bold red")


def run(
    workout: Annotated[
        str | None, typer.Option("--workout", help="Assess a single note by title")
    ] = None,
    week: Annotated[
        str | None, typer.Option("--week", help="Target week in YYYY-Www format (default: current)")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print extracted data without writing")
    ] = False,
) -> None:
    """Parse completed workout notes, extract metrics, and generate weekly assessment."""
    try:
        _run_assess(workout_title=workout, week=week, dry_run=dry_run)
    except ConfigNotFoundError:
        err_console.print("No config found. Run 'coach setup' first.")
        raise typer.Exit(code=1)
    except InferenceError as e:
        err_console.print(f"Inference error: {e}")
        err_console.print("Run 'coach setup' to check provider availability.")
        raise typer.Exit(code=1)
    except NotesClientError as e:
        err_console.print(f"Apple Notes error: {e}")
        err_console.print("Is Notes running? Try opening Notes.app and retrying.")
        raise typer.Exit(code=1)


def _current_iso_week() -> str:
    today = datetime.date.today()
    iso = today.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _run_assess(
    *,
    workout_title: str | None,
    week: str | None,
    dry_run: bool,
    notes_client: NotesClient | None = None,
    inference_provider: InferenceProvider | None = None,
) -> None:
    """Core logic for coach assess, injectable for testing."""
    cfg = load_config()

    client = notes_client or NotesClient(account=cfg.notes.account, root_folder=cfg.notes.folder)
    provider = inference_provider or get_provider(cfg)

    if workout_title:
        _assess_single(cfg, client, provider, workout_title, dry_run=dry_run)
    else:
        target_week = week or _current_iso_week()
        _assess_week(cfg, client, provider, target_week, dry_run=dry_run)


def _assess_single(
    cfg: Config,
    client: NotesClient,
    provider: InferenceProvider,
    title: str,
    *,
    dry_run: bool,
) -> None:
    """Assess a single workout note."""

    try:
        content = client.get_note(FOLDER_WORKOUTS, title)
    except NoteNotFoundError:
        err_console.print(f"Note not found: {title!r}")
        raise typer.Exit(code=1)

    workout = workout_from_note(content, title)
    result = _extract_metrics(provider, workout)

    if dry_run:
        console.print(f"[bold]{title}[/bold]")
        console.print(f"  status: {result.get('status')}")
        console.print(f"  RPE: {result.get('rpe')}")
        console.print(f"  mood: {result.get('mood')}")
        console.print(f"  summary: {result.get('summary')}")
        return

    # Update workout fields
    updated = _apply_metrics(workout, result)
    new_body = render_workout_note(updated)

    # Write ordering: local first, then Notes
    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    _write_local_workout(workouts_dir, updated)
    client.update_note(FOLDER_WORKOUTS, title, new_body)
    console.print(f"[green]Updated:[/green] {title}")


def _assess_week(
    cfg: Config,
    client: NotesClient,
    provider: InferenceProvider,
    week: str,
    *,
    dry_run: bool,
) -> None:
    """Assess all workouts for a week and write a weekly assessment note."""

    console.print(f"Assessing week [bold]{week}[/bold]...")

    # Load workouts from local files (source of truth per T7)
    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    weekly_workouts = _load_week_workouts(workouts_dir, week)

    if not weekly_workouts:
        console.print(f"[yellow]No workouts found for {week}.[/yellow]")
        return

    # Assess each completed workout
    assessed: list[tuple[Workout, dict[str, Any]]] = []
    for w in weekly_workouts:
        if not w.completed_content and not w.how_it_went:
            console.print(f"  [dim]Skipping {w.note_title} — no completion data[/dim]")
            continue

        result = _extract_metrics(provider, w)
        updated = _apply_metrics(w, result)
        assessed.append((updated, result))

        if not dry_run:
            _write_local_workout(workouts_dir, updated)
            if w.note_title:
                try:
                    new_body = render_workout_note(updated)
                    client.update_note(FOLDER_WORKOUTS, w.note_title, new_body)
                except NoteNotFoundError:
                    pass

    # Compute aggregate metrics
    completed = [w for w, _ in assessed if w.status == "completed"]
    skipped = [w for w, r in assessed if r.get("status") == "skipped"]
    all_rpe = [w.rpe for w, _ in assessed if w.rpe is not None]
    avg_rpe = sum(all_rpe) / len(all_rpe) if all_rpe else None
    total_duration = sum(w.duration_actual or 0 for w, _ in assessed)
    completion_rate = len(completed) / len(weekly_workouts) if weekly_workouts else 0.0

    # Generate weekly narrative
    session_details = "\n".join(
        f"- {w.date.isoformat()} {w.type} [{w.status}] RPE={w.rpe or '-'}" for w, _ in assessed
    )

    summary = _generate_weekly_summary(
        provider,
        week,
        len(completed),
        len(weekly_workouts),
        avg_rpe,
        total_duration,
        session_details,
    )
    next_week_notes = _generate_next_week_notes(
        provider, week, completion_rate, avg_rpe, total_duration, session_details, summary
    )

    # Build assessment note
    prs: list[dict[str, Any]] = []
    for _, result in assessed:
        prs.extend(result.get("prs", []))

    assessment_body = _render_assessment_note(
        week=week,
        sessions_planned=len(weekly_workouts),
        sessions_completed=len(completed),
        sessions_skipped=len(skipped),
        completion_rate=completion_rate,
        avg_rpe=avg_rpe,
        total_duration_min=total_duration,
        prs=prs,
        summary=summary,
        session_log=assessed,
        next_week_notes=next_week_notes,
    )

    if dry_run:
        console.print(assessment_body)
        return

    # Write ordering: local first, then Notes
    assessments_dir = resolve_data_path(cfg, "assessments_dir")
    assessments_dir.mkdir(parents=True, exist_ok=True)
    (assessments_dir / f"{week}.md").write_text(assessment_body)

    assessment_title = assessment_note_title(week)
    client.ensure_folder(FOLDER_ASSESSMENTS)
    if client.note_exists(FOLDER_ASSESSMENTS, assessment_title):
        client.update_note(FOLDER_ASSESSMENTS, assessment_title, assessment_body)
    else:
        client.create_note(FOLDER_ASSESSMENTS, assessment_title, assessment_body)

    console.print(f"[green]Assessment written:[/green] {assessment_title}")
    console.print(
        f"  Completion: {completion_rate:.0%} | Avg RPE: {avg_rpe:.1f}"
        if avg_rpe
        else f"  Completion: {completion_rate:.0%}"
    )
    console.print("\n[bold]Next Week Notes:[/bold]")
    console.print(f"  {next_week_notes}")


def _extract_metrics(provider: InferenceProvider, workout: Workout) -> dict[str, Any]:
    """Call LLM to extract metrics from a workout note. Returns parsed JSON dict."""

    metadata = (
        f"type: {workout.type}, subtype: {workout.subtype or '-'}, "
        f"duration_planned: {workout.duration_planned or '-'} min"
    )
    user = ASSESS_USER.format(
        metadata=metadata,
        completed=workout.completed_content or "(empty)",
        how_it_went=workout.how_it_went or "(empty)",
        assess_schema=ASSESS_SCHEMA,
    )
    req = InferenceRequest(system=ASSESS_SYSTEM, user=user, max_tokens=512)
    resp = provider.infer(req)

    try:
        return cast(dict[str, Any], json.loads(resp.text))
    except json.JSONDecodeError:
        # One retry
        correction = JSON_PARSE_CORRECTION.format(
            previous_response=resp.text[:500], schema=ASSESS_SCHEMA
        )
        retry_req = InferenceRequest(system=ASSESS_SYSTEM, user=correction, max_tokens=512)
        retry_resp = provider.infer(retry_req)
        try:
            return cast(dict[str, Any], json.loads(retry_resp.text))
        except json.JSONDecodeError as e:
            raise InferenceParseError(f"Could not parse assessment JSON: {e}") from e


def _apply_metrics(workout: Workout, result: dict[str, Any]) -> Workout:
    """Return a new Workout with extracted metrics applied."""
    import dataclasses

    updates: dict[str, Any] = {}
    if "status" in result:
        updates["status"] = result["status"]
    if result.get("rpe") is not None:
        updates["rpe"] = float(result["rpe"])
    if result.get("mood"):
        updates["mood"] = result["mood"]
    if result.get("soreness"):
        updates["soreness"] = result["soreness"]
    if result.get("duration_actual") is not None:
        updates["duration_actual"] = int(result["duration_actual"])
    if result.get("summary"):
        updates["how_it_went"] = result["summary"]

    return dataclasses.replace(workout, **updates)


def _write_local_workout(workouts_dir: Path, workout: Workout) -> None:
    """Write updated workout front matter + body to local file."""
    workouts_dir.mkdir(parents=True, exist_ok=True)
    slug = (
        (workout.note_title or workout.id)
        .lower()
        .replace(" ", "-")
        .replace("—", "")
        .replace("  ", "-")
    )
    filename = f"{workout.date.isoformat()}-{slug[:40]}.md"
    path = workouts_dir / filename
    path.write_text(render_workout_note(workout))


def _load_week_workouts(workouts_dir: Path, week: str) -> list[Workout]:
    """Load all workout files for the given ISO week from local storage."""
    if not workouts_dir.exists():
        return []

    # Parse ISO week to date range
    year_str, week_str = week.split("-W")
    year, wnum = int(year_str), int(week_str)
    jan4 = datetime.date(year, 1, 4)
    monday = jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=wnum - 1)
    sunday = monday + datetime.timedelta(days=6)

    workouts = []
    for path in sorted(workouts_dir.glob("*.md")):
        try:
            content = path.read_text()
            w = workout_from_note(content, path.stem)
            if monday <= w.date <= sunday:
                workouts.append(w)
        except Exception:
            continue
    return workouts


def _generate_weekly_summary(
    provider: InferenceProvider,
    week: str,
    completed: int,
    planned: int,
    avg_rpe: float | None,
    total_duration: int,
    session_details: str,
) -> str:

    user = WEEKLY_SUMMARY_USER.format(
        week=week,
        sessions_completed=completed,
        sessions_planned=planned,
        avg_rpe=f"{avg_rpe:.1f}" if avg_rpe else "N/A",
        total_duration_min=total_duration,
        session_details=session_details,
    )
    req = InferenceRequest(system=WEEKLY_SUMMARY_SYSTEM, user=user, max_tokens=256)
    return provider.infer(req).text.strip()


def _generate_next_week_notes(
    provider: InferenceProvider,
    week: str,
    completion_rate: float,
    avg_rpe: float | None,
    total_duration: int,
    session_details: str,
    observations: str,
) -> str:
    user = NEXT_WEEK_NOTES_USER.format(
        week=week,
        completion_rate=f"{completion_rate:.0%}",
        avg_rpe=f"{avg_rpe:.1f}" if avg_rpe else "N/A",
        total_duration_min=total_duration,
        session_details=session_details,
        observations=observations,
    )
    req = InferenceRequest(system=NEXT_WEEK_NOTES_SYSTEM, user=user, max_tokens=200)
    return provider.infer(req).text.strip()


def _render_assessment_note(
    *,
    week: str,
    sessions_planned: int,
    sessions_completed: int,
    sessions_skipped: int,
    completion_rate: float,
    avg_rpe: float | None,
    total_duration_min: int,
    prs: list[dict[str, Any]],
    summary: str,
    session_log: list[tuple[Workout, dict[str, Any]]],
    next_week_notes: str,
) -> str:
    """Render the full assessment note as plaintext."""
    prs_str = str(prs) if prs else "[]"
    avg_rpe_str = f"{avg_rpe:.1f}" if avg_rpe is not None else ""

    lines = [
        "---",
        f"week: {week}",
        f"generated: {datetime.date.today().isoformat()}",
        f"sessions_planned: {sessions_planned}",
        f"sessions_completed: {sessions_completed}",
        f"sessions_skipped: {sessions_skipped}",
        f"completion_rate: {completion_rate:.2f}",
        f"avg_rpe: {avg_rpe_str}",
        f"total_duration_min: {total_duration_min}",
        f"prs: {prs_str}",
        "---",
        "",
        "## Summary",
        summary,
        "",
        "## Session Log",
        "| Date | Workout | Status | RPE | Duration |",
        "|------|---------|--------|-----|----------|",
    ]

    for w, _ in session_log:
        title = w.note_title or w.id
        rpe_str = f"{w.rpe:.1f}" if w.rpe else "—"
        dur_str = f"{w.duration_actual} min" if w.duration_actual else "—"
        lines.append(f"| {w.date.isoformat()} | {title} | {w.status} | {rpe_str} | {dur_str} |")

    lines.extend(
        [
            "",
            "## Observations",
            "(generated from session data above)",
            "",
            "## Next Week Notes",
            next_week_notes,
        ]
    )

    return "\n".join(lines)
