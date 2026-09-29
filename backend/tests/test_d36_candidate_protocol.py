from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError

from evaluation.unlabeled_contracts import MAX_REVISION, UnlabeledTrialCase, canonical_case_sha256
from evaluation.scripts import evaluation_trial_host as trial_host
from evaluation.scripts.evaluation_trial_host import run_trial_host


PROTOCOL = (
    b'{"schema_version":1,"modes":["all_tools","stateful"],'
    b'"per_call_deadline_seconds":180,"maximum_model_calls":4,'
    b'"isolation":"fresh_case_state_under_source_group",'
    b'"scoring_owner":"external_evaluator"}'
)
FORBIDDEN_FIELDS = {
    "expected",
    "accepted_answers",
    "accepted_operations",
    "labels",
    "review_status",
    "review_ledger",
    "scoring_labels",
}


def _case() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "case_id": "D24-H001",
        "group_id": "D24-HG01",
        "category": "paraphrase",
        "split": "held_out",
        "event": {
            "kind": "none",
            "request": {
                "request_id": "held-out-request",
                "text": "字幕を64pxにして",
                "target_project_id": 101,
                "base_revision": 5,
                "continuation": None,
            },
        },
        "initial": {
            "project_id": 101,
            "revision": 5,
            "settings": {
                "subtitle_font_size": 48,
                "voicevox_speed_scale": 1.0,
                "voicevox_speaker_id": 0,
                "pronunciation_overrides": [],
                "narration_pacing_mode": "adaptive",
                "narration_sentence_pause_seconds": 1.5,
            },
            "project_status": "completed",
            "jobs": [],
            "history": [],
            "artifact_revisions": [2, 4],
            "prior_turns": [],
        },
        "case_sha256": "0" * 64,
    }


def _bound_case() -> dict[str, Any]:
    value = _case()
    value["case_sha256"] = canonical_case_sha256(value)
    return value


def _maximum_seed_case() -> dict[str, Any]:
    value = _case()
    settings = value["initial"]["settings"]
    value["initial"].update({
        "revision": 100,
        "additional_projects": [
            {
                "project_id": project_id,
                "revision": 100,
                "settings": settings,
                "project_status": "completed",
            }
            for project_id in range(200, 216)
        ],
        "jobs": [
            {
                "id": item_id,
                "project_id": 101,
                "status": "failed",
                "input_revision": 100,
                "cancel_requested": False,
                "input_settings": settings,
                "kind": "full",
                "block_index": None,
                "parent_job_id": item_id - 1 if item_id > 1 else None,
            }
            for item_id in range(1, 33)
        ],
        "history": [
            {
                "project_id": 101,
                "revision": revision,
                "settings": settings,
                "changed_fields": [],
                "restored_from_revision": 1 if revision > 1 else None,
            }
            for revision in range(1, 33)
        ],
        "artifact_revisions": list(range(1, 33)),
        "artifacts": [
            {
                "id": item_id,
                "project_id": 101,
                "job_id": None,
                "revision": item_id - 99,
                "file_content_hex": "78",
                "file_size": 1,
                "file_sha256": hashlib.sha256(b"x").hexdigest(),
            }
            for item_id in range(100, 132)
        ],
        "external_calls": [
            {
                "id": item_id,
                "job_id": item_id,
                "fingerprint": f"seed-call-{item_id}",
                "provider": "synthetic",
                "endpoint": "https://synthetic.invalid/d36",
                "remote_side_effect": False,
                "status": "failed",
                "attempts": 1,
                "response_status": None,
                "response_body_hex": None,
                "response_body_sha256": None,
                "response_content_type": None,
                "provider_response_id": None,
                "error_code": "synthetic_failure",
            }
            for item_id in range(1, 33)
        ],
        "prior_turns": [
            {
                "request_id": f"prior-{item_id}",
                "project_id": 101,
                "base_revision": 100,
                "status": "needs_input",
                "question": "値は？",
                "result_revision": None,
                "settings_saved": False,
                "proposal": None,
                "text": "字幕を変更",
                "relation": None if item_id == 1 else "answer",
                "parent_request_id": f"prior-{item_id - 1}" if item_id > 1 else None,
                "successor_request_id": f"prior-{item_id + 1}" if item_id < 8 else None,
            }
            for item_id in range(1, 9)
        ],
    })
    receipts = []
    for item_id in range(1, 33):
        canonical_request = json.dumps(
            {
                "operation_id": "project.status.get",
                "operation_version": 1,
                "project_id": 101,
                "base_revision": 100,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        result = {
            "operation_id": "project.status.get",
            "project_id": 101,
            "revision": 100,
            "changed": False,
        }
        receipts.append({
            "request_id": f"seed-receipt-{item_id}",
            "operation_id": "project.status.get",
            "operation_version": 1,
            "project_id": 101,
            "base_revision": 100,
            "result_revision": 100,
            "generation_requested": False,
            "job_id": item_id,
            "canonical_request_sha256": hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            "result_sha256": trial_host._hash(result),
        })
    value["initial"]["receipts"] = receipts
    value["initial"]["current_artifact_id"] = 163
    value["event"]["request"]["base_revision"] = 100
    value["case_sha256"] = canonical_case_sha256(value)
    return value


def _seed_graph_case() -> dict[str, Any]:
    value = _case()
    settings = value["initial"]["settings"]
    value["initial"].update({
        "current_artifact_id": 10,
        "additional_projects": [{
            "project_id": 202,
            "revision": 3,
            "settings": settings,
            "project_status": "completed",
            "current_artifact_id": 20,
        }],
        "jobs": [
            {"id": 1, "project_id": 101, "status": "failed", "input_revision": 4,
             "cancel_requested": False, "input_settings": settings, "kind": "full",
             "block_index": None, "parent_job_id": None},
            {"id": 2, "project_id": 101, "status": "completed", "input_revision": 5,
             "cancel_requested": False, "input_settings": settings, "kind": "full",
             "block_index": None, "parent_job_id": 1},
            {"id": 3, "project_id": 202, "status": "completed", "input_revision": 3,
             "cancel_requested": False, "input_settings": settings, "kind": "full",
             "block_index": None, "parent_job_id": None},
        ],
        "history": [
            {"project_id": 101, "revision": 1, "settings": settings,
             "changed_fields": [], "restored_from_revision": None},
            {"project_id": 101, "revision": 5, "settings": settings,
             "changed_fields": [], "restored_from_revision": 1},
            {"project_id": 202, "revision": 3, "settings": settings,
             "changed_fields": [], "restored_from_revision": None},
        ],
        "artifact_revisions": [4],
        "artifacts": [
            {"id": 10, "project_id": 101, "job_id": 2, "revision": 5,
             "file_content_hex": "78", "file_size": 1,
             "file_sha256": hashlib.sha256(b"x").hexdigest()},
            {"id": 20, "project_id": 202, "job_id": 3, "revision": 3,
             "file_content_hex": "78", "file_size": 1,
             "file_sha256": hashlib.sha256(b"x").hexdigest()},
        ],
        "external_calls": [{
            "id": 1, "job_id": 2, "fingerprint": "seed-call", "provider": "synthetic",
            "endpoint": "https://synthetic.invalid/d36", "remote_side_effect": False,
            "status": "failed", "attempts": 1, "response_status": None,
            "response_body_hex": None, "response_body_sha256": None,
            "response_content_type": None, "provider_response_id": None,
            "error_code": "synthetic_failure",
        }],
        "prior_turns": [
            {"request_id": "prior-1", "project_id": 101, "base_revision": 4,
             "status": "needs_input", "question": "値は？", "result_revision": None,
             "settings_saved": False, "proposal": None, "text": "字幕を変更",
             "relation": None, "parent_request_id": None, "successor_request_id": "prior-2"},
            {"request_id": "prior-2", "project_id": 101, "base_revision": 5,
             "status": "needs_input", "question": "値は？", "result_revision": None,
             "settings_saved": False, "proposal": None, "text": "64px",
             "relation": "answer", "parent_request_id": "prior-1", "successor_request_id": None},
        ],
    })
    canonical_request = json.dumps({
        "operation_id": "project.status.get", "operation_version": 1,
        "project_id": 101, "base_revision": 5,
    }, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    result = {"operation_id": "project.status.get", "project_id": 101,
              "revision": 5, "changed": False}
    value["initial"]["receipts"] = [{
        "request_id": "seed-receipt", "operation_id": "project.status.get",
        "operation_version": 1, "project_id": 101, "base_revision": 5,
        "result_revision": 5, "generation_requested": False, "job_id": 2,
        "canonical_request_sha256": hashlib.sha256(canonical_request.encode()).hexdigest(),
        "result_sha256": trial_host._hash(result),
    }]
    value["event"]["request"]["continuation"] = {
        "parent_request_id": "prior-2", "relation": "answer",
    }
    value["case_sha256"] = canonical_case_sha256(value)
    return value


def _refresh_receipt_identity(case: dict[str, Any]) -> None:
    item = case["initial"]["receipts"][0]
    canonical_request = {
        "operation_id": item["operation_id"], "operation_version": item["operation_version"],
        "project_id": item["project_id"], "base_revision": item["base_revision"],
    }
    result = {
        "operation_id": item["operation_id"], "project_id": item["project_id"],
        "revision": item["result_revision"],
        "changed": item["result_revision"] != item["base_revision"],
    }
    item["canonical_request_sha256"] = hashlib.sha256(json.dumps(
        canonical_request, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    item["result_sha256"] = trial_host._hash(result)


def _worker_observation() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "response": {
            "http_status": 200,
            "status": "completed",
            "mode": "all_tools",
            "executed": True,
            "requires_confirmation": False,
            "operation_id": "project.subtitle-font-size.set",
            "reason_code": None,
            "response_sha256": "b" * 64,
        },
        "before": {
            "state_sha256": "c" * 64,
            "project_status": "completed",
            "settings_sha256": "d" * 64,
            "projects_sha256": "1" * 64,
            "history_sha256": "2" * 64,
            "jobs_sha256": "3" * 64,
            "receipts_sha256": "4" * 64,
            "artifacts_sha256": "5" * 64,
            "external_calls_sha256": "6" * 64,
            "language_requests_sha256": "7" * 64,
            "language_turns_sha256": "8" * 64,
            "project_count": 1,
            "history_count": 0,
            "job_count": 0,
            "artifact_count": 2,
            "receipt_count": 0,
            "external_call_count": 0,
            "language_request_count": 0,
            "language_turn_count": 0,
        },
        "after": {
            "state_sha256": "e" * 64,
            "project_status": "completed",
            "settings_sha256": "f" * 64,
            "projects_sha256": "9" * 64,
            "history_sha256": "a" * 64,
            "jobs_sha256": "3" * 64,
            "receipts_sha256": "b" * 64,
            "artifacts_sha256": "5" * 64,
            "external_calls_sha256": "6" * 64,
            "language_requests_sha256": "c" * 64,
            "language_turns_sha256": "d" * 64,
            "project_count": 1,
            "history_count": 1,
            "job_count": 0,
            "artifact_count": 2,
            "receipt_count": 1,
            "external_call_count": 0,
            "language_request_count": 1,
            "language_turn_count": 1,
        },
        "effects": {
            "settings": 1,
            "revision": 1,
            "jobs": 0,
            "cancellations": 0,
            "receipts": 1,
            "artifacts": 0,
            "external_calls": 0,
            "history": 1,
            "language_records": 1,
        },
        "model_calls": 1,
        "failure_class": None,
        "replay": {
            "attempted": True,
            "model_calls": 0,
            "state_unchanged": True,
            "same_response": True,
            "response": {
                "http_status": 200,
                "status": "completed",
                "mode": "all_tools",
                "executed": True,
                "requires_confirmation": False,
                "operation_id": "project.subtitle-font-size.set",
                "reason_code": None,
                "response_sha256": "b" * 64,
            },
            "failure_class": None,
        },
        "confirmation": {
            "attempted": False,
            "duplicate_attempted": False,
            "state_sha256": None,
            "duplicate_same_response": None,
            "response": None,
            "duplicate_response": None,
            "failure_class": None,
        },
    }


def _model_types(annotation: Any) -> set[type[BaseModel]]:
    found: set[type[BaseModel]] = set()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        found.add(annotation)
    for argument in get_args(annotation):
        if get_origin(argument) is not None or isinstance(argument, type):
            found.update(_model_types(argument))
    return found


def _field_graph(root: type[BaseModel]) -> set[type[BaseModel]]:
    pending = [root]
    found: set[type[BaseModel]] = set()
    while pending:
        model = pending.pop()
        if model in found:
            continue
        found.add(model)
        for field in model.model_fields.values():
            pending.extend(_model_types(field.annotation) - found)
    return found


def test_final_protocol_has_exact_canonical_bytes() -> None:
    path = Path(__file__).parents[1] / "evaluation" / "final_protocol.json"
    assert path.read_bytes() == PROTOCOL
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "10dd87f5dcfa41575ee4b680644bf4d0b45bea0132e91900730af521addc97d9"
    assert json.loads(path.read_bytes()) == {
        "schema_version": 1,
        "modes": ["all_tools", "stateful"],
        "per_call_deadline_seconds": 180,
        "maximum_model_calls": 4,
        "isolation": "fresh_case_state_under_source_group",
        "scoring_owner": "external_evaluator",
    }


def test_unlabeled_contract_has_no_label_model_or_generic_field_graph() -> None:
    graph = _field_graph(UnlabeledTrialCase)
    assert all(model.__module__ == "evaluation.unlabeled_contracts" for model in graph)
    assert all(model.__name__ != "Case" for model in graph)
    assert all(model.model_config.get("extra") == "forbid" for model in graph)
    assert not FORBIDDEN_FIELDS.intersection(
        field_name for model in graph for field_name in model.model_fields
    )
    assert all(
        get_origin(field.annotation) is not dict
        for model in graph
        for field in model.model_fields.values()
    )


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "expected"),
        (("event",), "labels"),
        (("event", "request"), "review_ledger"),
        (("initial",), "review_status"),
        (("initial", "settings"), "accepted_operations"),
    ],
)
def test_unlabeled_contract_rejects_unknown_label_fields(path: tuple[str, ...], field: str) -> None:
    value = _case()
    target = value
    for part in path:
        target = target[part]
    target[field] = "must fail closed"
    with pytest.raises(ValidationError):
        UnlabeledTrialCase.model_validate(value)


def test_unlabeled_contract_rejects_multiple_cases() -> None:
    with pytest.raises(ValidationError):
        UnlabeledTrialCase.model_validate([_bound_case(), _bound_case()])


def test_case_hash_is_verified_over_canonical_case_without_hash_field() -> None:
    value = _bound_case()
    parsed = UnlabeledTrialCase.model_validate(value)
    assert parsed.case_sha256 == canonical_case_sha256(parsed)
    value["event"]["request"]["text"] += "改変"
    with pytest.raises(ValidationError, match="case_sha256"):
        UnlabeledTrialCase.model_validate(value)


@pytest.mark.parametrize("field", ["action", "when", "then"])
def test_event_rejects_unconsumed_generic_fields(field: str) -> None:
    value = _bound_case()
    value["event"][field] = "unconsumed"
    with pytest.raises(ValidationError):
        UnlabeledTrialCase.model_validate(value)


def test_event_requires_exact_kind_specific_fields() -> None:
    value = _bound_case()
    value["event"] = {
        "kind": "revision_race",
        "request": value["event"]["request"],
        "external_revision": 6,
        "external_settings": {"subtitle_font_size": 52},
    }
    value["case_sha256"] = canonical_case_sha256(value)
    UnlabeledTrialCase.model_validate(value)
    value["event"]["replacement_text"] = "must be rejected on this branch"
    value["case_sha256"] = canonical_case_sha256(value)
    with pytest.raises(ValidationError):
        UnlabeledTrialCase.model_validate(value)


@pytest.mark.parametrize(
    "null_field",
    [
        "subtitle_font_size",
        "voicevox_speed_scale",
        "voicevox_speaker_id",
        "pronunciation_overrides",
        "narration_pacing_mode",
        "narration_sentence_pause_seconds",
    ],
)
def test_revision_race_rejects_each_explicit_null_settings_field_before_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    null_field: str,
) -> None:
    value = _case()
    valid_field = "voicevox_speed_scale" if null_field == "subtitle_font_size" else "subtitle_font_size"
    valid_value: float | int = 1.0 if valid_field == "voicevox_speed_scale" else 52
    value["event"] = {
        "kind": "revision_race",
        "request": value["event"]["request"],
        "external_revision": 6,
        "external_settings": {valid_field: valid_value, null_field: None},
    }
    value["case_sha256"] = canonical_case_sha256(value)
    input_path = tmp_path / "explicit-null.json"
    input_path.write_text(json.dumps(value), encoding="utf-8")
    candidate = tmp_path / "candidate"
    (candidate / "backend").mkdir(parents=True)
    worker_called = False

    def forbidden_worker(*args: Any, **kwargs: Any) -> None:
        nonlocal worker_called
        worker_called = True

    monkeypatch.setattr(trial_host, "_run_candidate", forbidden_worker)
    with pytest.raises(ValueError, match="invalid unlabeled trial case"):
        run_trial_host(
            candidate_root=candidate,
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "output.json",
            storage=tmp_path / "storage",
            model="test-model",
        )
    assert not worker_called


def test_revision_race_rejects_seeded_history_collision() -> None:
    value = _case()
    value["initial"]["history"] = [{
        "project_id": 101,
        "revision": 5,
        "settings": value["initial"]["settings"],
        "changed_fields": [],
        "restored_from_revision": None,
    }]
    value["event"] = {
        "kind": "revision_race",
        "request": value["event"]["request"],
        "external_revision": 5,
        "external_settings": {"subtitle_font_size": 52},
    }
    value["case_sha256"] = canonical_case_sha256(value)

    with pytest.raises(ValidationError, match="external revision collides with seeded history"):
        UnlabeledTrialCase.model_validate(value)


def test_revision_race_rejects_revision_gap() -> None:
    value = _case()
    value["event"] = {
        "kind": "revision_race",
        "request": value["event"]["request"],
        "external_revision": 7,
        "external_settings": {"subtitle_font_size": 52},
    }
    value["case_sha256"] = canonical_case_sha256(value)

    with pytest.raises(ValidationError, match="external revision must be the next primary revision"):
        UnlabeledTrialCase.model_validate(value)


def test_prior_proposal_rejects_cross_branch_fields() -> None:
    value = _bound_case()
    value["initial"]["prior_turns"] = [{
        "request_id": "prior", "project_id": 101, "base_revision": 5,
        "status": "needs_input", "question": "値は？", "result_revision": None,
        "settings_saved": False, "text": "字幕を変更", "relation": None,
        "proposal": {
            "kind": "clarification", "question": "値は？", "missing_fields": ["arguments"],
            "operation_id": "project.status.get",
        },
    }]
    value["case_sha256"] = canonical_case_sha256(value)
    with pytest.raises(ValidationError):
        UnlabeledTrialCase.model_validate(value)


@pytest.mark.parametrize(
    "missing_fields",
    [
        ["revision"],
        ["job_id"],
        ["target", "arguments", "intent", "target"],
    ],
)
def test_prior_clarification_rejects_nonproduction_missing_fields_before_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_fields: list[str],
) -> None:
    value = _case()
    value["initial"]["prior_turns"] = [{
        "request_id": "prior", "project_id": 101, "base_revision": 5,
        "status": "needs_input", "question": "値は？", "result_revision": None,
        "settings_saved": False, "text": "字幕を変更", "relation": None,
        "proposal": {
            "kind": "clarification", "question": "値は？", "missing_fields": missing_fields,
        },
    }]
    value["case_sha256"] = canonical_case_sha256(value)
    input_path = tmp_path / "invalid-prior-clarification.json"
    input_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    worker_called = False

    def forbidden_worker(*args: Any, **kwargs: Any) -> None:
        nonlocal worker_called
        worker_called = True

    monkeypatch.setattr(trial_host, "_run_candidate", forbidden_worker)
    with pytest.raises(ValueError, match="invalid unlabeled trial case"):
        run_trial_host(
            candidate_root=Path(__file__).parents[2],
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "invalid-prior-clarification-output.json",
            storage=tmp_path / "invalid-prior-clarification-storage",
            model="d36-test-model",
        )
    assert not worker_called


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        (("initial", "settings", "subtitle_font_size"), 121),
        (("initial", "settings", "voicevox_speed_scale"), 2.01),
        (("initial", "settings", "narration_sentence_pause_seconds"), 5.01),
    ],
)
def test_numeric_limits_match_candidate_constraints(path: tuple[str, ...], bad: object) -> None:
    value = _bound_case()
    target: Any = value
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = bad
    value["case_sha256"] = canonical_case_sha256(value)
    with pytest.raises(ValidationError):
        UnlabeledTrialCase.model_validate(value)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ([{"surface": "   ", "reading": "エー", "accent": None}], "surface"),
        ([{"surface": "API。", "reading": "エー", "accent": None}], "delimiter"),
        ([{"surface": "API", "reading": "ァピ", "accent": None}], "reading"),
        ([{"surface": "API", "reading": "キャ", "accent": 2}], "accent"),
        ([
            {"surface": "API", "reading": "エー", "accent": None},
            {"surface": " API ", "reading": "ピー", "accent": None},
        ], "duplicate"),
    ],
)
def test_invalid_seed_pronunciations_are_rejected_before_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overrides: list[dict[str, Any]],
    message: str,
) -> None:
    value = _case()
    value["initial"]["settings"]["pronunciation_overrides"] = overrides
    value["case_sha256"] = canonical_case_sha256(value)
    input_path = tmp_path / f"invalid-pronunciation-{message}.json"
    input_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    worker_called = False

    def forbidden_worker(*args: Any, **kwargs: Any) -> None:
        nonlocal worker_called
        worker_called = True

    monkeypatch.setattr(trial_host, "_run_candidate", forbidden_worker)
    with pytest.raises(ValueError, match="invalid unlabeled trial case"):
        run_trial_host(
            candidate_root=Path(__file__).parents[2],
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / f"invalid-pronunciation-{message}-output.json",
            storage=tmp_path / f"invalid-pronunciation-{message}-storage",
            model="d36-test-model",
        )
    assert not worker_called


@pytest.mark.parametrize(
    ("mode", "index", "message"),
    [
        ("stateful", None, "stateful mode requires an index"),
        ("all_tools", "index", "all_tools mode rejects an index"),
    ],
)
def test_mode_index_rules_fail_before_candidate_invocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    index: str | None,
    message: str,
) -> None:
    candidate = tmp_path / "candidate"
    (candidate / "backend").mkdir(parents=True)
    input_path = tmp_path / "case.json"
    input_path.write_text(json.dumps(_bound_case()), encoding="utf-8")
    called = False

    def forbidden_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        raise AssertionError("candidate must not run")

    monkeypatch.setattr(subprocess, "run", forbidden_run)
    with pytest.raises(ValueError, match=message):
        run_trial_host(
            candidate_root=candidate,
            mode=mode,
            input_path=input_path,
            output_path=tmp_path / "observation.json",
            storage=tmp_path / "storage",
            model="test-model",
            index=(tmp_path / index) if index else None,
        )
    assert not called


def test_restart_host_passes_protocol_then_remaining_model_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    (candidate / "backend").mkdir(parents=True)
    case = _case()
    case["event"]["kind"] = "restart_resend"
    case["case_sha256"] = canonical_case_sha256(case)
    input_path = tmp_path / "case.json"
    input_path.write_text(json.dumps(case), encoding="utf-8")
    commands: list[list[str]] = []

    def completed(argv: list[str], **kwargs: Any) -> None:
        commands.append(argv)
        observation = _worker_observation()
        if kwargs["env"]["D36_WORKER_PHASE"] == "restart_prepare":
            observation["model_calls"] = 3
        else:
            observation["model_calls"] = 4
            observation["replay"]["model_calls"] = 1
        Path(kwargs["env"]["D36_WORKER_OUTPUT"]).write_text(
            json.dumps(observation), encoding="ascii"
        )

    monkeypatch.setattr("evaluation.scripts.evaluation_trial_host._run_candidate", completed)
    observation = run_trial_host(
        candidate_root=candidate,
        mode="all_tools",
        input_path=input_path,
        output_path=tmp_path / "observation.json",
        storage=tmp_path / "storage",
        model="test-model",
    )

    assert [command[-2:] for command in commands] == [
        ["--model-call-budget", "4"],
        ["--model-call-budget", "1"],
    ]
    assert observation.model_calls == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(("first_calls", "remaining"), [(3, 1), (4, 0)])
async def test_restart_model_budget_prevents_over_budget_adapter_calls(
    first_calls: int, remaining: int
) -> None:
    actual_adapter_calls = 0

    async def adapter_call() -> str:
        nonlocal actual_adapter_calls
        actual_adapter_calls += 1
        return "model response"

    first_budget = trial_host._ModelCallBudget(4)
    for _ in range(first_calls):
        assert await first_budget.complete(adapter_call) == "model response"
    restart_budget = trial_host._ModelCallBudget(remaining)
    for _ in range(remaining):
        assert await restart_budget.complete(adapter_call) == "model response"
    with pytest.raises(ValueError, match="^budget_exhausted$"):
        await restart_budget.complete(adapter_call)

    assert first_budget.calls + restart_budget.calls <= 4
    assert actual_adapter_calls == first_calls + remaining == 4


def test_worker_cli_accepts_only_explicit_budget_zero_through_four(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accepted: list[int] = []

    def worker(model_call_budget: int) -> int:
        accepted.append(model_call_budget)
        return 0

    monkeypatch.setattr(trial_host, "_candidate_worker", worker)
    for budget in (0, 4):
        monkeypatch.setattr(
            sys,
            "argv",
            ["evaluation_trial_host.py", "--candidate-worker", "--model-call-budget", str(budget)],
        )
        assert trial_host.main() == 0
    assert accepted == [0, 4]

    for budget in (-1, 5):
        monkeypatch.setattr(
            sys,
            "argv",
            ["evaluation_trial_host.py", "--candidate-worker", "--model-call-budget", str(budget)],
        )
        with pytest.raises(SystemExit):
            trial_host.main()


def test_host_uses_candidate_rooted_subprocess_and_writes_redacted_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    backend = candidate / "backend"
    backend.mkdir(parents=True)
    input_path = tmp_path / "case.json"
    input_path.write_text(json.dumps(_bound_case(), ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "observation.json"
    storage = tmp_path / "case-storage"
    captured: dict[str, Any] = {}

    def completed(argv: list[str], **kwargs: Any) -> None:
        captured.update(argv=argv, **kwargs)
        Path(kwargs["env"]["D36_WORKER_OUTPUT"]).write_text(
            json.dumps(_worker_observation()), encoding="ascii"
        )

    monkeypatch.setattr("evaluation.scripts.evaluation_trial_host._run_candidate", completed)
    observation = run_trial_host(
        candidate_root=candidate,
        mode="all_tools",
        input_path=input_path,
        output_path=output_path,
        storage=storage,
        model="test-model",
    )

    assert captured["cwd"] == backend
    assert captured["env"]["PYTHONPATH"] == str(backend.resolve())
    assert captured["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert captured["argv"][1] == "-B"
    assert "D36_WORKER_INPUT" in captured["env"]
    assert captured["env"]["D36_STORAGE_ROOT"] == str(storage.resolve())
    assert observation.case_sha256 == _bound_case()["case_sha256"]
    assert observation.input_sha256 == hashlib.sha256(input_path.read_bytes()).hexdigest()
    assert observation.mode == "all_tools"
    assert observation.candidate_snapshot_sha256 == trial_host._candidate_snapshot(candidate)
    assert output_path.read_bytes() == (
        json.dumps(observation.model_dump(mode="json"), ensure_ascii=True, allow_nan=False,
                   sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("ascii")
    rendered = output_path.read_text(encoding="ascii")
    for forbidden in ("字幕を64pxにして", "expected", "labels", "model_body", str(tmp_path)):
        assert forbidden not in rendered
    assert not (storage / ".observation.tmp").exists()


class _ModelHandler(BaseHTTPRequestHandler):
    proposal: dict[str, Any] = {
        "kind": "operation", "operation_id": "project.subtitle-font-size.set",
        "operation_version": 1, "arguments": {"value": 64}, "generate_after_save": False,
    }
    delay_seconds = 0.0
    calls = 0

    def do_POST(self) -> None:  # noqa: N802
        type(self).calls += 1
        time.sleep(type(self).delay_seconds)
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        content = json.dumps({"result": self.proposal}, ensure_ascii=False)
        body = json.dumps({
            "model": "d36-test-model", "choices": [{"finish_reason": "stop", "message": {
                "role": "assistant", "content": content,
            }}],
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


def test_maximum_valid_pronunciation_seed_reaches_real_worker(tmp_path: Path) -> None:
    case = _case()
    case["initial"]["settings"]["pronunciation_overrides"] = [
        {"surface": "A" * 80, "reading": "カ" * 160, "accent": 160},
        *[
            {"surface": f"term-{index}", "reading": "カ", "accent": 1}
            for index in range(1, 100)
        ],
    ]
    case["case_sha256"] = canonical_case_sha256(case)
    _ModelHandler.delay_seconds = 0
    _ModelHandler.calls = 0
    _ModelHandler.proposal = {"kind": "no_operation", "reason": "変更しません"}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        input_path = tmp_path / "maximum-pronunciation.json"
        input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        observation = run_trial_host(
            candidate_root=Path(__file__).parents[2],
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "maximum-pronunciation-output.json",
            storage=tmp_path / "maximum-pronunciation-storage",
            model="d36-test-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert observation.before.project_count == 1
    assert observation.failure_class is None
    assert _ModelHandler.calls == 1


def test_maximum_valid_seed_produces_valid_real_worker_observation(tmp_path: Path) -> None:
    _ModelHandler.delay_seconds = 0
    _ModelHandler.calls = 0
    _ModelHandler.proposal = {
        "kind": "operation",
        "operation_id": "project.status.get",
        "operation_version": 1,
        "arguments": {},
        "generate_after_save": False,
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        case = _maximum_seed_case()
        input_path = tmp_path / "maximum-seed.json"
        input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        observation = run_trial_host(
            candidate_root=Path(__file__).parents[2],
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "maximum-observation.json",
            storage=tmp_path / "maximum-storage",
            model="d36-test-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert observation.before.project_count == 17
    assert observation.before.history_count == observation.before.job_count == 32
    assert observation.before.artifact_count == 64
    assert observation.before.receipt_count == observation.before.external_call_count == 32
    assert observation.before.language_request_count == observation.before.language_turn_count == 8
    assert observation.after.receipt_count == 33
    assert observation.after.language_request_count == observation.after.language_turn_count == 9


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda case: case["initial"]["artifact_revisions"].__setitem__(0, 0), "artifact_revisions"),
        (lambda case: case["initial"]["artifact_revisions"].__setitem__(0, MAX_REVISION + 1), "artifact_revisions"),
        (lambda case: case["initial"]["artifact_revisions"].__setitem__(0, 6), "artifact revision"),
        (lambda case: case["initial"]["history"][0].__setitem__("project_id", 999), "history references unknown project"),
        (lambda case: case["initial"]["history"][0].__setitem__("revision", 6), "history revision exceeds owner revision"),
        (lambda case: case["initial"]["history"][1].__setitem__("restored_from_revision", 2), "history restore references unknown revision"),
        (lambda case: case["initial"]["jobs"][0].__setitem__("project_id", 999), "job references unknown project"),
        (lambda case: case["initial"]["jobs"][0].__setitem__("input_revision", 6), "job revision exceeds owner revision"),
        (lambda case: case["initial"]["jobs"][1].__setitem__("parent_job_id", 999), "parent job does not exist"),
        (lambda case: case["initial"]["jobs"][1].__setitem__("parent_job_id", 3), "parent job ownership mismatch"),
        (lambda case: case["initial"]["jobs"][0].__setitem__("parent_job_id", 2), "parent job cycle"),
        (lambda case: case["initial"]["artifacts"][0].__setitem__("project_id", 999), "artifact references unknown project"),
        (lambda case: case["initial"]["artifacts"][0].__setitem__("revision", 6), "artifact revision exceeds owner revision"),
        (lambda case: case["initial"]["artifacts"][0].__setitem__("job_id", 999), "artifact references unknown job"),
        (lambda case: (case["initial"]["artifacts"][0].__setitem__("job_id", 3),
                       case["initial"]["artifacts"][1].__setitem__("job_id", None)), "artifact job ownership mismatch"),
        (lambda case: (case["initial"]["receipts"][0].__setitem__("project_id", 999),
                       _refresh_receipt_identity(case)), "receipt references unknown project"),
        (lambda case: (case["initial"]["receipts"][0].__setitem__("result_revision", 6),
                       _refresh_receipt_identity(case)), "receipt revision exceeds owner revision"),
        (lambda case: case["initial"]["receipts"][0].__setitem__("job_id", 999), "receipt references unknown job"),
        (lambda case: case["initial"]["receipts"][0].__setitem__("job_id", 3), "receipt job ownership mismatch"),
        (lambda case: case["initial"]["external_calls"][0].__setitem__("job_id", 999), "external call references unknown job"),
        (lambda case: case["initial"]["prior_turns"][0].__setitem__("project_id", 999), "prior turn references unknown project"),
        (lambda case: case["initial"]["prior_turns"][1].update(proposal={
            "kind": "operation", "operation_id": "project.generation.retry",
            "operation_version": 1, "arguments": {"job_id": 999},
            "generate_after_save": False,
        }), "prior turn proposal references unknown job"),
        (lambda case: case["initial"]["prior_turns"][1].update(proposal={
            "kind": "operation", "operation_id": "project.settings.restore",
            "operation_version": 1, "arguments": {"revision": 2},
            "generate_after_save": False,
        }), "prior turn proposal references unknown history"),
        (lambda case: case["initial"]["prior_turns"][0].__setitem__("base_revision", 6), "prior turn revision exceeds owner revision"),
        (lambda case: case["initial"]["prior_turns"][1].__setitem__("parent_request_id", "missing"), "prior turn parent does not exist"),
        (lambda case: case["initial"]["prior_turns"][0].__setitem__("successor_request_id", "missing"), "prior turn successor does not exist"),
        (lambda case: (case["initial"]["prior_turns"][1].__setitem__("project_id", 202),
                       case["initial"]["prior_turns"][1].__setitem__("base_revision", 3)), "prior turn link ownership mismatch"),
        (lambda case: case["initial"]["prior_turns"][0].__setitem__("successor_request_id", None), "prior turn links must be reciprocal"),
        (lambda case: (case["initial"]["prior_turns"][0].update(
                           parent_request_id="prior-2", successor_request_id="prior-2"),
                       case["initial"]["prior_turns"][1].update(
                           parent_request_id="prior-1", successor_request_id="prior-1")), "prior turn cycle"),
        (lambda case: case["initial"].__setitem__("current_artifact_id", 999), "current artifact does not exist"),
        (lambda case: case["initial"].__setitem__("current_artifact_id", 20), "current artifact ownership mismatch"),
        (lambda case: case["initial"]["additional_projects"][0].__setitem__("current_artifact_id", 10), "current artifact ownership mismatch"),
        (lambda case: case["event"]["request"].__setitem__("target_project_id", 999), "request target references unknown project"),
        (lambda case: case["event"]["request"].__setitem__("base_revision", 6), "request revision exceeds target revision"),
        (lambda case: case["event"]["request"].__setitem__("request_id", "prior-1"), "request would create prior turn cycle"),
        (lambda case: case["event"]["request"]["continuation"].__setitem__("parent_request_id", "missing"), "continuation parent does not exist"),
        (lambda case: case["event"]["request"]["continuation"].__setitem__("parent_request_id", "prior-1"), "continuation parent already has successor"),
        (lambda case: (case["event"]["request"].__setitem__("target_project_id", 202),
                       case["event"]["request"].__setitem__("base_revision", 3)), "continuation parent ownership mismatch"),
        (lambda case: case["event"].update(
            kind="same_id_different_body", replacement_text="別の依頼",
            replacement_target_project_id=999), "replacement target references unknown project"),
    ],
    ids=[
        "artifact-revision-zero", "artifact-revision-max", "artifact-revision-future",
        "history-project", "history-revision", "history-restored-revision",
        "job-project", "job-revision", "job-parent", "job-parent-owner", "job-parent-cycle",
        "artifact-project", "artifact-revision", "artifact-job", "artifact-job-owner",
        "receipt-project", "receipt-revision", "receipt-job", "receipt-job-owner", "call-job",
        "turn-project", "turn-proposal-job", "turn-proposal-history", "turn-revision",
        "turn-parent", "turn-successor", "turn-owner", "turn-reciprocal", "turn-cycle",
        "current-artifact", "current-artifact-owner", "additional-current-artifact-owner",
        "request-target", "request-revision", "request-cycle", "continuation-parent",
        "continuation-superseded", "continuation-owner", "replacement-target",
    ],
)
def test_invalid_seed_graph_is_rejected_before_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    case = _seed_graph_case()
    mutation(case)
    case["case_sha256"] = canonical_case_sha256(case)
    input_path = tmp_path / "invalid-seed.json"
    input_path.write_text(json.dumps(case), encoding="utf-8")
    candidate = tmp_path / "candidate"
    (candidate / "backend").mkdir(parents=True)
    worker_called = False

    def forbidden_worker(*args: Any, **kwargs: Any) -> None:
        nonlocal worker_called
        worker_called = True

    with pytest.raises(ValidationError, match=message):
        UnlabeledTrialCase.model_validate(case)
    monkeypatch.setattr(trial_host, "_run_candidate", forbidden_worker)
    with pytest.raises(ValueError, match="invalid unlabeled trial case"):
        run_trial_host(candidate_root=candidate, mode="all_tools", input_path=input_path,
            output_path=tmp_path / "output.json", storage=tmp_path / "storage", model="test-model")
    assert not worker_called


@pytest.mark.parametrize(
    ("collection", "duplicate", "message"),
    [
        ("artifacts", lambda item: {**item, "id": 11}, "artifact job identities must be unique"),
        ("receipts", lambda item: {**item, "request_id": "second-receipt"}, "receipt job identities must be unique"),
        ("external_calls", lambda item: {**item, "id": 2}, "external call job fingerprints must be unique"),
    ],
)
def test_seed_graph_rejects_database_unique_constraint_collisions(
    collection: str, duplicate: Any, message: str
) -> None:
    case = _seed_graph_case()
    case["initial"][collection].append(duplicate(case["initial"][collection][0]))
    case["case_sha256"] = canonical_case_sha256(case)
    with pytest.raises(ValidationError, match=message):
        UnlabeledTrialCase.model_validate(case)


@pytest.mark.parametrize("field", ["canonical_request_sha256", "result_sha256"])
def test_seed_graph_rejects_receipt_identity_mismatch(field: str) -> None:
    case = _seed_graph_case()
    case["initial"]["receipts"][0][field] = "0" * 64
    case["case_sha256"] = canonical_case_sha256(case)
    with pytest.raises(ValidationError, match="receipt identity mismatch"):
        UnlabeledTrialCase.model_validate(case)


def test_derived_artifact_ids_must_fit_database_range() -> None:
    case = _bound_case()
    case["initial"]["artifacts"] = [{
        "id": 2**63 - 1,
        "project_id": 101,
        "job_id": None,
        "revision": 5,
        "file_content_hex": "78",
        "file_size": 1,
        "file_sha256": hashlib.sha256(b"x").hexdigest(),
    }]
    case["initial"]["artifact_revisions"] = [5]
    case["case_sha256"] = canonical_case_sha256(case)

    with pytest.raises(ValidationError, match="derived artifact IDs exceed database range"):
        UnlabeledTrialCase.model_validate(case)


def test_one_over_seed_limit_is_rejected_before_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _maximum_seed_case()
    case["initial"]["jobs"].append({
        "id": 33,
        "project_id": 101,
        "status": "failed",
        "input_revision": 100,
        "cancel_requested": False,
        "input_settings": case["initial"]["settings"],
        "kind": "full",
        "block_index": None,
        "parent_job_id": None,
    })
    case["case_sha256"] = canonical_case_sha256(case)
    input_path = tmp_path / "one-over.json"
    input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    worker_called = False

    def forbidden_worker(*args: Any, **kwargs: Any) -> None:
        nonlocal worker_called
        worker_called = True

    monkeypatch.setattr(trial_host, "_run_candidate", forbidden_worker)
    with pytest.raises(ValueError, match="invalid unlabeled trial case"):
        run_trial_host(
            candidate_root=Path(__file__).parents[2],
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "one-over-observation.json",
            storage=tmp_path / "one-over-storage",
            model="d36-test-model",
        )
    assert not worker_called


def test_real_worker_seeds_production_clarification_missing_fields_boundary(tmp_path: Path) -> None:
    _ModelHandler.delay_seconds = 0
    _ModelHandler.calls = 0
    case = _case()
    case["initial"]["prior_turns"] = [{
        "request_id": "prior", "project_id": 101, "base_revision": 5,
        "status": "needs_input", "question": "不足は？", "result_revision": None,
        "settings_saved": False, "text": "操作したい", "relation": None,
        "proposal": {
            "kind": "clarification",
            "question": "不足は？",
            "missing_fields": ["target", "arguments", "intent"],
        },
    }]
    case["case_sha256"] = canonical_case_sha256(case)
    _ModelHandler.proposal = {"kind": "no_operation", "reason": "変更しません"}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        input_path = tmp_path / "production-clarification-boundary.json"
        input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        observation = run_trial_host(
            candidate_root=Path(__file__).parents[2],
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "production-clarification-boundary-output.json",
            storage=tmp_path / "production-clarification-boundary-storage",
            model="d36-test-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert observation.before.language_request_count == 1
    assert observation.before.language_turn_count == 1
    assert observation.failure_class is None


@pytest.mark.asyncio
async def test_quiescent_candidate_dispatcher_is_cancelled_cleanly() -> None:
    task = asyncio.create_task(trial_host._quiescent_candidate_dispatcher())
    await asyncio.sleep(0)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


def test_seeded_pending_job_stays_quiescent_during_slow_model_call(tmp_path: Path) -> None:
    case = _case()
    case["initial"]["project_status"] = "generating"
    case["initial"]["jobs"] = [{
        "id": 1,
        "project_id": 101,
        "status": "pending",
        "input_revision": 5,
        "cancel_requested": False,
        "input_settings": case["initial"]["settings"],
        "kind": "full",
        "block_index": None,
        "parent_job_id": None,
    }]
    case["case_sha256"] = canonical_case_sha256(case)
    _ModelHandler.delay_seconds = 1.25
    _ModelHandler.calls = 0
    _ModelHandler.proposal = {
        "kind": "operation",
        "operation_id": "project.status.get",
        "operation_version": 1,
        "arguments": {},
        "generate_after_save": False,
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        input_path = tmp_path / "pending-slow-model.json"
        input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        observation = run_trial_host(
            candidate_root=Path(__file__).parents[2],
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "pending-slow-model-output.json",
            storage=tmp_path / "pending-slow-model-storage",
            model="d36-test-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
        )
    finally:
        _ModelHandler.delay_seconds = 0
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert _ModelHandler.calls == 1
    assert observation.before.job_count == observation.after.job_count == 1
    assert observation.before.jobs_sha256 == observation.after.jobs_sha256
    assert observation.before.artifacts_sha256 == observation.after.artifacts_sha256
    assert observation.before.external_calls_sha256 == observation.after.external_calls_sha256
    assert observation.effects.jobs == 0
    assert observation.effects.artifacts == 0
    assert observation.effects.external_calls == 0
    assert observation.effects.receipts == 1
    assert observation.effects.language_records == 1


def test_real_candidate_worker_executes_language_route(tmp_path: Path) -> None:
    _ModelHandler.delay_seconds = 0
    _ModelHandler.calls = 0
    _ModelHandler.proposal = {
        "kind": "operation",
        "operation_id": "project.subtitle-font-size.set",
        "operation_version": 1,
        "arguments": {"value": 64},
        "generate_after_save": False,
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        case = _bound_case()
        input_path = tmp_path / "real-case.json"
        input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        observation = run_trial_host(
            candidate_root=Path(__file__).parents[2], mode="all_tools", input_path=input_path,
            output_path=tmp_path / "real-observation.json", storage=tmp_path / "real-storage",
            model="d36-test-model", base_url=f"http://127.0.0.1:{server.server_port}/v1",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert observation.response.status == "completed"
    assert observation.response.operation_id == "project.subtitle-font-size.set"
    assert observation.effects.settings == observation.effects.revision == 1
    assert observation.effects.receipts == 1
    assert observation.before.settings_sha256 != observation.after.settings_sha256
    assert observation.response.http_status == 200


@pytest.mark.parametrize(
    "kind",
    [
        "none", "resend_identical", "restart_resend", "same_id_different_body",
        "concurrent_identical", "revision_race", "confirm_generation", "confirm_twice",
        "switch_target",
    ],
)
def test_real_worker_executes_every_allowed_event(tmp_path: Path, kind: str) -> None:
    _ModelHandler.delay_seconds = 0
    _ModelHandler.calls = 0
    case = _case()
    event: dict[str, Any] = {"kind": kind, "request": case["event"]["request"]}
    if kind == "same_id_different_body":
        event["replacement_text"] = "字幕を72pxにして"
        event["replacement_target_project_id"] = 101
    elif kind == "revision_race":
        event["external_revision"] = 6
        event["external_settings"] = {"subtitle_font_size": 52}
    elif kind == "switch_target":
        case["initial"]["additional_projects"] = [{
            "project_id": 202, "revision": 5, "settings": case["initial"]["settings"],
            "project_status": "completed",
        }]
        event.update(selected_project_id_after=202, replacement_text="字幕を64pxにして",
                     replacement_target_project_id=202)
    case["event"] = event
    case["case_sha256"] = canonical_case_sha256(case)
    proposal = ({
        "kind": "operation", "operation_id": "project.generation.start", "operation_version": 1,
        "arguments": {"kind": "full"}, "generate_after_save": False,
    } if kind in {"confirm_generation", "confirm_twice"} else {
        "kind": "operation", "operation_id": "project.subtitle-font-size.set", "operation_version": 1,
        "arguments": {"value": 64}, "generate_after_save": False,
    })
    _ModelHandler.proposal = proposal
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        input_path = tmp_path / f"{kind}.json"
        input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        observation = run_trial_host(
            candidate_root=Path(__file__).parents[2], mode="all_tools", input_path=input_path,
            output_path=tmp_path / f"{kind}-observation.json", storage=tmp_path / f"{kind}-storage",
            model="d36-test-model", base_url=f"http://127.0.0.1:{server.server_port}/v1",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    if kind in {"resend_identical", "restart_resend", "same_id_different_body", "concurrent_identical", "switch_target"}:
        assert observation.replay.attempted
        assert observation.replay.response is not None
    if kind in {"confirm_generation", "confirm_twice"}:
        assert observation.confirmation.attempted
        assert observation.confirmation.response is not None
        assert observation.confirmation.response.http_status == 200
    if kind == "same_id_different_body":
        assert observation.replay.response is not None
        assert observation.replay.response.http_status == 409
        assert observation.replay.response.status == "http_error"
        assert observation.replay.response.reason_code == "request_id_conflict"
    assert observation.confirmation.duplicate_attempted == (kind == "confirm_twice")


def test_revision_race_exact_next_revision_executes_real_worker(tmp_path: Path) -> None:
    _ModelHandler.delay_seconds = 0
    _ModelHandler.calls = 0
    case = _case()
    case["event"] = {
        "kind": "revision_race",
        "request": case["event"]["request"],
        "external_revision": 6,
        "external_settings": {"subtitle_font_size": 52},
    }
    case["case_sha256"] = canonical_case_sha256(case)
    _ModelHandler.proposal = {
        "kind": "operation",
        "operation_id": "project.status.get",
        "operation_version": 1,
        "arguments": {},
        "generate_after_save": False,
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        input_path = tmp_path / "valid-revision-race.json"
        input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        observation = run_trial_host(
            candidate_root=Path(__file__).parents[2],
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "valid-revision-race-observation.json",
            storage=tmp_path / "valid-revision-race-storage",
            model="d36-test-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert observation.before.history_count == 0
    assert observation.after.history_count == 1
    assert observation.effects.revision == 1
    assert observation.effects.history == 1
    assert observation.failure_class is None


def test_real_worker_preserves_null_and_explicit_artifact_pointers(tmp_path: Path) -> None:
    _ModelHandler.delay_seconds = 0
    _ModelHandler.calls = 0
    _ModelHandler.proposal = {"kind": "no_operation", "reason": "変更しません"}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    project_hashes: dict[str, str] = {}
    try:
        for name, artifact, current_artifact_id in (
            ("without-artifacts", None, None),
            ("artifacts-null", 10, None),
            ("artifacts-explicit", 10, 10),
        ):
            case = _case()
            case["initial"]["artifact_revisions"] = []
            case["initial"]["current_artifact_id"] = current_artifact_id
            if artifact is not None:
                case["initial"]["artifacts"] = [{
                    "id": artifact,
                    "project_id": 101,
                    "job_id": None,
                    "revision": 5,
                    "file_content_hex": "78",
                    "file_size": 1,
                    "file_sha256": hashlib.sha256(b"x").hexdigest(),
                }]
            case["case_sha256"] = canonical_case_sha256(case)
            input_path = tmp_path / f"{name}.json"
            input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
            observation = run_trial_host(
                candidate_root=Path(__file__).parents[2],
                mode="all_tools",
                input_path=input_path,
                output_path=tmp_path / f"{name}-output.json",
                storage=tmp_path / f"{name}-storage",
                model="d36-test-model",
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
            )
            project_hashes[name] = observation.before.projects_sha256
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert project_hashes["artifacts-null"] == project_hashes["without-artifacts"]
    assert project_hashes["artifacts-explicit"] != project_hashes["artifacts-null"]


def test_real_worker_seeds_complete_allowed_initial_state(tmp_path: Path) -> None:
    _ModelHandler.delay_seconds = 0
    _ModelHandler.calls = 0
    case = _case()
    settings = case["initial"]["settings"]
    case["initial"].update({
        "additional_projects": [{"project_id": 202, "revision": 3, "settings": settings,
                                 "project_status": "failed"}],
        "jobs": [{"id": 7, "project_id": 202, "status": "failed", "input_revision": 3,
                  "cancel_requested": False, "input_settings": settings, "kind": "full",
                  "block_index": None, "parent_job_id": None}],
        "history": [{"project_id": 101, "revision": 4, "settings": settings,
                     "changed_fields": ["subtitle_font_size"], "restored_from_revision": None}],
        "artifacts": [{"id": 10, "project_id": 101, "job_id": None, "revision": 5,
                       "file_content_hex": "7878", "file_size": 2,
                       "file_sha256": hashlib.sha256(b"xx").hexdigest()}],
        "external_calls": [{"id": 1, "job_id": 7, "fingerprint": "seed-call",
                            "provider": "synthetic", "endpoint": "https://synthetic.invalid/d36",
                            "remote_side_effect": False, "status": "failed", "attempts": 1,
                            "response_status": None, "response_body_sha256": None,
                            "response_content_type": None, "provider_response_id": None,
                            "error_code": "synthetic_failure"}],
        "prior_turns": [{"request_id": "prior", "project_id": 101, "base_revision": 5,
                         "status": "needs_input", "question": "値は？", "result_revision": None,
                         "settings_saved": False, "proposal": {"kind": "clarification",
                         "question": "値は？", "missing_fields": ["arguments"]},
                         "text": "字幕を変更", "relation": None}],
    })
    canonical_request = json.dumps({"operation_id": "project.status.get", "operation_version": 1,
        "project_id": 101, "base_revision": 5}, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    result = {"operation_id": "project.status.get", "project_id": 101, "revision": 5, "changed": False}
    case["initial"]["receipts"] = [{"request_id": "seed-receipt", "operation_id": "project.status.get",
        "operation_version": 1, "project_id": 101, "base_revision": 5, "result_revision": 5,
        "generation_requested": False, "job_id": None,
        "canonical_request_sha256": hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        "result_sha256": trial_host._hash(result)}]
    case["case_sha256"] = canonical_case_sha256(case)
    _ModelHandler.proposal = {"kind": "no_operation", "reason": "変更しません"}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        input_path = tmp_path / "seeded.json"
        input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        observation = run_trial_host(candidate_root=Path(__file__).parents[2], mode="all_tools",
            input_path=input_path, output_path=tmp_path / "seeded-output.json",
            storage=tmp_path / "seeded-storage", model="d36-test-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert observation.before.project_count == 2
    assert observation.before.job_count == observation.before.external_call_count == 1
    assert observation.before.history_count == observation.before.receipt_count == 1
    assert observation.before.artifact_count == 3
    assert observation.before.language_request_count == observation.before.language_turn_count == 1


def test_observation_contract_rejects_worker_exfiltration_strings() -> None:
    value = _worker_observation()
    value["response"]["reason_code"] = "secret-from-worker"
    with pytest.raises(ValidationError):
        trial_host._WorkerObservation.model_validate(value)
    value = _worker_observation()
    value["failure_class"] = "C:/private/path/secret"
    with pytest.raises(ValidationError):
        trial_host._WorkerObservation.model_validate(value)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["replay"].update(response=None),
        lambda value: value["confirmation"].update(attempted=True, state_sha256=None),
        lambda value: value["confirmation"].update(duplicate_attempted=True),
        lambda value: value["confirmation"].update(duplicate_same_response=True),
    ],
)
def test_event_projection_contract_rejects_inconsistent_attempt_evidence(
    change: Any,
) -> None:
    value = _worker_observation()
    change(value)
    with pytest.raises(ValidationError):
        trial_host._WorkerObservation.model_validate(value)


def test_subprocess_output_flood_is_killed_without_reading_logs(tmp_path: Path) -> None:
    storage = tmp_path / "logs"
    storage.mkdir()
    command = [sys.executable, "-c", "import sys,time;sys.stdout.write('x'*(3*1024*1024));sys.stdout.flush();time.sleep(30)"]
    with pytest.raises(ValueError, match="output limit"):
        trial_host._run_candidate(command, cwd=tmp_path, env=dict(os.environ), storage=storage)
    assert not list(storage.iterdir())


def test_redacted_projection_does_not_publish_model_prose(tmp_path: Path) -> None:
    secret = "EXFILTRATE_PRIVATE_MODEL_PROSE_91f32"
    _ModelHandler.proposal = {"kind": "no_operation", "reason": secret}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        input_path = tmp_path / "redaction.json"
        input_path.write_text(json.dumps(_bound_case(), ensure_ascii=False), encoding="utf-8")
        output_path = tmp_path / "redacted.json"
        run_trial_host(candidate_root=Path(__file__).parents[2], mode="all_tools", input_path=input_path,
            output_path=output_path, storage=tmp_path / "redaction-storage", model="d36-test-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert secret.encode() not in output_path.read_bytes()


def test_same_count_project_mutation_changes_full_state_hash(tmp_path: Path) -> None:
    case = _case()
    case["event"] = {"kind": "revision_race", "request": case["event"]["request"],
                     "external_revision": 6, "external_settings": {"subtitle_font_size": 52}}
    case["case_sha256"] = canonical_case_sha256(case)
    _ModelHandler.proposal = {"kind": "operation", "operation_id": "project.subtitle-font-size.set",
        "operation_version": 1, "arguments": {"value": 64}, "generate_after_save": False}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        input_path = tmp_path / "mutation.json"
        input_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        observation = run_trial_host(candidate_root=Path(__file__).parents[2], mode="all_tools",
            input_path=input_path, output_path=tmp_path / "mutation-output.json",
            storage=tmp_path / "mutation-storage", model="d36-test-model",
            base_url=f"http://127.0.0.1:{server.server_port}/v1")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert observation.before.project_count == observation.after.project_count == 1
    assert observation.before.projects_sha256 != observation.after.projects_sha256
    assert observation.effects.settings == 1


def test_logical_state_hashes_are_deterministic_across_fresh_runs(tmp_path: Path) -> None:
    _ModelHandler.proposal = {
        "kind": "operation", "operation_id": "project.subtitle-font-size.set",
        "operation_version": 1, "arguments": {"value": 64}, "generate_after_save": False,
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    observations = []
    try:
        payload = json.dumps(_bound_case(), ensure_ascii=False)
        for sequence in range(2):
            input_path = tmp_path / f"deterministic-{sequence}.json"
            input_path.write_text(payload, encoding="utf-8")
            observations.append(run_trial_host(
                candidate_root=Path(__file__).parents[2], mode="all_tools", input_path=input_path,
                output_path=tmp_path / f"deterministic-{sequence}-output.json",
                storage=tmp_path / f"deterministic-{sequence}-storage", model="d36-test-model",
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
            ))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    first, second = observations
    assert first.before == second.before
    assert first.after == second.after
    assert first.response == second.response
    assert first.effects == second.effects


def test_candidate_snapshot_detects_worker_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    backend = candidate / "backend"
    backend.mkdir(parents=True)
    source = backend / "candidate.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    input_path = tmp_path / "case.json"
    input_path.write_text(json.dumps(_bound_case()), encoding="utf-8")

    def mutating_worker(argv: list[str], **kwargs: Any) -> None:
        source.write_text("VALUE = 2\n", encoding="utf-8")
        Path(kwargs["env"]["D36_WORKER_OUTPUT"]).write_text(
            json.dumps(_worker_observation()), encoding="ascii"
        )

    monkeypatch.setattr("evaluation.scripts.evaluation_trial_host._run_candidate", mutating_worker)
    with pytest.raises(ValueError, match="candidate changed during trial"):
        run_trial_host(candidate_root=candidate, mode="all_tools", input_path=input_path,
            output_path=tmp_path / "output.json", storage=tmp_path / "storage", model="test-model")
    assert not (tmp_path / "output.json").exists()


def test_atomic_publish_uses_no_replace_hard_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    output = tmp_path / "published.json"
    real_link = os.link
    linked = False

    def competing_link(source: Path, destination: Path, *args: Any, **kwargs: Any) -> None:
        nonlocal linked
        linked = True
        output.write_bytes(b"competitor\n")
        real_link(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", competing_link)
    with pytest.raises(ValueError, match="output must not exist"):
        trial_host._atomic_publish(output, b"ours\n", candidate_root=candidate)
    assert linked
    assert output.read_bytes() == b"competitor\n"
    assert not list(tmp_path.glob(".published.json.*.tmp"))


def test_host_rejects_symlink_candidate_backend_when_supported(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    real_backend = tmp_path / "real-backend"
    real_backend.mkdir()
    try:
        (candidate / "backend").symlink_to(real_backend, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    input_path = tmp_path / "case.json"
    input_path.write_text(json.dumps(_bound_case()), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate root is invalid"):
        run_trial_host(candidate_root=candidate, mode="all_tools", input_path=input_path,
            output_path=tmp_path / "output.json", storage=tmp_path / "storage", model="test-model")


def test_host_refuses_label_input_and_nonfresh_storage_before_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    (candidate / "backend").mkdir(parents=True)
    storage = tmp_path / "case-storage"
    storage.mkdir()
    (storage / "stale").write_text("old", encoding="utf-8")
    input_path = tmp_path / "case.json"
    labeled = _bound_case()
    labeled["expected"] = {"status": "completed"}
    input_path.write_text(json.dumps(labeled), encoding="utf-8")

    def forbidden_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("candidate must not run")

    monkeypatch.setattr(subprocess, "run", forbidden_run)
    with pytest.raises(ValueError, match="invalid unlabeled trial case"):
        run_trial_host(
            candidate_root=candidate,
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "observation.json",
            storage=storage,
            model="test-model",
        )

    input_path.write_text(json.dumps(_bound_case()), encoding="utf-8")
    with pytest.raises(ValueError, match="storage must be empty"):
        run_trial_host(
            candidate_root=candidate,
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "observation.json",
            storage=storage,
            model="test-model",
        )
