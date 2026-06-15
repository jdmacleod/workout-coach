"""Shared note sync helpers used by both assess and sync commands."""

from __future__ import annotations

import dataclasses
import datetime
import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from coach.config import Config, resolve_data_path
from coach.intelligence.prompts import extract_json_text
from coach.intelligence.provider import InferenceProvider, InferenceRequest
from coach.models.workout import Workout
from coach.notes.client import NotesClient
from coach.notes.exceptions import NotesClientError
from coach.notes.parser import render_workout_note, workout_from_note
from coach.notes.schema import FOLDER_WORKOUTS, safe_slug

console = Console()

_SYNC_PARSE_SYSTEM = "You are a workout data extractor. Return ONLY valid JSON, no prose."
_SYNC_PARSE_USER = (
    "Extract workout fields from this note text. Return JSON with these fields:\n"
    '  - type: one of "strength", "cardio", "hiit", "mobility", "rest"\n'
    "  - duration_actual: integer minutes or null\n"
    "  - rpe: number 1-10 or null\n"
    "  - description: one-line summary of what was done (max 80 chars)\n"
    "Note text:\n"
    "{content}"
)
_SYNC_PARSE_MAX_TOKENS = 256

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_VALID_WORKOUT_TYPES = {"strength", "cardio", "hiit", "mobility", "rest"}
_SLUG_MAX_LEN = 40
_MAX_COLLISION_SUFFIX = 99
_WORKOUT_TEMPLATE_TITLE = "Template — Workout"


def _write_local_workout(workouts_dir: Path, workout: Workout, *, dest: Path | None = None) -> None:
    """Write workout front matter + body to local file.

    If `dest` is provided, write there directly (used by _sync_notes when
    a slug collision forces a different filename than the default).
    """
    workouts_dir.mkdir(parents=True, exist_ok=True)
    if dest is None:
        title = workout.note_title or workout.id
        title_suffix = title.removeprefix(workout.date.isoformat() + " ")
        slug = safe_slug(title_suffix)[:_SLUG_MAX_LEN] or "workout"
        dest = workouts_dir / f"{workout.date.isoformat()}-{slug}.md"
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(render_workout_note(workout))
    tmp.replace(dest)


def _parse_free_form(
    content: str,
    title: str,
    note_date: datetime.date,
    provider: InferenceProvider | None,
) -> Workout:
    """Parse a note with no YAML front matter.

    Tries LLM-assisted parse if provider is available; falls back to
    workout_from_note + date override on failure or when provider is None.
    """
    if provider is not None:
        try:
            req = InferenceRequest(
                system=_SYNC_PARSE_SYSTEM,
                user=_SYNC_PARSE_USER.format(content=content),
                max_tokens=_SYNC_PARSE_MAX_TOKENS,
            )
            resp = provider.infer(req)
            parsed = json.loads(extract_json_text(resp.text))
            if not isinstance(parsed, dict):
                raise ValueError("LLM returned non-object JSON")
            result: dict[str, Any] = parsed

            base = workout_from_note("", title)
            updates: dict[str, Any] = {"date": note_date}

            if result.get("type") in _VALID_WORKOUT_TYPES:
                updates["type"] = result["type"]
            if result.get("duration_actual") is not None:
                updates["duration_actual"] = int(result["duration_actual"])
            if result.get("rpe") is not None:
                updates["rpe"] = float(result["rpe"])
            if result.get("description"):
                updates["how_it_went"] = str(result["description"])

            return dataclasses.replace(base, **updates)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError, AttributeError):
            from rich.markup import escape

            console.print(
                f"[dim]Warning: LLM parse failed for '{escape(title)}' — using best-effort parse.[/dim]"
            )

    # Fallback: workout_from_note + date override
    base = workout_from_note(content, title)
    return dataclasses.replace(base, date=note_date)


def _sync_notes(
    cfg: Config,
    client: NotesClient,
    *,
    since: datetime.date | None = None,
    verbose: bool = True,
    provider: InferenceProvider | None = None,
    dry_run: bool = False,
) -> int:
    """Discover workout notes in Apple Notes and sync unsynced ones to local .md files.

    Returns the count of notes synced (or that would be synced in dry-run mode).
    """
    workouts_dir = resolve_data_path(cfg, "workouts_dir")
    titles = client.list_notes(FOLDER_WORKOUTS)

    synced = 0
    written_this_run: set[str] = set()
    # Collect rows for verbose table: (title, path_display, label)
    rows: list[tuple[str, str, str]] = []

    workouts_dir_rel = cfg.data.workouts_dir.rstrip("/")

    for title in titles:
        # Skip the setup template note (it's a placeholder, not a real workout)
        if title == _WORKOUT_TEMPLATE_TITLE:
            continue

        # Validate date prefix
        if len(title) < 10 or not _DATE_RE.match(title[:10]):
            rows.append(
                (
                    title,
                    "",
                    f"skipped — rename to '{datetime.date.today().isoformat()} {title}' to sync",
                )
            )
            continue

        date_str = title[:10]
        try:
            note_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            rows.append((title, "", "skipped — invalid date prefix"))
            continue

        # Apply --since filter (undated notes are handled above)
        if since is not None and note_date < since:
            continue

        # Derive filename
        title_suffix = title[11:] if len(title) > 10 else ""
        slug = safe_slug(title_suffix)[:_SLUG_MAX_LEN] or "workout"
        filename = f"{date_str}-{slug}.md"
        local_path = workouts_dir / filename

        # Collision: another note in this run already claimed this filename
        if filename in written_this_run:
            resolved = False
            for n in range(2, _MAX_COLLISION_SUFFIX + 2):
                alt = f"{date_str}-{slug}-{n}.md"
                if not (workouts_dir / alt).exists() and alt not in written_this_run:
                    filename = alt
                    local_path = workouts_dir / alt
                    resolved = True
                    break
            if not resolved:
                from rich.markup import escape

                console.print(
                    f"[yellow]  Warning: skipping '{escape(title)}' — "
                    f"too many notes with the same date/slug[/yellow]"
                )
                continue

        if local_path.exists():
            rows.append((title, f"{workouts_dir_rel}/{filename}", "already local"))
            continue

        # Pull content and write
        try:
            content = client.get_note(FOLDER_WORKOUTS, title)
            if not content.strip():
                rows.append((title, "", "skipped — note is empty"))
                continue

            if not dry_run:
                if content.lstrip().startswith("---"):
                    workout = workout_from_note(content, title)
                else:
                    workout = _parse_free_form(content, title, note_date, provider)
                _write_local_workout(workouts_dir, workout, dest=local_path)

            written_this_run.add(filename)
            synced += 1
            label = "would sync" if dry_run else "synced"
            rows.append((title, f"{workouts_dir_rel}/{filename}", label))

        except (NotesClientError, OSError, ValueError, json.JSONDecodeError) as exc:
            from rich.markup import escape

            console.print(
                f"[yellow]  Warning: skipping '{escape(title)}' — {escape(str(exc))}[/yellow]"
            )
            continue

    if verbose:
        console.print(f"Found {len(titles)} note(s) in Apple Notes, {synced} unsynced:")
        for title, path, label in rows:
            if path:
                console.print(f"  → {title}  → {path}  [{label}]", markup=False)
            else:
                console.print(f"  → {title}  [{label}]", markup=False)

    return synced
