from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError

from evaluation.unlabeled_contracts import UnlabeledTrialCase, canonical_case_sha256
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

    def do_POST(self) -> None:  # noqa: N802
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


def test_real_candidate_worker_executes_language_route(tmp_path: Path) -> None:
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


def test_real_worker_seeds_complete_allowed_initial_state(tmp_path: Path) -> None:
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
