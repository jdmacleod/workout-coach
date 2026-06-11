"""Note content parsing and rendering.

Front matter format:
    ---
    key: value
    ---

Section format:
    ## Section Name
    content...

All values are strings in front matter; callers coerce to the right types.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from coach.models.workout import Workout, WorkoutSource, WorkoutStatus, WorkoutType

if TYPE_CHECKING:
    from coach.models.plan import WeeklyPlan

# ── Parsing ───────────────────────────────────────────────────────────────────


def parse_front_matter(content: str) -> dict[str, Any]:
    """Extract key: value pairs from the first --- block.

    Returns an empty dict if no front matter block is found.
    Values are returned as strings (or None for empty values).
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    fm: dict[str, Any] = {}
    for _i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, raw_val = line.partition(":")
            key = key.strip()
            val = raw_val.strip()
            fm[key] = val if val else None
    return fm


def parse_sections(content: str) -> dict[str, str]:
    """Split note body into named sections by ## headers.

    Returns a dict mapping header names to their content (stripped).
    Content before the first ## header is ignored.
    """
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("## "):
            if current_name is not None:
                sections[current_name] = "\n".join(current_lines).strip()
            current_name = line[3:].strip()
            current_lines = []
        else:
            if current_name is not None:
                current_lines.append(line)

    if current_name is not None:
        sections[current_name] = "\n".join(current_lines).strip()

    return sections


# ── Rendering ─────────────────────────────────────────────────────────────────


def _fm_line(key: str, value: Any) -> str:
    return f"{key}: {value if value is not None else ''}"


def render_workout_note(workout: Workout) -> str:
    """Render a Workout dataclass to note plaintext."""
    tags_str = ", ".join(workout.tags) if workout.tags else ""
    fm_lines = [
        "---",
        _fm_line("id", workout.id),
        _fm_line("date", workout.date.isoformat()),
        _fm_line("type", workout.type),
        _fm_line("subtype", workout.subtype or ""),
        _fm_line("status", workout.status),
        _fm_line("duration_planned", workout.duration_planned),
        _fm_line("duration_actual", workout.duration_actual),
        _fm_line("distance_km", workout.distance_km),
        _fm_line("avg_hr", workout.avg_hr),
        _fm_line("rpe", workout.rpe),
        _fm_line("mood", workout.mood),
        _fm_line("soreness", workout.soreness),
        _fm_line("tags", tags_str),
        _fm_line("source", workout.source),
        "---",
    ]
    planned = workout.planned_content or "<!-- Fill in after the workout. -->"
    completed = (
        workout.completed_content
        or "<!-- Fill in after the workout. Free text or match the planned format. -->"
    )
    how_it_went = (
        workout.how_it_went
        or "<!-- Free text. The assessor will parse this for RPE, PRs, notes. -->"
    )

    return (
        "\n".join(fm_lines)
        + f"""

## Planned

{planned}

## Completed

{completed}

## How It Went

{how_it_went}
""".rstrip()
    )


def render_plan_note(plan: WeeklyPlan) -> str:
    """Render a WeeklyPlan dataclass to note plaintext."""

    fm_lines = [
        "---",
        _fm_line("week", plan.week),
        _fm_line("generated", plan.generated.isoformat()),
        _fm_line("status", plan.status),
        _fm_line("training_focus", plan.training_focus),
        _fm_line("weekly_volume", plan.weekly_volume),
        _fm_line("completion_rate", ""),
        _fm_line("avg_rpe", ""),
        "---",
    ]

    rows = [
        "## Schedule",
        "",
        "| Day | Workout | Source | Duration |",
        "|-----|---------|--------|----------|",
    ]
    for w in plan.workouts:
        day = w.date.strftime("%a") if hasattr(w, "date") and w.date else "—"
        title = w.note_title or f"{w.type.capitalize()} session"
        source = w.source if hasattr(w, "source") else "—"
        dur = (
            f"{w.duration_planned} min"
            if hasattr(w, "duration_planned") and w.duration_planned
            else "—"
        )
        rows.append(f"| {day} | {title} | {source} | {dur} |")

    gen_notes = (
        plan.generation_notes or "<!-- Rationale written by the planner at generation time -->"
    )
    rows.extend(
        [
            "",
            "## Generation Notes",
            gen_notes,
            "",
            "## Weekly Assessment",
            "<!-- Written by coach assess at end of week -->",
        ]
    )

    return "\n".join(fm_lines) + "\n\n" + "\n".join(rows)


# ── Round-trip ────────────────────────────────────────────────────────────────


def _coerce_int(val: str | None) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _coerce_float(val: str | None) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def workout_from_note(content: str, title: str) -> Workout:
    """Parse a workout note into a Workout dataclass.

    Missing optional fields are set to None. Required fields (id, date,
    type, status, source) fall back to sensible defaults if absent so
    the parser never raises on valid-but-sparse notes.
    """
    fm = parse_front_matter(content)
    sections = parse_sections(content)

    date_str = fm.get("date") or "1970-01-01"
    try:
        workout_date = date.fromisoformat(date_str)
    except ValueError:
        workout_date = date(1970, 1, 1)

    raw_type = (fm.get("type") or "strength").lower()
    valid_types = {"strength", "cardio", "hiit", "mobility", "rest", "external"}
    workout_type: WorkoutType = raw_type if raw_type in valid_types else "strength"  # type: ignore[assignment]

    raw_status = (fm.get("status") or "planned").lower()
    valid_statuses = {"planned", "completed", "skipped"}
    status: WorkoutStatus = raw_status if raw_status in valid_statuses else "planned"  # type: ignore[assignment]

    raw_source = (fm.get("source") or "manual").lower()
    valid_sources = {"generated", "manual", "external"}
    source: WorkoutSource = raw_source if raw_source in valid_sources else "manual"  # type: ignore[assignment]

    tags_raw = fm.get("tags") or ""
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

    return Workout(
        id=fm.get("id") or f"wrk-{date_str}-000",
        date=workout_date,
        type=workout_type,
        status=status,
        source=source,
        subtype=fm.get("subtype") or None,
        duration_planned=_coerce_int(fm.get("duration_planned")),
        duration_actual=_coerce_int(fm.get("duration_actual")),
        distance_km=_coerce_float(fm.get("distance_km")),
        avg_hr=_coerce_int(fm.get("avg_hr")),
        rpe=_coerce_float(fm.get("rpe")),
        mood=fm.get("mood") or None,
        soreness=fm.get("soreness") or None,
        tags=tags,
        note_title=title,
        planned_content=sections.get("Planned"),
        completed_content=sections.get("Completed"),
        how_it_went=sections.get("How It Went"),
    )
