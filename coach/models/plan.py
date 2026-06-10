from dataclasses import dataclass, field
from datetime import date


@dataclass
class WeeklyPlan:
    week: str              # ISO week: "YYYY-Www"
    generated: date
    training_focus: str
    weekly_volume: str
    workouts: list         # list[Workout]
    external_sessions: list = field(default_factory=list)  # list[ExternalSession]
    generation_notes: str | None = None
    status: str = "active"
