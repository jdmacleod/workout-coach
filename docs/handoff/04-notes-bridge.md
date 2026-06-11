# Apple Notes Bridge

## Overview

The notes bridge is the lowest-level subsystem. All other components depend on it.
It is implemented in `coach/notes/client.py` as a thin wrapper around `osascript`
subprocess calls. It must be reliable, explicit about errors, and never silently
swallow data.

---

## Architecture

```
coach/notes/
├── client.py     # AppleScript subprocess bridge (this document)
├── parser.py     # Plaintext / front matter parsing (see Data Models spec)
└── schema.py     # Note title patterns, folder names, templates
```

---

## AppleScript Execution

All AppleScript is executed via a single helper:

```python
import subprocess
from coach.notes.exceptions import NotesClientError, NotesTimeoutError

def _run_applescript(script: str) -> str:
    """Execute an AppleScript string via osascript. Returns stdout string.
    Raises NotesTimeoutError on timeout, NotesClientError on non-zero exit."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise NotesTimeoutError("osascript timed out after 30s")
    if result.returncode != 0:
        raise NotesClientError(
            f"AppleScript failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()
```

**Timeout:** 30 seconds. Notes operations can be slow on first call if Notes.app
is not running. The timeout avoids hanging the CLI indefinitely.

**Notes.app:** Does not need to be in the foreground but must be able to launch.
AppleScript will launch Notes.app in the background automatically if needed.

---

## Account and Folder Configuration

The Notes account name and root folder are read from config:

```toml
[notes]
account = "iCloud"          # Must match exactly the account name in Notes.app
folder  = "Exercise Coach"  # Root folder; subfolders created during setup
```

### Subfolder constants (`coach/notes/schema.py`)

```python
FOLDER_ROOT        = "Exercise Coach"
FOLDER_WORKOUTS    = "Exercise Coach/Workouts"
FOLDER_PLANS       = "Exercise Coach/Plans"
FOLDER_ASSESSMENTS = "Exercise Coach/Assessments"
```

---

## Client Interface

### `NotesClient` class

```python
class NotesClient:
    def __init__(self, account: str, root_folder: str): ...

    # Folder operations
    def ensure_folder(self, folder_path: str) -> None: ...

    # Note operations
    def create_note(self, folder: str, title: str, body: str) -> None: ...
    def get_note(self, folder: str, title: str) -> str: ...
    def update_note(self, folder: str, title: str, body: str) -> None: ...
    def note_exists(self, folder: str, title: str) -> bool: ...
    def list_notes(self, folder: str) -> list[str]: ...
    def delete_note(self, folder: str, title: str) -> None: ...
```

---

## AppleScript Implementations

### `ensure_folder`

Creates a folder if it does not exist. Safe to call repeatedly.

```applescript
tell application "Notes"
    set acct to account "{account}"
    if not (exists folder "{folder}" of acct) then
        make new folder at acct with properties {{name:"{folder}"}}
    end if
end tell
```

For nested folders (`Exercise Coach/Workouts`), the parent is created first.
The client resolves this by splitting on `/` and ensuring each level exists.

### `create_note`

```applescript
tell application "Notes"
    set targetFolder to folder "{folder}" of account "{account}"
    make new note at targetFolder with properties {{
        name: "{title}",
        body: "{escaped_body}"
    }}
end tell
```

**Body escaping:** The body string must have `"` replaced with `\"` and newlines
replaced with `\n` before interpolation into the AppleScript string. A dedicated
`_escape_for_applescript(text: str) -> str` helper handles this.

### `get_note`

```applescript
tell application "Notes"
    set theNote to first note of folder "{folder}" of account "{account}" ¬
        whose name is "{title}"
    return body of theNote
end tell
```

Apple Notes returns the body as HTML even for plaintext notes. The client strips
HTML tags before returning to the caller:

```python
import re

def _strip_html(html: str) -> str:
    """Strip HTML tags from Notes body content."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    return text.strip()
```

### `update_note`

Replaces the entire body of an existing note:

```applescript
tell application "Notes"
    set theNote to first note of folder "{folder}" of account "{account}" ¬
        whose name is "{title}"
    set body of theNote to "{escaped_body}"
end tell
```

### `note_exists`

```applescript
tell application "Notes"
    set matchCount to count of (notes of folder "{folder}" of account "{account}" ¬
        whose name is "{title}")
    return matchCount > 0
end tell
```

Returns `"true"` or `"false"` as a string; the client coerces to `bool`.

### `list_notes`

```applescript
tell application "Notes"
    set noteNames to name of every note of folder "{folder}" of account "{account}"
    return noteNames
end tell
```

Returns a comma-separated AppleScript list. The client splits on `, ` to produce
a Python list. Note titles containing commas are an edge case; titles should be
designed to avoid them (the schema uses ` — ` as a separator, never commas).

Empty folder edge case: AppleScript returns `""` (empty string) when the folder
has no notes. The client must guard against this:

```python
raw = _run_applescript(script)
titles = raw.split(", ") if raw else []
return [t for t in titles if t]  # filter spurious empty strings
```

---

## Error Types

```python
# coach/notes/exceptions.py

class NotesClientError(Exception):
    """Base class for all Notes bridge errors."""

class NoteNotFoundError(NotesClientError):
    """Raised when a requested note does not exist."""

class FolderNotFoundError(NotesClientError):
    """Raised when a target folder does not exist."""

class NotesTimeoutError(NotesClientError):
    """Raised when an osascript call exceeds the timeout."""
```

---

## Note Title Schema

Titles must be unique within a folder and are used as the primary lookup key.
AppleScript queries by exact title match.

| Note Type | Title Pattern | Example |
|---|---|---|
| Workout | `YYYY-MM-DD <Type> — <Subtitle>` | `2025-06-07 Strength — Upper Body` |
| Weekly Plan | `Week YYYY-Www` | `Week 2025-W23` |
| Assessment | `Assessment YYYY-Www` | `Assessment 2025-W23` |
| Config | `_Config` | `_Config` |
| Training Info | `_Training Info` | `_Training Info` |

The `—` character is an em dash (U+2014), used to avoid ambiguity with hyphens
in dates and type names.

---

## Performance Notes

AppleScript calls to Notes.app take approximately 200–800 ms each, depending on:
- Whether Notes.app is already running
- Number of notes in the folder
- iCloud sync activity

Mitigation strategies:
- **Batch reads at the start of a command** rather than querying per-note mid-flow.
- **Write to Notes only after local validation** passes (parser round-trip check).
- **Reporting reads local files directly** — `coach report` and `coach status` glob
  `data/workouts/*.md` and never call Notes.

---

## Testing the Bridge

Because AppleScript requires a live Notes.app, the bridge cannot be unit tested
without mocking. `MockNotesClient` lives in `tests/notes/mock_client.py` (not in
the production package) and is injected into commands via dependency injection.

```python
# tests/notes/mock_client.py
from coach.notes.client import NotesClient
from coach.notes.exceptions import NoteNotFoundError

class MockNotesClient(NotesClient):
    """In-memory mock for testing. Stores notes in a dict."""
    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def create_note(self, folder, title, body):
        self._store[(folder, title)] = body

    def get_note(self, folder, title):
        key = (folder, title)
        if key not in self._store:
            raise NoteNotFoundError(title)
        return self._store[key]

    def update_note(self, folder, title, body):
        self._store[(folder, title)] = body

    def note_exists(self, folder, title):
        return (folder, title) in self._store

    def list_notes(self, folder):
        return [t for (f, t) in self._store if f == folder]

    def ensure_folder(self, folder_path):
        pass  # no-op in tests
```

All command tests inject `MockNotesClient` via dependency injection. Integration
tests that run against real Notes are marked `@pytest.mark.integration` and skipped
in CI.

All command tests inject `MockNotesClient` via dependency injection. Integration
tests that run against real Notes are marked `@pytest.mark.integration` and skipped
in CI.
