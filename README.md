# Exercise Coach

[![CI](https://github.com/jdmacleod/workout-coach/actions/workflows/ci.yml/badge.svg)](https://github.com/jdmacleod/workout-coach/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jdmacleod/workout-coach/graph/badge.svg)](https://codecov.io/gh/jdmacleod/workout-coach)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An Apple Notes-based fitness coaching CLI for macOS. Generates weekly workout plans,
logs sessions, and produces weekly assessments — all using a configurable LLM running
on-device or via API. Plans and workouts sync to your iPhone automatically through iCloud.

```
coach setup                   # run this first — creates config and Notes folders
coach plan                    # generate next week's plan → writes to Apple Notes
coach status                  # today's workout + week completion
coach assess                  # assess completed workouts → produces weekly summary
coach report                  # trends: volume, RPE, streaks
```

---

## Requirements

- macOS 13 or later
- Apple Notes (iCloud account)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for environment management
- One inference provider:
  - **Swift Foundation Models** (macOS 26+, on-device, recommended)
  - **Ollama** (local, any macOS) — `brew install ollama`
  - **Anthropic API** (cloud, any macOS) — requires `ANTHROPIC_API_KEY`

---

## Installation

```bash
git clone https://github.com/jdmacleod/workout-coach.git
cd workout-coach
uv sync
```

Verify:

```bash
uv run coach --help
```

---

## Quick start

**1. Initialize:**

```bash
uv run coach setup
```

Answers 6 questions (name, training days, goal, injuries, available equipment, session
duration), creates `config/config.toml`, sets up Apple Notes folders, and bootstraps
the exercise library at `data/exercise-library/`.

**2. Describe your training:**

Edit `data/training-info.md` — your equipment, schedule, training history. This is the
coach's context for every plan it generates.

**3. Generate your first plan:**

```bash
uv run coach plan
```

Creates a week of workout notes in Apple Notes and local copies in `data/plans/` and `data/workouts/`.

**4. Complete workouts, then assess:**

Fill in the **Completed** and **How It Went** sections of each workout note in Apple Notes
(on Mac or iPhone). At the end of the week:

```bash
uv run coach assess
```

The assessment extracts metrics, detects PRs, and writes **Next Week Notes** that are
automatically picked up by the next `coach plan`.

---

## Commands

| Command | Description |
|---|---|
| `coach setup` | First-time init: config, data dirs, Notes folders |
| `coach plan` | Generate a weekly workout plan (writes to Notes + local) |
| `coach assess` | Parse completed workouts, extract metrics, write assessment |
| `coach log` | Quick interactive entry for unplanned workouts |
| `coach report [summary\|volume\|rpe\|prs\|streak]` | Trends and statistics from local files |
| `coach status` | Week-at-a-glance: today's workout, completion count |

Run `coach <command> --help` for full options on any command.

---

## Inference providers

`config/config.toml` is created by `coach setup`. Configure the LLM provider there:

```toml
[llm]
provider = "swift"          # swift | apple | ollama | llamacpp | anthropic
```

| Provider | macOS | Notes |
|---|---|---|
| `swift` | 26+ | On-device Foundation Models. Build: `make -C swift build` |
| `apple` | 26+ | Apple Intelligence via Shortcuts.app |
| `ollama` | 13+ | Local LLM server. `brew install ollama && ollama pull llama3.2` |
| `llamacpp` | 13+ | llama.cpp OpenAI-compatible server |
| `anthropic` | 13+ | Anthropic API. Set `ANTHROPIC_API_KEY` env var. |

Run `coach setup` at any time to see provider availability for your system.

---

## Data layout

```
config/
  config.example.toml   — copy to config.toml and edit
  config.toml           — your config (gitignored)

data/
  training-info.md      — your training profile (edit freely)
  exercise-library/     — exercise library (bootstrapped by setup, add your own)
  workouts/             — local copies of workout notes (gitignored)
  plans/                — local copies of weekly plans (gitignored)
  assessments/          — local copies of assessments (gitignored)
  examples/             — sample notes shipped with the repo
```

Apple Notes folder structure (created by `coach setup`):

```
Exercise Coach/
  Plans/                — weekly plan notes
  Workouts/             — individual session notes
  Assessments/          — weekly assessment notes
```

---

## Weekly cycle

```
Monday   →  coach plan        (generates the week's workouts in Notes)
Mon–Sun  →  complete workouts (fill in notes on Mac or iPhone)
Sunday   →  coach assess      (extracts metrics, writes Next Week Notes)
Monday   →  coach plan        (picks up last week's coaching notes automatically)
```

---

## Documentation

- [Tutorial: Your first week](docs/tutorial-first-week.md)
- [How to configure inference providers](docs/howto-configure-providers.md)
- [Command reference](docs/reference-commands.md)
- [Configuration reference](docs/reference-config.md)

---

## Development

```bash
uv sync                                             # install all deps
uv run pytest tests/ -m "not integration and not usability and not usability_live"  # unit tests
uv run ruff check coach/ tests/ && uv run ruff format coach/ tests/ && uv run mypy coach/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full dev setup.

---

## License

MIT — see [LICENSE](LICENSE).
