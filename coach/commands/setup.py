"""coach setup — first-time initialization."""
from __future__ import annotations

import platform
import shutil
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from coach.config import (
    CONFIG_DIR,
    CONFIG_EXAMPLE,
    CONFIG_FILE,
    DATA_DIR,
    EXAMPLES_DIR,
    PROJECT_ROOT,
    ConfigError,
    ConfigNotFoundError,
    load_config,
)
from coach.notes.exceptions import NotesClientError

console = Console()
err_console = Console(stderr=True, style="bold red")

app = typer.Typer(invoke_without_command=True, help="First-time initialization and configuration.")


@app.callback()
def run(
    non_interactive: Annotated[bool, typer.Option("--non-interactive", help="Skip questionnaire; use config.toml as-is")] = False,
    reset: Annotated[bool, typer.Option("--reset", help="Re-run setup even if already configured")] = False,
) -> None:
    """First-time initialization. Creates config, data directories, and Notes folder structure."""
    try:
        _run_setup(non_interactive=non_interactive, reset=reset)
    except ConfigError as e:
        err_console.print(f"Configuration error: {e}")
        raise typer.Exit(code=1)
    except NotesClientError as e:
        err_console.print(f"Apple Notes error: {e}")
        err_console.print("Is Notes running? Try opening Notes.app and retrying.")
        raise typer.Exit(code=1)


def _run_setup(*, non_interactive: bool, reset: bool) -> None:
    if CONFIG_FILE.exists() and not reset:
        console.print(f"[green]Config already exists at {CONFIG_FILE}[/green]")
        console.print("Run [bold]coach setup --reset[/bold] to reconfigure.")
        return

    # Step 1: Copy config example if missing
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        shutil.copy(CONFIG_EXAMPLE, CONFIG_FILE)
        console.print(f"Created config at [bold]{CONFIG_FILE}[/bold]")

    # Step 2: Create data directories
    for subdir in ("workouts", "plans", "assessments"):
        (DATA_DIR / subdir).mkdir(parents=True, exist_ok=True)
    console.print(f"Created data directories under [bold]{DATA_DIR}[/bold]")

    if not non_interactive:
        _run_questionnaire()

    # Step 3: Copy training-info example if missing
    training_info = DATA_DIR / "training-info.md"
    if not training_info.exists():
        shutil.copy(EXAMPLES_DIR / "training-info.md", training_info)
        console.print(f"Copied example training info to [bold]{training_info}[/bold]")
        console.print("Edit [bold]data/training-info.md[/bold] to describe your training.")

    # Step 4: Detect macOS version and show provider table
    _show_provider_table()

    # Step 5: Create Apple Notes folder structure
    console.print("\n[bold]Setting up Apple Notes folders...[/bold]")
    _setup_notes_folders()

    console.print("\n[green bold]Setup complete![/green bold]")
    console.print("Next: edit [bold]data/training-info.md[/bold], then run [bold]coach plan[/bold]")


def _run_questionnaire() -> None:
    """Interactive questionnaire to populate config.toml."""
    console.print("\n[bold]Let's configure Exercise Coach.[/bold]")

    name = typer.prompt("Your name", default="")
    days = typer.prompt("How many days per week do you currently train?", default="4")
    goal = typer.prompt(
        "Primary training goal (strength / endurance / general fitness / weight loss / sport-specific)",
        default="general fitness",
    )
    injuries = typer.prompt("Any injuries or limitations? (leave blank if none)", default="")

    _write_config_values(name=name, days=days, goal=goal, injuries=injuries)
    console.print("[green]Config updated.[/green]")


def _write_config_values(*, name: str, days: str, goal: str, injuries: str) -> None:
    """Update key fields in config.toml."""
    text = CONFIG_FILE.read_text()

    def _set(text: str, key: str, value: str) -> str:
        import re
        pattern = rf'^({re.escape(key)}\s*=\s*).*$'
        replacement = rf'\g<1>"{value}"'
        new_text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
        return new_text

    text = _set(text, "name", name)
    text = _set(text, "primary_goal", goal)
    text = _set(text, "injury_notes", injuries)

    # fitness_days_per_week is an integer, no quotes
    import re
    text = re.sub(
        r'^(fitness_days_per_week\s*=\s*).*$',
        rf'\g<1>{days}',
        text,
        flags=re.MULTILINE,
    )
    CONFIG_FILE.write_text(text)


def _show_provider_table() -> None:
    """Display a table of provider availability."""
    ver_str = platform.mac_ver()[0]
    macos_major = 0
    if ver_str:
        try:
            macos_major = int(ver_str.split(".")[0])
        except (ValueError, IndexError):
            pass

    table = Table(title="Inference Provider Availability", show_header=True)
    table.add_column("Provider")
    table.add_column("Available")
    table.add_column("Note")

    swift_binary = (PROJECT_ROOT / "swift/.build/release/CoachInfer").exists()
    swift_ok = macos_major >= 26 and swift_binary
    table.add_row(
        "swift (Foundation Models)",
        "[green]Yes[/green]" if swift_ok else "[red]No[/red]",
        "macOS 26+ required" if macos_major < 26 else ("binary missing — run swift build" if not swift_binary else "ready"),
    )

    import os
    anthropic_ok = bool(os.environ.get("ANTHROPIC_API_KEY"))
    table.add_row(
        "anthropic",
        "[green]Yes[/green]" if anthropic_ok else "[yellow]Maybe[/yellow]",
        "Set ANTHROPIC_API_KEY to enable",
    )

    table.add_row("ollama", "[yellow]Unknown[/yellow]", "Run: brew install ollama")
    table.add_row("llamacpp", "[yellow]Unknown[/yellow]", "Requires local server")

    console.print(table)

    if macos_major >= 26 and not swift_binary:
        console.print(
            "\n[bold]Tip:[/bold] Build the Swift inference binary with:\n"
            "  cd swift && swift build -c release"
        )


def _setup_notes_folders() -> None:
    """Create Apple Notes folder structure."""
    try:
        from coach.notes.client import NotesClient
        from coach.notes.schema import FOLDER_ASSESSMENTS, FOLDER_PLANS, FOLDER_ROOT, FOLDER_WORKOUTS

        cfg = load_config()
        client = NotesClient(account=cfg.notes.account, root_folder=cfg.notes.folder)
        for folder in (FOLDER_ROOT, FOLDER_PLANS, FOLDER_WORKOUTS, FOLDER_ASSESSMENTS):
            client.ensure_folder(folder)
            console.print(f"  [green]✓[/green] {folder}")
    except ConfigNotFoundError:
        pass  # config not yet written; skip Notes setup
    except NotesClientError as e:
        console.print(f"  [yellow]Warning:[/yellow] Could not create Notes folders: {e}")
        console.print("  You can re-run [bold]coach setup[/bold] once Notes.app is running.")
