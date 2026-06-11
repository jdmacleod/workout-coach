from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from coach.models.workout import Workout


@dataclass
class WeeklyPlan:
    week: str  # ISO week: "YYYY-Www"
    generated: date
    training_focus: str
    weekly_volume: str
    workouts: list[Workout]
    external_sessions: list[Any] = field(default_factory=list)
    generation_notes: str | None = None
    status: str = "active"
