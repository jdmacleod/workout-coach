"""Synthetic data for the 13-week usability simulation."""

from __future__ import annotations

import dataclasses
import datetime
from pathlib import Path
from typing import Any, TypedDict

from coach.notes.parser import render_workout_note, workout_from_note


class WeekProfile(TypedDict):
    week_num: int
    focus: str  # strength | deload | general
    volume: str  # light | moderate | high
    n_completed: int  # 3 or 4 (out of 4 planned sessions)
    avg_rpe: float
    has_pr: bool
    theme: str


WEEK_PROFILES: list[WeekProfile] = [
    {
        "week_num": 1,
        "focus": "strength",
        "volume": "moderate",
        "n_completed": 4,
        "avg_rpe": 7.5,
        "has_pr": False,
        "theme": "base building",
    },
    {
        "week_num": 2,
        "focus": "strength",
        "volume": "moderate",
        "n_completed": 4,
        "avg_rpe": 7.8,
        "has_pr": False,
        "theme": "base building",
    },
    {
        "week_num": 3,
        "focus": "strength",
        "volume": "moderate",
        "n_completed": 4,
        "avg_rpe": 8.0,
        "has_pr": False,
        "theme": "base building",
    },
    {
        "week_num": 4,
        "focus": "deload",
        "volume": "light",
        "n_completed": 3,
        "avg_rpe": 6.0,
        "has_pr": False,
        "theme": "deload",
    },
    {
        "week_num": 5,
        "focus": "strength",
        "volume": "moderate",
        "n_completed": 4,
        "avg_rpe": 7.5,
        "has_pr": False,
        "theme": "progression",
    },
    {
        "week_num": 6,
        "focus": "strength",
        "volume": "high",
        "n_completed": 4,
        "avg_rpe": 8.0,
        "has_pr": False,
        "theme": "progression",
    },
    {
        "week_num": 7,
        "focus": "strength",
        "volume": "high",
        "n_completed": 4,
        "avg_rpe": 8.2,
        "has_pr": False,
        "theme": "progression",
    },
    {
        "week_num": 8,
        "focus": "strength",
        "volume": "high",
        "n_completed": 4,
        "avg_rpe": 7.8,
        "has_pr": True,
        "theme": "progression",
    },
    {
        "week_num": 9,
        "focus": "strength",
        "volume": "high",
        "n_completed": 3,
        "avg_rpe": 8.5,
        "has_pr": False,
        "theme": "hard week",
    },
    {
        "week_num": 10,
        "focus": "strength",
        "volume": "moderate",
        "n_completed": 4,
        "avg_rpe": 7.5,
        "has_pr": False,
        "theme": "maintenance",
    },
    {
        "week_num": 11,
        "focus": "strength",
        "volume": "moderate",
        "n_completed": 4,
        "avg_rpe": 7.8,
        "has_pr": True,
        "theme": "maintenance",
    },
    {
        "week_num": 12,
        "focus": "strength",
        "volume": "moderate",
        "n_completed": 4,
        "avg_rpe": 7.5,
        "has_pr": False,
        "theme": "maintenance",
    },
    {
        "week_num": 13,
        "focus": "general",
        "volume": "moderate",
        "n_completed": 3,
        "avg_rpe": 7.3,
        "has_pr": False,
        "theme": "evaluation",
    },
]


# Per-session completion content templates keyed by (type, slot_index)
# slot_index: 0=Mon, 1=Wed, 2=Fri, 3=Sat
_STRENGTH_COMPLETIONS: list[dict[str, Any]] = [
    {
        "completed": "- Bench Press: 3x5 @ 155 lb\n- Barbell Row: 3x8 @ 125 lb\n- Pull-ups: 3x6\n- OHP: 3x8 @ 95 lb\nTotal: 38 min",
        "how_it_went": "Solid session. Bench felt smooth. Pull-ups getting stronger.",
        "duration": 38,
    },
    {
        "completed": "- Back Squat: 3x5 @ 185 lb\n- Romanian Deadlift: 3x8 @ 135 lb\n- Barbell Lunge: 3x10 per leg\nTotal: 42 min",
        "how_it_went": "Good leg day. Squat depth was solid. Hamstrings a bit tight afterward.",
        "duration": 42,
    },
    {
        "completed": "- Deadlift: 1x5 @ 225 lb\n- Barbell Hip Thrust: 3x10 @ 135 lb\n- Pull-ups: 3x8\nTotal: 40 min",
        "how_it_went": "Felt strong on pulls. Deadlift moved well. Lower back fine.",
        "duration": 40,
    },
    {
        "completed": "- OHP: 3x5 @ 105 lb\n- Bench Press: 3x8 @ 145 lb\n- Barbell Row: 3x8 @ 130 lb\nTotal: 40 min",
        "how_it_went": "OHP moving up. Felt energized. Good finisher session for the week.",
        "duration": 40,
    },
]

_CARDIO_COMPLETIONS: list[dict[str, Any]] = [
    {
        "completed": "Zone 2 run, 35 min, avg HR 138 bpm. Easy conversational pace.",
        "how_it_went": "Felt good. Easy breathing the whole time. Weather was nice.",
        "duration": 35,
    },
]

_MOBILITY_COMPLETIONS: list[dict[str, Any]] = [
    {
        "completed": "Hip flexor stretches, thoracic rotations, hamstring stretch, shoulder mobility work. 28 min.",
        "how_it_went": "Felt loose afterward. Hips a bit tight to start but opened up.",
        "duration": 28,
    },
]

_HIIT_COMPLETIONS: list[dict[str, Any]] = [
    {
        "completed": "6 rounds: 10 pull-ups, 15 push-ups, 20 air squats. 1 min rest between rounds. 30 min total.",
        "how_it_went": "Lung burner. Last two rounds were tough but pushed through.",
        "duration": 30,
    },
]


def _completion_for_type(workout_type: str, slot: int) -> dict[str, Any]:
    """Return completion content for a given workout type and slot index."""
    if workout_type == "strength":
        return _STRENGTH_COMPLETIONS[slot % len(_STRENGTH_COMPLETIONS)]
    if workout_type == "cardio":
        return _CARDIO_COMPLETIONS[0]
    if workout_type == "hiit":
        return _HIIT_COMPLETIONS[0]
    # mobility / rest / other
    return _MOBILITY_COMPLETIONS[0]


def simulate_completions(
    profile: WeekProfile,
    workouts_dir: Path,
    monday: datetime.date,
) -> int:
    """Update workout files in-place to simulate user completion for the week.

    The last (4th) session is skipped for weeks where n_completed < 4.
    Returns the actual number of sessions updated as completed.
    """
    sunday = monday + datetime.timedelta(days=6)
    week_files = sorted(
        p for p in workouts_dir.glob("*.md") if _file_date_in_range(p, monday, sunday)
    )

    n_completed = profile["n_completed"]
    actual_completed = 0

    for slot, path in enumerate(week_files):
        content = path.read_text()
        w = workout_from_note(content, path.stem)

        is_completed = slot < n_completed
        if is_completed:
            tmpl = _completion_for_type(w.type, slot)
            how = tmpl["how_it_went"]
            if profile["has_pr"] and slot == 1:  # PR on Wed (lower body)
                how += " Hit a new squat PR today — 5 lb over last best!"
            elif profile["avg_rpe"] >= 8.5:
                how = f"Grinder today. RPE {profile['avg_rpe']}. Pushed through."
            elif profile["focus"] == "deload":
                how = "Nice and easy. Good active recovery."
            updated = dataclasses.replace(
                w,
                completed_content=tmpl["completed"],
                how_it_went=how,
                duration_actual=tmpl["duration"],
            )
            actual_completed += 1
        else:
            updated = dataclasses.replace(
                w,
                completed_content="Skipped — needed rest day.",
                how_it_went="",
            )

        path.write_text(render_workout_note(updated))

    return actual_completed


def _file_date_in_range(path: Path, start: datetime.date, end: datetime.date) -> bool:
    """Check if a workout file's date (from front matter) falls within [start, end]."""
    try:
        content = path.read_text()
        w = workout_from_note(content, path.stem)
        return start <= w.date <= end
    except Exception:
        return False


TRAINING_INFO = """\
# Training Philosophy

Compound lifts first. Progressive overload each week.
Barbell work: squat, bench, deadlift, OHP.
Pull-ups for back and grip strength.
4 sessions per week: 2 upper, 1 lower, 1 active recovery.

# Available Equipment

- Barbell and plates (full rack)
- Pull-up bar
- Resistance bands

# Session Duration

Max 45 minutes per session. Keep rest periods tight.

# Recovery

Active recovery on Saturday: mobility, stretching, light cardio.
Sleep 7-9 hours. Eat enough protein.
"""
