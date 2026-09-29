from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError

from evaluation.unlabeled_contracts import UnlabeledTrialCase
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
        "case_sha256": "a" * 64,
    }


def _worker_observation() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "response": {
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
            "revision": 5,
            "project_status": "completed",
            "settings_sha256": "d" * 64,
            "job_count": 0,
            "artifact_count": 2,
            "receipt_count": 0,
            "external_call_count": 0,
        },
        "after": {
            "state_sha256": "e" * 64,
            "revision": 6,
            "project_status": "completed",
            "settings_sha256": "f" * 64,
            "job_count": 0,
            "artifact_count": 2,
            "receipt_count": 1,
            "external_call_count": 0,
        },
        "effects": {
            "settings": 1,
            "revision": 1,
            "jobs": 0,
            "cancellations": 0,
            "receipts": 1,
            "artifacts": 0,
            "external_calls": 0,
        },
        "model_calls": 1,
        "failure_class": None,
        "replay": {
            "attempted": True,
            "model_calls": 0,
            "state_unchanged": True,
            "same_response": True,
            "failure_class": None,
        },
        "confirmation": {
            "attempted": False,
            "duplicate_attempted": False,
            "state_sha256": None,
            "duplicate_same_response": None,
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
        UnlabeledTrialCase.model_validate([_case(), _case()])


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
    input_path.write_text(json.dumps(_case()), encoding="utf-8")
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


def test_host_uses_candidate_rooted_subprocess_and_writes_redacted_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    backend = candidate / "backend"
    backend.mkdir(parents=True)
    input_path = tmp_path / "case.json"
    input_path.write_text(json.dumps(_case(), ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "observation.json"
    storage = tmp_path / "case-storage"
    captured: dict[str, Any] = {}

    def completed(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0, json.dumps(_worker_observation()), "")

    monkeypatch.setattr(subprocess, "run", completed)
    observation = run_trial_host(
        candidate_root=candidate,
        mode="all_tools",
        input_path=input_path,
        output_path=output_path,
        storage=storage,
        model="test-model",
    )

    assert captured["cwd"] == backend
    assert captured["timeout"] == 750
    assert captured["env"]["PYTHONPATH"] == str(backend.resolve())
    assert "D36_WORKER_INPUT" in captured["env"]
    assert captured["env"]["D36_STORAGE_ROOT"] == str(storage.resolve())
    assert observation.case_sha256 == "a" * 64
    assert observation.input_sha256 == hashlib.sha256(input_path.read_bytes()).hexdigest()
    assert observation.mode == "all_tools"
    assert output_path.read_bytes() == (
        json.dumps(observation.model_dump(mode="json"), ensure_ascii=True, allow_nan=False,
                   sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("ascii")
    rendered = output_path.read_text(encoding="ascii")
    for forbidden in ("字幕を64pxにして", "expected", "labels", "model_body", str(tmp_path)):
        assert forbidden not in rendered
    assert not (storage / ".observation.tmp").exists()


def test_host_refuses_label_input_and_nonfresh_storage_before_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    (candidate / "backend").mkdir(parents=True)
    storage = tmp_path / "case-storage"
    storage.mkdir()
    (storage / "stale").write_text("old", encoding="utf-8")
    input_path = tmp_path / "case.json"
    labeled = _case()
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

    input_path.write_text(json.dumps(_case()), encoding="utf-8")
    with pytest.raises(ValueError, match="storage must be empty"):
        run_trial_host(
            candidate_root=candidate,
            mode="all_tools",
            input_path=input_path,
            output_path=tmp_path / "observation.json",
            storage=storage,
            model="test-model",
        )
