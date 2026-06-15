"""Workout metrics extraction helpers shared by assess and sync commands."""

from __future__ import annotations

import dataclasses
import json
from typing import Any, cast

from coach.intelligence.exceptions import InferenceParseError
from coach.intelligence.prompts import (
    ASSESS_SCHEMA,
    ASSESS_SCHEMA_DICT,
    ASSESS_SYSTEM,
    ASSESS_USER,
    JSON_PARSE_CORRECTION,
    extract_json_text,
)
from coach.intelligence.provider import InferenceProvider, InferenceRequest
from coach.models.workout import Workout


def _extract_metrics(provider: InferenceProvider, workout: Workout) -> dict[str, Any]:
    """Call LLM to extract metrics from a workout note. Returns parsed JSON dict."""
    metadata = (
        f"type: {workout.type}, subtype: {workout.subtype or '-'}, "
        f"duration_planned: {workout.duration_planned or '-'} min"
    )
    user = ASSESS_USER.format(
        metadata=metadata,
        completed=workout.completed_content or "(empty)",
        how_it_went=workout.how_it_went or "(empty)",
        assess_schema=ASSESS_SCHEMA,
    )
    req = InferenceRequest(
        system=ASSESS_SYSTEM, user=user, max_tokens=1500, schema=ASSESS_SCHEMA_DICT
    )
    resp = provider.infer(req)

    try:
        return cast(dict[str, Any], json.loads(extract_json_text(resp.text)))
    except json.JSONDecodeError:
        correction = JSON_PARSE_CORRECTION.format(
            previous_response=resp.text[:500], schema=ASSESS_SCHEMA
        )
        retry_req = InferenceRequest(system=ASSESS_SYSTEM, user=correction, max_tokens=1500)
        retry_resp = provider.infer(retry_req)
        try:
            return cast(dict[str, Any], json.loads(extract_json_text(retry_resp.text)))
        except json.JSONDecodeError as e:
            raise InferenceParseError(f"Could not parse assessment JSON: {e}") from e


def _apply_metrics(workout: Workout, result: dict[str, Any]) -> Workout:
    """Return a new Workout with extracted metrics applied."""
    updates: dict[str, Any] = {}
    if "status" in result:
        updates["status"] = result["status"]
    if result.get("rpe") is not None:
        updates["rpe"] = float(result["rpe"])
    if result.get("mood"):
        updates["mood"] = result["mood"]
    if result.get("soreness"):
        updates["soreness"] = result["soreness"]
    if result.get("duration_actual") is not None:
        updates["duration_actual"] = int(result["duration_actual"])
    if result.get("summary"):
        updates["how_it_went"] = result["summary"]

    return dataclasses.replace(workout, **updates)
