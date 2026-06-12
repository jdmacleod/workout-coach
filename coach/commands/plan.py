"""coach plan — generate a weekly workout plan."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from coach.config import (
    EXAMPLES_DIR,
    Config,
    ConfigNotFoundError,
    load_config,
    resolve_data_path,
)
from coach.intelligence.exceptions import InferenceError, InferenceParseError
from coach.intelligence.prompts import (
    JSON_PARSE_CORRECTION,
    PLAN_GENERATION_SYSTEM,
    PLAN_GENERATION_USER,
    PLAN_SCHEMA,
    PLAN_SCHEMA_DICT,
    extract_json_text,
)
from coach.intelligence.provider import InferenceProvider, InferenceRequest, get_provider
from coach.models.plan import WeeklyPlan
from coach.models.workout import Workout
from coach.notes.client import NotesClient
from coach.notes.exceptions import NotesClientError
from coach.notes.parser import (
    parse_front_matter,
    parse_sections,
    render_plan_note,
    render_plan_note_html,
    render_workout_note,
    render_workout_note_html,
    workout_from_note,
)
from coach.notes.schema import (
    FOLDER_PLANS,
    FOLDER_WORKOUTS,
    assessment_note_title,
    plan_note_title,
    safe_slug,
    workout_note_title,
)

console = Console()
err_console = Console(stderr=True, style="bold red")


def run(
    week: Annotated[
        str | None, typer.Option("--week", help="Target week in YYYY-Www format")
    ] = None,
    focus: Annotated[
        str | None,
        typer.Option("--focus", help="Override training focus: strength|cardio|deload|recovery"),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print plan without writing to Notes or disk")
    ] = False,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Replace existing plan for the target week")
    ] = False,
    no_calendar: Annotated[
        bool, typer.Option("--no-calendar", help="Skip calendar source queries")
    ] = False,
) -> None:
    """Generate a weekly workout plan."""
    try:
        _run_plan(
            week=week, focus=focus, dry_run=dry_run, overwrite=overwrite, no_calendar=no_calendar
        )
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


_STRENGTH_HEADINGS = ("Warm-up", "Main Lifts", "Accessories")


def _normalize_planned_content(content: str, wtype: str) -> str:
    """Split inline 'Heading: item1, item2' lines into proper heading + bullets.

    The LLM reliably uses bullet lists for Main Lifts/Accessories but often
    collapses Warm-up (and occasionally other headings) into a single line:
      Warm-up: goblet squat, hip circles, glute bridges
    This normalises those lines to:
      Warm-up:
      - goblet squat
      - hip circles
      - glute bridges
    Only applied to strength workouts and only for the known section headings.
    """
    if wtype not in ("strength", "hiit"):
        return content
    lines = content.splitlines()
    result: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        split = False
        for heading in _STRENGTH_HEADINGS:
            prefix = heading + ": "
            if stripped.startswith(prefix) and not stripped.endswith(":"):
                result.append(heading + ":")
                items_text = stripped[len(prefix) :]
                for item in items_text.split(","):
                    item = item.strip().rstrip(".")
                    if item:
                        result.append(f"- {item}")
                split = True
                break
        if not split:
            result.append(ln)
    return "\n".join(result)


def _resolve_target_week(week_str: str | None) -> str:
    """Return YYYY-Www for next Monday's ISO week (or the provided string)."""
    if week_str:
        return week_str
    today = datetime.date.today()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + datetime.timedelta(days=days_until_monday)
    iso = next_monday.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _week_to_monday(week_str: str) -> datetime.date:
    """Convert YYYY-Www to the Monday date of that week."""
    year_str, week_str_part = week_str.split("-W")
    year = int(year_str)
    week = int(week_str_part)
    jan4 = datetime.date(year, 1, 4)
    week_start = jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=week - 1)
    return week_start


def _load_next_week_notes(cfg: Config, week: str, notes_client: NotesClient) -> str:
    """Read the ## Next Week Notes section from the prior week's assessment."""
    from coach.notes.exceptions import NotesClientError
    from coach.notes.parser import parse_sections
    from coach.notes.schema import FOLDER_ASSESSMENTS

    # Determine prior week
    monday = _week_to_monday(week)
    prior_monday = monday - datetime.timedelta(weeks=1)
    iso = prior_monday.isocalendar()
    prior_week = f"{iso.year}-W{iso.week:02d}"

    # Try Apple Notes first (authoritative). Catch any Notes error — reading
    # prior-week data is optional; write failures still surface normally.
    assessment_title = assessment_note_title(prior_week)
    try:
        content = notes_client.get_note(FOLDER_ASSESSMENTS, assessment_title)
        sections = parse_sections(content)
        notes_text = sections.get("Next Week Notes", "").strip()
        if notes_text:
            return notes_text
    except NotesClientError:
        pass

    # Fallback: local assessment file
    assessments_dir = resolve_data_path(cfg, "assessments_dir")
    local_path = assessments_dir / f"{prior_week}.md"
    if local_path.exists():
        from coach.notes.parser import parse_sections as ps

        sections = ps(local_path.read_text())
        notes_text = sections.get("Next Week Notes", "").strip()
        if notes_text:
            return notes_text

    return "(none yet — first week)"


def _load_history_summary(cfg: Config, weeks: int = 4) -> str:
    """Glob last N weeks of workout files and produce a text summary."""
    from coach.notes.parser import workout_from_note

    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    if not workouts_dir.exists():
        return "(no history yet)"

    cutoff = datetime.date.today() - datetime.timedelta(weeks=weeks)
    workouts: list[Workout] = []
    for path in sorted(workouts_dir.glob("*.md")):
        try:
            content = path.read_text()
            w = workout_from_note(content, path.stem)
            if w.date >= cutoff:
                workouts.append(w)
        except Exception:
            continue

    if not workouts:
        return "(no history yet)"

    lines = []
    for w in workouts:
        rpe_str = f" RPE {w.rpe}" if w.rpe else ""
        dur_str = (
            f" {w.duration_actual}min"
            if w.duration_actual
            else (f" {w.duration_planned}min (planned)" if w.duration_planned else "")
        )
        lines.append(
            f"- {w.date.isoformat()} {w.type}/{w.subtype or '-'} [{w.status}]{rpe_str}{dur_str}"
        )

    return "\n".join(lines)


def _run_plan(
    *,
    week: str | None,
    focus: str | None,
    dry_run: bool,
    overwrite: bool,
    no_calendar: bool,
    notes_client: NotesClient | None = None,
    inference_provider: InferenceProvider | None = None,
) -> None:
    """Core logic for coach plan, injectable for testing."""
    cfg = load_config()

    target_week = _resolve_target_week(week)
    console.print(f"Generating plan for [bold]{target_week}[/bold]...")

    # Check for existing plan
    plans_dir = resolve_data_path(cfg, "plans_dir")
    local_plan_path = plans_dir / f"{target_week}.md"

    if local_plan_path.exists() and not overwrite:
        console.print(f"[yellow]Plan already exists for {target_week}.[/yellow]")
        console.print("Use [bold]--overwrite[/bold] to replace it.")
        raise typer.Exit(0)

    # If overwrite and local plan exists, skip LLM and re-push to Notes
    if local_plan_path.exists() and overwrite:
        console.print(f"Re-pushing existing plan from {local_plan_path}...")
        _push_plan_to_notes(cfg, local_plan_path, target_week, notes_client)
        console.print("[green]Plan re-pushed to Apple Notes.[/green]")
        return

    # Load training info
    training_info_path = resolve_data_path(cfg, "training_info")
    if not training_info_path.exists():
        import shutil

        shutil.copy(EXAMPLES_DIR / "training-info.md", training_info_path)
        console.print(
            f"Copied example training-info.md to {training_info_path}. "
            "Edit it to match your training."
        )
    training_info = training_info_path.read_text()

    # Set up clients
    client = notes_client or NotesClient(account=cfg.notes.account, root_folder=cfg.notes.folder)
    provider = inference_provider or get_provider(cfg)
    console.print(f"[dim]{provider.display_name()}[/dim]")

    # Load Next Week Notes from prior assessment
    next_week_notes = _load_next_week_notes(cfg, target_week, client)

    # Load history
    history_summary = _load_history_summary(cfg)

    # Build prompt
    monday = _week_to_monday(target_week)
    days_of_week = [(monday + datetime.timedelta(days=i)).strftime("%a") for i in range(7)]
    available_days = ", ".join(days_of_week)

    user_prompt = PLAN_GENERATION_USER.format(
        config_note=f"Name: {cfg.user.name}\nTimezone: {cfg.user.timezone}",
        profile_days_per_week=cfg.profile.fitness_days_per_week,
        profile_primary_goal=cfg.profile.primary_goal,
        profile_injury_notes=cfg.profile.injury_notes or "None",
        next_week_notes=next_week_notes,
        training_info=training_info,
        history_summary=history_summary,
        external_sessions="(none — calendar integration disabled)"
        if no_calendar or not cfg.calendar.enabled
        else "(loading...)",
        available_days=available_days,
        plan_schema=PLAN_SCHEMA,
    )

    if focus:
        user_prompt += f"\n\nOverride training focus: {focus}"

    # Call inference (with one retry on parse error)
    with console.status("Thinking...", spinner="dots"):
        raw_response = _infer_with_retry(
            provider, PLAN_GENERATION_SYSTEM, user_prompt, PLAN_SCHEMA, PLAN_SCHEMA_DICT
        )

    # Parse JSON response
    try:
        plan_data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        raise InferenceParseError(
            f"Failed to parse plan JSON: {e}\nResponse: {raw_response[:200]}"
        ) from e

    # Build plan objects
    workouts: list[Workout] = []
    monday_date = monday
    day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

    for session in plan_data.get("sessions", []):
        day_offset = day_map.get(session.get("day", "Mon"), 0)
        session_date = monday_date + datetime.timedelta(days=day_offset)
        wtype = session.get("type", "strength")
        wtitle = session.get("title", "Session")

        # Strip leading type word if the LLM echoed it despite schema instructions
        # e.g. type="strength", title="Strength Lower Body" → "Lower Body"
        type_prefix = wtype.capitalize() + " "
        if wtitle.startswith(type_prefix):
            wtitle = wtitle.removeprefix(type_prefix)

        note_title = workout_note_title(
            session_date.isoformat(),
            wtitle,
        )
        slug = f"{wtitle.lower().replace(' ', '-')}"
        w = Workout(
            id=f"wrk-{session_date.isoformat().replace('-', '')}-{slug[:8]}",
            date=session_date,
            type=wtype,
            status="planned",
            source="generated",
            subtype=session.get("subtype"),
            duration_planned=session.get("duration_minutes"),
            planned_content=_normalize_planned_content(
                session.get("planned_content") or session.get("rationale") or "",
                wtype,
            )
            or None,
            note_title=note_title,
        )
        workouts.append(w)

    plan = WeeklyPlan(
        week=target_week,
        generated=datetime.date.today(),
        training_focus=plan_data.get("training_focus", "general"),
        weekly_volume=plan_data.get("weekly_volume", "moderate"),
        workouts=workouts,
        generation_notes=plan_data.get("generation_notes"),
    )

    if dry_run:
        _print_plan_table(plan)
        return

    # Write local files first (minimizes partial-state on Notes failure)
    plans_dir.mkdir(parents=True, exist_ok=True)
    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    workouts_dir.mkdir(parents=True, exist_ok=True)

    for w in workouts:
        title_suffix = (w.note_title or "session").removeprefix(w.date.isoformat() + " ")
        slug = safe_slug(title_suffix)
        filename = f"{w.date.isoformat()}-{slug[:40]}.md"
        (workouts_dir / filename).write_text(render_workout_note(w))

    local_plan_path.write_text(render_plan_note(plan))
    console.print("[green]Local files written.[/green]")

    with console.status("Updating Apple Notes...", spinner="dots"):
        client.ensure_folder(FOLDER_PLANS)
        client.ensure_folder(FOLDER_WORKOUTS)
        for w in workouts:
            if w.note_title and w.type != "rest":
                client.create_note(FOLDER_WORKOUTS, w.note_title, render_workout_note_html(w))
        plan_title = plan_note_title(target_week)
        client.create_note(FOLDER_PLANS, plan_title, render_plan_note_html(plan))
    console.print("[green]Apple Notes updated.[/green]")

    _print_plan_table(plan)


def _infer_with_retry(
    provider: InferenceProvider,
    system: str,
    user: str,
    schema: str,
    schema_dict: dict[str, Any] | None = None,
) -> str:
    """Call inference with one retry on parse failure."""
    req = InferenceRequest(system=system, user=user, max_tokens=2048, schema=schema_dict)
    resp = provider.infer(req)

    text = extract_json_text(resp.text)
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Retry with correction prompt
    correction = JSON_PARSE_CORRECTION.format(previous_response=resp.text[:500], schema=schema)
    retry_req = InferenceRequest(system=system, user=correction, max_tokens=2048)
    retry_resp = provider.infer(retry_req)
    retry_text = extract_json_text(retry_resp.text)
    try:
        json.loads(retry_text)
        return retry_text
    except json.JSONDecodeError as e:
        raise InferenceParseError(
            f"Could not parse plan JSON after retry: {e}\nResponse: {retry_text[:200]}"
        ) from e


def _push_plan_to_notes(
    cfg: Config, plan_path: Path, week: str, notes_client: NotesClient | None
) -> None:
    """Re-push an existing local plan to Apple Notes as HTML.

    Reads plan metadata from the local plan file's front matter and loads
    workout objects from local workout files. Creates any missing Notes
    folders and notes; updates existing ones. Does not call the LLM.
    """
    client = notes_client or NotesClient(account=cfg.notes.account, root_folder=cfg.notes.folder)
    content = plan_path.read_text()
    fm = parse_front_matter(content)
    sections = parse_sections(content)

    # Load workouts from local files for the week (source of truth)
    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    workouts: list[Workout] = []
    if workouts_dir.exists():
        year_str, week_num_str = week.split("-W")
        year, wnum = int(year_str), int(week_num_str)
        jan4 = datetime.date(year, 1, 4)
        monday = jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=wnum - 1)
        sunday = monday + datetime.timedelta(days=6)
        for path in sorted(workouts_dir.glob("*.md")):
            try:
                w = workout_from_note(path.read_text(), path.stem)
                if monday <= w.date <= sunday:
                    workouts.append(w)
            except Exception:
                continue

    # Reconstruct WeeklyPlan for HTML rendering
    generated_str = fm.get("generated") or datetime.date.today().isoformat()
    try:
        generated = datetime.date.fromisoformat(generated_str)
    except ValueError:
        generated = datetime.date.today()

    plan = WeeklyPlan(
        week=fm.get("week") or week,
        generated=generated,
        training_focus=fm.get("training_focus") or "general",
        weekly_volume=fm.get("weekly_volume") or "moderate",
        workouts=workouts,
        status=fm.get("status") or "active",
        generation_notes=sections.get("Generation Notes") or None,
    )

    # Push workout notes: create any that are missing, update existing ones
    client.ensure_folder(FOLDER_WORKOUTS)
    for w in workouts:
        if not w.note_title or w.type == "rest":
            continue
        note_html = render_workout_note_html(w)
        if client.note_exists(FOLDER_WORKOUTS, w.note_title):
            client.update_note(FOLDER_WORKOUTS, w.note_title, note_html)
        else:
            client.create_note(FOLDER_WORKOUTS, w.note_title, note_html)

    # Push plan note: create if missing, update if existing
    plan_title = plan_note_title(week)
    client.ensure_folder(FOLDER_PLANS)
    plan_html = render_plan_note_html(plan)
    if client.note_exists(FOLDER_PLANS, plan_title):
        client.update_note(FOLDER_PLANS, plan_title, plan_html)
    else:
        client.create_note(FOLDER_PLANS, plan_title, plan_html)


def _print_plan_table(plan: WeeklyPlan) -> None:
    """Print a summary table of the plan."""
    table = Table(
        title=f"Plan for {plan.week} — {plan.training_focus.capitalize()}", show_header=True
    )
    table.add_column("Day")
    table.add_column("Workout")
    table.add_column("Duration")
    table.add_column("Type")

    for w in plan.workouts:
        day = w.date.strftime("%a") if w.date else "—"
        title = w.note_title or f"{w.type}"
        dur = f"{w.duration_planned} min" if w.duration_planned else "—"
        table.add_row(day, title, dur, w.type)

    console.print(table)
    if plan.generation_notes:
        console.print(f"\n[dim]{plan.generation_notes}[/dim]")
