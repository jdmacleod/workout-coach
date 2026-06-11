# Command Reference

Exercise Coach CLI — complete reference for every command and flag.

> **First time?** Run `coach setup` before anything else. It creates `config/config.toml`,
> the data directories, and the Apple Notes folder structure that all other commands depend on.

All commands follow the pattern `coach <command> [options]`. Run `coach --help` or
`coach <command> --help` for inline help at any time.

---

## coach setup

First-time initialization. Creates the config file, data directories, and Apple Notes
folder structure. Safe to re-run with `--reset`.

```
coach setup [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--non-interactive` | `false` | Skip the questionnaire; use `config.toml` as-is |
| `--reset` | `false` | Re-run setup even if already configured |

**What setup does:**

1. Copies `config/config.example.toml` → `config/config.toml` (if not present)
2. Creates `data/workouts/`, `data/plans/`, `data/assessments/`
3. Runs an interactive questionnaire to populate your name, training days, goal, and injuries
4. Shows a provider availability table for your macOS version
5. Creates `Exercise Coach/Plans`, `Exercise Coach/Workouts`, `Exercise Coach/Assessments` folders in Apple Notes

**Requires:** Apple Notes running and configured.

**Example:**

```bash
uv run coach setup
uv run coach setup --reset   # reconfigure from scratch
```

---

## coach plan

Generate a weekly workout plan. Calls the configured LLM provider, writes the plan as
an Apple Note, and saves a local copy in `data/plans/`.

```
coach plan [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--week YYYY-Www` | next Monday's ISO week | Target week (e.g. `2026-W25`) |
| `--focus TYPE` | from LLM | Override training focus: `strength`, `cardio`, `deload`, `recovery` |
| `--dry-run` | `false` | Print the plan without writing to Notes or disk |
| `--overwrite` | `false` | Replace an existing plan for the target week |
| `--no-calendar` | `false` | Skip calendar source queries |

**Behavior:**

- Reads `data/training-info.md` for your training profile (copies example if missing)
- Loads the prior week's "Next Week Notes" from Apple Notes (carries coaching context forward)
- Reads the last 4 weeks of local workout files to build a history summary
- Calls the LLM once; retries once on JSON parse failure
- Writes local files **first**, then Apple Notes (recovery: `--overwrite` re-pushes without re-calling LLM)

**Example:**

```bash
uv run coach plan
uv run coach plan --week 2026-W26 --focus deload
uv run coach plan --dry-run
uv run coach plan --overwrite   # re-push existing local plan to Notes
```

---

## coach assess

Parse completed workout notes, extract metrics with the LLM, and generate a weekly
assessment with Next Week Notes.

```
coach assess [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--workout TITLE` | none | Assess a single note by its exact title |
| `--week YYYY-Www` | current ISO week | Target week |
| `--dry-run` | `false` | Print extracted metrics without writing |

**Behavior:**

- Reads workout notes from `Exercise Coach/Workouts` in Apple Notes for the target week
- Calls the LLM to extract RPE, PRs, and a written summary for each completed workout
- Generates a weekly summary and Next Week Notes
- Writes the assessment to `Exercise Coach/Assessments/Assessment YYYY-Www` and locally to `data/assessments/`

**Example:**

```bash
uv run coach assess                      # assess current week
uv run coach assess --week 2026-W24
uv run coach assess --workout "2026-06-09 Strength — Upper Body"
uv run coach assess --dry-run
```

---

## coach log

Quick interactive entry for ad hoc workouts not in the weekly plan. Prompts for type,
title, duration, RPE, and notes. Writes to Apple Notes and saves a local file.

```
coach log [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--date YYYY-MM-DD` | today | Date of workout |
| `--type TYPE` | prompted | Workout type: `strength`, `cardio`, `hiit`, `mobility`, `rest` |
| `--title TEXT` | prompted | Short title (e.g. "Upper Body", "Zone 2 Run") |

**Interactive prompts (if options not provided):**

- Workout type (default: `strength`)
- Short title
- Duration in minutes (optional)
- Brief description (optional)
- RPE 1–10 (optional)
- How did it go? (optional free text)

**Example:**

```bash
uv run coach log
uv run coach log --date 2026-06-10 --type cardio --title "Morning Run"
```

**After logging:** run `coach assess --workout "<title>"` to extract full metrics.

---

## coach report

Display workout trends and statistics. Reads local files only — no Apple Notes access required.

```
coach report [SUBCOMMAND] [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `SUBCOMMAND` | `summary` | One of: `summary`, `volume`, `rpe`, `prs`, `streak` |
| `--weeks N` | `8` | Lookback window in weeks |
| `--format FORMAT` | `table` | Output format: `table`, `json`, `csv` (`csv` supported for `summary` only) |
| `--type TYPE` | none | Filter by workout type (e.g. `strength`, `cardio`) |

### Subcommands

**summary** — Weekly breakdown: session count, completion rate, average RPE, total minutes, primary focus.

**volume** — Minutes per week, broken down by workout type (strength / cardio / hiit / mobility).

**rpe** — Per-session RPE trend in chronological order.

**prs** — Personal records. Requires prior `coach assess` runs to populate metrics.

**streak** — Current and longest consecutive-day training streaks.

**Examples:**

```bash
uv run coach report                         # weekly summary, last 8 weeks
uv run coach report summary --weeks 12
uv run coach report volume --format json
uv run coach report rpe --type cardio
uv run coach report streak
```

---

## coach status

Week-at-a-glance summary. Reads local files only — no Apple Notes access, no LLM call.

```
coach status [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--week YYYY-Www` | current ISO week | Target week |

**Output:** one line — current week, today's workout (or "Rest day"), completed vs. total sessions this week.

**Example:**

```bash
uv run coach status
uv run coach status --week 2026-W24
```

---

## Common patterns

**First use:**

```bash
uv run coach setup
# edit data/training-info.md
uv run coach plan
```

**Weekly cycle:**

```bash
# Monday: generate the plan
uv run coach plan

# During the week: check in
uv run coach status

# After each workout: update the note in Apple Notes (or log ad hoc)
uv run coach log                           # for unplanned workouts

# Sunday/Monday: assess and carry forward
uv run coach assess
```

**Reporting:**

```bash
uv run coach report                        # quick weekly summary
uv run coach report volume --weeks 12     # 3-month volume trends
uv run coach report rpe --format csv > rpe.csv
```

## Related

- [Configuration reference](reference-config.md) — all `config.toml` settings
- [Tutorial: Your first week](tutorial-first-week.md) — end-to-end walkthrough
- [How-to: configure inference providers](howto-configure-providers.md)
