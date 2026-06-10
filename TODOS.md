# Exercise Coach — TODOS

Items deferred from v0.1. Each item includes context, motivation, and a starting point.

---

## T1 — Catch Anthropic SDK exceptions in AnthropicProvider.infer()
**Priority:** P2 | **Effort:** S (human: ~30min / CC: ~5min)

**What:** Add `try/except anthropic.APIError` (and subclasses `AuthenticationError`, `RateLimitError`) to `AnthropicProvider.infer()`. Re-raise as `InferenceError` with a user-readable message.

**Why:** Currently a bad API key or rate limit hit surfaces as an unhandled exception. User sees a Python traceback instead of "Inference error: invalid API key."

**Context:** `AnthropicProvider` is a fallback provider (user must have `ANTHROPIC_API_KEY` set). Error paths are less common than Swift provider failures, but the user experience is worse when they hit.

**Start:** `coach/intelligence/providers/anthropic.py` — wrap the `client.messages.create()` call.

**Depends on:** Nothing — isolated to one method.

---

## T2 — Handle malformed workout front matter gracefully
**Priority:** P2 | **Effort:** S (human: ~30min / CC: ~5min)

**What:** In `load_workouts()`, wrap YAML front matter parsing in try/except. Skip malformed files with a warning: `"Warning: skipping {filename} — invalid front matter"`.

**Why:** A single corrupted `.md` file currently crashes `coach report`, `coach plan`, and `coach status`. Since files are system-generated this is rare, but manual edits or disk corruption can produce invalid YAML.

**Context:** All file-based commands glob `data/workouts/*.md` and parse front matter. The shared `load_workouts()` helper is the right fix point.

**Start:** `coach/intelligence/load_workouts.py` (or wherever the helper lives).

**Depends on:** Nothing.

---

## T3 — iOS Quick Log Shortcut (EC-QuickLog)
**Priority:** P3 | **Effort:** M (human: ~2 days / CC: ~30min)

**What:** A Shortcuts workflow on iPhone that logs a workout in ~30 seconds from the Home Screen. Prompts for: type, title, duration, brief notes. Writes a workout `.md` file to `data/workouts/` via iCloud Drive.

**Why:** The biggest friction point in the plan → workout → assess loop is workout entry. A Home Screen widget or widget reduces it to 30 seconds. Post-workout logging is time-sensitive; the more friction, the more skipped entries.

**Context:** The file-based data design (`data/workouts/*.md`) makes this possible without a server. iCloud Drive sync can expose the directory to iOS. The Shortcut creates the markdown file directly; `coach assess` processes it on next run.

**Start:** Prototype the Shortcut on macOS Shortcuts first; test iCloud Drive write; then distribute as `.shortcut` file in `shortcuts/`.

**Depends on:** Stable `data/workouts/` format (v0.1 must ship first).

---

## T4 — launchd agent for automatic Monday morning plan generation
**Priority:** P3 | **Effort:** M (human: ~1 day / CC: ~20min)

**What:** A launchd agent plist that runs `coach plan` each Monday at 07:00. Requires a stable install path (not project-relative binary).

**Why:** The vision: plans appear in Notes before you've had coffee. Manual `coach plan` every Monday is friction. Automation closes the loop.

**Context:** Requires resolving the binary/install path first (T5 — pre-built binary or a proper `~/.local/` install path). The plist targets `/usr/local/bin/coach` or `~/.local/bin/coach`, not a cloned-repo path.

**Start:** Draft `LaunchAgents/com.exercise-coach.autoplan.plist`. Document in `docs/launchd-setup.md`.

**Depends on:** Stable install path (not `pip install -e .`); ideally after T5 ships.

---

## T5 — Pre-built CoachInfer binary in GitHub Releases (arm64 + x86_64)
**Priority:** P3 | **Effort:** M (human: ~2 days / CC: ~30min)

**What:** Build `CoachInfer` for arm64 and x86_64 in GitHub Actions on each release tag. Upload as release assets. `coach setup` downloads the appropriate binary instead of running `swift build`.

**Why:** The current install requires Xcode Command Line Tools + `swift build` (~5 minutes). A pre-built binary reduces setup to `pip install -e . && coach setup` with a ~5 second download. Dramatically better install UX for non-developers.

**Context:** The binary is pure Swift with no external dependencies (only FoundationModels framework). A CI build matrix (macOS 14 arm64, macOS 13 x86_64) produces two artifacts. `coach setup` checks architecture, downloads the right binary, makes it executable.

**Start:** Create `.github/workflows/release.yml` with `swift build -c release` for both targets. Add download logic to `coach/commands/setup.py`.

**Depends on:** v0.1 released first; stable CoachInfer interface.

---

## T6 — Optimize load_workouts() glob for large datasets
**Priority:** P3 | **Effort:** S (human: ~30min / CC: ~5min)

**What:** Instead of globbing `data/workouts/*.md` and filtering in Python by date, generate date-range glob patterns for only the N relevant weeks and glob those directly.

**Why:** After 2 years of training (~100+ files), `coach plan` reads and parses all workout files just to filter to the last 4 weeks. Small optimization, but clean.

**Context:** `load_workouts()` is the shared helper used by `coach plan`, `coach report`, and `coach status`. The simplest fix: compute ISO week date ranges, glob `data/workouts/YYYY-MM-*.md` per week, union the matches.

**Start:** `coach/commands/plan.py` (or wherever `load_workouts()` lives).

**Depends on:** Nothing — isolated to the glob + filter pattern.

---

## T7 — Specify coach assess --week behavior when Notes/local files disagree
**Priority:** P2 | **Effort:** S (human: ~1h / CC: ~10min)

**What:** Define and implement the authoritative source for `coach assess --week` when Notes and local files are out of sync. For example: Notes has a workout that local files don't (user edited Notes directly), or local has a file that Notes doesn't (the Notes write failed after `coach log`).

**Why:** Silent inconsistency during `assess --week` could produce incorrect completion rates and a misleading `## Next Week Notes` paragraph (the core feedback signal). The error is downstream and hard to trace.

**Proposed rule:** Local files are the source of truth for `coach assess --week`. If Notes has edits not reflected locally (user added content in Notes), the user should run `coach sync` (or manually export the Notes content) before assessing. Document this contract in `03-cli-commands.md`.

**Context:** `coach plan` writes local files first, then pushes to Notes (write ordering added in this eng review). Assessments should follow the same convention: read from local, write back to local first, then push to Notes.

**Start:** `03-cli-commands.md` assess section edge cases; then `coach/commands/assess.py`.

**Depends on:** Nothing.
