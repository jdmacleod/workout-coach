# Contributing

## Prerequisites

- macOS (Apple Notes integration requires it)
- [uv](https://docs.astral.sh/uv/) for Python environment management

## Dev setup

```bash
# Install dependencies (creates .venv and uv.lock)
uv sync

# Verify the install
uv run coach --help
```

## Running tests

```bash
# Unit tests — no Apple Notes required, fast
uv run pytest tests/ -m "not integration"

# Integration tests — requires Notes.app running and configured
uv run pytest tests/ -m integration

# Search smoke tests — hit live APIs; keyed providers skip when no key is configured
uv run pytest tests/ -m search -v

# All tests
uv run pytest tests/
```

## Lint, format, type check

```bash
uv run ruff check coach/ tests/        # lint
uv run ruff check --fix coach/ tests/  # auto-fix lint issues
uv run ruff format coach/ tests/       # format
uv run mypy coach/                     # type check (strict)
```

All three must pass clean before committing. Run them together:

```bash
uv run ruff check coach/ tests/ && uv run ruff format coach/ tests/ && uv run mypy coach/
```

## Adding dependencies

```bash
uv add <package>        # runtime dependency → [project.dependencies]
uv add --dev <package>  # dev dependency → [dependency-groups] dev
```

Commit `uv.lock` alongside any dependency changes.

## Exercise library

The exercise library lives in `data/examples/exercise-library/` (committed). Each file uses YAML-like front matter:

```markdown
---
name: Floor Press
equipment: [barbell, bumper_plates]
type: strength-push
difficulty: intermediate
---
## Sets / Reps
- Strength: 4x4-6 @ 75-85% 1RM

## Cues
...
```

Equipment tags use ALL-semantics: every tag must be present in the user's `available_equipment` for the exercise to be eligible. An empty `equipment: []` means bodyweight — always eligible. See `data/examples/exercise-library/CONTRIBUTING.md` for the full format spec and category list.
