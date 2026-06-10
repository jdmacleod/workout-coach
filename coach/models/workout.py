from dataclasses import dataclass, field
from datetime import date
from typing import Literal

WorkoutType = Literal["strength", "cardio", "hiit", "mobility", "rest", "external"]
WorkoutStatus = Literal["planned", "completed", "skipped"]
WorkoutSource = Literal["generated", "manual", "external"]


@dataclass
class Workout:
    id: str
    date: date
    type: WorkoutType
    status: WorkoutStatus
    source: WorkoutSource
    subtype: str | None = None
    duration_planned: int | None = None
    duration_actual: int | None = None
    distance_km: float | None = None
    avg_hr: int | None = None
    rpe: float | None = None
    mood: str | None = None
    soreness: str | None = None
    tags: list[str] = field(default_factory=list)
    note_title: str | None = None
    planned_content: str | None = None
    completed_content: str | None = None
    how_it_went: str | None = None
