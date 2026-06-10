"""Unit tests for coach/notes/parser.py"""
from datetime import date

import pytest

from coach.notes.parser import (
    parse_front_matter,
    parse_sections,
    render_workout_note,
    workout_from_note,
)
from coach.models.workout import Workout


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
