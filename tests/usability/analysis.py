"""Output collection and Markdown report generation for the 13-week simulation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coach.notes.parser import parse_front_matter, parse_sections


@dataclass
class WeekResult:
    week_num: int
    week_str: str
    focus: str
    volume: str
    theme: str
    n_completed_target: int
    n_sessions_planned: int
    plan_ok: bool
    assess_ok: bool
    status_ok: bool
    avg_rpe_extracted: float | None
    next_week_notes_len: int  # char count of next-week notes in assessment
    constraint_violations: list[str]
    extraction_failures: list[str]
    duplicate_files: list[str]  # filenames with doubled date prefix
    report_ran: bool  # whether the report command was executed for this week
    report_row_found: bool  # week appears in report summary output


class Collector:
    """Accumulates per-week simulation results."""

    def __init__(self) -> None:
        self.results: list[WeekResult] = []

    def record(
        self,
        week_num: int,
        week_str: str,
        focus: str,
        volume: str,
        theme: str,
        n_completed_target: int,
        plan_ok: bool,
        assess_ok: bool,
        status_ok: bool,
        workouts_dir: Path,
        assessments_dir: Path,
        report_output: str,
        report_ran: bool,
    ) -> None:
        assessment_path = assessments_dir / f"{week_str}.md"
        avg_rpe = _extract_avg_rpe(assessment_path)
        next_week_notes_len = _extract_next_week_notes_len(assessment_path)
        constraint_violations = _check_plan_constraints(workouts_dir, week_str)
        extraction_failures = _check_extraction_failures(assessment_path)
        duplicates = _find_duplicate_files(workouts_dir)
        n_sessions_planned = _count_week_files(workouts_dir, week_str)
        report_row_found = (not report_ran) or (week_str in report_output)

        self.results.append(
            WeekResult(
                week_num=week_num,
                week_str=week_str,
                focus=focus,
                volume=volume,
                theme=theme,
                n_completed_target=n_completed_target,
                n_sessions_planned=n_sessions_planned,
                plan_ok=plan_ok,
                assess_ok=assess_ok,
                status_ok=status_ok,
                avg_rpe_extracted=avg_rpe,
                next_week_notes_len=next_week_notes_len,
                constraint_violations=constraint_violations,
                extraction_failures=extraction_failures,
                duplicate_files=duplicates,
                report_ran=report_ran,
                report_row_found=report_row_found,
            )
        )

    def as_json(self) -> str:
        rows: list[dict[str, Any]] = []
        for r in self.results:
            rows.append(
                {
                    "week_num": r.week_num,
                    "week_str": r.week_str,
                    "focus": r.focus,
                    "volume": r.volume,
                    "theme": r.theme,
                    "n_completed_target": r.n_completed_target,
                    "n_sessions_planned": r.n_sessions_planned,
                    "plan_ok": r.plan_ok,
                    "assess_ok": r.assess_ok,
                    "status_ok": r.status_ok,
                    "avg_rpe_extracted": r.avg_rpe_extracted,
                    "next_week_notes_len": r.next_week_notes_len,
                    "constraint_violations": r.constraint_violations,
                    "extraction_failures": r.extraction_failures,
                    "duplicate_files": r.duplicate_files,
                    "report_ran": r.report_ran,
                    "report_row_found": r.report_row_found,
                }
            )
        return json.dumps(rows, indent=2)


def _extract_avg_rpe(assessment_path: Path) -> float | None:
    if not assessment_path.exists():
        return None
    try:
        fm = parse_front_matter(assessment_path.read_text())
        val = fm.get("avg_rpe")
        return float(str(val)) if val not in (None, "", "null") else None
    except Exception:
        return None


def _extract_next_week_notes_len(assessment_path: Path) -> int:
    if not assessment_path.exists():
        return 0
    try:
        sections = parse_sections(assessment_path.read_text())
        notes = sections.get("Next Week Notes", "")
        return len(notes.strip())
    except Exception:
        return 0


def _check_plan_constraints(workouts_dir: Path, week_str: str) -> list[str]:
    """Return list of constraint violations in the week's workout files."""
    import datetime

    year_str, w_str = week_str.split("-W")
    year, wnum = int(year_str), int(w_str)
    jan4 = datetime.date(year, 1, 4)
    monday = jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=wnum - 1)
    sunday = monday + datetime.timedelta(days=6)

    violations: list[str] = []
    if not workouts_dir.exists():
        return violations

    for path in sorted(workouts_dir.glob("*.md")):
        try:
            from coach.notes.parser import workout_from_note

            content = path.read_text()
            w = workout_from_note(content, path.stem)
            if not (monday <= w.date <= sunday):
                continue
            if w.duration_planned and w.duration_planned > 45:
                violations.append(
                    f"{path.name}: duration {w.duration_planned} min exceeds 45-min limit"
                )
            # Check planned content for equipment not in allowed list
            content_lower = (w.planned_content or "").lower()
            for disallowed in ("dumbbell", "cable", "machine", "kettlebell", "trap bar"):
                if disallowed in content_lower:
                    violations.append(
                        f"{path.name}: mentions '{disallowed}' — not in allowed equipment"
                    )
        except Exception:
            continue

    return violations


def _check_extraction_failures(assessment_path: Path) -> list[str]:
    """Return any notes about extraction quality in the assessment file."""
    if not assessment_path.exists():
        return ["Assessment file missing"]
    try:
        fm = parse_front_matter(assessment_path.read_text())
        failures: list[str] = []
        if fm.get("avg_rpe") in (None, "", "null"):
            failures.append("avg_rpe not extracted")
        if fm.get("completion_rate") in (None, "", "null"):
            failures.append("completion_rate missing")
        return failures
    except Exception:
        return ["Failed to parse assessment front matter"]


def _find_duplicate_files(workouts_dir: Path) -> list[str]:
    """Return filenames that have a doubled date prefix (assess bug artifact)."""
    if not workouts_dir.exists():
        return []
    # Pattern: YYYY-MM-DD-YYYY-MM-DD-*.md
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}-.*\.md$")
    return [p.name for p in workouts_dir.glob("*.md") if pattern.match(p.name)]


_DOUBLED_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}-")


def _count_week_files(workouts_dir: Path, week_str: str) -> int:
    """Count original (non-duplicated) workout files for the given ISO week."""
    import datetime

    if not workouts_dir.exists():
        return 0
    year_str, w_str = week_str.split("-W")
    year, wnum = int(year_str), int(w_str)
    jan4 = datetime.date(year, 1, 4)
    monday = jan4 - datetime.timedelta(days=jan4.weekday()) + datetime.timedelta(weeks=wnum - 1)
    sunday = monday + datetime.timedelta(days=6)

    count = 0
    for path in workouts_dir.glob("*.md"):
        if _DOUBLED_DATE_RE.match(path.name):
            continue  # skip assess-created duplicate files
        try:
            from coach.notes.parser import workout_from_note

            w = workout_from_note(path.read_text(), path.stem)
            if monday <= w.date <= sunday:
                count += 1
        except Exception:
            continue
    return count


def generate_report(collector: Collector) -> str:
    """Generate a human-readable Markdown analysis report."""
    results = collector.results
    total_weeks = len(results)

    plan_failures = [r for r in results if not r.plan_ok]
    assess_failures = [r for r in results if not r.assess_ok]
    status_failures = [r for r in results if not r.status_ok]
    all_violations: list[str] = [v for r in results for v in r.constraint_violations]
    all_ext_failures: list[str] = [f for r in results for f in r.extraction_failures]
    all_duplicates: list[str] = [d for r in results for d in r.duplicate_files]
    rpe_missing = [r for r in results if r.avg_rpe_extracted is None]
    notes_missing = [r for r in results if r.next_week_notes_len < 20]
    report_missing = [r for r in results if r.report_ran and not r.report_row_found]

    lines: list[str] = [
        "# 13-Week Usability Simulation Report",
        "",
        "## Simulation Overview",
        "",
        f"- **Weeks simulated**: {total_weeks}",
        "- **User persona**: Jason — 4 sessions/week, barbell + pull-up bar",
        "- **Completion arc**: base building → deload (W4) → progression → hard (W9) → maintenance → evaluation",
        "- **Completion rate**: 4/4 most weeks; 3/4 on W4, W9, W13",
        "",
        "## Week-by-Week Table",
        "",
        "| # | Week | Focus | Volume | Theme | Planned | Completed | RPE | Assessment | Notes Len | Plan | Assess | Status |",
        "|---|------|-------|--------|-------|---------|-----------|-----|------------|-----------|------|--------|--------|",
    ]

    for r in results:
        rpe_str = f"{r.avg_rpe_extracted:.1f}" if r.avg_rpe_extracted is not None else "—"
        plan_icon = "✓" if r.plan_ok else "✗"
        assess_icon = "✓" if r.assess_ok else "✗"
        status_icon = "✓" if r.status_ok else "✗"
        lines.append(
            f"| {r.week_num} | {r.week_str} | {r.focus} | {r.volume} | {r.theme} "
            f"| {r.n_sessions_planned} | {r.n_completed_target} "
            f"| {rpe_str} | {assess_icon} "
            f"| {r.next_week_notes_len} | {plan_icon} | {assess_icon} | {status_icon} |"
        )

    lines += [
        "",
        "## Command Reliability",
        "",
        f"- **Plan**: {total_weeks - len(plan_failures)}/{total_weeks} succeeded"
        + (f" — failures: {[r.week_str for r in plan_failures]}" if plan_failures else ""),
        f"- **Assess**: {total_weeks - len(assess_failures)}/{total_weeks} succeeded"
        + (f" — failures: {[r.week_str for r in assess_failures]}" if assess_failures else ""),
        f"- **Status**: {total_weeks - len(status_failures)}/{total_weeks} succeeded"
        + (f" — failures: {[r.week_str for r in status_failures]}" if status_failures else ""),
        f"- **Report**: ran for {sum(1 for r in results if r.report_ran)}/{total_weeks} weeks; "
        f"{total_weeks - len(report_missing)}/{total_weeks} weeks found in output",
        "",
        "## LLM Extraction Quality",
        "",
        f"- **RPE extracted**: {total_weeks - len(rpe_missing)}/{total_weeks} assessments",
        f"- **Extraction failures**: {len(all_ext_failures)} total",
    ]
    if all_ext_failures:
        for f in all_ext_failures[:10]:
            lines.append(f"  - {f}")

    lines += [
        "",
        "## Next-Week Notes Continuity",
        "",
        f"- **Non-empty next-week notes**: {total_weeks - len(notes_missing)}/{total_weeks}",
    ]
    if notes_missing:
        lines.append(
            f"- **Missing/short notes** (<20 chars): weeks {[r.week_str for r in notes_missing]}"
        )
    lines.append("- Next-week notes feed into the following week's plan prompt.")
    lines.append("  Gaps here reduce plan context quality.")

    lines += [
        "",
        "## Planning Constraint Check",
        "",
        f"- **Total violations detected**: {len(all_violations)}",
    ]
    if all_violations:
        for v in all_violations[:15]:
            lines.append(f"  - {v}")
    else:
        lines.append("- No duration or equipment violations found.")

    lines += [
        "",
        "## Duplicate File Detection",
        "",
        f"- **Duplicate files found**: {len(set(all_duplicates))}",
    ]
    if all_duplicates:
        unique_dups = sorted(set(all_duplicates))
        lines.append(
            "- **Root cause**: `_write_local_workout` uses `safe_slug(note_title)` where `note_title`"
            " already contains the date prefix, resulting in filenames like "
            "`YYYY-MM-DD-YYYY-MM-DD-slug.md` alongside the original `YYYY-MM-DD-slug.md`."
        )
        lines.append(
            "- **Impact**: History summary and report see duplicate workout entries per week."
        )
        for d in unique_dups[:5]:
            lines.append(f"  - `{d}`")
        if len(unique_dups) > 5:
            lines.append(f"  - ... and {len(unique_dups) - 5} more")

    lines += [
        "",
        "## Identified Gaps",
        "",
        "The following issues were surfaced by the simulation:",
        "",
    ]

    gaps: list[str] = []
    if all_duplicates:
        gaps.append(
            "**[BUG] Duplicate workout files after `assess`**: `_write_local_workout` "
            "slugs from `note_title` (which includes the date), creating `YYYY-MM-DD-YYYY-MM-DD-slug.md` "
            "instead of updating the original plan-generated file. Fix: strip date prefix from note_title "
            "in `_write_local_workout` before slugging."
        )
    if rpe_missing:
        gaps.append(
            f"**[QUALITY] RPE not extracted** in {len(rpe_missing)} assessment(s): "
            f"weeks {[r.week_str for r in rpe_missing]}. Check LLM extraction prompt."
        )
    if notes_missing:
        gaps.append(
            f"**[QUALITY] Short next-week notes** ({len(notes_missing)} weeks): "
            "Notes under 20 chars provide insufficient context for subsequent plan generation."
        )
    if all_violations:
        gaps.append(
            f"**[CONSTRAINT] Plan violations**: {len(all_violations)} duration or equipment issues "
            "detected in generated workout files. Correction pass may not fully enforce constraints."
        )
    if report_missing:
        gaps.append(
            f"**[REPORT] Missing weeks in report**: {[r.week_str for r in report_missing]} "
            "did not appear in `report summary` output."
        )
    if not gaps:
        gaps.append("No gaps identified in this simulation run.")

    for g in gaps:
        lines.append(f"- {g}")

    lines += ["", "---", "*Generated by 13-week usability simulation.*"]
    return "\n".join(lines)
