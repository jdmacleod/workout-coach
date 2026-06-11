# Implementation Guide & Build Order

## Purpose of This Document

This document is the primary handoff guide for implementation. It defines the
recommended build order, the acceptance criteria for each phase, and the
conventions Claude Code should follow throughout.

---

## Conventions

### Python style
- Python 3.12+. Use `match` statements, `X | Y` union types, `tomllib`.
- Type hints on all public functions and class methods.
- Dataclasses for data containers; no Pydantic (keeps dependencies minimal).
- `ruff` for linting and formatting. Line length: 100.
- `mypy --strict` should pass on all source files.

### Error handling
- Define domain exceptions in `exceptions.py` per subsystem.
- Never silence exceptions silently. Log or re-raise.
- All CLI commands catch domain exceptions and exit with code 1 + human message.
- `--dry-run` flags must never write to Notes, disk, or the index.

### Testing
- Unit tests in `tests/`. Mirror source structure.
- `MockNotesClient` injected for all command tests.
- Integration tests (require live Notes.app) marked `@pytest.mark.integration`.
- No integration tests run in CI. Unit tests must cover all logic paths.
- Target: unit tests pass with `pytest -m "not integration"`.

### AppleScript
- All scripts defined as module-level string constants in the file that uses them.
- Escape helper `_escape_for_applescript(text)` used for all user-supplied strings.
- Timeout: 30 seconds on all `osascript` calls.

### Commit style
- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`
- Each phase below should produce at least one commit per bullet.

---

## Build Order

### Phase 1 — Project Skeleton

**Goal:** Installable package with a working `coach` command that prints help.

- [ ] Create directory structure per `01-repository-structure.md`
- [ ] Write `pyproject.toml` with all dependencies and the `coach` entry point
- [ ] Write `coach/cli.py` with Typer app and stub command registration
- [ ] Write `coach/config.py` with `Config` dataclasses and `load_config()`
- [ ] Write `config/config.example.toml` (full contents per `07-configuration.md`)
- [ ] Write `.gitignore` (per `01-repository-structure.md`)
- [ ] Write `data/examples/training-info.md`
- [ ] Write `data/examples/workouts/*.md` (5 example files)
- [ ] Write `data/examples/plans/week-example.md`
- [ ] Verify: `pip install -e .` succeeds; `coach --help` prints command list

**Acceptance:** `coach --help` shows all commands. No import errors.

---

### Phase 2 — Notes Bridge

**Goal:** Python can create, read, update, and list notes in Apple Notes.

**Files:** `coach/notes/client.py`, `coach/notes/exceptions.py`, `coach/notes/schema.py`

- [ ] Implement `_run_applescript(script)` with timeout and error handling
- [ ] Implement `_escape_for_applescript(text)` 
- [ ] Implement `_strip_html(html)` for Notes body content
- [ ] Implement `NotesClient` with all methods per `04-notes-bridge.md`
- [ ] Implement `MockNotesClient` in `tests/notes/mock_client.py`
- [ ] Write unit tests for `_escape_for_applescript` and `_strip_html`
- [ ] Write integration test: create note, read it back, assert content matches
- [ ] Define note title schema constants in `schema.py`

**Acceptance:** Integration test creates a note titled `Test — Exercise Coach`
in a `Test` folder, reads it back, and asserts the body matches. Test is marked
`@pytest.mark.integration` and excluded from CI.

---

### Phase 3 — Data Models & Parser

**Goal:** Note content can be round-tripped through parser without data loss.

**Files:** `coach/models/*.py`, `coach/notes/parser.py`

- [ ] Implement `Workout`, `WeeklyPlan`, `ExternalSession`, `Metric` dataclasses
- [ ] Implement `parse_front_matter(content)` — handles missing fields gracefully
- [ ] Implement `parse_sections(content)` — splits on `##` headers
- [ ] Implement `render_workout_note(workout)` — produces valid front matter + body
- [ ] Implement `render_plan_note(plan)` — produces table + front matter
- [ ] Implement `workout_from_note(content, title)` — full round-trip
- [ ] Unit tests: parse known fixture strings; render and re-parse; assert equality
- [ ] Unit tests: front matter with missing optional fields does not raise

**Acceptance:** `workout_from_note(render_workout_note(workout), title)` produces
an equal `Workout` for all fields. Parser handles empty `## Completed` gracefully.

---

---

### Phase 4 — Swift Inference Binary + Providers

**Goal:** The `coach-infer` Swift binary compiles and returns a valid JSON response;
the Python `SwiftInferenceProvider` calls it and returns a string. All other providers
are implemented as fallbacks.

**Files:** `swift/Package.swift`, `swift/Sources/CoachInfer/main.swift`,
`coach/intelligence/provider.py`, `coach/intelligence/providers/*.py`,
`coach/intelligence/prompts.py`, `coach/intelligence/exceptions.py`

**Swift binary (build first — required for acceptance):**
- [ ] Write `swift/Package.swift` with macOS 26 platform target (per `05-inference-providers.md`)
- [ ] Write `swift/Sources/CoachInfer/main.swift` — reads JSON from stdin, calls `LanguageModelSession`, writes JSON to stdout
- [ ] Build: `cd swift && swift build -c release` — confirm binary at `swift/.build/release/CoachInfer`
- [ ] Smoke test: `echo '{"system":"You are a coach.","user":"Say hi.","max_tokens":20}' | swift/.build/release/CoachInfer` returns `{"text":"...","model":"apple/on-device"}`

**Python provider layer:**
- [ ] Implement `InferenceRequest`, `InferenceResponse`, `InferenceProvider` ABC
- [ ] Implement `get_provider(config)` factory
- [ ] Implement `SwiftInferenceProvider` — calls `coach-infer` binary via subprocess; `is_available()` checks macOS 26+ via `platform.mac_ver()` AND binary path exists
- [ ] If Swift provider is configured but binary is missing or macOS < 26, emit a clear error message and exit 1 (do not silently fall through)
- [ ] Implement `AnthropicProvider` — primary cloud fallback
- [ ] Implement `OllamaProvider` — local fallback
- [ ] Implement `LlamaCppProvider` (shares base with Ollama)
- [ ] Implement `AppleIntelligenceProvider` (shortcuts subprocess)
- [ ] Implement `MockInferenceProvider` for testing — returns configurable fixed response
- [ ] Write all prompt templates in `prompts.py`
- [ ] JSON parse retry logic: on `InferenceParseError`, retry once with correction prompt
- [ ] Unit tests: mock provider returns expected response; factory selects correct class
- [ ] Unit test: `get_provider()` with unknown provider name raises `ConfigError`
- [ ] Unit test: `get_provider()` with `is_available()` returning `False` raises `InferenceError`

**Acceptance:** On macOS 26+, `swift build` succeeds and `SwiftInferenceProvider.infer(InferenceRequest(system="...", user="..."))` returns a non-empty `InferenceResponse`. On macOS < 26, `SwiftInferenceProvider.is_available()` returns `False` without error.

---

### Phase 5 — `coach setup`

**Goal:** First-time setup creates config, data dirs, and Notes folder structure.

**Files:** `coach/commands/setup.py`

- [ ] Detect missing config; copy from example
- [ ] Create `data/workouts/`, `data/plans/`, `data/assessments/`
- [ ] Interactive questionnaire using `typer.prompt()`
- [ ] Detect macOS version via `platform.mac_ver()`:
  - macOS 26+: display "Swift Foundation Models (on-device)" as the recommended default; offer to build the binary now (`cd swift && swift build -c release`)
  - macOS < 26: skip Swift option; show Ollama and Anthropic as the available choices
- [ ] Provider availability check using `is_available()` on each provider class; display availability table
- [ ] If Swift selected and binary not yet built, run `swift build -c release` and confirm binary at configured path before writing config
- [ ] Notes folder creation via `NotesClient.ensure_folder()`
- [ ] Write `_Config` note from questionnaire answers
- [ ] Copy `data/examples/training-info.md` → `data/training-info.md` if absent
- [ ] `--non-interactive` flag skips questionnaire; defaults to `swift` provider on macOS 26+, `ollama` otherwise
- [ ] Unit tests with `MockNotesClient` and temp directory

**Acceptance:** Running `coach setup --non-interactive` against a fresh temp directory
creates all expected files and directories. `config/config.toml` exists and is valid TOML.
On macOS 26+, `config.toml` contains `provider = "swift"` and the binary path is populated.

---

### Phase 6 — `coach log`

**Goal:** Ad hoc workout logging. Enables real-data testing of the plan → workout → assess loop before full reporting is built.

**Files:** `coach/commands/log.py`

- [ ] Interactive prompts: date (default today), type, title, duration, brief description
- [ ] Optionally prompt for immediate post-workout notes (RPE, how it went)
- [ ] Create workout note in Apple Notes (`Exercise Coach/Workouts/`)
- [ ] Write `data/workouts/YYYY-MM-DD-<slug>.md`
- [ ] Print note title; suggest `coach assess --workout <title>` for full extraction
- [ ] Unit tests with `MockNotesClient`

**Acceptance:** `coach log --date 2026-06-09 --type strength --title "Upper Body"` creates a note in Apple Notes and a local markdown file with correctly formatted front matter.

---

### Phase 7 — `coach plan`

**Goal:** A weekly plan is generated and written to Notes and disk.

**Files:** `coach/commands/plan.py`

- [ ] Week resolution logic (`YYYY-Www` parsing, default to next week)
- [ ] Existing plan detection and `--overwrite` guard
- [ ] Read `_Training Info` note and `data/training-info.md`
- [ ] Read prior week's Assessment note (`Assessment YYYY-Www`) and extract `## Next Week Notes` section as carry-forward context; treat as empty string if no prior assessment exists
- [ ] Build 4-week history summary by globbing `data/workouts/*.md` and parsing front matter; handle empty/missing dir gracefully on first run
- [ ] Calendar source stub: skip if `calendar.enabled = false`
- [ ] Build and send planning prompt (include carry-forward context from Next Week Notes)
- [ ] Parse JSON response; handle `InferenceParseError`
- [ ] Render and create individual workout notes via `NotesClient`
- [ ] Write workout files to `data/workouts/`
- [ ] Render and create weekly plan note
- [ ] Write `data/plans/YYYY-Www.md`
- [ ] `--dry-run` prints plan table; writes nothing
- [ ] Unit tests with `MockNotesClient` and `MockInferenceProvider`

**Acceptance:** `coach plan --dry-run` prints a 7-day schedule table to the terminal.
`coach plan` (live) creates a plan note and 5–7 workout notes in Apple Notes.

---

### Phase 8 — `coach assess`

**Goal:** Completed workout notes are parsed and metrics are written back.

**Files:** `coach/commands/assess.py`

- [ ] Single workout mode (`--workout TITLE`)
- [ ] Week mode (`--week YYYY-Www`)
- [ ] Read `## Completed` and `## How It Went` sections
- [ ] Skip note if both sections are empty (warn, do not error)
- [ ] Send assessment prompt; parse JSON response
- [ ] Update note front matter with extracted fields (`status`, `rpe`, `mood`, `soreness`, `duration_actual`)
- [ ] Write updated note back via `NotesClient.update_note()`
- [ ] Write updated front matter to local `data/workouts/` file
- [ ] Weekly aggregate: compute completion rate, avg RPE from local workout files
- [ ] Generate weekly narrative via LLM
- [ ] Create/update assessment note (`Assessment YYYY-Www` in `Exercise Coach/Assessments/`)
- [ ] Write `data/assessments/YYYY-Www.md`
- [ ] **LLM writes `## Next Week Notes` section** in the Assessment note: a paragraph summarising patterns, flags, and recommendations for the following week's plan; `coach plan` reads this section as primary carry-forward context
- [ ] `--dry-run` prints extracted data and Next Week Notes content; writes nothing
- [ ] Unit tests with fixtures for completed and empty notes
- [ ] Unit test: `coach assess --week` with `MockNotesClient` + `MockInferenceProvider` produces an Assessment note body containing a non-empty `## Next Week Notes` section
- [ ] Integration test: `coach plan` with prior Assessment note containing `## Next Week Notes = "Focus on recovery"` → verify `MockInferenceProvider` received a prompt where `## Next Week Notes` section contains that text

**Acceptance:** Given a workout note with a filled `## How It Went` section,
`coach assess --workout <title> --dry-run` prints extracted RPE, mood, and summary.
`coach assess --week` creates an Assessment note with a populated `## Next Week Notes` section.

---

### Phase 9 — `coach report` and `coach status`

**Goal:** File-based reporting and week-at-a-glance status.

**Files:** `coach/commands/report.py`, `coach/commands/status.py`

- [ ] `coach report summary` — glob `data/workouts/*.md`, parse front matter, print table for last N weeks
- [ ] `coach report volume` — duration by type per week, parsed from workout files
- [ ] `coach report rpe` — RPE trend from workout file front matter
- [ ] `coach report streak` — current/longest streaks from workout files
- [ ] `--format json` and `--format csv` output modes
- [ ] Helper: `load_workouts(data_dir, weeks=8) -> list[Workout]` — glob + parse, shared by all report subcommands
- [ ] Unit tests for all report subcommands using fixture markdown files
- [ ] `coach status` full implementation: ISO week detection, glob `data/plans/YYYY-Www.md` and `data/workouts/*.md`, parse `status` front matter, output `Week YYYY-Www | Today: <session title> (planned) | This week: N/M completed`; if no plan: prompt to run `coach plan`

**Acceptance:** `coach report summary --weeks 4 --format table` prints a formatted
table by reading `data/workouts/*.md` directly. `coach report summary --format json`
outputs valid JSON. No database required. `coach status` prints a one-line summary
for the current ISO week without requiring Apple Notes access.

---

---

### Phase 10 — Calendar Integration

**Goal:** External sessions from Apple Calendar appear in plan as fixed blocks.

**Files:** `coach/calendar/source.py`, `coach/calendar/sources/*.py`

- [ ] `CalendarSource` ABC and `ExternalSession` normalization
- [ ] `ManualSource` — parse `## Recurring External Classes` section
- [ ] `AppleCalendarSource` — AppleScript event query
- [ ] `ICSSource` — local file and URL
- [ ] `GoogleCalendarSource` — API with OAuth (guarded by optional dependency)
- [ ] `classify_session()` keyword map
- [ ] `format_external_sessions()` for prompt injection
- [ ] Deduplication across sources
- [ ] Integration into `coach plan` — inject into prompt; render `⟳` in plan table
- [ ] `coach setup` calendar questionnaire section
- [ ] Unit tests: manual parser with fixture strings; classification map

**Acceptance:** With Apple Calendar synced and a yoga class on Tuesday,
`coach plan --dry-run` shows the yoga class as a fixed row in the plan table
with source `apple_calendar`.

---

### Phase 11 — Apple Shortcuts

**Goal:** Three Shortcuts are distributable and callable from Python.

**Files:** `shortcuts/*.shortcut`, `shortcuts/README.md`

- [ ] `EC-Generate.shortcut` — takes text input, passes through Apple Intelligence, returns text
- [ ] `EC-Assess.shortcut` — same pattern for assessment task
- [ ] `EC-Summarize.shortcut` — weekly narrative generation
- [ ] `EC-QuickLog.shortcut` — iOS shortcut for creating a minimal workout note
- [ ] `shortcuts/README.md` — import instructions, Shortcuts.app setup
- [ ] `AppleIntelligenceProvider.is_available()` — checks `shortcuts list` output
- [ ] Document in README that Shortcuts require macOS 15+ with Apple Intelligence enabled

**Acceptance:** After importing `EC-Assess.shortcut`, running
`shortcuts run EC-Assess --input-path -` with sample text returns a non-empty response.

---

## What to Build First

If starting from scratch with no existing files:

1. Phase 1 (skeleton) — gets the project installable
2. Phase 3 (models + parser) — pure Python, no external dependencies, good test coverage target
3. Phase 4 (Swift binary + providers) — build and smoke-test the Swift binary first, then the Python bridge; on macOS < 26, use Anthropic as a temporary stand-in to validate the inference pipeline while the Swift path is unavailable
4. Phase 2 (Notes bridge) — requires macOS; build last among core infrastructure
5. Phases 5–9 — commands in order; each depends on the phases above
   - Phase 6 (`coach log`) is deliberately placed before plan/assess to enable real-data testing of the core loop

Phases 10–11 are independent enhancements that can be built in any order after Phase 9.

---

## Files Claude Code Should Create First

In order:

1. `pyproject.toml`
2. `coach/__init__.py`, `coach/cli.py`
3. `coach/config.py`
4. `coach/models/workout.py`, `plan.py`, `session.py`, `metrics.py`
5. `coach/notes/exceptions.py`, `coach/notes/schema.py`
6. `coach/notes/parser.py`
7. `swift/Package.swift`, `swift/Sources/CoachInfer/main.swift` (build and smoke-test before writing the Python bridge)
8. `coach/intelligence/provider.py`, `coach/intelligence/exceptions.py`
9. `coach/intelligence/prompts.py`
10. `coach/intelligence/providers/swift.py` (primary — wraps the binary built in step 7)
11. `coach/intelligence/providers/anthropic.py`, `ollama.py`, `llamacpp.py`, `apple.py` (fallbacks)
12. `coach/notes/client.py` (AppleScript bridge; requires macOS)
13. `coach/commands/setup.py`
14. `coach/commands/log.py`
15. `coach/commands/plan.py`
16. `coach/commands/assess.py`
17. `coach/commands/report.py`, `coach/commands/status.py`
17. `shortcuts/` directory and README
18. `config/config.example.toml`, `data/examples/**`
19. `.gitignore`, `README.md`, `CONTRIBUTING.md`
