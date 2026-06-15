# Repository Structure & Gitignore

## Full Directory Tree

```
exercise-coach/
│
├── .gitignore
├── README.md
├── pyproject.toml
├── CONTRIBUTING.md
├── LICENSE
│
├── coach/
│   ├── __init__.py
│   ├── cli.py                        # Typer app, command registration
│   ├── config.py                     # Config loading, path resolution
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── setup.py                  # coach setup
│   │   ├── plan.py                   # coach plan
│   │   ├── assess.py                 # coach assess
│   │   ├── log.py                    # coach log
│   │   ├── report.py                 # coach report
│   │   └── sync.py                   # coach sync (index rebuild)
│   ├── notes/
│   │   ├── __init__.py
│   │   ├── client.py                 # AppleScript bridge
│   │   ├── parser.py                 # Front matter + section parsing
│   │   └── schema.py                 # Note field definitions, templates
│   ├── intelligence/
│   │   ├── __init__.py
│   │   ├── provider.py               # ABC + factory function
│   │   ├── prompts.py                # Prompt templates
│   │   └── providers/
│   │       ├── __init__.py
│   │       ├── swift.py              # Swift binary bridge
│   │       ├── apple.py              # Shortcuts bridge
│   │       ├── ollama.py             # Ollama REST
│   │       ├── llamacpp.py           # llama.cpp REST
│   │       └── anthropic.py          # Anthropic SDK
│   ├── calendar/
│   │   ├── __init__.py
│   │   ├── source.py                 # ABC + factory
│   │   └── sources/
│   │       ├── __init__.py
│   │       ├── manual.py             # Parsed from training-info.md
│   │       ├── apple.py              # Apple Calendar AppleScript
│   │       ├── google.py             # Google Calendar API
│   │       └── ics.py                # ICS file/URL
│   ├── models/
│   │   ├── __init__.py
│   │   ├── workout.py                # Workout dataclass
│   │   ├── plan.py                   # WeeklyPlan dataclass
│   │   ├── session.py                # ExternalSession dataclass
│   │   └── metrics.py                # Metric dataclass
│   └── store/
│       ├── __init__.py
│       ├── index.py                  # SQLite read/write
│       └── migrations.py            # Schema versioning
│
├── swift/
│   ├── Package.swift
│   └── Sources/
│       └── CoachInfer/
│           └── main.swift
│
├── shortcuts/
│   ├── EC-GenerateWorkout.shortcut
│   ├── EC-AssessWorkout.shortcut
│   ├── EC-WeeklySummary.shortcut
│   ├── EC-QuickLog.shortcut          # iOS quick log shortcut
│   └── README.md
│
├── config/
│   └── config.example.toml          # Committed — documents all options
│   # config.toml                    # Gitignored — user's real config
│   # google-credentials.json        # Gitignored
│   # google-token.json              # Gitignored
│
└── data/
    ├── examples/                     # Committed — never gitignored
    │   ├── training-info.md
    │   ├── exercise-library/         # 34 exercises across 6 categories (bootstrapped by setup)
    │   │   ├── CONTRIBUTING.md
    │   │   ├── strength-push/
    │   │   ├── strength-pull/
    │   │   ├── strength-lower/
    │   │   ├── cardio/
    │   │   ├── hiit/
    │   │   └── mobility/
    │   ├── workouts/
    │   │   ├── strength-upper.md
    │   │   ├── strength-lower.md
    │   │   ├── cardio-zone2.md
    │   │   ├── hiit-intervals.md
    │   │   └── mobility.md
    │   └── plans/
    │       └── week-example.md
    # training-info.md               # Gitignored — user's real file
    # exercise-library/              # Gitignored — bootstrapped from examples/ by setup
    # workouts/                      # Gitignored
    # plans/                         # Gitignored
    # assessments/                   # Gitignored
    # index.db                       # Gitignored
```

---

## `.gitignore`

```gitignore
# === User configuration ===
config/config.toml
config/google-credentials.json
config/google-token.json
config/*.ics

# === User data ===
data/training-info.md
data/exercise-library/
data/workouts/
data/plans/
data/assessments/
data/index.db
data/*.ics

# === Swift build ===
swift/.build/
swift/*.o
swift/*.d

# === Python ===
__pycache__/
*.py[cod]
*.pyo
.venv/
venv/
dist/
build/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# === macOS ===
.DS_Store
**/.DS_Store
```

---

## `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "exercise-coach"
version = "0.1.0"
description = "Apple Notes-based fitness coaching CLI"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
dependencies = [
    "typer>=0.12",
    "httpx>=0.27",
    "icalendar>=5.0",
    "anthropic>=0.30",
    "rich>=13.0",
]

[project.optional-dependencies]
google = [
    "google-api-python-client>=2.0",
    "google-auth-httplib2>=0.2",
    "google-auth-oauthlib>=1.0",
]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.scripts]
coach = "coach.cli:app"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true
```

---

## Path Resolution

All paths resolve relative to the project root, detected at import time:

```python
# coach/config.py
from pathlib import Path

# Walk up from this file to find the project root (contains pyproject.toml)
def _find_project_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("Cannot find project root (no pyproject.toml found)")

PROJECT_ROOT    = _find_project_root()
CONFIG_DIR      = PROJECT_ROOT / "config"
CONFIG_FILE     = CONFIG_DIR / "config.toml"
CONFIG_EXAMPLE  = CONFIG_DIR / "config.example.toml"
DATA_DIR        = PROJECT_ROOT / "data"
EXAMPLES_DIR    = DATA_DIR / "examples"
```

This means the project can be cloned to any directory and still resolves data correctly.
