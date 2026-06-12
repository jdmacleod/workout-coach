"""Unit tests for coach/notes/parser.py"""

from datetime import date

from coach.models.workout import Workout
from coach.notes.parser import (
    parse_front_matter,
    parse_sections,
    render_assessment_note_html,
    render_plan_note_html,
    render_workout_note,
    render_workout_note_html,
    workout_from_note,
)

SAMPLE_WORKOUT_NOTE = """\
---
id: wrk-20250607-001
date: 2025-06-07
type: strength
subtype: upper
status: completed
duration_planned: 55
duration_actual: 52
distance_km:
avg_hr:
rpe: 7.0
mood: good
soreness: mild
tags: push, pull, upper-body
source: generated
---

## Planned

Bench Press: 4×5

## Completed

Done all sets.

## How It Went

Felt strong.
"""


def test_parse_front_matter_basic():
    fm = parse_front_matter(SAMPLE_WORKOUT_NOTE)
    assert fm["id"] == "wrk-20250607-001"
    assert fm["date"] == "2025-06-07"
    assert fm["type"] == "strength"
    assert fm["rpe"] == "7.0"
    assert fm["distance_km"] is None  # empty value


def test_parse_front_matter_no_block():
    assert parse_front_matter("No front matter here") == {}


def test_parse_front_matter_missing_optional_fields_does_not_raise():
    content = "---\nid: x\ndate: 2025-01-01\ntype: rest\nstatus: planned\nsource: manual\n---\n"
    fm = parse_front_matter(content)
    assert fm["id"] == "x"
    # optional fields absent — no KeyError
    assert fm.get("rpe") is None


def test_parse_sections_basic():
    sections = parse_sections(SAMPLE_WORKOUT_NOTE)
    assert "Planned" in sections
    assert "Completed" in sections
    assert "How It Went" in sections
    assert sections["Planned"] == "Bench Press: 4×5"
    assert sections["Completed"] == "Done all sets."
    assert sections["How It Went"] == "Felt strong."


def test_parse_sections_empty_section():
    content = "---\n---\n\n## Completed\n\n## How It Went\ntext"
    sections = parse_sections(content)
    assert sections["Completed"] == ""
    assert sections["How It Went"] == "text"


def test_workout_from_note_round_trip():
    workout = workout_from_note(SAMPLE_WORKOUT_NOTE, "2025-06-07 Strength — Upper Body")
    assert workout.id == "wrk-20250607-001"
    assert workout.date == date(2025, 6, 7)
    assert workout.type == "strength"
    assert workout.status == "completed"
    assert workout.rpe == 7.0
    assert workout.duration_planned == 55
    assert workout.duration_actual == 52
    assert workout.tags == ["push", "pull", "upper-body"]
    assert workout.planned_content == "Bench Press: 4×5"
    assert workout.completed_content == "Done all sets."
    assert workout.how_it_went == "Felt strong."


def test_workout_from_note_missing_optional_fields():
    sparse = "---\nid: wrk-x\ndate: 2025-01-01\ntype: rest\nstatus: planned\nsource: manual\n---\n"
    workout = workout_from_note(sparse, "Rest Day")
    assert workout.rpe is None
    assert workout.mood is None
    assert workout.tags == []


# ── HTML render functions ─────────────────────────────────────────────────────


def test_render_workout_note_html_structure():
    """render_workout_note_html produces metadata line and h2 section headings (no H1 — Apple Notes shows note name)."""
    workout = Workout(
        id="wrk-20260617-001",
        date=date(2026, 6, 17),
        type="strength",
        status="planned",
        source="generated",
        subtype="upper",
        duration_planned=55,
        planned_content="Bench Press 4x5\nOHP 3x8",
        note_title="2026-06-17 Upper Body Push",
    )
    html = render_workout_note_html(workout)
    assert "<h1>" not in html
    assert "<b>Type:</b>" in html
    assert "<b>Duration:</b>" in html
    assert "<h2>Planned</h2>" in html
    assert "<h2>Completed</h2>" in html
    assert "<h2>How It Went</h2>" in html


def test_render_workout_note_html_multiline_planned_becomes_list():
    """Multi-line planned_content renders as <ul>/<li> list."""
    workout = Workout(
        id="wrk-20260617-001",
        date=date(2026, 6, 17),
        type="strength",
        status="planned",
        source="generated",
        planned_content="Bench Press 4x5\nOHP 3x8\nDips 3x12",
        note_title="2026-06-17 Strength — Push",
    )
    html = render_workout_note_html(workout)
    assert "<ul>" in html
    assert "<li>Bench Press 4x5</li>" in html
    assert "<li>OHP 3x8</li>" in html


def test_content_to_html_nested_list():
    """_content_to_html renders indented '- ' markers as nested <ul> elements."""
    from coach.notes.parser import _content_to_html

    content = "- Bench Press: 4x5\n  - Warmup: 2x10\n  - Work: 4x5\n- OHP: 3x8"
    html = _content_to_html(content, "placeholder")
    assert "<ul>" in html
    assert "<li>Bench Press: 4x5" in html
    assert "<li>Warmup: 2x10</li>" in html
    assert "<li>Work: 4x5</li>" in html
    assert "<li>OHP: 3x8</li>" in html
    assert html.count("<ul>") == 2
    assert html.count("</ul>") == 2


def test_content_to_html_subheading_becomes_h3():
    """Lines ending with ':' that are not list items render as <h3>."""
    from coach.notes.parser import _content_to_html

    content = "Main Lifts:\n- Back Squat: 4x5\n- Romanian Deadlift: 3x8\n\nAccessories:\n- Split Squat: 3x8"
    html = _content_to_html(content, "placeholder")
    assert "<h3>Main Lifts:</h3>" in html
    assert "<h3>Accessories:</h3>" in html
    assert "<li>Back Squat: 4x5</li>" in html
    assert "<li>Romanian Deadlift: 3x8</li>" in html
    assert "<li>Split Squat: 3x8</li>" in html
    assert "<p>Main Lifts:</p>" not in html


def test_content_to_html_list_item_with_colon_not_subheading():
    """A list item that contains a colon does NOT become an <h3>."""
    from coach.notes.parser import _content_to_html

    content = "- Back Squat: 4x5\n- OHP: 3x8"
    html = _content_to_html(content, "placeholder")
    assert "<h3>" not in html
    assert "<li>Back Squat: 4x5</li>" in html


def test_md_subheadings_prefixes_colon_lines():
    """_md_subheadings adds ### to non-list lines ending with ':'."""
    from coach.notes.parser import _md_subheadings

    content = "Warm-up:\n- goblet squat\nMain Lifts:\n- Back Squat: 4x5"
    result = _md_subheadings(content)
    assert result.startswith("### Warm-up:")
    assert "### Main Lifts:" in result
    assert "- goblet squat" in result
    assert "- Back Squat: 4x5" in result


def test_md_subheadings_idempotent():
    """_md_subheadings does not double-prefix already-prefixed lines."""
    from coach.notes.parser import _md_subheadings

    content = "### Main Lifts:\n- Back Squat: 4x5"
    assert _md_subheadings(content) == content


def test_content_to_html_mixed_list_and_paragraph():
    """_content_to_html renders non-list lines as <p> elements alongside list blocks."""
    from coach.notes.parser import _content_to_html

    content = "Note: go heavy today\n- Squat: 5x5\n- Deadlift: 3x3"
    html = _content_to_html(content, "placeholder")
    assert "<p>Note: go heavy today</p>" in html
    assert "<li>Squat: 5x5</li>" in html
    assert "<li>Deadlift: 3x3</li>" in html


def test_render_workout_note_html_empty_content_shows_placeholder():
    """No planned_content renders an italic placeholder, not blank."""
    workout = Workout(
        id="wrk-20260617-001",
        date=date(2026, 6, 17),
        type="mobility",
        status="planned",
        source="generated",
        note_title="2026-06-17 Mobility — Recovery",
    )
    html = render_workout_note_html(workout)
    assert "<i>" in html
    assert "Fill in" in html


def test_render_workout_note_html_escapes_special_chars():
    """HTML-special chars in workout data are escaped in the output."""
    workout = Workout(
        id="wrk-x",
        date=date(2026, 1, 1),
        type="strength",
        status="planned",
        source="manual",
        planned_content="a & b < c > d",
        note_title="Test & Note",
    )
    html = render_workout_note_html(workout)
    assert "&amp;" in html
    assert "&lt;" in html
    assert "&gt;" in html


def test_render_plan_note_html_structure():
    """render_plan_note_html produces metadata line and bulleted schedule (no H1 — Apple Notes shows note name)."""
    from datetime import date as d

    from coach.models.plan import WeeklyPlan

    sessions = [
        Workout(
            id="w1",
            date=d(2026, 6, 16),
            type="strength",
            status="planned",
            source="generated",
            duration_planned=55,
            note_title="2026-06-16 Upper Body",
        ),
        Workout(
            id="w2",
            date=d(2026, 6, 18),
            type="cardio",
            status="planned",
            source="generated",
            duration_planned=45,
            note_title="2026-06-18 Zone 2",
        ),
    ]
    plan = WeeklyPlan(
        week="2026-W25",
        generated=d(2026, 6, 10),
        training_focus="strength",
        weekly_volume="moderate",
        workouts=sessions,
        generation_notes="Balanced week.",
    )
    html = render_plan_note_html(plan)
    assert "<h1>" not in html
    assert "<b>Focus:</b>" in html
    assert "<b>Volume:</b>" in html
    assert "<h2>Schedule</h2>" in html
    assert "<ul>" in html
    assert "<li>" in html
    assert "55" in html
    assert "<h2>Generation Notes</h2>" in html
    assert "Balanced week." in html


def test_render_assessment_note_html_stats_and_sections():
    """render_assessment_note_html includes completion stats and session log."""
    workout = Workout(
        id="w1",
        date=date(2026, 6, 16),
        type="strength",
        status="completed",
        source="generated",
        rpe=7.5,
        duration_actual=55,
        note_title="2026-06-16 Strength — Upper Body",
    )
    html = render_assessment_note_html(
        week="2026-W25",
        sessions_planned=3,
        sessions_completed=2,
        sessions_skipped=1,
        completion_rate=0.67,
        avg_rpe=7.5,
        total_duration_min=100,
        prs=[],
        summary="Solid week.",
        session_log=[(workout, {})],
        next_week_notes="Keep it up.",
    )
    assert "<h1>" not in html
    assert "2/3" in html
    assert "<h2>Session Log</h2>" in html
    assert "<li>" in html
    assert "<h2>Next Week Notes</h2>" in html
    assert "Keep it up." in html


def test_render_assessment_note_html_prs_section():
    """render_assessment_note_html includes a Personal Records section when prs provided."""
    html = render_assessment_note_html(
        week="2026-W25",
        sessions_planned=1,
        sessions_completed=1,
        sessions_skipped=0,
        completion_rate=1.0,
        avg_rpe=8.0,
        total_duration_min=60,
        prs=[{"exercise": "Squat", "value": "100kg"}],
        summary="Great week.",
        session_log=[],
        next_week_notes="Push harder.",
    )
    assert "<h2>Personal Records</h2>" in html
    assert "Squat" in html
    assert "100kg" in html


def test_render_and_reparse_round_trip():
    workout = Workout(
        id="wrk-20250101-001",
        date=date(2025, 1, 1),
        type="cardio",
        status="planned",
        source="generated",
        subtype="zone2",
        duration_planned=45,
        tags=["running", "aerobic"],
        planned_content="Easy 45-min run.",
    )
    rendered = render_workout_note(workout)
    reparsed = workout_from_note(rendered, "test")
    assert reparsed.id == workout.id
    assert reparsed.date == workout.date
    assert reparsed.type == workout.type
    assert reparsed.status == workout.status
    assert reparsed.duration_planned == workout.duration_planned
    assert reparsed.tags == workout.tags
    assert reparsed.planned_content == workout.planned_content
