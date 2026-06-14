"""Shared fixtures for the 13-week usability simulation."""

from __future__ import annotations

from pathlib import Path

import pytest

from coach.config import Config, DataConfig, NotesConfig, ProfileConfig, UserConfig


def make_sim_config(tmp: Path) -> Config:
    """Build a Config that points all data dirs at tmp subdirectories."""
    cfg = Config()
    cfg.user = UserConfig(name="Jason", timezone="America/New_York")
    cfg.profile = ProfileConfig(
        fitness_days_per_week=4,
        primary_goal="general fitness",
        injury_notes="",
        available_equipment=["barbell", "pull-up bar"],
        max_session_duration_minutes=45,
    )
    cfg.data = DataConfig(
        training_info=str(tmp / "training-info.md"),
        workouts_dir=str(tmp / "workouts") + "/",
        plans_dir=str(tmp / "plans") + "/",
        assessments_dir=str(tmp / "assessments") + "/",
    )
    cfg.notes = NotesConfig(plan_note_links=False)
    return cfg


@pytest.fixture(scope="session")
def sim_tmp(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped temp directory so all 13 weeks share the same file tree."""
    return tmp_path_factory.mktemp("simulation")


@pytest.fixture(scope="session")
def sim_tmp_live(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped temp directory for the live-LLM simulation run."""
    return tmp_path_factory.mktemp("simulation_live")
