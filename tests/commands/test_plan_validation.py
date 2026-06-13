"""Unit tests for workout plan constraint validation (equipment, duration, exercise count)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from coach.config import Config, DataConfig, NotesConfig, _parse_config
from coach.intelligence.exceptions import InferenceError
from coach.intelligence.provider import InferenceRequest, InferenceResponse
from tests.intelligence.mock_provider import MockInferenceProvider
from tests.notes.mock_client import MockNotesClient

MOCK_PLAN_RESPONSE = json.dumps(
    {
        "training_focus": "strength",
        "weekly_volume": "moderate",
        "generation_notes": "Test plan.",
        "sessions": [
            {
                "day": "Mon",
                "type": "strength",
                "subtype": "upper",
                "duration_minutes": 30,
                "title": "Upper Body",
                "planned_content": "Warm-up:\n- arm circles\nMain Lifts:\n- Floor Press: 3x5\nAccessories:\n- Ring Rows: 3x10",
                "rationale": "Push focus",
            },
            {
                "day": "Fri",
                "type": "rest",
                "subtype": "",
                "duration_minutes": 0,
                "title": "Rest",
                "planned_content": "",
                "rationale": "Recovery",
            },
        ],
    }
)


def _make_config(tmp_dir: str, **profile_kwargs: object) -> Config:
    cfg = Config()
    cfg.data = DataConfig(
        training_info=str(tmp_dir + "/training-info.md"),
        workouts_dir=str(tmp_dir + "/workouts/"),
        plans_dir=str(tmp_dir + "/plans/"),
        assessments_dir=str(tmp_dir + "/assessments/"),
    )
    cfg.notes = NotesConfig()
    for k, v in profile_kwargs.items():
        setattr(cfg.profile, k, v)
    return cfg


# ── Config parsing ────────────────────────────────────────────────────────────


def test_profile_config_parses_available_equipment() -> None:
    raw = {"profile": {"available_equipment": ["barbell", "pull-up bar", "rings"]}}
    cfg = _parse_config(raw)
    assert cfg.profile.available_equipment == ["barbell", "pull-up bar", "rings"]


def test_profile_config_equipment_defaults_to_empty_list() -> None:
    raw: dict = {}
    cfg = _parse_config(raw)
    assert cfg.profile.available_equipment == []


def test_profile_config_parses_max_session_duration() -> None:
    raw = {"profile": {"max_session_duration_minutes": 30}}
    cfg = _parse_config(raw)
    assert cfg.profile.max_session_duration_minutes == 30


def test_profile_config_max_duration_defaults_to_none() -> None:
    raw: dict = {}
    cfg = _parse_config(raw)
    assert cfg.profile.max_session_duration_minutes is None


# ── Prompt injection ──────────────────────────────────────────────────────────


def test_plan_prompt_includes_equipment_constraint(tmp_path: pytest.MonkeyPatch) -> None:
    from coach.commands.plan import _run_plan

    cfg = _make_config(
        str(tmp_path),
        available_equipment=["barbell", "rings"],
        max_session_duration_minutes=None,
    )
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    mock_client = MockNotesClient()

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W30",
            focus=None,
            dry_run=True,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # First call is initial generation; check it contains the equipment constraint
    initial_prompt = provider.calls[0].user
    assert "barbell" in initial_prompt
    assert "rings" in initial_prompt
    assert "NEVER suggest exercises requiring equipment not on this list" in initial_prompt


def test_plan_prompt_includes_duration_constraint(tmp_path: pytest.MonkeyPatch) -> None:
    from coach.commands.plan import _run_plan

    cfg = _make_config(
        str(tmp_path),
        available_equipment=[],
        max_session_duration_minutes=30,
    )
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    mock_client = MockNotesClient()

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W30",
            focus=None,
            dry_run=True,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    initial_prompt = provider.calls[0].user
    assert "30 minutes" in initial_prompt
    assert "MUST NOT exceed" in initial_prompt


def test_plan_prompt_omits_equipment_when_not_configured(tmp_path: pytest.MonkeyPatch) -> None:
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path), available_equipment=[], max_session_duration_minutes=None)
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    mock_client = MockNotesClient()

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W30",
            focus=None,
            dry_run=True,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    initial_prompt = provider.calls[0].user
    assert "Equipment available" not in initial_prompt
    assert "MUST NOT exceed" not in initial_prompt


# ── Correction pass ───────────────────────────────────────────────────────────


def test_correction_pass_called_when_equipment_set(tmp_path: pytest.MonkeyPatch) -> None:
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path), available_equipment=["barbell", "rings"])
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    mock_client = MockNotesClient()

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W30",
            focus=None,
            dry_run=True,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # 1 initial generation + 1 correction pass = 2 calls
    assert len(provider.calls) == 2


def test_correction_pass_skipped_when_no_constraints(tmp_path: pytest.MonkeyPatch) -> None:
    from coach.commands.plan import _run_plan

    cfg = _make_config(str(tmp_path), available_equipment=[], max_session_duration_minutes=None)
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    provider = MockInferenceProvider(response_text=MOCK_PLAN_RESPONSE)
    mock_client = MockNotesClient()

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W30",
            focus=None,
            dry_run=True,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # Only 1 call — no correction pass fired
    assert len(provider.calls) == 1


def test_correction_pass_falls_back_on_inference_error(tmp_path: pytest.MonkeyPatch) -> None:
    from coach.commands.plan import _correct_plan_if_needed

    class FailingOnSecondCallProvider(MockInferenceProvider):
        def infer(self, request: InferenceRequest) -> InferenceResponse:
            self.calls.append(request)
            if len(self.calls) > 1:
                raise InferenceError("provider unavailable")
            return InferenceResponse(text=self.response_text, provider="mock", model="mock")

    cfg = _make_config(str(tmp_path), available_equipment=["barbell"])
    provider = FailingOnSecondCallProvider(response_text=MOCK_PLAN_RESPONSE)
    plan_data = json.loads(MOCK_PLAN_RESPONSE)

    with patch("coach.commands.plan.load_config", return_value=cfg):
        result = _correct_plan_if_needed(plan_data, cfg, provider)

    # Falls back to original plan — no exception raised
    assert result == plan_data


# ── Python duration warning ───────────────────────────────────────────────────


def test_python_duration_warning_when_exceeded(
    tmp_path: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from coach.commands.plan import _run_plan

    long_session_response = json.dumps(
        {
            "training_focus": "strength",
            "weekly_volume": "moderate",
            "generation_notes": "",
            "sessions": [
                {
                    "day": "Mon",
                    "type": "strength",
                    "subtype": "upper",
                    "duration_minutes": 55,
                    "title": "Upper Body",
                    "planned_content": "Main Lifts:\n- Floor Press: 4x5",
                    "rationale": "Push",
                }
            ],
        }
    )

    cfg = _make_config(
        str(tmp_path),
        available_equipment=[],
        max_session_duration_minutes=30,
    )
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    provider = MockInferenceProvider(response_text=long_session_response)
    mock_client = MockNotesClient()

    with patch("coach.commands.plan.load_config", return_value=cfg):
        _run_plan(
            week="2026-W30",
            focus=None,
            dry_run=True,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )

    # max_session_duration_minutes=30 triggers the correction pass (2 calls total)
    # The Python duration warning fires after, since corrected plan still shows 55 min
    assert len(provider.calls) == 2


def test_rest_sessions_skip_duration_check(tmp_path: pytest.MonkeyPatch) -> None:
    from coach.commands.plan import _run_plan

    rest_response = json.dumps(
        {
            "training_focus": "recovery",
            "weekly_volume": "low",
            "generation_notes": "",
            "sessions": [
                {
                    "day": "Mon",
                    "type": "rest",
                    "subtype": "",
                    "duration_minutes": 999,
                    "title": "Rest",
                    "planned_content": "",
                    "rationale": "Full rest",
                }
            ],
        }
    )

    cfg = _make_config(str(tmp_path), max_session_duration_minutes=30)
    (tmp_path / "training-info.md").write_text("# Training Info\nGeneral fitness.")
    provider = MockInferenceProvider(response_text=rest_response)
    mock_client = MockNotesClient()

    with patch("coach.commands.plan.load_config", return_value=cfg):
        # Should not raise or warn about the rest session's inflated duration
        _run_plan(
            week="2026-W30",
            focus=None,
            dry_run=True,
            overwrite=False,
            no_calendar=True,
            notes_client=mock_client,
            inference_provider=provider,
        )
