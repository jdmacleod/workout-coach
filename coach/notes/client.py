"""Apple Notes bridge via osascript subprocess calls."""

from __future__ import annotations

import re
import subprocess

from coach.notes.exceptions import (
    NoteNotFoundError,
    NotesClientError,
    NotesTimeoutError,
)


def _escape_for_applescript(text: str) -> str:
    """Escape a string for safe interpolation into an AppleScript string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def _strip_html(html: str) -> str:
    """Strip HTML tags from Notes body content.

    Converts semantic heading/list tags to Markdown-equivalent text before
    stripping so that parse_sections() and parse_front_matter() can process
    the result the same way they handle locally-stored plaintext files.
    Newlines are injected around block elements so lines don't run together.
    """
    text = html
    text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<li[^>]*>(.*?)</li>", r"\n- \1", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _folder_script_lines(folder_path: str, account_esc: str) -> list[str]:
    """Return AppleScript lines that walk a slash-separated path, setting `targetFolder`.

    For "Exercise Coach/Assessments" this produces:
        set acct to account "iCloud"
        set targetFolder to folder "Exercise Coach" of acct
        set targetFolder to folder "Assessments" of targetFolder
    """
    parts = [p for p in folder_path.split("/") if p]
    first_esc = _escape_for_applescript(parts[0])
    lines = [
        f'    set acct to account "{account_esc}"',
        f'    set targetFolder to folder "{first_esc}" of acct',
    ]
    for part in parts[1:]:
        part_esc = _escape_for_applescript(part)
        lines.append(f'    set targetFolder to folder "{part_esc}" of targetFolder')
    return lines


def _is_not_found_error(exc: Exception) -> bool:
    """Return True for any AppleScript error that means a folder or note was not found.

    Notes.app returns error -1728 (Can't get object) for all missing-item lookups,
    but the human-readable prefix varies by macOS version:
      - "Can't get folder ..."      (macOS 14/15)
      - "Can't find item ..."       (macOS 16+)
      - "doesn't exist"
      - "was not found"
    Matching on the numeric code (-1728) catches all variants regardless of phrasing.
    """
    msg = str(exc)
    return (
        "Can't get" in msg
        or "doesn't exist" in msg
        or "Can't find" in msg
        or "was not found" in msg
        or "(-1728)" in msg
    )


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
        """Create a folder (or nested hierarchy) if it does not exist.

        For nested paths like "Exercise Coach/Workouts", each component is
        created at its parent rather than as a flat name with slashes.
        """
        parts = [p for p in folder_path.split("/") if p]
        if not parts:
            return

        account_esc = _escape_for_applescript(self._account)
        first_esc = _escape_for_applescript(parts[0])

        lines = [
            'tell application "Notes"',
            f'    set acct to account "{account_esc}"',
            f'    if not (exists folder "{first_esc}" of acct) then',
            f'        make new folder at acct with properties {{name:"{first_esc}"}}',
            "    end if",
            f'    set currentParent to folder "{first_esc}" of acct',
        ]
        for part in parts[1:]:
            part_esc = _escape_for_applescript(part)
            lines += [
                f'    if not (exists folder "{part_esc}" of currentParent) then',
                f'        make new folder at currentParent with properties {{name:"{part_esc}"}}',
                "    end if",
                f'    set currentParent to folder "{part_esc}" of currentParent',
            ]
        lines.append("end tell")
        _run_applescript("\n".join(lines))

    # ── Note operations ────────────────────────────────────────────────────────

    def create_note(self, folder: str, title: str, body: str) -> None:
        """Create a new note in the given folder."""
        account_esc = _escape_for_applescript(self._account)
        title_esc = _escape_for_applescript(title)
        body_esc = _escape_for_applescript(body)
        setup = "\n".join(_folder_script_lines(folder, account_esc))
        script = f"""tell application "Notes"
{setup}
    make new note at targetFolder with properties {{name:"{title_esc}", body:"{body_esc}"}}
end tell
"""
        _run_applescript(script)

    def get_note(self, folder: str, title: str) -> str:
        """Return the plaintext body of a note. Raises NoteNotFoundError if absent."""
        account_esc = _escape_for_applescript(self._account)
        title_esc = _escape_for_applescript(title)
        setup = "\n".join(_folder_script_lines(folder, account_esc))
        script = f"""tell application "Notes"
{setup}
    set theNote to first note of targetFolder whose name is "{title_esc}"
    return body of theNote
end tell
"""
        try:
            html = _run_applescript(script)
        except NotesClientError as e:
            if _is_not_found_error(e):
                raise NoteNotFoundError(title) from e
            raise
        return _strip_html(html)

    def update_note(self, folder: str, title: str, body: str) -> None:
        """Replace the entire body of an existing note."""
        account_esc = _escape_for_applescript(self._account)
        title_esc = _escape_for_applescript(title)
        body_esc = _escape_for_applescript(body)
        setup = "\n".join(_folder_script_lines(folder, account_esc))
        script = f"""tell application "Notes"
{setup}
    set theNote to first note of targetFolder whose name is "{title_esc}"
    set body of theNote to "{body_esc}"
end tell
"""
        try:
            _run_applescript(script)
        except NotesClientError as e:
            if _is_not_found_error(e):
                raise NoteNotFoundError(title) from e
            raise

    def note_exists(self, folder: str, title: str) -> bool:
        """Return True if a note with the given title exists in the folder."""
        account_esc = _escape_for_applescript(self._account)
        title_esc = _escape_for_applescript(title)
        setup = "\n".join(_folder_script_lines(folder, account_esc))
        script = f"""tell application "Notes"
{setup}
    set matchCount to count of (notes of targetFolder whose name is "{title_esc}")
    return matchCount > 0
end tell
"""
        try:
            result = _run_applescript(script)
        except NotesClientError as e:
            if _is_not_found_error(e):
                return False
            raise
        return result.lower() == "true"

    def list_notes(self, folder: str) -> list[str]:
        """Return a list of note titles in the folder."""
        account_esc = _escape_for_applescript(self._account)
        setup = "\n".join(_folder_script_lines(folder, account_esc))
        script = f"""tell application "Notes"
{setup}
    set noteNames to name of every note of targetFolder
    return noteNames
end tell
"""
        try:
            raw = _run_applescript(script)
        except NotesClientError as e:
            if _is_not_found_error(e):
                return []
            raise
        titles = raw.split(", ") if raw else []
        return [t for t in titles if t]

    def delete_note(self, folder: str, title: str) -> None:
        """Delete a note by title. Raises NoteNotFoundError if absent."""
        account_esc = _escape_for_applescript(self._account)
        title_esc = _escape_for_applescript(title)
        setup = "\n".join(_folder_script_lines(folder, account_esc))
        script = f"""tell application "Notes"
{setup}
    set theNote to first note of targetFolder whose name is "{title_esc}"
    delete theNote
end tell
"""
        try:
            _run_applescript(script)
        except NotesClientError as e:
            if _is_not_found_error(e):
                raise NoteNotFoundError(title) from e
            raise
