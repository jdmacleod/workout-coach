from dataclasses import dataclass
from datetime import date, time


@dataclass
class ExternalSession:
    title: str
    date: date
    start_time: time
    duration_minutes: int
    source: str           # "manual" | "apple_calendar" | "google_api" | "ics"
    calendar_name: str
    session_type: str     # "yoga" | "pilates" | "unknown"
    intensity: str        # "low" | "moderate" | "high"
    recovery_cost: int    # 1–5
