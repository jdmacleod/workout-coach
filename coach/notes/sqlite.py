"""NoteStore.sqlite helpers for looking up stable Apple Notes UUIDs."""

from __future__ import annotations

import html as _html
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

NOTESTORE = Path.home() / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite"

_fda_warned: bool = False


def _url_id(xcoredata_id: str) -> str:
    """Extract numeric PK string from an x-coredata URI.

    "x-coredata://UUID/ICNote/p123" → "123"
    """
    raw = xcoredata_id.rpartition("/")[2] if xcoredata_id else ""
    return raw[1:] if raw.startswith("p") else raw


def lookup_uuids(primary_keys: list[str]) -> dict[str, str]:
    """Query NoteStore.sqlite for stable iCloud UUIDs given numeric PK strings.

    Returns a dict mapping pk_str → ZIDENTIFIER UUID. Returns {} on
    PermissionError (Full Disk Access not granted to Terminal), printing a
    one-time warning. Makes a temp copy of the DB (including WAL/SHM files)
    to avoid lock contention with Notes.app.
    """
    global _fda_warned
    valid_keys = [pk for pk in primary_keys if pk.isdigit()]
    if not valid_keys or not NOTESTORE.exists():
        return {}
    try:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            tmp = Path(f.name)
        shutil.copy2(NOTESTORE, tmp)
        for ext in ("-wal", "-shm"):
            src = Path(str(NOTESTORE) + ext)
            if src.exists():
                shutil.copy2(src, Path(str(tmp) + ext))
        placeholders = ",".join("?" * len(valid_keys))
        with sqlite3.connect(str(tmp)) as con:
            rows = con.execute(
                f"SELECT Z_PK, ZIDENTIFIER FROM ZICCLOUDSYNCINGOBJECT"
                f" WHERE Z_PK IN ({placeholders})",
                [int(pk) for pk in valid_keys],
            ).fetchall()
        tmp.unlink(missing_ok=True)
        return {str(pk): uuid for pk, uuid in rows if uuid}
    except PermissionError:
        if not _fda_warned:
            _fda_warned = True
            print(
                "Warning: Full Disk Access not granted to Terminal — "
                "plan note will use numeric note IDs instead of stable UUIDs.\n"
                "Grant access in System Settings → Privacy & Security → Full Disk Access.",
                file=sys.stderr,
            )
        return {}
    except Exception:
        return {}


def note_link(title: str, xcoredata_id: str, uuid: str = "") -> str:
    """Return an HTML <a> link targeting the given note in Apple Notes.

    Prefers the stable iCloud UUID (from NoteStore.sqlite) over the numeric
    fallback extracted from the x-coredata URI. Falls back to plain escaped
    text if neither is available.

    applenotes://showNote?identifier= renders as a clickable link in Apple Notes
    even though reading body back via AppleScript shows only <u>Title</u>.
    """
    escaped = _html.escape(title)
    identifier = uuid or _url_id(xcoredata_id)
    if not identifier:
        return escaped
    return f'<a href="applenotes://showNote?identifier={identifier}">{escaped}</a>'
