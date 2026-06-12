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

import html as _html
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


def _md_subheadings(content: str) -> str:
    """Prefix sub-heading lines (non-list lines ending with ':') with '### '.

    Keeps markdown structure consistent with HTML, where the same lines
    become <h3> elements. Already-prefixed lines (starting with '#') are
    left unchanged so the function is safe to call more than once.
    """
    lines = []
    for ln in content.splitlines():
        stripped = ln.strip()
        if stripped.endswith(":") and not stripped.startswith(("#", "-", "*")):
            lines.append(f"### {stripped}")
        else:
            lines.append(ln)
    return "\n".join(lines)


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
        _fm_line("note_title", workout.note_title or ""),
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
    planned = _md_subheadings(workout.planned_content or "<!-- Fill in after the workout. -->")
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
        note_title=fm.get("note_title") or title,
        planned_content=sections.get("Planned"),
        completed_content=sections.get("Completed"),
        how_it_went=sections.get("How It Went"),
    )


# ── HTML rendering for Apple Notes ───────────────────────────────────────────


def _he(value: Any) -> str:
    """HTML-escape a value for safe embedding in HTML text content."""
    return _html.escape(str(value)) if value is not None else ""


def _render_nested_list(items: list[tuple[int, str]]) -> str:
    """Convert (indent_level, text) pairs into nested <ul>/<li> HTML."""
    html: list[str] = []
    depth_stack: list[int] = []

    for indent, text in items:
        if not depth_stack:
            html.append("<ul>")
            html.append(f"<li>{_he(text)}")
            depth_stack.append(indent)
        elif indent > depth_stack[-1]:
            html.append(f"<ul><li>{_he(text)}")
            depth_stack.append(indent)
        elif indent == depth_stack[-1]:
            html.append(f"</li><li>{_he(text)}")
        else:
            while len(depth_stack) > 1 and indent < depth_stack[-1]:
                html.append("</li></ul>")
                depth_stack.pop()
            html.append(f"</li><li>{_he(text)}")

    while depth_stack:
        html.append("</li></ul>")
        depth_stack.pop()

    return "".join(html)


def _content_to_html(content: str | None, placeholder: str) -> str:
    """Render free-form or list content as HTML.

    Lines starting with '- ' or '* ' become list items; indented markers
    produce nested lists. Non-list lines ending with ':' become <h3>
    sub-headings. All other lines become <p> elements.
    """
    if not content or not content.strip():
        return f"<p><i>{placeholder}</i></p>"

    non_empty = [ln for ln in content.splitlines() if ln.strip()]
    if not non_empty:
        return f"<p><i>{placeholder}</i></p>"

    def _is_li(ln: str) -> bool:
        return ln.lstrip(" \t").startswith(("- ", "* "))

    def _is_sh(ln: str) -> bool:
        return ln.strip().endswith(":") and not _is_li(ln)

    def _indent(ln: str) -> int:
        return len(ln) - len(ln.lstrip(" \t"))

    def _li_text(ln: str) -> str:
        return ln.lstrip(" \t")[2:]

    has_list = any(_is_li(ln) for ln in non_empty)
    has_sh = any(_is_sh(ln) for ln in non_empty)

    # Fast paths: plain prose only
    if not has_list and not has_sh:
        if len(non_empty) == 1:
            return f"<p>{_he(non_empty[0].strip())}</p>"
        items = "".join(f"<li>{_he(ln.strip())}</li>" for ln in non_empty)
        return f"<ul>{items}</ul>"

    # General case: sub-headings, list items, and prose may be mixed
    parts: list[str] = []
    pending: list[tuple[int, str]] = []

    def flush() -> None:
        if pending:
            parts.append(_render_nested_list(list(pending)))
            pending.clear()

    for ln in non_empty:
        if _is_li(ln):
            pending.append((_indent(ln), _li_text(ln)))
        elif _is_sh(ln):
            flush()
            parts.append(f"<h3>{_he(ln.strip())}</h3>")
        else:
            flush()
            parts.append(f"<p>{_he(ln.strip())}</p>")

    flush()
    return "".join(parts)


def _para_html(content: str | None, placeholder: str) -> str:
    """Render free-form paragraph content as HTML <p>, preserving line breaks."""
    if not content or not content.strip():
        return f"<p><i>{placeholder}</i></p>"
    escaped = _he(content.strip()).replace("\n", "<br>")
    return f"<p>{escaped}</p>"


def render_workout_note_html(workout: Workout) -> str:
    """Render a Workout to HTML for Apple Notes display (no YAML front matter).

    The <h1> is the first line of the body — Apple Notes derives the note's title
    from it. The note is created via two-step AppleScript (name first, body second)
    so there is no duplication between the list title and the body heading.
    """
    title_html = f"<h1>{_he(workout.note_title or workout.id)}</h1>" if workout.note_title else ""
    type_str = _he(workout.type.capitalize())
    if workout.subtype:
        type_str += f" / {_he(workout.subtype)}"
    meta_parts = [f"<b>Type:</b> {type_str}"]
    if workout.duration_planned:
        meta_parts.append(f"<b>Duration:</b> {workout.duration_planned}&nbsp;min")
    if workout.status and workout.status != "planned":
        meta_parts.append(f"<b>Status:</b> {_he(workout.status)}")
    if workout.rpe is not None:
        meta_parts.append(f"<b>RPE:</b> {workout.rpe}")
    meta = " &nbsp; ".join(meta_parts)

    planned_html = _content_to_html(workout.planned_content, "Fill in after the workout.")
    completed_html = _content_to_html(
        workout.completed_content,
        "Fill in after the workout. Free text or match the planned format.",
    )
    how_html = _para_html(workout.how_it_went, "Free text - RPE, PRs, how you felt.")

    parts = []
    if title_html:
        parts.append(title_html)
    parts += [
        f"<p>{meta}</p>",
        "<p>&nbsp;</p>",
        "<h2>Planned</h2>",
        planned_html,
        "<p>&nbsp;</p>",
        "<h2>Completed</h2>",
        completed_html,
        "<p>&nbsp;</p>",
        "<h2>How It Went</h2>",
        how_html,
    ]
    return "\n".join(parts)


def render_plan_note_html(plan: WeeklyPlan) -> str:
    """Render a WeeklyPlan to HTML for Apple Notes display (no YAML front matter).

    The <h1> is the first line of the body — Apple Notes derives the note's name from it.
    """
    focus = _he(plan.training_focus.capitalize())
    volume = _he(plan.weekly_volume.capitalize())
    generated = _he(plan.generated.isoformat())

    items = []
    for w in plan.workouts:
        day = _he(w.date.strftime("%a")) if w.date else "-"
        title_text = _he(w.note_title or f"{w.type.capitalize()} session")
        dur = f" - {w.duration_planned}&nbsp;min" if w.duration_planned else ""
        items.append(f"<li><b>{day}</b> - {title_text}{dur}</li>")
    schedule_html = (
        f"<ul>{''.join(items)}</ul>" if items else "<p><i>No sessions scheduled.</i></p>"
    )

    gen_notes_html = _para_html(plan.generation_notes, "")

    parts = [
        f"<h1>Week {_he(plan.week)}</h1>",
        f"<p><b>Focus:</b> {focus} &nbsp; <b>Volume:</b> {volume} &nbsp; <b>Generated:</b> {generated}</p>",
        "<p>&nbsp;</p>",
        "<h2>Schedule</h2>",
        schedule_html,
    ]
    if plan.generation_notes:
        parts += ["<p>&nbsp;</p>", "<h2>Generation Notes</h2>", gen_notes_html]

    return "\n".join(parts)


def render_assessment_note(
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
    """Render the full assessment note as plaintext (YAML front matter + Markdown)."""
    prs_str = str(prs) if prs else "[]"
    avg_rpe_str = f"{avg_rpe:.1f}" if avg_rpe is not None else ""

    lines = [
        "---",
        f"week: {week}",
        f"generated: {date.today().isoformat()}",
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


def render_assessment_note_html(
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
    """Render the full assessment note as HTML for Apple Notes display."""
    avg_rpe_str = f"{avg_rpe:.1f}" if avg_rpe is not None else "-"
    completion_pct = f"{completion_rate:.0%}"

    session_items = []
    for w, _ in session_log:
        label = _he(w.note_title or w.id)
        status = _he(w.status)
        rpe_part = f" - RPE {w.rpe:.1f}" if w.rpe else ""
        dur_part = f" - {w.duration_actual}&nbsp;min" if w.duration_actual else ""
        day = _he(w.date.strftime("%a %b %-d"))
        session_items.append(f"<li><b>{day}</b> - {label} - {status}{rpe_part}{dur_part}</li>")

    session_html = (
        f"<ul>{''.join(session_items)}</ul>" if session_items else "<p><i>No sessions.</i></p>"
    )

    pr_parts = []
    if prs:
        pr_items = "".join(
            f"<li>{_he(pr.get('exercise', '?'))}: {_he(pr.get('value', '?'))}</li>" for pr in prs
        )
        pr_parts = ["<h2>Personal Records</h2>", f"<ul>{pr_items}</ul>"]

    parts = [
        f"<h1>Assessment - Week {_he(week)}</h1>",
        (
            f"<p><b>Completion:</b> {sessions_completed}/{sessions_planned} ({completion_pct})"
            f" &nbsp; <b>Avg RPE:</b> {avg_rpe_str}"
            f" &nbsp; <b>Total:</b> {total_duration_min}&nbsp;min</p>"
        ),
        "<h2>Summary</h2>",
        _para_html(summary, ""),
        "<h2>Session Log</h2>",
        session_html,
        *pr_parts,
        "<h2>Next Week Notes</h2>",
        _para_html(next_week_notes, ""),
    ]

    return "\n".join(parts)
