"""Synthetic LLM response factory and sequential mock provider for usability tests."""

from __future__ import annotations

import datetime
import json

from coach.intelligence.provider import InferenceProvider, InferenceRequest, InferenceResponse
from tests.usability.synthetic_data import WeekProfile

# ---------------------------------------------------------------------------
# Plan session templates
# ---------------------------------------------------------------------------

_STANDARD_SESSIONS = [
    {
        "day": "Mon",
        "type": "strength",
        "subtype": "upper push",
        "duration_minutes": 40,
        "title": "Upper Body Push",
        "planned_content": (
            "### Warm-up:\n- Arm circles, band pull-aparts, light row 2x10\n"
            "### Main Lifts:\n- Bench Press: 3x5 @ 70% 1RM\n- OHP: 3x8 @ 60% 1RM\n"
            "### Accessories:\n- Pull-ups: 3x6\n- Barbell Row: 3x8"
        ),
        "rationale": "Push-focused upper day to build pressing strength",
    },
    {
        "day": "Wed",
        "type": "strength",
        "subtype": "lower",
        "duration_minutes": 40,
        "title": "Lower Body",
        "planned_content": (
            "### Warm-up:\n- Hip circles, goblet squat 2x10, leg swings\n"
            "### Main Lifts:\n- Back Squat: 3x5 @ 75% 1RM\n- Romanian Deadlift: 3x8\n"
            "### Accessories:\n- Barbell Lunge: 3x10 per leg"
        ),
        "rationale": "Squat-focused lower day for leg strength",
    },
    {
        "day": "Fri",
        "type": "cardio",
        "subtype": "zone2",
        "duration_minutes": 35,
        "title": "Zone 2 Run",
        "planned_content": "Easy 35-min run at conversational pace. Avg HR target: 130-140 bpm.",
        "rationale": "Aerobic base building and active recovery",
    },
    {
        "day": "Sat",
        "type": "mobility",
        "subtype": "recovery",
        "duration_minutes": 30,
        "title": "Mobility Recovery",
        "planned_content": (
            "- Hip flexor stretch: 2 min each side\n"
            "- Thoracic rotation: 2x10 each direction\n"
            "- Hamstring stretch: 2 min each side\n"
            "- Shoulder mobility: band dislocates, arm circles"
        ),
        "rationale": "Active recovery and mobility maintenance",
    },
]

_HIGH_VOLUME_SESSIONS = [
    {
        "day": "Mon",
        "type": "strength",
        "subtype": "upper push",
        "duration_minutes": 40,
        "title": "Upper Body Push",
        "planned_content": (
            "### Warm-up:\n- Band pull-aparts 2x15, light bench warm-up\n"
            "### Main Lifts:\n- Bench Press: 4x5 @ 75% 1RM\n- OHP: 4x6 @ 65% 1RM\n"
            "### Accessories:\n- Pull-ups: 4x6\n- Barbell Row: 3x10"
        ),
        "rationale": "Higher-volume push day in progression block",
    },
    {
        "day": "Tue",
        "type": "strength",
        "subtype": "lower",
        "duration_minutes": 40,
        "title": "Lower Body",
        "planned_content": (
            "### Main Lifts:\n- Back Squat: 4x5 @ 78% 1RM\n- Deadlift: 2x3 @ 85% 1RM\n"
            "### Accessories:\n- Barbell Lunge: 3x10 per leg"
        ),
        "rationale": "High-intensity lower body session",
    },
    {
        "day": "Thu",
        "type": "strength",
        "subtype": "upper pull",
        "duration_minutes": 40,
        "title": "Upper Body Pull",
        "planned_content": (
            "### Main Lifts:\n- Barbell Row: 4x8 @ 65% 1RM\n- Pull-ups: 4x8\n"
            "### Accessories:\n- Face Pulls with band: 3x15\n- Barbell Curl: 3x10"
        ),
        "rationale": "Pull-focused day to balance push volume",
    },
    {
        "day": "Sat",
        "type": "hiit",
        "subtype": "circuit",
        "duration_minutes": 30,
        "title": "HIIT Circuit",
        "planned_content": (
            "6 rounds:\n- 10 pull-ups\n- 15 push-ups\n- 20 air squats\n- 1 min rest between rounds"
        ),
        "rationale": "Conditioning circuit to complement strength work",
    },
]

_DELOAD_SESSIONS = [
    {
        "day": "Mon",
        "type": "strength",
        "subtype": "upper light",
        "duration_minutes": 30,
        "title": "Upper Body Light",
        "planned_content": (
            "### Lifts (light — 60% 1RM):\n- Bench Press: 3x5 @ 60% 1RM\n"
            "- OHP: 3x8 @ 50% 1RM\n- Pull-ups: 3x5 (easy)"
        ),
        "rationale": "Deload — reduced volume and intensity",
    },
    {
        "day": "Wed",
        "type": "strength",
        "subtype": "lower light",
        "duration_minutes": 30,
        "title": "Lower Body Light",
        "planned_content": (
            "### Lifts (light — 60% 1RM):\n- Back Squat: 3x5 @ 60% 1RM\n"
            "- Romanian Deadlift: 3x8 @ 55% 1RM"
        ),
        "rationale": "Deload lower — maintain movement patterns",
    },
    {
        "day": "Fri",
        "type": "cardio",
        "subtype": "easy",
        "duration_minutes": 30,
        "title": "Easy Walk",
        "planned_content": "30-min brisk walk. No intensity targets.",
        "rationale": "Light aerobic activity during deload",
    },
    {
        "day": "Sat",
        "type": "mobility",
        "subtype": "recovery",
        "duration_minutes": 30,
        "title": "Yoga Flow",
        "planned_content": (
            "- Sun salutations: 5 rounds\n- Hip openers\n- Spinal twists\n- Legs up the wall"
        ),
        "rationale": "Full recovery — yoga and stretching",
    },
]


def _sessions_for_profile(profile: WeekProfile) -> list[dict[str, object]]:
    """Select session list based on week profile."""
    if profile["focus"] == "deload":
        return _DELOAD_SESSIONS
    if profile["volume"] == "high":
        return _HIGH_VOLUME_SESSIONS
    return _STANDARD_SESSIONS


def make_plan_json(profile: WeekProfile) -> str:
    """Return a JSON string for the plan generation LLM call."""
    sessions = _sessions_for_profile(profile)
    notes = (
        f"Week {profile['week_num']} of 13 ({profile['theme']}). "
        f"Focus: {profile['focus']}. Volume: {profile['volume']}. "
        "Equipment: barbell, pull-up bar."
    )
    return json.dumps(
        {
            "training_focus": profile["focus"],
            "weekly_volume": profile["volume"],
            "generation_notes": notes,
            "sessions": sessions,
        }
    )


# ---------------------------------------------------------------------------
# Assessment response factories
# ---------------------------------------------------------------------------


def make_assess_json(
    *,
    rpe: float | None,
    status: str = "completed",
    duration: int = 40,
    mood: str = "good",
    soreness: str = "mild",
    has_pr: bool = False,
) -> str:
    """Return a JSON string for the per-workout metric extraction LLM call."""
    prs: list[dict[str, str]] = []
    if has_pr:
        prs = [{"exercise": "Back Squat", "value": "New 5RM — 205 lb"}]
    return json.dumps(
        {
            "status": status,
            "duration_actual": duration if status == "completed" else None,
            "rpe": rpe,
            "mood": mood if status == "completed" else None,
            "soreness": soreness if status == "completed" else None,
            "prs": prs,
            "deviations": [],
            "summary": (
                f"Solid session at RPE {rpe}."
                if status == "completed"
                else "Session skipped — rest day."
            ),
        }
    )


def make_weekly_summary(profile: WeekProfile) -> str:
    """Return plain-text weekly summary narrative."""
    rpe = profile["avg_rpe"]
    n = profile["n_completed"]
    if profile["focus"] == "deload":
        return (
            f"Deload week complete. Completed {n}/4 sessions at an easy RPE {rpe}. "
            "Body feels recovered and ready to push again next week."
        )
    if rpe >= 8.5:
        return (
            f"Hard week — {n}/4 sessions completed at RPE {rpe}. "
            "Pushed through some fatigue. Recovery priority this weekend."
        )
    if profile["has_pr"]:
        return (
            f"Strong week. {n}/4 sessions completed at RPE {rpe}. "
            "Hit a new squat PR — training is paying off!"
        )
    return (
        f"Good week of training. {n}/4 sessions completed at avg RPE {rpe}. "
        f"Theme: {profile['theme']}. Consistent effort across all sessions."
    )


def make_next_week_notes(profile: WeekProfile) -> str:
    """Return plain-text next-week recommendations."""
    rpe = profile["avg_rpe"]
    if profile["focus"] == "deload":
        return (
            "- Return to normal training load next week.\n"
            "- Increase squat and bench by 5 lb from pre-deload numbers.\n"
            "- Monitor energy — if still fatigued, one more light week."
        )
    if rpe >= 8.5:
        return (
            "- Consider a light session on Monday to recover from high RPE this week.\n"
            "- Keep volume similar but reduce intensity by 5% on main lifts.\n"
            "- Prioritize sleep and protein intake this week."
        )
    if profile["has_pr"]:
        return (
            "- Build on the PR — add 5 lb to squat next week.\n"
            "- Keep bench and OHP at current load for one more week before adding.\n"
            "- Continue current recovery protocols — they're working."
        )
    return (
        f"- Continue progressive overload: add 5 lb to main lifts if RPE was under {rpe + 0.3:.1f}.\n"
        "- Keep cardio at 35 min zone 2 — aerobic base building on track.\n"
        "- Maintain 4-session frequency."
    )


# ---------------------------------------------------------------------------
# Sequential mock provider
# ---------------------------------------------------------------------------


class SequentialProvider(InferenceProvider):
    """Mock inference provider that returns responses in sequence.

    Cycles on the last response once the sequence is exhausted. Records all
    calls for assertion and analysis.
    """

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[InferenceRequest] = []

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        self.calls.append(request)
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return InferenceResponse(
            text=self.responses[idx],
            provider="mock",
            model="mock-sequential",
        )

    def is_available(self) -> bool:
        return True

    def provider_name(self) -> str:
        return "mock"

    def display_name(self) -> str:
        return "mock / sequential"


def make_plan_provider(profile: WeekProfile) -> SequentialProvider:
    """Provider for the plan command (2 calls: generate + correction pass)."""
    plan_json = make_plan_json(profile)
    return SequentialProvider([plan_json, plan_json])


def make_assess_provider(profile: WeekProfile, n_sessions: int) -> SequentialProvider:
    """Provider for the assess command (n_sessions extractions + summary + next-week).

    Sessions are ordered Mon < Wed < Fri < Sat (sorted by file date). The last
    session is skipped for weeks with n_completed < 4.
    """
    n_completed = profile["n_completed"]
    rpe = profile["avg_rpe"]
    responses: list[str] = []

    for slot in range(n_sessions):
        is_completed = slot < n_completed
        if is_completed:
            # Vary RPE slightly around the weekly average
            slot_rpe = round(rpe + (slot - 1.5) * 0.2, 1)
            has_pr = profile["has_pr"] and slot == 1  # PR on slot 1 (Wed lower body)
            responses.append(
                make_assess_json(
                    rpe=slot_rpe,
                    status="completed",
                    duration=40 if slot < 2 else (35 if slot == 2 else 30),
                    mood="good" if rpe < 8.0 else "fatigued",
                    soreness="mild" if rpe < 8.5 else "moderate",
                    has_pr=has_pr,
                )
            )
        else:
            responses.append(make_assess_json(rpe=None, status="skipped"))

    responses.append(make_weekly_summary(profile))
    responses.append(make_next_week_notes(profile))
    return SequentialProvider(responses)


def compute_base_monday() -> datetime.date:
    """Return the Monday 12 weeks before the current week.

    This keeps the simulation in recent dates so history accumulates
    within the 4-week lookback window for the last few simulated weeks.
    """
    today = datetime.date.today()
    current_monday = today - datetime.timedelta(days=today.weekday())
    return current_monday - datetime.timedelta(weeks=12)


def week_str_for_monday(monday: datetime.date) -> str:
    """Return YYYY-Www string for a given Monday."""
    iso = monday.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"
