# Configuration Spec

## Overview

Configuration is split into two files:

| File | Purpose | In repo |
|---|---|---|
| `config/config.example.toml` | Documents every option; safe to commit | Yes |
| `config/config.toml` | User's real config; contains personal data | No (gitignored) |

`coach setup` creates `config/config.toml` from the example file and populates it
interactively. After setup, the user can hand-edit `config.toml` directly.

---

## `config/config.example.toml`

```toml
# Exercise Coach — Configuration
# Copy to config/config.toml and edit. config.toml is gitignored.

# ── User ──────────────────────────────────────────────────────────────────────

[user]
name     = "Your Name"
timezone = "America/Los_Angeles"   # IANA timezone string

# ── LLM Inference ─────────────────────────────────────────────────────────────

[llm]
# Options: swift | apple | ollama | llamacpp | anthropic
# swift is the default on macOS 26+; use ollama or anthropic on older systems
provider = "swift"

[llm.swift]
# Path to the compiled coach-infer binary (relative to project root)
binary = "swift/.build/release/CoachInfer"

[llm.apple]
# Prefix used to identify Exercise Coach shortcuts in Shortcuts.app
shortcut_prefix = "EC-"

[llm.ollama]
base_url = "http://localhost:11434"
model    = "llama3.2"

[llm.llamacpp]
server_url = "http://localhost:8080"
model_path = "~/models/mistral-7b-instruct.gguf"   # informational only

[llm.anthropic]
model = "claude-sonnet-4-20250514"
# API key is read from the ANTHROPIC_API_KEY environment variable.
# Do not paste your API key into this file.

# ── User Profile (cold-start onboarding) ─────────────────────────────────────
# Written by `coach setup`. Values are injected into the planning prompt.

[profile]
fitness_days_per_week = 4
primary_goal          = "general fitness"   # strength | endurance | general fitness | weight loss | sport-specific
injury_notes          = ""                  # free text; empty means none

# ── Apple Notes ───────────────────────────────────────────────────────────────

[notes]
account = "iCloud"            # Must match the account name in Notes.app exactly
folder  = "Exercise Coach"    # Root folder; subfolders are created by setup

# ── Data Paths ────────────────────────────────────────────────────────────────
# All paths are relative to the project root.

[data]
training_info   = "data/training-info.md"
workouts_dir    = "data/workouts/"
plans_dir       = "data/plans/"
assessments_dir = "data/assessments/"

# ── Calendar Integration ──────────────────────────────────────────────────────

[calendar]
enabled = false

# Sources tried in order. Options: manual | apple | google | ics
sources = ["manual", "apple"]

# Calendar display names to search (Apple Calendar or Google Calendar)
calendars = ["Yoga Studio", "My Calendar"]

# Event title keywords to include (case-insensitive)
event_patterns = [
    "yoga", "pilates", "vinyasa", "reformer",
    "yin", "barre", "ashtanga", "hot yoga", "hatha"
]

[calendar.recovery_costs]
# Override default recovery cost (1 = very easy, 5 = very hard) per keyword
"yin yoga"  = 1
"vinyasa"   = 2
"reformer"  = 3
"hot yoga"  = 4

[calendar.google]
credentials_file = "config/google-credentials.json"
token_file       = "config/google-token.json"
calendar_ids     = ["primary"]

[calendar.ics]
url  = ""   # Google Calendar private ICS URL (leave blank if not used)
file = ""   # Path to exported .ics file (leave blank if not used)
```

---

## Config Loading (`coach/config.py`)

```python
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Locate project root at import time
def _find_project_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("Cannot find project root (no pyproject.toml found)")

PROJECT_ROOT = _find_project_root()
CONFIG_FILE  = PROJECT_ROOT / "config" / "config.toml"


@dataclass
class LLMSwiftConfig:
    binary: str = "swift/.build/release/CoachInfer"

@dataclass
class LLMAppleConfig:
    shortcut_prefix: str = "EC-"

@dataclass
class LLMOllamaConfig:
    base_url: str = "http://localhost:11434"
    model: str = "llama3.2"

@dataclass
class LLMLlamaCppConfig:
    server_url: str = "http://localhost:8080"
    model_path: str = ""

@dataclass
class LLMAnthropicConfig:
    model: str = "claude-sonnet-4-20250514"

@dataclass
class LLMConfig:
    provider: str = "swift"
    swift: LLMSwiftConfig = field(default_factory=LLMSwiftConfig)
    apple: LLMAppleConfig = field(default_factory=LLMAppleConfig)
    ollama: LLMOllamaConfig = field(default_factory=LLMOllamaConfig)
    llamacpp: LLMLlamaCppConfig = field(default_factory=LLMLlamaCppConfig)
    anthropic: LLMAnthropicConfig = field(default_factory=LLMAnthropicConfig)

@dataclass
class ProfileConfig:
    fitness_days_per_week: int = 4
    primary_goal: str = "general fitness"
    injury_notes: str = ""

@dataclass
class NotesConfig:
    account: str = "iCloud"
    folder: str = "Exercise Coach"

@dataclass
class DataConfig:
    training_info: str = "data/training-info.md"
    workouts_dir: str = "data/workouts/"
    plans_dir: str = "data/plans/"
    assessments_dir: str = "data/assessments/"

@dataclass
class CalendarGoogleConfig:
    credentials_file: str = "config/google-credentials.json"
    token_file: str = "config/google-token.json"
    calendar_ids: list[str] = field(default_factory=lambda: ["primary"])

@dataclass
class CalendarICSConfig:
    url: str = ""
    file: str = ""

@dataclass
class CalendarConfig:
    enabled: bool = False
    sources: list[str] = field(default_factory=lambda: ["manual"])
    calendars: list[str] = field(default_factory=list)
    event_patterns: list[str] = field(default_factory=list)
    recovery_costs: dict[str, int] = field(default_factory=dict)
    google: CalendarGoogleConfig = field(default_factory=CalendarGoogleConfig)
    ics: CalendarICSConfig = field(default_factory=CalendarICSConfig)

@dataclass
class UserConfig:
    name: str = ""
    timezone: str = "America/New_York"

@dataclass
class Config:
    user: UserConfig = field(default_factory=UserConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    notes: NotesConfig = field(default_factory=NotesConfig)
    data: DataConfig = field(default_factory=DataConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        raise ConfigNotFoundError(
            f"No config found at {CONFIG_FILE}. Run 'coach setup' first."
        )
    with open(CONFIG_FILE, "rb") as f:
        try:
            raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"Invalid TOML in {CONFIG_FILE}: {e}") from e
    return _parse_config(raw)


def _parse_config(raw: dict) -> Config:
    """Map nested TOML dict to Config dataclasses with per-level defaults.

    Pattern: use .get() at each level with {} fallback, then filter keys
    to __dataclass_fields__ so unknown TOML keys don't crash construction.
    """
    def _dc(cls, d: dict):
        """Construct a dataclass from a dict, ignoring unknown keys."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    llm_raw = raw.get("llm", {})
    cal_raw = raw.get("calendar", {})
    return Config(
        user=_dc(UserConfig, raw.get("user", {})),
        llm=LLMConfig(
            provider=llm_raw.get("provider", "swift"),
            swift=_dc(LLMSwiftConfig, llm_raw.get("swift", {})),
            apple=_dc(LLMAppleConfig, llm_raw.get("apple", {})),
            ollama=_dc(LLMOllamaConfig, llm_raw.get("ollama", {})),
            llamacpp=_dc(LLMLlamaCppConfig, llm_raw.get("llamacpp", {})),
            anthropic=_dc(LLMAnthropicConfig, llm_raw.get("anthropic", {})),
        ),
        profile=_dc(ProfileConfig, raw.get("profile", {})),
        notes=_dc(NotesConfig, raw.get("notes", {})),
        data=_dc(DataConfig, raw.get("data", {})),
        calendar=CalendarConfig(
            enabled=cal_raw.get("enabled", False),
            sources=cal_raw.get("sources", ["manual"]),
            calendars=cal_raw.get("calendars", []),
            event_patterns=cal_raw.get("event_patterns", []),
            recovery_costs=cal_raw.get("recovery_costs", {}),
            google=_dc(CalendarGoogleConfig, cal_raw.get("google", {})),
            ics=_dc(CalendarICSConfig, cal_raw.get("ics", {})),
        ),
    )


class ConfigNotFoundError(Exception):
    pass

class ConfigError(Exception):
    pass
```

### Path resolution helper

All data paths in `DataConfig` are relative to the project root. A helper
resolves them to absolute `Path` objects:

```python
def resolve_data_path(config: Config, key: str) -> Path:
    relative = getattr(config.data, key)
    return (PROJECT_ROOT / relative).resolve()
```

---

## Setup Questionnaire Flow

`coach setup` writes the following keys interactively:

```
[user]
  name      ← "What's your name?"
  timezone  ← detected from system, confirmed

[llm]
  provider  ← provider availability table → user selects

[profile]
  fitness_days_per_week ← "How many days per week are you currently training?"
  primary_goal          ← "What's your primary training goal?"
                           (strength / endurance / general fitness / weight loss / sport-specific)
  injury_notes          ← "Any injuries or limitations I should know about?" (free text, skippable)

[calendar]
  enabled   ← "Do you have yoga/Pilates classes to include? (y/n)"
  sources   ← if enabled: "Check Apple Calendar, Google, or enter manually?"
  calendars ← if apple or google: "Enter calendar names (comma-separated)"
```

If `--non-interactive` is passed, `[profile]` defaults are used:
`fitness_days_per_week: 4`, `primary_goal: general fitness`, `injury_notes: ""`.

All other values copy from `config.example.toml` defaults unchanged and can be
edited by hand afterward.

---

## Environment Variables

The following environment variables override config file values when set:

| Variable | Overrides |
|---|---|
| `ANTHROPIC_API_KEY` | Required for Anthropic provider; never stored in config |
| `COACH_CONFIG` | Path to config file (overrides default location) |
| `COACH_DATA_DIR` | Overrides `[data]` directory root |
| `COACH_NO_COLOR` | Disables Rich terminal color output |
