"""Unit tests for coach/notes/sqlite.py"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import coach.notes.sqlite as sqlite_mod
from coach.notes.sqlite import _url_id, lookup_uuids, note_link


@pytest.fixture(autouse=True)
def reset_fda_warned() -> None:
    sqlite_mod._fda_warned = False


# ── _url_id ───────────────────────────────────────────────────────────────────


def test_url_id_p_prefix() -> None:
    assert _url_id("x-coredata://UUID/ICNote/p123") == "123"


def test_url_id_no_p_prefix() -> None:
    assert _url_id("x-coredata://UUID/ICNote/456") == "456"


def test_url_id_empty() -> None:
    assert _url_id("") == ""


def test_url_id_no_slash() -> None:
    # Without a "/" rpartition returns the whole string as the last segment.
    # "p123" starts with "p", so the "p" is stripped → "123".
    assert _url_id("p123") == "123"


def test_url_id_p_only() -> None:
    assert _url_id("x-coredata://UUID/ICNote/p") == ""


# ── lookup_uuids ──────────────────────────────────────────────────────────────


def test_lookup_uuids_empty_list() -> None:
    assert lookup_uuids([]) == {}


def test_lookup_uuids_non_digit_keys() -> None:
    assert lookup_uuids(["abc", "xyz"]) == {}


def test_lookup_uuids_permission_error() -> None:
    """PermissionError on NoteStore copy returns {} and prints a one-time warning."""
    with (
        patch("coach.notes.sqlite.shutil.copy2", side_effect=PermissionError("denied")),
        patch("coach.notes.sqlite.NOTESTORE") as mock_path,
    ):
        mock_path.exists.return_value = True
        result = lookup_uuids(["123"])
    assert result == {}
    assert sqlite_mod._fda_warned is True


def test_lookup_uuids_permission_error_warns_once() -> None:
    """Warning is printed only once across multiple calls."""
    with (
        patch("coach.notes.sqlite.shutil.copy2", side_effect=PermissionError("denied")),
        patch("coach.notes.sqlite.NOTESTORE") as mock_path,
    ):
        mock_path.exists.return_value = True
        lookup_uuids(["123"])
        lookup_uuids(["456"])
    assert sqlite_mod._fda_warned is True


def test_lookup_uuids_mocked_db(tmp_path: Path) -> None:
    """Happy path: temp DB copy returns Z_PK → ZIDENTIFIER mapping."""
    db_path = tmp_path / "NoteStore.sqlite"
    with sqlite3.connect(str(db_path)) as con:
        con.execute("CREATE TABLE ZICCLOUDSYNCINGOBJECT (Z_PK INTEGER, ZIDENTIFIER TEXT)")
        con.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES (123, 'STABLE-UUID-1')")
        con.execute("INSERT INTO ZICCLOUDSYNCINGOBJECT VALUES (456, 'STABLE-UUID-2')")

    with patch("coach.notes.sqlite.NOTESTORE", db_path):
        result = lookup_uuids(["123", "456", "999"])

    assert result == {"123": "STABLE-UUID-1", "456": "STABLE-UUID-2"}
    assert "999" not in result


def test_lookup_uuids_notestore_missing() -> None:
    """Returns {} when NoteStore.sqlite does not exist."""
    with patch("coach.notes.sqlite.NOTESTORE") as mock_path:
        mock_path.exists.return_value = False
        result = lookup_uuids(["123"])
    assert result == {}


# ── note_link ─────────────────────────────────────────────────────────────────


def test_note_link_with_uuid() -> None:
    link = note_link("Upper Body Push", "x-coredata://UUID/ICNote/p123", uuid="MY-UUID")
    assert 'href="applenotes://showNote?identifier=MY-UUID"' in link
    assert "Upper Body Push" in link
    assert link.startswith("<a ")


def test_note_link_numeric_fallback() -> None:
    link = note_link("Zone 2 Run", "x-coredata://UUID/ICNote/p456")
    assert 'href="applenotes://showNote?identifier=456"' in link
    assert "Zone 2 Run" in link


def test_note_link_no_id() -> None:
    result = note_link("Rest Day", "")
    assert result == "Rest Day"
    assert "<a" not in result


def test_note_link_escapes_html_in_title() -> None:
    result = note_link("Strength & Power", "x-coredata://UUID/ICNote/p1")
    assert "&amp;" in result
    assert "<a" in result
