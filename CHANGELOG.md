# Changelog

All notable changes to Exercise Coach are documented here.

## [0.6.0] — 2026-06-14

### Added

- **Workout variation engine** — `coach plan` now rotates exercises week-to-week via three mechanisms: an exercise library sampler, a periodization directive, and progressive overload hints extracted from your completed workout history.
- **Exercise library** (`data/exercise-library/`) — 34 exercises across 6 categories (strength-push, strength-pull, strength-lower, cardio, HIIT, mobility). Each file has equipment tags, sets/reps prescriptions, cues, and progressions. `coach setup` bootstraps the library on first run. Add your own exercises in any category.
- **ISO-week seeding** — the same week always samples the same exercises from the library. Different weeks rotate automatically. Adding new exercise files redistributes across future weeks with no config needed.
- **Equipment-aware filtering** — exercises are filtered by your `available_equipment` before sampling. ALL equipment tags on a file must match (e.g. an exercise requiring `[barbell, bumper_plates]` is skipped if you only have `[barbell]`). Bodyweight exercises (empty tag list) always appear.
- **Periodization directives** — after 4+ consistent training weeks, the prompt receives a progressive overload suggestion. After 3+ weeks with avg RPE ≥ 8.0, it receives a volume-reduction note. These are suppressed if the prior week's assessment already addresses the topic.
- **Deload signal** — if the last 2 weeks average RPE ≥ 8.5 across 3+ sessions, a deload recommendation is injected into the planning context.
- **Progressive overload hints** — `parse_exercise_sets()` scans your completed workout sections for load data. Exercises that reached a new personal best get a "+2.5 kg" hint in the planning context.
- **`ExerciseSet` dataclass and `parse_exercise_sets()`** — new structured parser in `coach/notes/parser.py` that extracts exercise name, sets, reps, and load from free-form completed-workout sections (e.g. `- Floor Press: 4x5 @ 62.5kg`).
- **`exercise_library` config field** — `[data]` section gains `exercise_library` pointing to the library directory (default `data/exercise-library/`).
- **Ollama context window discovery** — `OllamaProvider` now reads the native context ceiling from `/api/tags` on startup and clamps `num_ctx` to that ceiling. Raises `InferenceError` when the prompt fills the context window (silent truncation detected post-response). Default `num_ctx` raised from 2048 → 8192.
- **Ollama JSON format mode** — structured inference calls (plan/assess) now use `format: "json"` for more reliable JSON output.

### Changed

- `coach plan` loads workout history once via `_load_recent_workouts()` and delegates `_load_history_summary()` to it. Prior implementation globbed the workouts directory twice.

### For contributors

- New `tests/commands/test_plan_variation.py` — 28 test cases covering all variation engine functions.
- New `parse_exercise_sets` cases in `tests/notes/test_parser.py`.
- Exercise library format documented in `data/examples/exercise-library/CONTRIBUTING.md`.

## [0.4.1] — 2026-06-13

### Added

- **Equipment and session duration in setup** — `coach setup` now asks for your available equipment (e.g. `barbell, pull-up bar`) and maximum session duration (in minutes). Both are written to `[profile]` in `config.toml` and carried forward as hard constraints for every plan.
- **Plan constraint enforcement with self-correction pass** — `coach plan` now injects `available_equipment` and `max_session_duration_minutes` as explicit constraints into the planning prompt. If the LLM generates exercises requiring equipment you don't have, or sessions that exceed your time budget, a self-correction pass fires automatically before the plan is written.
- **Web search for exercise research on the Swift provider** — when `available_equipment` is non-empty and the `swift` provider is active, `coach plan` runs a pre-plan web search phase. The on-device model uses a `WebSearchTool` to look up exercises and example workouts matching your exact equipment before generating the plan JSON. Providers tried in order: Brave Search → Exa → Tavily → DuckDuckGo (free fallback). Configure API keys in `[search]` in `config.toml`.

### For contributors

- New `search` pytest marker for external API smoke tests (`uv run pytest tests/ -m search -v`). Keyed providers (Brave, Exa, Tavily) skip automatically when no key is configured; DuckDuckGo always runs.
- Fixed DuckDuckGo `no_redirect=1` parameter missing from both Swift and Python implementations.

## [0.4.0] — 2026-06-12

### Added

- **Clickable note-to-note links in plan note** — workout titles in the weekly schedule are now `applenotes://` hyperlinks that open the corresponding workout note directly. Numeric IDs always work; stable iCloud UUIDs are used when Full Disk Access is granted to Terminal. Configurable via `plan_note_links` in `[notes]` (default `true`); the `coach setup` questionnaire also sets this.

### Fixed

- **Workout section bullet formatting** — items under `Main Lifts:` and `Accessories:` are now consistently formatted as list entries. Previously the LLM would bullet only the first item and leave the rest as plain text.
- **Notes: line not bulleted** — the trailing `Notes:` line (coaching cues) after the Accessories section is now rendered as a plain line, not a list entry.

## [0.1.0] — 2026-06-10

Initial release of Exercise Coach v0.1 — an Apple Notes-based macOS fitness coaching CLI.

### Added

**Core commands**
- `coach plan` — generate a weekly workout plan via LLM, write to Apple Notes and local files
- `coach assess` — parse completed workout notes, extract metrics, produce weekly assessment with Next Week Notes
- `coach log` — quick ad hoc workout entry (interactive prompts)
- `coach report` — workout trends and statistics (summary / volume / rpe / prs / streak subcommands)
- `coach status` — week-at-a-glance from local files (no Apple Notes required)
- `coach setup` — first-time initialization: config, data directories, Apple Notes folder structure

**Intelligence providers**
- Swift Foundation Models (macOS 26+, local, private)
- Apple Intelligence via Shortcuts (macOS 26+)
- Anthropic Claude API (cloud fallback, requires `ANTHROPIC_API_KEY`)
- Ollama (local LLM server)
- llama.cpp server

**Apple Notes bridge**
- Full AppleScript bridge with 30 s timeout and structured error types
- HTML stripping for note bodies returned by Notes.app
- Front-matter parser and section parser for workout/plan/assessment notes

**Data model**
- `Workout` dataclass — type, status, RPE, duration, tags, planned/completed/reflection content
- `WeeklyPlan` dataclass — workouts list, training focus, volume, generation notes
- Note rendering and round-trip parsing for all note types

**Write ordering**
- Local files written first, then Apple Notes — recovery via `--overwrite` if Notes write fails
- `coach plan --overwrite` re-pushes an existing local plan to Notes without re-calling the LLM

**Testing**
- 32 unit tests; 0 integration tests (integration tests require a live Notes.app)
- `MockNotesClient` and `MockInferenceProvider` for fully offline testing
- Injectable `notes_client` / `inference_provider` parameters on all core functions

**Toolchain**
- `uv` for environment and dependency management (`uv sync`, `uv add`, `uv run`)
- `ruff` for linting and formatting (rules: E, W, F, I, UP, B, SIM)
- `mypy` with `strict = true` for type checking
- All three pass clean on every commit
