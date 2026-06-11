# Changelog

All notable changes to Exercise Coach are documented here.

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
