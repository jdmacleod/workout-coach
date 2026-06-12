"""Prompt templates for all LLM tasks."""

from __future__ import annotations

import re
from typing import Any


def extract_json_text(text: str) -> str:
    """Strip markdown code fences from LLM output before JSON parsing.

    Models often wrap JSON in ```json...``` blocks despite being told not to.
    """
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text.strip())
    return m.group(1).strip() if m else text.strip()


PLAN_GENERATION_SYSTEM = """
You are a personal fitness coach generating a weekly training plan.
Respond only with a valid JSON object matching the schema provided.
Do not include any explanation, preamble, or markdown formatting.
""".strip()

PLAN_GENERATION_USER = """
## User Profile
{config_note}
Days per week: {profile_days_per_week}
Primary goal: {profile_primary_goal}
Injury notes: {profile_injury_notes}

## Next Week Notes (from last assessment — highest priority context)
{next_week_notes}

## Training Philosophy and Example Workouts
{training_info}

## Recent History (last 4 weeks)
{history_summary}

## Fixed Sessions This Week
{external_sessions}

## Available Days
{available_days}

## Constraints
- No high-intensity session the day after a session with recovery_cost >= 3
- At least 1 full rest day per week
- Match weekly volume to recent history (avoid >10% load increase)

## Response Schema
{plan_schema}
""".strip()

PLAN_SCHEMA = """{
  "training_focus": "string",
  "weekly_volume": "low|moderate|high",
  "generation_notes": "string",
  "sessions": [
    {
      "day": "Mon|Tue|Wed|Thu|Fri|Sat|Sun",
      "type": "strength|cardio|hiit|mobility|rest|external",
      "subtype": "string",
      "duration_minutes": 0,
      "title": "concise subtitle only — no type word, no date. BAD: 'Strength Upper Body', GOOD: 'Upper Body Push'. BAD: 'Cardio Zone 2', GOOD: 'Zone 2 Run'.",
      "planned_content": "Use section headings ending in ':' (e.g. 'Warm-up:', 'Main Lifts:', 'Accessories:') followed by '- item' lines. Each exercise on its own line. Use 'x' for sets/reps (e.g. '4x5', '3x8'). No comma-separated activities within a single bullet.",
      "rationale": "string"
    }
  ]
}"""

# Machine-parseable counterpart to PLAN_SCHEMA for the Swift provider's DynamicGenerationSchema.
PLAN_SCHEMA_DICT: dict[str, Any] = {
    "type": "object",
    "name": "PlanResponse",
    "properties": [
        {"name": "training_focus", "schema": {"type": "string"}, "is_optional": False},
        {"name": "weekly_volume", "schema": {"type": "string"}, "is_optional": False},
        {"name": "generation_notes", "schema": {"type": "string"}, "is_optional": False},
        {
            "name": "sessions",
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "name": "Session",
                    "properties": [
                        {"name": "day", "schema": {"type": "string"}, "is_optional": False},
                        {"name": "type", "schema": {"type": "string"}, "is_optional": False},
                        {"name": "subtype", "schema": {"type": "string"}, "is_optional": True},
                        {
                            "name": "duration_minutes",
                            "schema": {"type": "integer"},
                            "is_optional": True,
                        },
                        {"name": "title", "schema": {"type": "string"}, "is_optional": False},
                        {
                            "name": "planned_content",
                            "schema": {"type": "string"},
                            "is_optional": True,
                        },
                        {"name": "rationale", "schema": {"type": "string"}, "is_optional": False},
                    ],
                },
            },
            "is_optional": False,
        },
    ],
}

ASSESS_SYSTEM = """
You are a fitness coach extracting structured data from a completed workout log.
Respond only with a valid JSON object matching the schema provided.
Do not include any explanation, preamble, or markdown formatting.
""".strip()

ASSESS_USER = """
## Workout Metadata
{metadata}

## Completed Section
{completed}

## How It Went
{how_it_went}

## Response Schema
{assess_schema}
""".strip()

ASSESS_SCHEMA = """{
  "status": "completed|skipped",
  "duration_actual": null,
  "rpe": null,
  "mood": "great|good|neutral|tired|bad|null",
  "soreness": "none|mild|moderate|high|null",
  "prs": [{"exercise": "string", "value": "string"}],
  "deviations": ["string"],
  "summary": "string"
}"""

# Machine-parseable counterpart to ASSESS_SCHEMA for the Swift provider's DynamicGenerationSchema.
ASSESS_SCHEMA_DICT: dict[str, Any] = {
    "type": "object",
    "name": "AssessResponse",
    "properties": [
        {"name": "status", "schema": {"type": "string"}, "is_optional": False},
        {"name": "duration_actual", "schema": {"type": "integer"}, "is_optional": True},
        {"name": "rpe", "schema": {"type": "double"}, "is_optional": True},
        {"name": "mood", "schema": {"type": "string"}, "is_optional": True},
        {"name": "soreness", "schema": {"type": "string"}, "is_optional": True},
        {
            "name": "prs",
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "name": "PR",
                    "properties": [
                        {"name": "exercise", "schema": {"type": "string"}, "is_optional": False},
                        {"name": "value", "schema": {"type": "string"}, "is_optional": False},
                    ],
                },
            },
            "is_optional": False,
        },
        {
            "name": "deviations",
            "schema": {"type": "array", "items": {"type": "string"}},
            "is_optional": False,
        },
        {"name": "summary", "schema": {"type": "string"}, "is_optional": False},
    ],
}

WEEKLY_SUMMARY_SYSTEM = """
You are a fitness coach writing a concise weekly training summary.
Write 2–3 sentences in plain English. No bullet points. No headers.
Mention overall performance, any notable highs or lows, and one forward-looking note.
""".strip()

WEEKLY_SUMMARY_USER = """
## Week: {week}
## Sessions: {sessions_completed} of {sessions_planned} completed
## Average RPE: {avg_rpe}
## Total Duration: {total_duration_min} min

## Session Details
{session_details}
""".strip()

NEXT_WEEK_NOTES_SYSTEM = """
You are a fitness coach writing carry-forward notes for next week's plan.
Write 1–3 sentences in plain English. No bullet points, no headers.
Focus on: fatigue level, any injuries noted, whether a deload is needed, volume targets.
""".strip()

NEXT_WEEK_NOTES_USER = """
## Week: {week}
## Completion rate: {completion_rate}
## Average RPE: {avg_rpe}
## Total Duration: {total_duration_min} min

## Session Details
{session_details}

## Observations from this week
{observations}

Write the Next Week Notes paragraph now.
""".strip()

JSON_PARSE_CORRECTION = """
Your previous response was not valid JSON. Please respond with ONLY a valid JSON
object matching the schema. No explanation, no markdown code fences, no preamble.

Previous response:
{previous_response}

Schema:
{schema}
""".strip()
