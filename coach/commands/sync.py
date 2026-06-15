"""coach sync — discover iPhone-created workout notes and sync to local files."""

from __future__ import annotations

import contextlib
import datetime
from typing import Annotated

import typer
from rich.console import Console

from coach.config import ConfigNotFoundError, load_config
from coach.intelligence.provider import get_provider
from coach.notes.client import NotesClient
from coach.notes.exceptions import NotesClientError
from coach.notes.local import _sync_notes

console = Console()
err_console = Console(stderr=True, style="bold red")


def run(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="List what would be synced without writing")
    ] = False,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Sync only notes dated on or after YYYY-MM-DD"),
    ] = None,
) -> None:
    """Discover iPhone-created workout notes in Apple Notes and sync to local files."""
    try:
        _run_sync(dry_run=dry_run, since_str=since)
    except ConfigNotFoundError:
        err_console.print("No config found. Run 'coach setup' first.")
        raise typer.Exit(code=1)
    except NotesClientError as e:
        err_console.print(f"Apple Notes error: {e}")
        err_console.print("Is Notes running? Try opening Notes.app and retrying.")
        raise typer.Exit(code=1)


def _run_sync(
    *,
    dry_run: bool,
    since_str: str | None,
    notes_client: NotesClient | None = None,
) -> int:
    """Core sync logic, injectable for testing. Returns synced count."""
    cfg = load_config()

    since: datetime.date | None = None
    if since_str:
        try:
            since = datetime.date.fromisoformat(since_str)
        except ValueError:
            err_console.print(f"Invalid --since date: {since_str!r} (expected YYYY-MM-DD)")
            raise typer.Exit(code=1)

    client = notes_client or NotesClient(account=cfg.notes.account, root_folder=cfg.notes.folder)

    provider = None
    with contextlib.suppress(Exception):
        provider = get_provider(cfg)

    return _sync_notes(
        cfg,
        client,
        since=since,
        verbose=True,
        provider=provider,
        dry_run=dry_run,
    )
