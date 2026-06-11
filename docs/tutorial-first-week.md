# Tutorial: Your First Week with Exercise Coach

You'll set up Exercise Coach, generate your first AI-powered workout plan, log a session,
and end the week with an automated assessment. By the end, you'll have a complete
coaching cycle running on your Mac — plans written to Apple Notes, data stored locally,
and weekly summaries carried forward automatically.

## What you'll need

- macOS 13+ (macOS 26+ recommended for on-device AI via Swift Foundation Models)
- [uv](https://docs.astral.sh/uv/) installed (`brew install uv`)
- Apple Notes open and signed in to iCloud
- An inference provider ready (Anthropic API key, Ollama, or Swift on macOS 26+)
- The Exercise Coach source code cloned locally

---

## Step 1: Install

From the project directory:

```bash
uv sync
```

This creates a `.venv` and installs all dependencies. Verify:

```bash
uv run coach --help
```

You should see a list of commands: `setup`, `plan`, `assess`, `log`, `report`, `status`.

---

## Step 2: Set up

Run the setup wizard:

```bash
uv run coach setup
```

You'll be asked:

- **Your name** — injected into prompts so the LLM addresses you personally
- **Training days per week** — guides plan volume
- **Primary goal** — `strength`, `endurance`, `general fitness`, etc.
- **Injuries / limitations** — passed as constraints to the planner (leave blank if none)

Setup also:
- Creates `config/config.toml` from the example
- Creates `data/workouts/`, `data/plans/`, `data/assessments/`
- Shows a provider availability table for your macOS version
- Creates the `Exercise Coach/Plans`, `Exercise Coach/Workouts`, and `Exercise Coach/Assessments` folders in Apple Notes

After setup, check that your inference provider shows as **ready**. If it doesn't, see
[How to configure inference providers](howto-configure-providers.md).

---

## Step 3: Describe your training

Open `data/training-info.md` (created automatically from the example). Edit it to describe:

- Your equipment and where you train
- Typical weekly schedule and time constraints
- Training history and current fitness level
- Any exercises or movements to avoid

This file is the coach's "context" — the richer it is, the more relevant your plans will be.
The example file includes strength, cardio, and mobility templates to show the expected format.

---

## Step 4: Generate your first plan

```bash
uv run coach plan
```

This targets **next Monday's week** by default. The coach:

1. Reads your training profile from `data/training-info.md`
2. Calls the LLM to produce a structured JSON plan
3. Writes a plan note to `Exercise Coach/Plans/` in Apple Notes
4. Creates individual workout notes in `Exercise Coach/Workouts/`
5. Saves local copies in `data/plans/` and `data/workouts/`

At the end, a table shows the week's sessions — days, titles, types, and planned durations.

Open Apple Notes and find the **Exercise Coach** folder. You should see the plan note and
individual workout notes already there.

---

## Step 5: Check your week

```bash
uv run coach status
```

Output: one line showing today's workout (or "Rest day") and how many sessions are
completed vs. planned this week.

```
Week 2026-W25 | Today: 2026-06-08 Strength — Upper Body (planned) | This week: 0/4 completed
```

Run this any time for a quick pulse check. No LLM call, no Notes access — reads local files only.

---

## Step 6: Complete a workout

Open the workout note in Apple Notes on your Mac or iPhone. In the **Completed** section,
fill in what you actually did. In **How It Went**, add your RPE (1–10), any personal
records, and notes on how the session felt.

```
## Completed
Bench Press: 4×5 @ 90 kg
Overhead Press: 3×8 @ 62.5 kg
Pull-ups: 3×8, 3×7, 3×6
Cable rows: 3×12 @ 55 kg

## How It Went
RPE 7. Bench felt strong — matched last week at same weight. Overhead was tough on the
3rd set. PR: OHP 62.5 kg × 8 reps.
```

For unplanned workouts (a spontaneous run, a class), log them directly:

```bash
uv run coach log
```

You'll be prompted for type, title, duration, and RPE.

---

## Step 7: Assess the week

At the end of the week (or Monday morning), run the assessment:

```bash
uv run coach assess
```

The coach reads each completed workout note, extracts metrics, and produces:

- RPE and duration summaries per session
- Personal records detected in the notes
- A written weekly summary
- **Next Week Notes** — coaching observations carried into the next plan

The assessment is saved to `Exercise Coach/Assessments/Assessment YYYY-Www` in Apple Notes
and locally to `data/assessments/`.

---

## Step 8: Generate next week's plan

The cycle repeats. Next week's plan automatically picks up the coaching context:

```bash
uv run coach plan
```

The planner reads the **Next Week Notes** from last week's assessment and uses them to
adjust focus, volume, and exercise selection.

---

## What you built

A complete personal coaching loop:

```
plan → complete workouts → assess → next plan
```

All your training data lives in Apple Notes (synced to iPhone via iCloud) and in local
Markdown files you can read and edit directly. The LLM never stores your data — it only
sees what you send it per request.

## Next steps

- Edit `data/training-info.md` regularly as your fitness changes
- Use `coach report` to see trends across weeks: `uv run coach report`
- Explore plan options: `uv run coach plan --focus deload` for a recovery week
- Read the [command reference](reference-commands.md) for all available options
