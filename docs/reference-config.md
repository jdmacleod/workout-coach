# Configuration Reference

Exercise Coach is configured via `config/config.toml`. Run `coach setup` to create it
from the example, or copy `config/config.example.toml` manually and edit.

`config/config.toml` is gitignored — your personal settings and API keys stay local.

---

## [user]

```toml
[user]
name     = "Your Name"
timezone = "America/Los_Angeles"
```

| Key | Type | Description |
|---|---|---|
| `name` | string | Your name. Injected into planning and assessment prompts. |
| `timezone` | string | IANA timezone string (e.g. `America/New_York`, `Europe/London`). Used for calendar integration. |

---

## [llm]

```toml
[llm]
provider = "swift"
```

| Key | Type | Options | Description |
|---|---|---|---|
| `provider` | string | `swift`, `apple`, `ollama`, `llamacpp`, `anthropic` | The active inference provider. Run `coach setup` to see which are available on your system. |

**Provider availability by platform:**

| Provider | macOS 13–25 | macOS 26+ | Notes |
|---|---|---|---|
| `swift` | No | Yes | Requires compiled binary. See [How-to: configure providers](howto-configure-providers.md). |
| `apple` | No | Yes | Uses Apple Intelligence via Shortcuts. |
| `ollama` | Yes | Yes | Requires Ollama running locally. |
| `llamacpp` | Yes | Yes | Requires llama.cpp server running locally. |
| `anthropic` | Yes | Yes | Requires `ANTHROPIC_API_KEY` environment variable. |

---

## [llm.swift]

```toml
[llm.swift]
binary = "swift/.build/release/CoachInfer"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `binary` | string | `swift/.build/release/CoachInfer` | Path to the compiled Swift inference binary, relative to the project root. Build with `make -C swift build`. |

---

## [llm.apple]

```toml
[llm.apple]
shortcut_prefix = "EC-"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `shortcut_prefix` | string | `EC-` | Prefix used to identify Exercise Coach shortcuts in Shortcuts.app. Shortcuts must be named `EC-Plan`, `EC-Assess`, etc. |

---

## [llm.ollama]

```toml
[llm.ollama]
base_url = "http://localhost:11434"
model    = "llama3.2"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `base_url` | string | `http://localhost:11434` | Ollama server URL. |
| `model` | string | `llama3.2` | Model name as known to Ollama (e.g. `llama3.2`, `mistral`, `qwen2.5`). |

---

## [llm.llamacpp]

```toml
[llm.llamacpp]
server_url  = "http://localhost:8080"
model_path  = "~/models/mistral-7b-instruct.gguf"
```

| Key | Type | Description |
|---|---|---|
| `server_url` | string | llama.cpp server URL (OpenAI-compatible `/v1/chat/completions`). |
| `model_path` | string | Path to the `.gguf` model file. Informational only — the server must be started separately. |

---

## [llm.anthropic]

```toml
[llm.anthropic]
model = "claude-sonnet-4-20250514"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `model` | string | `claude-sonnet-4-20250514` | Anthropic model ID. |

**API key:** set the `ANTHROPIC_API_KEY` environment variable. Do not paste the key into `config.toml`.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## [profile]

Written by `coach setup`. Values are injected into every planning and assessment prompt.

```toml
[profile]
fitness_days_per_week        = 4
primary_goal                 = "general fitness"
injury_notes                 = ""
available_equipment          = ["barbell", "pull-up bar"]
max_session_duration_minutes = 60
```

| Key | Type | Description |
|---|---|---|
| `fitness_days_per_week` | integer | How many days per week you currently train. Guides plan volume. |
| `primary_goal` | string | `strength`, `endurance`, `general fitness`, `weight loss`, or `sport-specific`. Sets the planning objective. |
| `injury_notes` | string | Free text describing injuries or limitations. Injected into the planning prompt as constraints. Empty string means none. |
| `available_equipment` | array | Equipment you have access to (e.g. `["barbell", "pull-up bar", "kettlebell"]`). Limits exercise selection and, on the Swift provider, activates pre-plan web search. Empty array = bodyweight only. |
| `max_session_duration_minutes` | integer or null | Hard cap on session length in minutes. The planner keeps every session within this budget. `null` or omitting the key = no limit. |

---

## [notes]

```toml
[notes]
account = "iCloud"
folder  = "Exercise Coach"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `account` | string | `iCloud` | Notes account name, exactly as it appears in Notes.app sidebar (case-sensitive). Use `On My Mac` for a local-only account. |
| `folder` | string | `Exercise Coach` | Root folder for all Exercise Coach notes. `coach setup` creates `<folder>/Plans`, `<folder>/Workouts`, and `<folder>/Assessments` automatically. |

---

## [data]

All paths are relative to the project root.

```toml
[data]
training_info    = "data/training-info.md"
workouts_dir     = "data/workouts/"
plans_dir        = "data/plans/"
assessments_dir  = "data/assessments/"
exercise_library = "data/exercise-library/"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `training_info` | string | `data/training-info.md` | Your training profile document. The planner reads this on every `coach plan` run. Edit it freely. |
| `workouts_dir` | string | `data/workouts/` | Directory for local workout note copies. Mirrored from Apple Notes. |
| `plans_dir` | string | `data/plans/` | Directory for local plan copies (one file per week: `YYYY-Www.md`). |
| `assessments_dir` | string | `data/assessments/` | Directory for local assessment copies. |
| `exercise_library` | string | `data/exercise-library/` | Root directory of the exercise library. `coach setup` bootstraps this from `data/examples/exercise-library/` on first run. Add subdirectories and `.md` files to expand the pool. |

---

## [calendar]

Calendar integration is disabled by default. When enabled, upcoming external sessions
(yoga, pilates, etc.) are loaded and their recovery cost is factored into the plan.

```toml
[calendar]
enabled = false
sources = ["manual", "apple"]
calendars = ["Yoga Studio", "My Calendar"]
event_patterns = ["yoga", "pilates", "vinyasa"]
```

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable calendar integration. |
| `sources` | array | `["manual", "apple"]` | Sources tried in order: `manual`, `apple`, `google`, `ics`. |
| `calendars` | array | `[]` | Calendar display names to search in Apple Calendar or Google Calendar. |
| `event_patterns` | array | `[]` | Event title keywords to include (case-insensitive). |

### [calendar.recovery_costs]

Override the default recovery cost (1 = very easy, 5 = very hard) per event keyword:

```toml
[calendar.recovery_costs]
"yin yoga"  = 1
"vinyasa"   = 2
"hot yoga"  = 4
```

### [calendar.google]

```toml
[calendar.google]
credentials_file = "config/google-credentials.json"
token_file       = "config/google-token.json"
calendar_ids     = ["primary"]
```

| Key | Type | Description |
|---|---|---|
| `credentials_file` | string | Path to Google OAuth credentials JSON (from Google Cloud Console). |
| `token_file` | string | Path where the OAuth token is stored after first login. |
| `calendar_ids` | array | Google Calendar IDs to query (e.g. `["primary"]`). |

### [calendar.ics]

```toml
[calendar.ics]
url  = ""   # Google Calendar private ICS URL
file = ""   # Path to exported .ics file
```

---

## [search]

Optional API keys for web search providers. Used by the Swift inference bridge during plan
generation when `profile.available_equipment` is non-empty. Providers are tried in priority
order; DuckDuckGo is always the free fallback.

```toml
[search]
brave_search_api_key = ""
exa_api_key          = ""
tavily_api_key       = ""
```

| Key | Type | Provider | Description |
|---|---|---|---|
| `brave_search_api_key` | string | [Brave Search](https://api.search.brave.com/) | Priority 1. Best general fitness results. |
| `exa_api_key` | string | [Exa](https://exa.ai/) | Priority 2. Semantic / AI-native search. |
| `tavily_api_key` | string | [Tavily](https://tavily.com/) | Priority 3. AI-optimized RAG search. |

Leave all keys blank to use DuckDuckGo only (free, no signup required). DuckDuckGo returns
Wikipedia abstracts and is less effective for specific exercise queries.

**Note:** Web search only activates on the `swift` provider when `available_equipment` is non-empty.
All other providers ignore this section.

---

## Related

- [Command reference](reference-commands.md) — all commands and flags
- [How-to: configure inference providers](howto-configure-providers.md)
