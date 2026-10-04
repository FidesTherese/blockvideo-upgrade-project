"""D37 projection accepts the partial D24 states the development seed accepts."""
from __future__ import annotations

import json

from evaluation.blinded_runner import case_to_unlabeled
from evaluation.contracts import Case
from evaluation.projection_diagnostics import projection_failure
from tests.test_d37_blinded_runner import _score_case


def _with_initial(case: Case, **changes: object) -> Case:
    return case.model_copy(update={"initial": case.initial.model_copy(update=changes)})


def test_partial_job_and_history_settings_complete_from_owner_settings() -> None:
    base = _score_case("none")
    case = _with_initial(
        base,
        revision=3,
        jobs=[{"id": 7, "project_id": 1, "status": "failed", "input_revision": 2,
               "cancel_requested": False, "input_settings": {"subtitle_font_size": 40}}],
        history=[{"revision": 2, "settings": {"subtitle_font_size": 44}}],
    )

    projected = case_to_unlabeled(case)

    current = projected.initial.settings
    job = projected.initial.jobs[0]
    assert job.input_settings.subtitle_font_size == 40
    assert job.input_settings.voicevox_speed_scale == current.voicevox_speed_scale
    assert job.input_settings.narration_sentence_pause_seconds == 0.2
    assert job.kind == "full"
    history = projected.initial.history[0].settings
    assert history.subtitle_font_size == 44
    assert history.voicevox_speaker_id == current.voicevox_speaker_id


def test_other_project_jobs_seed_a_default_project_like_the_development_seed() -> None:
    case = _with_initial(
        _score_case("none"),
        jobs=[{"id": 9, "project_id": 5, "status": "running", "input_revision": 4,
               "cancel_requested": False, "kind": "full",
               "input_settings": {"subtitle_font_size": 60}}],
    )

    projected = case_to_unlabeled(case)

    (other,) = projected.initial.additional_projects
    assert (other.project_id, other.revision, other.project_status) == (5, 4, "generating")
    assert other.settings.subtitle_font_size == 60
    assert other.settings.voicevox_speed_scale == 1.0
    assert projected.initial.jobs[0].input_settings == other.settings


def test_prior_turn_identity_defaults_to_the_selected_project() -> None:
    case = _with_initial(
        _score_case("none"),
        revision=2,
        prior_turns=[
            {"request_id": "turn-1", "text": "synthetic earlier turn", "status": "needs_input",
             "question": "どのくらいにしますか？"},
            {"request_id": "turn-2", "text": "synthetic answer", "status": "completed",
             "settings_saved": True, "result_revision": 2},
        ],
    )

    first, second = case_to_unlabeled(case).initial.prior_turns

    assert (first.project_id, first.base_revision, first.settings_saved) == (1, 2, False)
    assert (second.project_id, second.base_revision, second.settings_saved) == (1, 1, True)


def test_projection_failure_report_is_structural_and_content_free() -> None:
    secret = "秘密の依頼文"
    base = _score_case("revision_race")
    case = base.model_copy(update={
        "event": base.event.model_copy(update={"details": {"competing": secret}}),
        "initial": base.initial.model_copy(update={"prior_turns": [
            {"request_id": "turn-1", "text": secret, "status": secret}
        ]}),
    })

    report = projection_failure(case)

    assert report is not None
    assert report["error"] == "missing_key"
    assert report["missing_key"] == "external_revision"
    assert report["event_detail_keys"] == ["competing"]
    assert report["prior_turns"][0]["status"] == "<redacted>"
    assert secret not in json.dumps(report, ensure_ascii=False)
    assert projection_failure(_score_case("none")) is None
