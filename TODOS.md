# Exercise Coach — TODOS

Items deferred from current scope. Each item includes context, motivation, and a starting point.

---

## ~~T11~~ — Smart sync gate: honor iPhone edits to existing workout notes ✓ COMPLETED in v0.8.0

---

## ~~T12~~ — Harmonize "How It Went" placeholder text across MD and HTML renders ✓ COMPLETED in v0.9.0

---

## T9 — Python-side web search for exercise discovery (any provider)
**Priority:** P3 | **Effort:** M (human: ~1.5h / CC: ~15min)

**What:** Extend exercise discovery web search (currently Swift-only, equipment-constraint focused) to work on any provider via Python-side Brave/DuckDuckGo query. Skipped automatically if no API key is configured. Inject top 3-5 results as supplementary exercise options alongside the `data/exercise-library/` block.

**Why:** The local exercise library is finite. Users who train consistently will eventually exhaust it. Web search keeps the option pool fresh without requiring manual library authoring.

**Context:** Deferred from the workout variation CEO review (2026-06-15). Ship the local exercise library first (base scope). Revisit after the library is live and users report they've seen all the exercises. The Brave/DuckDuckGo integration pattern already exists in `coach/intelligence/providers/swift.py` and the `SearchConfig` dataclass is in `coach/config.py`.

**Start:** `coach/commands/plan.py` — add `_search_exercise_options(session_types, equipment, cfg)` that calls Brave or DDG with `"[session_type] exercises [equipment]"`, extracts exercise names from results, and returns a short supplementary block. Gate on `cfg.search.brave_search_api_key or True` (DDG needs no key).

**Depends on:** Local exercise library (base variation scope) shipped first.

---

## T10 — Session type balance enforcer (post-generation hard check)
**Priority:** P3 | **Effort:** S (human: ~30min / CC: ~5min)

**What:** A post-generation validation check (mirroring the equipment violation check in `_correct_plan_if_needed()`) that fires a correction pass if the generated plan contains more than 2 consecutive sessions of the same subtype (e.g., 3 consecutive strength-push sessions in a 4-day plan).

**Why:** The periodization directive injection (prompt-level) addresses the root cause at generation time. This would be a hard backstop if the LLM ignores the directive. Add only if the directive proves insufficient in practice.

**Context:** Deferred from the workout variation CEO review (2026-06-15). The periodization directive is tried first. If users still report repetitive plans after that ships, add this enforcer as a correction-pass fallback.

**Start:** `coach/commands/plan.py:_correct_plan_if_needed()` — add a `_check_session_type_balance(sessions)` helper that returns violations when subtypes repeat >2 consecutively. Wire into the correction prompt if violations found.

**Depends on:** Periodization directive injection (variation scope base) shipped first.

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

## ~~T6~~ — Optimize load_workouts() glob for large datasets ✓ COMPLETED in v0.9.0

---

## ~~T8~~ — Eval harness for LLM constraint validation ✓ COMPLETED in v0.9.0
