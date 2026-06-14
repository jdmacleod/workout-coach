# Changelog

All notable changes to Exercise Coach are documented here.

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
