# CLI Commands Specification

## Entry Point

The application is installed as the `coach` command via `pyproject.toml`:

```toml
[project.scripts]
coach = "coach.cli:app"
```

All commands are registered in `coach/cli.py` using Typer:

```python
import typer
from coach.commands import setup, plan, assess, log, report, status

app = typer.Typer(name="coach", help="Exercise Coach — Apple Notes fitness CLI")
app.add_typer(setup.app, name="setup")
app.command()(plan.run)
app.command()(assess.run)
app.command()(log.run)
app.command()(report.run)
app.command()(status.run)
```

---

## `coach setup`

**Purpose:** First-time initialization. Creates config, data directories, Notes folder
structure, and validates the configured inference provider.

**File:** `coach/commands/setup.py`

### Behavior (in order)

1. Detect project root; verify `config/config.example.toml` exists.
2. If `config/config.toml` does not exist, copy from example.
3. Create `data/workouts/`, `data/plans/`, `data/assessments/` if missing.
4. Interactive questionnaire (skippable with `--non-interactive`):
   - Name, timezone
   - Fitness level (beginner / intermediate / advanced)
   - Available days and session length constraints
   - Equipment available
   - Injury notes
   - Recurring external classes (day, time, type, duration)
5. Probe inference providers; display availability table; prompt user to select default.
6. If Swift provider selected: offer to build the binary.
7. If Google Calendar selected: run OAuth flow; save token to `config/google-token.json`.
8. Write user answers to `config/config.toml`.
9. Copy `data/examples/training-info.md` → `data/training-info.md` if not present.
10. Create Apple Notes folder structure via AppleScript:
    - `Exercise Coach`
    - `Exercise Coach/Plans`
    - `Exercise Coach/Workouts`
    - `Exercise Coach/Assessments`
    - Write `_Config` note from questionnaire answers.
11. Print next step: `edit data/training-info.md, then run: coach plan`

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--non-interactive` | bool | false | Skip questionnaire; use config.toml as-is |
| `--reset` | bool | false | Re-run setup even if already configured |

---

## `coach plan`

**Purpose:** Generate a weekly workout plan. Reads user config, training info, recent
history, and any external sessions for the target week. Writes a plan note to Apple
Notes and creates individual workout stub notes.

**File:** `coach/commands/plan.py`

### Behavior (in order)

1. Resolve target week (default: next Monday's ISO week).
2. Check for existing plan for that week; warn if found (use `--overwrite` to replace).
3. Read `data/training-info.md`. If absent, copy from `data/examples/training-info.md` and print: `"Copied example training-info.md to data/training-info.md. Edit it to match your training."` Read `_Config` note and `[profile]` config from Apple Notes. Read the most recent `Assessments/Assessment YYYY-Www` note from Apple Notes (the authoritative source); if found, extract the `## Next Week Notes` section and inject it as primary planning context into the prompt (before `## Training Philosophy`). If the Notes read fails, fall back to `data/assessments/YYYY-Www.md`.
4. Glob `data/workouts/*.md` for past 4 weeks; parse front matter for history context.
5. Collect external sessions for the target week from configured calendar sources.
6. Build planning prompt (see Inference Spec).
7. Call configured inference provider; parse structured plan from response. If `InferenceParseError`, exit before any writes.
8. **Write local files first** (minimizes partial-state on Apple Notes failure):
   - Write `data/workouts/YYYY-MM-DD-<slug>.md` for each session.
   - Write `data/plans/YYYY-Www.md`.
9. **Write to Apple Notes** (after all local files succeed):
   - For each session: render workout note and create in `Exercise Coach/Workouts/` via AppleScript.
   - Render weekly plan note; create in `Exercise Coach/Plans/`.
10. Print plan summary table to terminal.

**Recovery from partial Apple Notes failure:** If step 9 fails mid-write, local files are intact. The user can re-run `coach plan --overwrite` to retry the Notes writes. On `--overwrite`, if a local plan file exists, skip the LLM call and re-push from local files to Notes.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--week` | str | next week | Target week in `YYYY-Www` format |
| `--focus` | str | auto | Override training focus: `strength \| cardio \| deload \| recovery` |
| `--dry-run` | bool | false | Print plan without writing to Notes or disk |
| `--overwrite` | bool | false | Replace existing plan for the target week |
| `--no-calendar` | bool | false | Skip calendar source queries |

### Planning Prompt Structure

```
SYSTEM:
You are a personal fitness coach. Generate a weekly workout plan as structured data.
Respond only with a JSON object matching the schema below. No preamble or explanation.

USER:
## User Profile
<_Config note content + profile.fitness_days_per_week + profile.primary_goal + profile.injury_notes>

## Next Week Notes (from last assessment — highest priority context)
<## Next Week Notes section from most recent assessment, or "(none yet — first week)" if absent>

## Training Philosophy and Example Workouts
<training-info.md content>

## Recent History (last 4 weeks)
<file-based summary: workout types, avg RPE, completion rate, volume>

## Fixed Sessions This Week (do not move or remove)
<ExternalSession list — day, time, type, duration, recovery_cost>

## Available Days
<days not occupied by external sessions or rest>

## Instructions
Generate a 7-day plan. For each day provide:
- type, subtype, duration_minutes, title, planned_content, rationale

Respect these constraints:
- No high-intensity session the day after recovery_cost >= 3
- At least 1 full rest day
- Total weekly load consistent with recent history (avoid sudden spikes)

## Response Schema
{
  "training_focus": string,
  "weekly_volume": "low|moderate|high",
  "generation_notes": string,
  "sessions": [
    {
      "day": "Mon|Tue|Wed|Thu|Fri|Sat|Sun",
      "type": string,
      "subtype": string,
      "duration_minutes": int,
      "title": string,
      "planned_content": string,
      "rationale": string
    }
  ]
}
```

---

## `coach assess`

**Purpose:** Parse completed workout notes, extract structured metrics via the
configured LLM, write extracted data back to notes, and generate a weekly assessment.

**File:** `coach/commands/assess.py`

### Behavior (in order)

1. Determine target scope: single workout, or full week.
2. Load workout notes from Apple Notes (or local files).
3. For each note where `status != planned`:
   a. Extract `## Completed` and `## How It Went` sections.
   b. If either section has content, run assessment prompt against configured provider.
   c. Parse JSON response: `{rpe, mood, soreness, duration_actual, prs, deviations, summary}`.
   d. Update front matter fields in the note (`status: completed`, `rpe`, `mood`, etc.).
   e. Write updated note back to Apple Notes via AppleScript.
4. If assessing a full week:
   a. Aggregate metrics from all sessions.
   b. Generate weekly narrative via LLM.
   c. Write a "Next Week Notes" carry-forward paragraph: 1-3 sentences in plain English, no headers or bullets. Focus on fatigue level, injuries noted, whether a deload is needed, and any volume targets. Example: *"Good strength week but fatigue is building. Recommend deloading Friday and keeping Saturday light. Upper body volume was too high — cap at 3 sets per lift next week."* Append as `## Next Week Notes` section to the Assessment note.

**`coach plan` injection contract:** If the `## Next Week Notes` section exists and is non-empty after `.strip()`, inject as-is as `{next_week_notes}` in the planning prompt. If empty or missing (e.g. first week), substitute `"(none yet — first week)"`.
   d. Create/update `Assessments/Assessment YYYY-Www` note.
   e. Write `data/assessments/YYYY-Www.md`.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--workout` | str | none | Assess a single note by title |
| `--week` | str | current week | Target week in `YYYY-Www` format |
| `--dry-run` | bool | false | Print extracted data without writing |

### Assessment Prompt Structure

```
SYSTEM:
You are a fitness coach reviewing a completed workout log.
Extract structured data from the log and return only a JSON object. No preamble.

USER:
## Workout Metadata
type: strength, subtype: upper, duration_planned: 50 min

## Completed Section
<## Completed content from note>

## How It Went
<## How It Went content from note>

## Response Schema
{
  "status": "completed|skipped",
  "duration_actual": int_or_null,
  "rpe": float_1_to_10_or_null,
  "mood": "great|good|neutral|tired|bad|null",
  "soreness": "none|mild|moderate|high|null",
  "prs": [{"exercise": string, "value": string}],
  "deviations": [string],
  "summary": string
}
```

---

## `coach log`

**Purpose:** Quick interactive entry for ad hoc workouts not in the weekly plan.

**File:** `coach/commands/log.py`

### Behavior

1. Prompt for: date (default today), type, title, duration, brief description.
2. Optionally prompt for immediate post-workout notes (RPE, how it went).
3. Create workout note in Apple Notes and write to `data/workouts/`.
4. Print note title; suggest `coach assess --workout <title>` for full extraction.

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--date` | str | today | Date of workout `YYYY-MM-DD` |
| `--type` | str | prompted | Workout type |
| `--title` | str | prompted | Short title |

---

## `coach status`

**Purpose:** Week-at-a-glance summary. Reads local files only; no Apple Notes access required.

**File:** `coach/commands/status.py`

### Behavior (in order)

1. Determine current ISO week using `datetime.date.today().isocalendar()`.
2. Glob `data/plans/YYYY-Www.md` for the current week. If not found: print `"No plan for current week. Run \`coach plan\` to generate one."` and exit 0.
3. Glob `data/workouts/YYYY-MM-DD-*.md` for the current week; parse front matter `status` field for each.
4. Find today's workout(s) by matching the filename date to today's date.
5. Print one-line summary to stdout.

### Output format

```
Week 2026-W23 | Today: Strength — Upper Body (planned) | This week: 2/5 completed
```

Edge cases:
- Rest day (no workout file for today): `Today: Rest day`
- Multiple sessions today: show first with `status: planned` or `status != completed`
- No session today: `Today: No session scheduled`

### Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--week` | str | current week | Target week in `YYYY-Www` format |

---

## `coach report`

**Purpose:** Read workout and plan markdown files and display trends. No Apple Notes access required.

**File:** `coach/commands/report.py`

### Output Modes

| Subcommand | Description |
|---|---|
| `coach report summary` | Weekly completion rates, avg RPE, volume — last N weeks |
| `coach report volume` | Total duration and session count by week and type |
| `coach report rpe` | RPE trend over time |
| `coach report prs` | Personal record log |
| `coach report streak` | Current and longest training streaks |

### Options (global)

| Flag | Type | Default | Description |
|---|---|---|---|
| `--weeks` | int | 8 | Lookback window |
| `--format` | str | table | Output format: `table \| json \| csv` |
| `--type` | str | all | Filter by workout type |

### Example Output (`coach report summary --weeks 4`)

```
Week       Sessions  Completed  Avg RPE  Total Min  Focus
─────────────────────────────────────────────────────────
2025-W20   6         5 (83%)    6.4      265        strength
2025-W21   6         6 (100%)   7.1      310        strength
2025-W22   5         4 (80%)    5.9      220        deload
2025-W23   6         5 (83%)    6.8      285        strength
```

---

## Error Handling Standards

All commands follow this pattern:

```python
import typer
from rich.console import Console

console = Console()
err_console = Console(stderr=True, style="bold red")

def run(...):
    try:
        ...
    except NotesClientError as e:
        err_console.print(f"Apple Notes error: {e}")
        err_console.print("Is Notes running? Try opening Notes.app and retrying.")
        raise typer.Exit(code=1)
    except InferenceError as e:
        err_console.print(f"Inference error: {e}")
        err_console.print("Run 'coach setup' to check provider availability.")
        raise typer.Exit(code=1)
    except ConfigNotFoundError:
        err_console.print("No config found. Run 'coach setup' first.")
        raise typer.Exit(code=1)
```

Exit codes:
- `0` — success
- `1` — recoverable error (config missing, provider down)
- `2` — unrecoverable error (data corruption, unexpected exception)
