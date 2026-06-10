# Calendar Integration Spec

## Overview

The calendar subsystem discovers external sessions (yoga, Pilates, and similar
classes) for a target week and surfaces them to the planner as immovable,
pre-loaded constraints. It is opt-in: if `[calendar] enabled = false` in config,
the planner runs without any external session data.

---

## Architecture

```
coach/calendar/
├── source.py          # ABC, ExternalSession model, factory
└── sources/
    ├── manual.py      # Parses recurring classes from training-info.md
    ├── apple.py       # Apple Calendar via AppleScript
    ├── google.py      # Google Calendar API
    └── ics.py         # ICS file or URL
```

---

## Core Interface

```python
# coach/calendar/source.py

from abc import ABC, abstractmethod
from datetime import date
from coach.models.session import ExternalSession

class CalendarSource(ABC):

    @abstractmethod
    def get_sessions(self, week_start: date, week_end: date) -> list[ExternalSession]:
        """Return ExternalSession objects in the given date range."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...
```

```python
# Factory — tries sources in configured order; returns merged, deduplicated list

def get_external_sessions(
    config: Config,
    week_start: date,
    week_end: date,
) -> list[ExternalSession]:

    sources = []
    for source_name in config.calendar.sources:
        cls = _SOURCE_MAP[source_name]
        source = cls(config)
        if source.is_available():
            sources.append(source)

    sessions = []
    for source in sources:
        sessions.extend(source.get_sessions(week_start, week_end))

    return _deduplicate(sessions)
```

Deduplication matches on `(date, session_type)` — if the same class appears in
both the manual list and Apple Calendar, the calendar version (with actual time)
takes precedence.

---

## Source: Manual Declaration

**File:** `coach/calendar/sources/manual.py`

Parses the `## Recurring External Classes` section of `data/training-info.md`.
No external dependencies. Always available. Covers the 80% case.

### Expected format in `training-info.md`

```markdown
## Recurring External Classes
- Tuesday 07:00 — Vinyasa Yoga (60 min)
- Thursday 18:30 — Reformer Pilates (55 min)
```

### Parser behavior

```python
import re
from datetime import date, time, timedelta

WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

LINE_PATTERN = re.compile(
    r"^-\s+(?P<day>\w+)\s+(?P<hour>\d{1,2}):(?P<min>\d{2})"
    r"\s+[—-]\s+(?P<title>[^(]+)\((?P<duration>\d+)\s*min\)",
    re.IGNORECASE,
)

def get_sessions(self, week_start: date, week_end: date) -> list[ExternalSession]:
    lines = self._read_recurring_section()
    sessions = []
    for line in lines:
        m = LINE_PATTERN.match(line.strip())
        if not m:
            continue
        weekday_num = WEEKDAY_MAP[m.group("day").lower()]
        session_date = week_start + timedelta(days=weekday_num)
        if not (week_start <= session_date <= week_end):
            continue
        session_type, intensity = classify_session(m.group("title"))
        sessions.append(ExternalSession(
            title=m.group("title").strip(),
            date=session_date,
            start_time=time(int(m.group("hour")), int(m.group("min"))),
            duration_minutes=int(m.group("duration")),
            source="manual",
            calendar_name="training-info",
            session_type=session_type,
            intensity=intensity,
            recovery_cost=RECOVERY_COST_MAP.get(session_type, {}).get(intensity, 2),
        ))
    return sessions
```

---

## Source: Apple Calendar

**File:** `coach/calendar/sources/apple.py`

Queries Apple Calendar via AppleScript. Works with any calendar synced to
Apple Calendar — including Google Calendar, which most macOS users sync automatically.

### Configuration

```toml
[calendar.apple]
calendars = ["Yoga Studio", "Fitness Classes"]   # Calendar names in Apple Calendar
```

### AppleScript

```applescript
tell application "Calendar"
    set startDate to date "{start_iso}"
    set endDate to date "{end_iso}"
    set results to {}
    repeat with calName in {"{cal1}", "{cal2}"}
        try
            set targetCal to calendar calName
            set calEvents to (every event of targetCal ¬
                whose start date >= startDate and start date <= endDate)
            repeat with evt in calEvents
                set end of results to (summary of evt) & "|" & ¬
                    ((start date of evt) as string) & "|" & ¬
                    ((end date of evt) as string)
            end repeat
        end try
    end repeat
    return results
end tell
```

The result is a list of `title|start_datetime|end_datetime` strings. Python splits
on `|` and parses datetime strings with `dateutil.parser`.

Keyword filtering is applied in Python after retrieval, not in AppleScript:

```python
def _matches_patterns(title: str, patterns: list[str]) -> bool:
    return any(p.lower() in title.lower() for p in patterns)
```

Only events matching `config.calendar.event_patterns` are converted to
`ExternalSession` objects.

---

## Source: Google Calendar API

**File:** `coach/calendar/sources/google.py`

**Dependencies:** `google-api-python-client`, `google-auth-oauthlib` (optional install)

**OAuth flow:** Runs once during `coach setup`. Saves token to `config/google-token.json`.

```python
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

class GoogleCalendarSource(CalendarSource):

    def _get_service(self):
        creds = Credentials.from_authorized_user_file(
            self.config.calendar.google.token_file, SCOPES
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("calendar", "v3", credentials=creds)

    def get_sessions(self, week_start, week_end):
        service = self._get_service()
        sessions = []
        for cal_id in self.config.calendar.google.calendar_ids:
            events = service.events().list(
                calendarId=cal_id,
                timeMin=f"{week_start.isoformat()}T00:00:00Z",
                timeMax=f"{week_end.isoformat()}T23:59:59Z",
                singleEvents=True,
                orderBy="startTime",
            ).execute().get("items", [])

            for event in events:
                title = event.get("summary", "")
                if not self._matches_patterns(title):
                    continue
                sessions.append(self._parse_event(event))
        return sessions

    def is_available(self) -> bool:
        token_file = Path(self.config.calendar.google.token_file)
        return token_file.exists()
```

---

## Source: ICS

**File:** `coach/calendar/sources/ics.py`

**Dependencies:** `icalendar`

Supports both a local `.ics` file and a remote URL (Google Calendar private ICS).

```python
from icalendar import Calendar
import httpx

class ICSSource(CalendarSource):

    def _load_calendar(self) -> Calendar:
        if self.config.calendar.ics.url:
            r = httpx.get(self.config.calendar.ics.url, timeout=15)
            r.raise_for_status()
            return Calendar.from_ical(r.content)
        elif self.config.calendar.ics.file:
            return Calendar.from_ical(
                Path(self.config.calendar.ics.file).read_bytes()
            )
        raise ConfigError("ICS source requires either url or file in config")

    def get_sessions(self, week_start, week_end):
        cal = self._load_calendar()
        sessions = []
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            title = str(component.get("SUMMARY", ""))
            if not self._matches_patterns(title):
                continue
            start = component.get("DTSTART").dt
            end = component.get("DTEND").dt
            if not (week_start <= start.date() <= week_end):
                continue
            sessions.append(self._build_session(title, start, end))
        return sessions
```

---

## Session Classification

```python
# coach/calendar/source.py

CLASSIFICATION_MAP: dict[str, tuple[str, str]] = {
    "yin":          ("yoga",    "low"),
    "restorative":  ("yoga",    "low"),
    "gentle yoga":  ("yoga",    "low"),
    "vinyasa":      ("yoga",    "moderate"),
    "hatha":        ("yoga",    "moderate"),
    "yoga":         ("yoga",    "moderate"),   # fallback if no subtype matched
    "ashtanga":     ("yoga",    "high"),
    "hot yoga":     ("yoga",    "high"),
    "power yoga":   ("yoga",    "high"),
    "mat pilates":  ("pilates", "low"),
    "pilates":      ("pilates", "moderate"),   # fallback
    "reformer":     ("pilates", "moderate"),
    "clinical":     ("pilates", "low"),
    "barre":        ("barre",   "moderate"),
}

RECOVERY_COST_MAP: dict[str, dict[str, int]] = {
    "yoga":    {"low": 1, "moderate": 2, "high": 4},
    "pilates": {"low": 1, "moderate": 3, "high": 4},
    "barre":   {"low": 2, "moderate": 3, "high": 4},
}

def classify_session(title: str) -> tuple[str, str]:
    """Return (session_type, intensity) from event title. Case-insensitive."""
    lower = title.lower()
    for keyword, result in CLASSIFICATION_MAP.items():
        if keyword in lower:
            return result
    return ("unknown", "moderate")
```

---

## Config Reference

```toml
[calendar]
enabled = false

# Sources tried in order; merged results are deduplicated
sources = ["manual", "apple"]   # "manual" | "apple" | "google" | "ics"

# Calendar names to search (Apple Calendar or display names)
calendars = ["Yoga Studio", "Fitness Classes"]

# Keywords matched against event titles (case-insensitive)
event_patterns = [
    "yoga", "pilates", "vinyasa", "reformer",
    "yin", "barre", "ashtanga", "hot yoga", "hatha"
]

# Optional: override recovery cost for specific keywords
[calendar.recovery_costs]
"yin yoga"   = 1
"vinyasa"    = 2
"reformer"   = 3
"hot yoga"   = 4

[calendar.google]
credentials_file = "config/google-credentials.json"
token_file       = "config/google-token.json"
calendar_ids     = ["primary"]

[calendar.ics]
url  = ""   # Google Calendar private ICS URL
file = ""   # or path to exported .ics file
```

---

## Planning Integration

The planner receives a list of `ExternalSession` objects and formats them into the
planning prompt as fixed constraints:

```python
def format_external_sessions(sessions: list[ExternalSession]) -> str:
    if not sessions:
        return "None."
    lines = []
    for s in sorted(sessions, key=lambda x: x.date):
        day = s.date.strftime("%A")
        time_str = s.start_time.strftime("%H:%M") if s.start_time else "TBD"
        lines.append(
            f"- {day} {time_str} — {s.title} "
            f"({s.duration_minutes} min, recovery_cost: {s.recovery_cost})"
        )
    return "\n".join(lines)
```

The plan note renders external sessions with a `⟳` marker and includes their source:

```markdown
| Tue | ⟳ Vinyasa Yoga | apple_calendar | 60 min |
```

This distinguishes them visually from generated sessions without requiring any
special rendering support from Apple Notes.
