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
    ASSESS_SCHEMA_DICT,
    ASSESS_SYSTEM,
    ASSESS_USER,
    JSON_PARSE_CORRECTION,
    NEXT_WEEK_NOTES_SYSTEM,
    NEXT_WEEK_NOTES_USER,
    WEEKLY_SUMMARY_SYSTEM,
    WEEKLY_SUMMARY_USER,
    extract_json_text,
)
from coach.intelligence.provider import InferenceProvider, InferenceRequest, get_provider
from coach.models.workout import Workout
from coach.notes.client import NotesClient
from coach.notes.exceptions import NoteNotFoundError, NotesClientError
from coach.notes.parser import (
    parse_sections,
    render_assessment_note,
    render_assessment_note_html,
    render_workout_note,
    render_workout_note_html,
    workout_from_note,
)
from coach.notes.schema import (
    FOLDER_ASSESSMENTS,
    FOLDER_WORKOUTS,
    assessment_note_title,
    safe_slug,
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
    console.print(f"[dim]{provider.display_name()}[/dim]")

    if workout_title:
        _assess_single(cfg, client, provider, workout_title, dry_run=dry_run)
    else:
        target_week = week or _current_iso_week()
        _assess_week(cfg, client, provider, target_week, dry_run=dry_run)


def _find_local_workout_by_title(workouts_dir: Path, title: str) -> Workout | None:
    """Find a local workout file whose note_title matches `title`.

    Filters by date prefix from the title (first 10 chars) to avoid a full scan.
    """
    date_prefix = title[:10] if len(title) >= 10 else ""
    if not workouts_dir.exists():
        return None
    pattern = f"{date_prefix}*.md" if date_prefix else "*.md"
    for path in workouts_dir.glob(pattern):
        try:
            w = workout_from_note(path.read_text(), path.stem)
            if w.note_title == title:
                return w
        except Exception:
            continue
    return None


def _assess_single(
    cfg: Config,
    client: NotesClient,
    provider: InferenceProvider,
    title: str,
    *,
    dry_run: bool,
) -> None:
    """Assess a single workout note.

    Section content (Completed, How It Went) is read from Apple Notes so
    that user edits in Notes are captured. Structured metadata (date, type,
    status, etc.) is loaded from the local file where YAML front matter lives.
    """
    import dataclasses

    try:
        content = client.get_note(FOLDER_WORKOUTS, title)
    except NoteNotFoundError:
        err_console.print(f"Note not found: {title!r}")
        raise typer.Exit(code=1)

    sections = parse_sections(content)

    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    local_workout = _find_local_workout_by_title(workouts_dir, title)
    if local_workout is None:
        workout = workout_from_note(content, title)
    else:
        workout = dataclasses.replace(
            local_workout,
            completed_content=sections.get("Completed") or local_workout.completed_content,
            how_it_went=sections.get("How It Went") or local_workout.how_it_went,
        )

    with console.status(f"Extracting metrics: {title}...", spinner="dots"):
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

    # Write ordering: local first, then Notes
    _write_local_workout(workouts_dir, updated)
    client.update_note(FOLDER_WORKOUTS, title, render_workout_note_html(updated))
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

        label = w.note_title or w.date.isoformat()
        with console.status(f"  Extracting metrics: {label}...", spinner="dots"):
            result = _extract_metrics(provider, w)
        updated = _apply_metrics(w, result)
        assessed.append((updated, result))

        if not dry_run:
            _write_local_workout(workouts_dir, updated)
            if w.note_title:
                import contextlib

                with contextlib.suppress(NoteNotFoundError):
                    client.update_note(
                        FOLDER_WORKOUTS, w.note_title, render_workout_note_html(updated)
                    )

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

    with console.status("Generating weekly summary...", spinner="dots"):
        summary = _generate_weekly_summary(
            provider,
            week,
            len(completed),
            len(weekly_workouts),
            avg_rpe,
            total_duration,
            session_details,
        )
    with console.status("Generating next-week notes...", spinner="dots"):
        next_week_notes = _generate_next_week_notes(
            provider, week, completion_rate, avg_rpe, total_duration, session_details, summary
        )

    # Build assessment note
    prs: list[dict[str, Any]] = []
    for _, result in assessed:
        prs.extend(result.get("prs", []))

    assessment_kwargs: dict[str, Any] = dict(
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
    assessment_body = render_assessment_note(**assessment_kwargs)

    if dry_run:
        console.print(assessment_body)
        return

    # Write ordering: local first (plaintext), then Notes (HTML)
    assessments_dir = resolve_data_path(cfg, "assessments_dir")
    assessments_dir.mkdir(parents=True, exist_ok=True)
    (assessments_dir / f"{week}.md").write_text(assessment_body)

    assessment_title = assessment_note_title(week)
    assessment_html = render_assessment_note_html(**assessment_kwargs)
    client.ensure_folder(FOLDER_ASSESSMENTS)
    if client.note_exists(FOLDER_ASSESSMENTS, assessment_title):
        client.update_note(FOLDER_ASSESSMENTS, assessment_title, assessment_html)
    else:
        client.create_note(FOLDER_ASSESSMENTS, assessment_title, assessment_html)

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
    req = InferenceRequest(
        system=ASSESS_SYSTEM, user=user, max_tokens=1500, schema=ASSESS_SCHEMA_DICT
    )
    resp = provider.infer(req)

    try:
        return cast(dict[str, Any], json.loads(extract_json_text(resp.text)))
    except json.JSONDecodeError:
        # One retry
        correction = JSON_PARSE_CORRECTION.format(
            previous_response=resp.text[:500], schema=ASSESS_SCHEMA
        )
        retry_req = InferenceRequest(system=ASSESS_SYSTEM, user=correction, max_tokens=1500)
        retry_resp = provider.infer(retry_req)
        try:
            return cast(dict[str, Any], json.loads(extract_json_text(retry_resp.text)))
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
    title = workout.note_title or workout.id
    title_suffix = title.removeprefix(workout.date.isoformat() + " ")
    slug = safe_slug(title_suffix)
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
        except Exception as exc:
            console.print(f"  [dim]Warning: skipping {path.name} — {exc}[/dim]")
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
    req = InferenceRequest(system=WEEKLY_SUMMARY_SYSTEM, user=user, max_tokens=800)
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
    req = InferenceRequest(system=NEXT_WEEK_NOTES_SYSTEM, user=user, max_tokens=800)
    text = provider.infer(req).text.strip()
    # Drop any leading lines that are markdown headers — the model sometimes echoes
    # the user prompt structure (## Week:, ## Completion rate:, etc.) before writing
    # the actual notes. Those headers break parse_sections when stored in the assessment.
    lines = text.splitlines()
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()
