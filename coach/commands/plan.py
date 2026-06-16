"""coach plan — generate a weekly workout plan."""

from __future__ import annotations

import datetime
import json
import random
from pathlib import Path
from typing import Annotated, Any, cast

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
    PLAN_CORRECTION_SYSTEM,
    PLAN_CORRECTION_USER,
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
    parse_exercise_sets,
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
    """Normalize LLM-generated planned content into consistent heading + bullet form.

    Handles two LLM output patterns:

    1. Single-line: "Main Lifts: item1, item2" → heading + one bullet per item
    2. Multi-line: heading on its own line, items below — some bulleted, some not.
       Plain-text items under a known section heading are promoted to list items.

    Only applied to strength and hiit workouts.
    """
    if wtype not in ("strength", "hiit"):
        return content
    lines = content.splitlines()

    # Pass 1: expand "Heading: item1, item2" single-line form
    expanded: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        matched = False
        for heading in _STRENGTH_HEADINGS:
            prefix = heading + ": "
            if stripped.startswith(prefix) and not stripped.endswith(":"):
                expanded.append(heading + ":")
                for item in stripped[len(prefix) :].split(","):
                    item = item.strip().rstrip(".")
                    if item:
                        expanded.append(f"- {item}")
                matched = True
                break
        if not matched:
            expanded.append(ln)

    # Pass 2: within each known section, promote plain-text lines to list items.
    # The LLM often bullets only the first item and leaves the rest as plain text.
    section_headings = {h + ":" for h in _STRENGTH_HEADINGS}
    result: list[str] = []
    in_section = False
    for ln in expanded:
        stripped = ln.strip()
        heading_text = stripped.lstrip("#").strip()
        if heading_text in section_headings:
            in_section = True
            result.append(ln)
        elif not stripped:
            in_section = False
            result.append(ln)
        elif in_section and not stripped.startswith(("-", "*", "#")):
            if stripped.startswith(("Notes:", "Note:")):
                in_section = False
                result.append(ln)
            else:
                result.append(f"- {stripped}")
        else:
            result.append(ln)

    return "\n".join(result)


def _resolve_target_week(week_str: str | None) -> str:
    """Return YYYY-Www for the current or upcoming week (or the provided string).

    If today is Monday, returns this week. Otherwise returns the next Monday's week.
    """
    if week_str:
        return week_str
    today = datetime.date.today()
    days_until_monday = (7 - today.weekday()) % 7
    target_monday = today + datetime.timedelta(days=days_until_monday)
    iso = target_monday.isocalendar()
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


def _load_recent_workouts(cfg: Config, weeks: int = 5) -> list[Workout]:
    """Glob last N weeks of workout files, returning Workout objects sorted by date."""
    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    if not workouts_dir.exists():
        return []
    cutoff = datetime.date.today() - datetime.timedelta(weeks=weeks)
    workouts: list[Workout] = []
    for path in sorted(workouts_dir.glob("*.md")):
        try:
            content = path.read_text()
            w = workout_from_note(content, path.stem)
            if w.date >= cutoff and w.type != "rest":
                workouts.append(w)
        except Exception as exc:
            console.print(f"[dim]Warning: skipping {path.name} — {exc}[/dim]")
            continue
    return workouts


def _load_history_summary(cfg: Config, weeks: int = 4) -> str:
    """Produce a weekly rollup summary of recent workouts."""
    from collections import defaultdict

    workouts = _load_recent_workouts(cfg, weeks=weeks)
    if not workouts:
        return "(no history yet)"

    weekly: dict[tuple[int, int], list[Workout]] = defaultdict(list)
    for w in workouts:
        iso = w.date.isocalendar()
        weekly[(iso.year, iso.week)].append(w)

    lines = []
    for (year, week_num), week_workouts in sorted(weekly.items()):
        types = "/".join(w.type for w in week_workouts)
        rpes = [w.rpe for w in week_workouts if w.rpe is not None]
        avg_rpe_str = f", avg RPE {sum(rpes) / len(rpes):.1f}" if rpes else ""
        total_min = sum((w.duration_actual or w.duration_planned or 0) for w in week_workouts)
        dur_str = f", {total_min} min" if total_min else ""
        lines.append(
            f"- {year}-W{week_num:02d}: {len(week_workouts)} sessions,"
            f" types: {types}{avg_rpe_str}{dur_str}"
        )

    return "\n".join(lines)


def _notes_already_mention(notes: str, *keywords: str) -> bool:
    """Return True if any keyword appears in notes (case-insensitive)."""
    lower = notes.lower()
    return any(kw.lower() in lower for kw in keywords)


def _build_periodization_directive(history: list[Workout]) -> str:
    """Return a periodization note based on training history length and recent RPE."""
    from collections import defaultdict

    if len(history) < 3:
        return ""
    weekly: dict[tuple[int, int], list[Workout]] = defaultdict(list)
    for w in history:
        iso = w.date.isocalendar()
        weekly[(iso.year, iso.week)].append(w)
    weeks_sorted = sorted(weekly.keys())
    if len(weeks_sorted) < 2:
        return ""
    last_3 = weeks_sorted[-3:] if len(weeks_sorted) >= 3 else weeks_sorted
    rpes = [w.rpe for wk in last_3 for w in weekly[wk] if w.rpe is not None]
    avg_rpe = sum(rpes) / len(rpes) if rpes else None
    if avg_rpe is not None and avg_rpe >= 8.0 and len(weeks_sorted) >= 3:
        return (
            f"Periodization: athlete is approaching peak fatigue (recent avg RPE {avg_rpe:.1f}). "
            "Consider a moderate volume reduction (10–15% fewer sets) to allow recovery."
        )
    if len(weeks_sorted) >= 4:
        return (
            "Periodization: 4+ consistent training weeks. "
            "Maintain progressive overload — add 2.5–5 kg to main lifts or add one rep per set."
        )
    return ""


def _check_deload_signal(history: list[Workout]) -> str:
    """Return a deload recommendation if fatigue signals are present in last 2 weeks."""
    if not history:
        return ""
    cutoff = datetime.date.today() - datetime.timedelta(weeks=2)
    recent = [w for w in history if w.date >= cutoff and w.rpe is not None]
    if len(recent) < 3:
        return ""
    avg_rpe = sum(w.rpe for w in recent if w.rpe is not None) / len(recent)
    if avg_rpe >= 8.5:
        return (
            f"Deload signal: recent avg RPE {avg_rpe:.1f} over {len(recent)} sessions. "
            "Recommend deload week — reduce loads 20%, volume 30–40%, keep movement patterns."
        )
    return ""


def _build_overload_hints(history: list[Workout]) -> str:
    """Scan completed sections for exercise loads and emit progressive overload hints."""
    from collections import defaultdict

    exercise_loads: dict[str, list[float]] = defaultdict(list)
    for w in history:
        if not w.completed_content:
            continue
        for s in parse_exercise_sets(w.completed_content):
            if s.load_kg is not None:
                exercise_loads[s.name.lower()].append(s.load_kg)

    if not exercise_loads:
        return ""

    hints: list[str] = []
    for name, loads in exercise_loads.items():
        if len(loads) < 2:
            continue
        if loads[-1] >= max(loads[:-1]):
            hints.append(
                f"  - {name.title()}: last recorded {loads[-1]:.1f} kg"
                " — consider adding 2.5 kg this week"
            )

    if not hints:
        return ""
    return "Progressive Overload Hints (from completed workouts):\n" + "\n".join(hints)


def _parse_exercise_front_matter(content: str) -> dict[str, Any]:
    """Parse YAML-like front matter from exercise library files."""
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    end = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = i
            break
    if end == -1:
        return {}
    result: dict[str, Any] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            result[key] = [item.strip() for item in inner.split(",") if item.strip()]
        else:
            result[key] = val
    return result


def _extract_exercise_sets_reps(content: str) -> str:
    """Get the first bullet from the Sets/Reps or Duration section of an exercise file."""
    in_section = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## Sets") or stripped.startswith("## Duration"):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("-"):
                return stripped.lstrip("-").strip()
            if stripped.startswith("##"):
                break
    return ""


def _sample_exercise_library(equipment: list[str], cfg: Config) -> str:
    """Sample one exercise per category from the library, filtered by available equipment.

    Uses ISO week number as seed so the same week always produces the same selection.
    Returns an empty string if the library directory doesn't exist.
    """
    lib_path = resolve_data_path(cfg, "exercise_library")
    if not lib_path.exists():
        console.print("[dim]Exercise library not found — skipping exercise rotation.[/dim]")
        return ""

    normalized_equip = {e.lower().replace(" ", "_").replace("-", "_") for e in equipment}
    week_num = datetime.date.today().isocalendar().week
    rng = random.Random(week_num)

    categories = [
        "strength-push",
        "strength-pull",
        "strength-lower",
        "cardio",
        "hiit",
        "mobility",
    ]
    samples: list[str] = []
    for category in categories:
        cat_dir = lib_path / category
        if not cat_dir.exists():
            continue
        eligible: list[Path] = []
        for ex_path in sorted(cat_dir.glob("*.md")):
            fm = _parse_exercise_front_matter(ex_path.read_text())
            required: list[str] = fm.get("equipment", [])
            if isinstance(required, list) and all(tag in normalized_equip for tag in required):
                eligible.append(ex_path)
        if not eligible:
            continue
        chosen = rng.choice(eligible)
        fm = _parse_exercise_front_matter(chosen.read_text())
        name = fm.get("name", chosen.stem)
        sets_reps = _extract_exercise_sets_reps(chosen.read_text())
        entry = f"- **{name}** ({category})"
        if sets_reps:
            entry += f": {sets_reps}"
        samples.append(entry)

    if not samples:
        return ""
    return "## Exercise Rotation Options\n" + "\n".join(samples)


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
    recent_workouts = _load_recent_workouts(cfg)

    # Equipment and duration constraints (needed for variation signals and prompt)
    equipment = cfg.profile.available_equipment
    max_duration = cfg.profile.max_session_duration_minutes

    # Build variation signals
    signals: list[str] = []
    deload_signal = _check_deload_signal(recent_workouts)
    if deload_signal and not _notes_already_mention(
        next_week_notes, "deload", "recovery week", "lighter"
    ):
        signals.append(deload_signal)
    periodization_dir = _build_periodization_directive(recent_workouts)
    if periodization_dir and not _notes_already_mention(
        next_week_notes, "overload", "progressive", "increase", "deload"
    ):
        signals.append(periodization_dir)
    overload_hints = _build_overload_hints(recent_workouts)
    if overload_hints:
        signals.append(overload_hints)

    # Build exercise options block
    exercise_lib = _sample_exercise_library(equipment, cfg)
    exercise_options_parts: list[str] = []
    if exercise_lib:
        exercise_options_parts.append(exercise_lib)
    if signals:
        exercise_options_parts.append("## Training Signals\n" + "\n".join(signals))
    exercise_options = "\n\n".join(exercise_options_parts)

    # Build prompt
    monday = _week_to_monday(target_week)
    days_of_week = [(monday + datetime.timedelta(days=i)).strftime("%a") for i in range(7)]
    available_days = ", ".join(days_of_week)

    equipment_constraint = (
        f"- Equipment available: {', '.join(equipment)}. "
        "NEVER suggest exercises requiring equipment not on this list.\n"
        if equipment
        else ""
    )
    duration_constraint = (
        f"- Sessions MUST NOT exceed {max_duration} minutes. "
        "Plan the number of exercises to fit within this limit.\n"
        if max_duration
        else ""
    )

    user_prompt = PLAN_GENERATION_USER.format(
        config_note=f"Name: {cfg.user.name}\nTimezone: {cfg.user.timezone}",
        profile_days_per_week=cfg.profile.fitness_days_per_week,
        profile_primary_goal=cfg.profile.primary_goal,
        profile_injury_notes=cfg.profile.injury_notes or "None",
        next_week_notes=next_week_notes,
        training_info=training_info,
        exercise_options=exercise_options,
        history_summary=history_summary,
        external_sessions="(none — calendar integration disabled)"
        if no_calendar or not cfg.calendar.enabled
        else "(loading...)",
        available_days=available_days,
        equipment_constraint=equipment_constraint,
        duration_constraint=duration_constraint,
        plan_schema=PLAN_SCHEMA,
    )

    if focus:
        user_prompt += f"\n\nOverride training focus: {focus}"

    # Enable web search on the Swift provider when equipment constraints are configured
    use_search = bool(cfg.profile.available_equipment) and provider.provider_name() == "swift"

    with console.status("Thinking...", spinner="dots"):
        raw_response = _infer_with_retry(
            provider,
            PLAN_GENERATION_SYSTEM,
            user_prompt,
            PLAN_SCHEMA,
            PLAN_SCHEMA_DICT,
            enable_search=use_search,
        )

    # Parse JSON response
    try:
        plan_data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        raise InferenceParseError(
            f"Failed to parse plan JSON: {e}\nResponse: {raw_response[:200]}"
        ) from e

    # Correction pass: ask the LLM to self-audit against equipment/duration constraints
    with console.status("Checking constraints...", spinner="dots"):
        plan_data = _correct_plan_if_needed(plan_data, cfg, provider)

    # Python-level session count enforcement: keep only the first N training sessions
    target_count = cfg.profile.fitness_days_per_week
    if target_count:
        sessions = plan_data.get("sessions", [])
        training = [s for s in sessions if s.get("type", "strength") != "rest"]
        if len(training) > target_count:
            keep = set(id(s) for s in training[:target_count])
            plan_data = {**plan_data, "sessions": [s for s in sessions if id(s) in keep]}
            console.print(
                f"[dim]Trimmed plan from {len(training)} to {target_count} sessions.[/dim]"
            )

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
                _scrub_equipment(
                    session.get("planned_content") or session.get("rationale") or "",
                    equipment,
                ),
                wtype,
            )
            or None,
            note_title=note_title,
        )
        workouts.append(w)

    # Python duration clamp (deterministic, runs after correction pass)
    if max_duration:
        for w in workouts:
            if w.type != "rest" and w.duration_planned and w.duration_planned > max_duration:
                w.duration_planned = max_duration
                console.print(
                    f"[dim]Clamped {w.date.strftime('%a')} session to {max_duration} min.[/dim]"
                )

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
        if w.type == "rest":
            continue
        title_suffix = (w.note_title or "session").removeprefix(w.date.isoformat() + " ")
        slug = safe_slug(title_suffix)
        filename = f"{w.date.isoformat()}-{slug[:40]}.md"
        (workouts_dir / filename).write_text(render_workout_note(w))

    local_plan_path.write_text(render_plan_note(plan))
    console.print("[green]Local files written.[/green]")

    with console.status("Updating Apple Notes...", spinner="dots"):
        client.ensure_folder(FOLDER_PLANS)
        client.ensure_folder(FOLDER_WORKOUTS)
        note_xcids: dict[str, str] = {}
        for w in workouts:
            if w.note_title and w.type != "rest":
                xcid = client.create_note(
                    FOLDER_WORKOUTS, w.note_title, render_workout_note_html(w)
                )
                if xcid and w.note_title:
                    note_xcids[w.note_title] = xcid

        note_urls: dict[str, str] = {}
        if cfg.notes.plan_note_links and note_xcids:
            from coach.notes.sqlite import _url_id, lookup_uuids

            pks = {title: _url_id(xcid) for title, xcid in note_xcids.items()}
            uuid_map = lookup_uuids([pk for pk in pks.values() if pk])
            for title, pk in pks.items():
                uuid = uuid_map.get(pk, "")
                identifier = uuid or pk
                if identifier:
                    note_urls[title] = f"applenotes://showNote?identifier={identifier}"

        plan_title = plan_note_title(target_week)
        client.create_note(FOLDER_PLANS, plan_title, render_plan_note_html(plan, note_urls or None))
    console.print("[green]Apple Notes updated.[/green]")

    _print_plan_table(plan)


_EQUIPMENT_KEYWORDS: frozenset[str] = frozenset(
    {
        "dumbbell",
        "dumbbells",
        "kettlebell",
        "kettlebells",
        "cable",
        "cables",
        "machine",
        "resistance band",
        "bands",
        "trx",
        "rings",
        "box",
        "trap bar",
        "hex bar",
        "smith machine",
        "sled",
        "landmine",
        "dip bar",
    }
)


def _scrub_equipment(content: str, allowed: list[str]) -> str:
    """Replace disallowed equipment keywords in planned_content with the first allowed item."""
    import re

    if not content or not allowed:
        return content
    allowed_lower = {e.lower() for e in allowed}
    substitute = allowed[0]
    lines = content.splitlines()
    result = []
    for line in lines:
        line_lower = line.lower()
        for kw in _EQUIPMENT_KEYWORDS:
            if kw in line_lower and kw not in allowed_lower:
                line = re.sub(re.escape(kw), substitute, line, flags=re.IGNORECASE)
        result.append(line)
    return "\n".join(result)


def _check_equipment_violations(sessions: list[dict[str, Any]], allowed: list[str]) -> list[str]:
    """Return violation strings for sessions using equipment not in allowed list."""
    allowed_lower = {e.lower() for e in allowed}
    violations = []
    for sess in sessions:
        content = (sess.get("planned_content") or sess.get("rationale") or "").lower()
        for kw in _EQUIPMENT_KEYWORDS:
            if kw in content and kw not in allowed_lower:
                violations.append(
                    f"{sess.get('day', '?')} '{sess.get('title', '?')}': mentions '{kw}'"
                )
                break
    return violations


def _correct_plan_if_needed(
    plan_data: dict[str, Any],
    cfg: Config,
    provider: InferenceProvider,
) -> dict[str, Any]:
    """Ask the LLM to self-audit the plan against equipment and duration constraints.

    Retries once with a stricter prompt on failure. After correction, runs a
    Python-level equipment check and prints any remaining violations.
    """
    equipment = cfg.profile.available_equipment
    max_duration = cfg.profile.max_session_duration_minutes

    if not equipment and not max_duration:
        return plan_data

    constraints: list[str] = []
    if equipment:
        constraints.append(
            f"Equipment available: {', '.join(equipment)}. "
            "Replace any exercise requiring equipment not on this list with an equivalent "
            "exercise that uses only the available equipment."
        )
    if max_duration:
        constraints.append(
            f"Each session must not exceed {max_duration} minutes. "
            "Reduce exercise count if needed to fit the time budget."
        )

    constraints_text = "\n".join(f"- {c}" for c in constraints)

    def _attempt(prompt_prefix: str = "") -> dict[str, Any] | None:
        prompt = PLAN_CORRECTION_USER.format(
            constraints=constraints_text,
            plan_json=json.dumps(plan_data),
            plan_schema=PLAN_SCHEMA,
        )
        if prompt_prefix:
            prompt = prompt_prefix + "\n\n" + prompt
        try:
            raw = _infer_with_retry(
                provider, PLAN_CORRECTION_SYSTEM, prompt, PLAN_SCHEMA, PLAN_SCHEMA_DICT
            )
            return cast(dict[str, Any], json.loads(raw))
        except (InferenceError, json.JSONDecodeError):
            return None

    result = _attempt()
    if result is None:
        strict_prefix = (
            f"CRITICAL: Every session MUST use ONLY this equipment: "
            f"{', '.join(equipment or [])}. No substitutions allowed."
        )
        result = _attempt(strict_prefix)

    if result is None:
        console.print(
            "[yellow]Warning: constraint correction failed after retry. Using original plan.[/yellow]"
        )
        return plan_data

    if equipment:
        violations = _check_equipment_violations(result.get("sessions", []), equipment)
        if violations:
            console.print(
                "[yellow]Warning: LLM correction did not fully fix equipment violations "
                "(Python scrubbing will handle these):[/yellow]"
            )
            for v in violations:
                console.print(f"  [yellow]• {v}[/yellow]")

    return result


def _infer_with_retry(
    provider: InferenceProvider,
    system: str,
    user: str,
    schema: str,
    schema_dict: dict[str, Any] | None = None,
    enable_search: bool = False,
) -> str:
    """Call inference with one retry on parse failure."""
    req = InferenceRequest(
        system=system, user=user, max_tokens=3500, schema=schema_dict, enable_search=enable_search
    )
    resp = provider.infer(req)

    text = extract_json_text(resp.text)
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Retry with correction prompt
    correction = JSON_PARSE_CORRECTION.format(previous_response=resp.text[:500], schema=schema)
    retry_req = InferenceRequest(system=system, user=correction, max_tokens=3500)
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
