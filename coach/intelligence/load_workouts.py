"""Shared helper for loading workout files from disk."""
from __future__ import annotations

import datetime
from pathlib import Path

from coach.models.workout import Workout
from coach.notes.parser import workout_from_note


def load_workouts(workouts_dir: Path, weeks: int = 8) -> list[Workout]:
    """Glob data/workouts/*.md for the last N weeks, parse front matter.

    Skips malformed files with a warning rather than crashing.
    """
    if not workouts_dir.exists():
        return []

    cutoff = datetime.date.today() - datetime.timedelta(weeks=weeks)
    workouts: list[Workout] = []

    for path in sorted(workouts_dir.glob("*.md")):
        try:
            content = path.read_text()
            w = workout_from_note(content, path.stem)
            if w.date >= cutoff:
                workouts.append(w)
        except Exception as exc:
            import sys
            print(f"Warning: skipping {path.name} — {exc}", file=sys.stderr)
            continue

    return workouts
