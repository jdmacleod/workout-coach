import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast


def _find_project_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError("Cannot find project root (no pyproject.toml found)")


PROJECT_ROOT = _find_project_root()
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "config.toml"
CONFIG_EXAMPLE = CONFIG_DIR / "config.example.toml"
DATA_DIR = PROJECT_ROOT / "data"
EXAMPLES_DIR = DATA_DIR / "examples"


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
    available_equipment: list[str] = field(default_factory=list)
    max_session_duration_minutes: int | None = None


@dataclass
class NotesConfig:
    account: str = "iCloud"
    folder: str = "Exercise Coach"
    plan_note_links: bool = True


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
class SearchConfig:
    brave_search_api_key: str = ""
    exa_api_key: str = ""
    tavily_api_key: str = ""


@dataclass
class Config:
    user: UserConfig = field(default_factory=UserConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    notes: NotesConfig = field(default_factory=NotesConfig)
    data: DataConfig = field(default_factory=DataConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    search: SearchConfig = field(default_factory=SearchConfig)


class ConfigNotFoundError(Exception):
    pass


class ConfigError(Exception):
    pass


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        raise ConfigNotFoundError(f"No config found at {CONFIG_FILE}. Run 'coach setup' first.")
    with open(CONFIG_FILE, "rb") as f:
        try:
            raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"Invalid TOML in {CONFIG_FILE}: {e}") from e
    return _parse_config(raw)


def _parse_config(raw: dict[str, Any]) -> Config:
    def _dc(cls: Any, d: dict[str, Any]) -> Any:
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
        search=_dc(SearchConfig, raw.get("search", {})),
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


def resolve_data_path(config: Config, key: str) -> Path:
    relative = cast(str, getattr(config.data, key))
    return (PROJECT_ROOT / relative).resolve()
