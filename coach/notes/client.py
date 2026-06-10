"""Apple Notes bridge via osascript subprocess calls."""
from __future__ import annotations

import re
import subprocess

from coach.notes.exceptions import (
    FolderNotFoundError,
    NoteNotFoundError,
    NotesClientError,
    NotesTimeoutError,
)


def _escape_for_applescript(text: str) -> str:
    """Escape a string for safe interpolation into an AppleScript string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def _strip_html(html: str) -> str:
    """Strip HTML tags from Notes body content."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return text.strip()


def _run_applescript(script: str) -> str:
    """Execute an AppleScript string via osascript.

    Returns stdout stripped of trailing whitespace.
    Raises NotesTimeoutError on timeout, NotesClientError on non-zero exit.
    """
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


class NotesClient:
    """Thin wrapper around osascript for Apple Notes operations."""

    def __init__(self, account: str = "iCloud", root_folder: str = "Exercise Coach") -> None:
        self._account = account
        self._root_folder = root_folder

    # ── Folder operations ──────────────────────────────────────────────────────

    def ensure_folder(self, folder_path: str) -> None:
        """Create a folder if it does not exist. Safe to call repeatedly.

        For nested paths like "Exercise Coach/Workouts", creates the parent first.
        """
        parts = folder_path.split("/")
        # Build each level: "Exercise Coach", "Exercise Coach/Workouts", ...
        for i in range(1, len(parts) + 1):
            partial = "/".join(parts[:i])
            escaped = _escape_for_applescript(partial)
            account_esc = _escape_for_applescript(self._account)
            script = f"""
tell application "Notes"
    set acct to account "{account_esc}"
    if not (exists folder "{escaped}" of acct) then
        make new folder at acct with properties {{name:"{escaped}"}}
    end if
end tell
"""
            _run_applescript(script)

    # ── Note operations ────────────────────────────────────────────────────────

    def create_note(self, folder: str, title: str, body: str) -> None:
        """Create a new note in the given folder."""
        account_esc = _escape_for_applescript(self._account)
        folder_esc = _escape_for_applescript(folder)
        title_esc = _escape_for_applescript(title)
        body_esc = _escape_for_applescript(body)
        script = f"""
tell application "Notes"
    set targetFolder to folder "{folder_esc}" of account "{account_esc}"
    make new note at targetFolder with properties {{name:"{title_esc}", body:"{body_esc}"}}
end tell
"""
        _run_applescript(script)

    def get_note(self, folder: str, title: str) -> str:
        """Return the plaintext body of a note. Raises NoteNotFoundError if absent."""
        account_esc = _escape_for_applescript(self._account)
        folder_esc = _escape_for_applescript(folder)
        title_esc = _escape_for_applescript(title)
        script = f"""
tell application "Notes"
    set theNote to first note of folder "{folder_esc}" of account "{account_esc}" ¬
        whose name is "{title_esc}"
    return body of theNote
end tell
"""
        try:
            html = _run_applescript(script)
        except NotesClientError as e:
            if "Can't get" in str(e) or "doesn't exist" in str(e):
                raise NoteNotFoundError(title) from e
            raise
        return _strip_html(html)

    def update_note(self, folder: str, title: str, body: str) -> None:
        """Replace the entire body of an existing note."""
        account_esc = _escape_for_applescript(self._account)
        folder_esc = _escape_for_applescript(folder)
        title_esc = _escape_for_applescript(title)
        body_esc = _escape_for_applescript(body)
        script = f"""
tell application "Notes"
    set theNote to first note of folder "{folder_esc}" of account "{account_esc}" ¬
        whose name is "{title_esc}"
    set body of theNote to "{body_esc}"
end tell
"""
        try:
            _run_applescript(script)
        except NotesClientError as e:
            if "Can't get" in str(e) or "doesn't exist" in str(e):
                raise NoteNotFoundError(title) from e
            raise

    def note_exists(self, folder: str, title: str) -> bool:
        """Return True if a note with the given title exists in the folder."""
        account_esc = _escape_for_applescript(self._account)
        folder_esc = _escape_for_applescript(folder)
        title_esc = _escape_for_applescript(title)
        script = f"""
tell application "Notes"
    set matchCount to count of (notes of folder "{folder_esc}" of account "{account_esc}" ¬
        whose name is "{title_esc}")
    return matchCount > 0
end tell
"""
        result = _run_applescript(script)
        return result.lower() == "true"

    def list_notes(self, folder: str) -> list[str]:
        """Return a list of note titles in the folder."""
        account_esc = _escape_for_applescript(self._account)
        folder_esc = _escape_for_applescript(folder)
        script = f"""
tell application "Notes"
    set noteNames to name of every note of folder "{folder_esc}" of account "{account_esc}"
    return noteNames
end tell
"""
        raw = _run_applescript(script)
        titles = raw.split(", ") if raw else []
        return [t for t in titles if t]

    def delete_note(self, folder: str, title: str) -> None:
        """Delete a note by title. Raises NoteNotFoundError if absent."""
        account_esc = _escape_for_applescript(self._account)
        folder_esc = _escape_for_applescript(folder)
        title_esc = _escape_for_applescript(title)
        script = f"""
tell application "Notes"
    set theNote to first note of folder "{folder_esc}" of account "{account_esc}" ¬
        whose name is "{title_esc}"
    delete theNote
end tell
"""
        try:
            _run_applescript(script)
        except NotesClientError as e:
            if "Can't get" in str(e) or "doesn't exist" in str(e):
                raise NoteNotFoundError(title) from e
            raise
