
## Coding conventions

### Python environment

Use **uv** for all Python environment and dependency management:

```bash
uv sync                     # install all deps (creates/updates .venv and uv.lock)
uv add <package>            # add a runtime dependency
uv add --dev <package>      # add a dev dependency (goes into [dependency-groups] dev)
uv run <cmd>                # run a command in the managed venv
```

Dev dependencies live in `[dependency-groups]` (PEP 735), not `[project.optional-dependencies]`.

### Linting and formatting

Use **ruff** for both linting and formatting, and **mypy** for type checking:

```bash
uv run ruff check coach/ tests/        # lint
uv run ruff check --fix coach/ tests/  # auto-fix lint issues
uv run ruff format coach/ tests/       # format
uv run mypy coach/                     # type check
```

Ruff rules in effect: E, W, F, I, UP, B, SIM (see `[tool.ruff.lint]` in pyproject.toml for ignores).
Mypy is configured with `strict = true` and `ignore_missing_imports = true`.

**All three tools must pass clean before committing.** Run them together:

```bash
uv run ruff check coach/ tests/ && uv run ruff format coach/ tests/ && uv run mypy coach/
```

### Testing

```bash
uv run pytest tests/ -m "not integration and not usability and not usability_live"  # unit tests (fast, no Apple Notes, no LLM)
uv run pytest tests/ -m integration        # integration tests (requires Notes.app)
uv run pytest tests/ -m "not integration and not usability_live"                    # matches CI
uv run pytest tests/ -m usability -v -s    # synthetic 13-week simulation (no LLM)
uv run pytest tests/usability/test_simulation_live_short.py -m usability_live -v -s  # 6-week live LLM
uv run pytest tests/usability/test_simulation_live.py -m usability_live -v -s        # 13-week live LLM
```

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
