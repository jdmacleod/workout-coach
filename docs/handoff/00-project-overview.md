# Exercise Coach — Project Overview

## Purpose

Exercise Coach is an open source macOS CLI application that uses Apple Notes as its
primary data store to plan, log, and assess personal fitness training. The system
generates structured workout plans, stores them as human-readable notes synced via
iCloud, and assesses completed sessions using a configurable LLM inference provider.

## Design Principles

- **Apple Notes as database.** iCloud sync, cross-device access, and human editability
  are non-negotiable. No proprietary database the user cannot open on their phone.
- **Local-first.** All inference runs on-device by default. Cloud providers are
  opt-in fallbacks, never the default path.
- **Plaintext durability.** Note content uses YAML front matter in plaintext.
  Apple Notes' HTML stripping is assumed; markdown rendering is never relied upon.
- **Project-local data.** User config and data live inside the project directory,
  gitignored. The repository ships example files that document expected formats.
- **Minimal dependencies.** Standard library where possible. External packages only
  for things the stdlib cannot do (TOML parsing, HTTP, calendar parsing).

## Technology Stack

| Layer | Technology |
|---|---|
| CLI | Python 3.12+ with Typer |
| Notes I/O | AppleScript via `osascript` subprocess |
| AI — primary | Swift binary wrapping Foundation Models (macOS 26+) |
| AI — alternative | Apple Intelligence via macOS Shortcuts |
| AI — local fallback | Ollama or llama.cpp (OpenAI-compatible REST) |
| AI — cloud fallback | Anthropic API |
| Calendar integration | Apple Calendar (AppleScript), Google Calendar API, ICS |
| Local index | SQLite via stdlib `sqlite3` |
| Config format | TOML via `tomllib` (stdlib, Python 3.11+) |
| Packaging | `pyproject.toml`, installable via `pipx` |

## Repository Layout

```
exercise-coach/
├── .gitignore
├── README.md
├── pyproject.toml
├── coach/                    # Python application source
│   ├── cli.py
│   ├── config.py
│   ├── commands/
│   ├── notes/
│   ├── intelligence/
│   ├── calendar/
│   ├── models/
│   └── store/
├── swift/                    # Swift inference binary
│   ├── Package.swift
│   └── Sources/CoachInfer/main.swift
├── shortcuts/                # Apple Shortcuts (.shortcut files)
├── config/                   # User config (partially gitignored)
│   └── config.example.toml
└── data/                     # User data (partially gitignored)
    └── examples/
```

## Platforms

- **macOS 13+** — full CLI functionality
- **macOS 26+** — adds Swift Foundation Models inference provider
- **iOS** — read/write workout notes via Apple Notes natively; no CLI

## Open Source

- License: MIT
- The `data/examples/` directory ships with the repo as documentation
- User personal data is gitignored by pattern; never committed
- Google OAuth credentials and tokens are gitignored

---

*See individual spec documents for detailed design of each subsystem.*
