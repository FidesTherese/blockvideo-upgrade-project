"""Run one label-free trial against a detached D35 candidate subprocess."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_WORKER_OUTPUT_BYTES = 512 * 1024
MAX_SUBPROCESS_LOG_BYTES = 2 * 1024 * 1024
PROTOCOL_DEADLINE_SECONDS = 180
MODEL_CALL_LIMIT = 4
SUBPROCESS_TIMEOUT_SECONDS = PROTOCOL_DEADLINE_SECONDS * MODEL_CALL_LIMIT + 30
_REPARSE_POINT = 0x400

ResponseStatus = Literal["ready", "needs_input", "unsupported", "blocked", "error", "completed", "dismissed", "http_error"]
ResponseMode = Literal["all_tools", "semantic", "stateful"]
OperationId = Literal[
    "project.subtitle-font-size.set", "project.subtitle-font-size.adjust", "project.settings.update",
    "project.status.get", "project.generation.start", "project.generation.cancel",
    "project.generation.retry", "project.settings.restore",
]
ReasonCode = Literal[
    "invalid_request", "stale_state", "project_busy", "request_conflict", "dialogue_superseded",
    "dialogue_unavailable", "dialogue_limit", "parent_not_found", "dialogue_target_mismatch",
    "dialogue_not_pending", "dialogue_stale", "target_required", "target_conflict", "target_not_found",
    "request_not_ready", "confirmation_mismatch", "generation_confirmation_required",
    "core_request_conflict", "request_not_found", "request_id_conflict", "invalid_arguments",
    "operation_not_found", "invalid_generation_request", "job_not_found", "job_not_retryable",
    "settings_revision_not_found", "database_busy", "external_outcome_unknown",
    "interpretation_failed", "interpretation_interrupted", "model_not_configured", "not_ready",
    "invalid_input", "invalid_json", "invalid_output", "candidate_not_offered", "invalid_response",
    "refused", "incomplete_response", "response_too_large", "http_error", "timeout",
    "configuration_error", "connection_failed", "model_mismatch", "retrieval_deadline",
    "retrieval_integrity_failed", "retrieval_unavailable", "deadline_exceeded", "internal_error",
]
FailureClass = Literal[
    "http_4xx", "http_5xx", "candidate_error", "model_call_limit", "timeout", "output_limit",
    "invalid_observation",
]
ProjectStatusValue = Literal[
    "pending", "splitting", "planning", "generating", "rendering", "completed", "failed", "cancelled",
]


class _StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RedactedResponse(_StrictRecord):
    status: ResponseStatus
    mode: ResponseMode
    executed: bool
    requires_confirmation: bool
    operation_id: OperationId | None = None
    reason_code: ReasonCode | None = None
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RedactedState(_StrictRecord):
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    project_status: ProjectStatusValue
    settings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    projects_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    history_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    jobs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipts_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    external_calls_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    language_requests_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    language_turns_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    project_count: int = Field(ge=1, le=17)
    history_count: int = Field(ge=0, le=32)
    job_count: int = Field(ge=0, le=32)
    artifact_count: int = Field(ge=0, le=32)
    receipt_count: int = Field(ge=0, le=64)
    external_call_count: int = Field(ge=0, le=32)
    language_request_count: int = Field(ge=0, le=16)
    language_turn_count: int = Field(ge=0, le=16)


class ObservedEffects(_StrictRecord):
    settings: int = Field(ge=0, le=1)
    revision: int = Field(ge=0, le=10**12)
    jobs: int = Field(ge=0, le=1)
    cancellations: int = Field(ge=0, le=1)
    receipts: int = Field(ge=0, le=1)
    artifacts: int = Field(ge=0, le=1)
    external_calls: int = Field(ge=0, le=1)
    history: int = Field(ge=0, le=1)
    language_records: int = Field(ge=0, le=1)


class ReplayObservation(_StrictRecord):
    attempted: bool
    model_calls: int = Field(ge=0, le=MODEL_CALL_LIMIT)
    state_unchanged: bool
    same_response: bool
    failure_class: FailureClass | None = None


class ConfirmationObservation(_StrictRecord):
    attempted: bool
    duplicate_attempted: bool
    state_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    duplicate_same_response: bool | None = None
    failure_class: FailureClass | None = None


class _WorkerObservation(_StrictRecord):
    schema_version: Literal[1]
    response: RedactedResponse
    before: RedactedState
    after: RedactedState
    effects: ObservedEffects
    model_calls: int = Field(ge=0, le=MODEL_CALL_LIMIT)
    failure_class: FailureClass | None = None
    replay: ReplayObservation
    confirmation: ConfirmationObservation


class TrialObservation(_WorkerObservation):
    case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["all_tools", "stateful"]


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value).rstrip(b"\n")).hexdigest()


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT)


def _lstat_regular(path: Path, error: str) -> os.stat_result:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(error)
    return metadata


def _lstat_directory(path: Path, error: str) -> os.stat_result:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(error)
    return metadata


def _bounded_bytes(path: Path, limit: int, error: str) -> bytes:
    before = _lstat_regular(path, error)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError(error)
        value = os.read(descriptor, limit + 1)
    finally:
        os.close(descriptor)
    if len(value) > limit:
        raise ValueError(error)
    return value


def _contained(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return False
    return True


def _outside_candidate(path: Path, candidate_root: Path) -> bool:
    return not _contained(path, candidate_root)


def _secure_directory(path: Path, *, create: bool, empty: bool, error: str) -> Path:
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
        _lstat_directory(path.parent, error)
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
    _lstat_directory(path, error)
    resolved = path.resolve(strict=True)
    if empty and any(path.iterdir()):
        raise ValueError(error)
    return resolved


def _exclusive_file(path: Path) -> int:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.open(path, flags, 0o600)


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = _exclusive_file(path)
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _clean_environment(candidate_backend: Path, storage: Path, case_path: Path, worker_output: Path,
                       mode: str, model: str, index: Path | None, base_url: str, *, phase: str,
                       previous_output: Path | None = None) -> dict[str, str]:
    retained = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    env = {name: os.environ[name] for name in retained if name in os.environ}
    env.update({
        "PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0", "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(candidate_backend), "D36_WORKER_INPUT": str(case_path),
        "D36_WORKER_OUTPUT": str(worker_output), "D36_STORAGE_ROOT": str(storage),
        "D36_WORKER_PHASE": phase, "D36_MODE": mode, "D36_MODEL": model,
        "D36_BASE_URL": base_url, "DATABASE_URL": f"sqlite:///{(storage / 'trial.db').as_posix()}",
        "STORAGE_ROOT": str(storage), "LANGUAGE_MODEL": model, "LANGUAGE_BASE_URL": base_url,
        "LANGUAGE_REVIEW_ALL": "false",
    })
    if previous_output is not None:
        env["D36_PREVIOUS_OUTPUT"] = str(previous_output)
    if index is not None:
        env.update({"D36_INDEX": str(index), "LANGUAGE_RETRIEVAL_INDEX": str(index),
                    "LANGUAGE_RETRIEVAL_READINESS": "true"})
    return env


def _unlink_retry(path: Path) -> None:
    for attempt in range(20):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.025)


def _run_candidate(command: list[str], *, cwd: Path, env: dict[str, str], storage: Path) -> None:
    token = secrets.token_hex(16)
    stdout_path, stderr_path = storage / f"worker-{token}.stdout", storage / f"worker-{token}.stderr"
    stdout_fd, stderr_fd = _exclusive_file(stdout_path), _exclusive_file(stderr_path)
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=stdout_fd, stderr=stderr_fd, close_fds=True)
    except OSError:
        os.close(stdout_fd)
        os.close(stderr_fd)
        raise ValueError("candidate subprocess failed") from None
    os.close(stdout_fd)
    os.close(stderr_fd)
    deadline = time.monotonic() + SUBPROCESS_TIMEOUT_SECONDS
    failure: str | None = None
    try:
        while process.poll() is None:
            if time.monotonic() >= deadline:
                failure = "candidate subprocess timed out"
                process.kill()
                break
            if stdout_path.stat().st_size > MAX_SUBPROCESS_LOG_BYTES or stderr_path.stat().st_size > MAX_SUBPROCESS_LOG_BYTES:
                failure = "candidate subprocess output limit exceeded"
                process.kill()
                break
            time.sleep(0.02)
        process.wait(timeout=5)
        if failure is not None or process.returncode != 0:
            raise ValueError(failure or "candidate subprocess failed")
        if stdout_path.stat().st_size > MAX_SUBPROCESS_LOG_BYTES or stderr_path.stat().st_size > MAX_SUBPROCESS_LOG_BYTES:
            raise ValueError("candidate subprocess output limit exceeded")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        _unlink_retry(stdout_path)
        _unlink_retry(stderr_path)


def _atomic_publish(output_path: Path, payload: bytes, *, candidate_root: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parent = _secure_directory(output_path.parent, create=False, empty=False, error="output directory is invalid")
    if not _outside_candidate(parent, candidate_root):
        raise ValueError("trial storage and output must be external to candidate")
    if output_path.exists() or output_path.is_symlink():
        raise ValueError("output must not exist")
    temporary = parent / f".{output_path.name}.{secrets.token_hex(16)}.tmp"
    try:
        _write_exclusive(temporary, payload)
        _lstat_regular(temporary, "output temporary file is invalid")
        if not _contained(temporary, parent):
            raise ValueError("output temporary file escaped output directory")
        if output_path.exists() or output_path.is_symlink():
            raise ValueError("output must not exist")
        os.replace(temporary, output_path)
        _lstat_regular(output_path, "published output is invalid")
        _fsync_directory(parent)
    finally:
        temporary.unlink(missing_ok=True)


def run_trial_host(*, candidate_root: Path, mode: str, input_path: Path, output_path: Path,
                   storage: Path, model: str, index: Path | None = None,
                   base_url: str = "http://127.0.0.1:1234/v1") -> TrialObservation:
    if mode not in {"all_tools", "stateful"}:
        raise ValueError("unsupported evaluation mode")
    if mode == "stateful" and index is None:
        raise ValueError("stateful mode requires an index")
    if mode == "all_tools" and index is not None:
        raise ValueError("all_tools mode rejects an index")
    if not model.strip() or len(model) > 128 or len(base_url) > 512:
        raise ValueError("model configuration is invalid")

    raw_input = _bounded_bytes(input_path, MAX_INPUT_BYTES, "invalid unlabeled trial input")
    try:
        from evaluation.unlabeled_contracts import UnlabeledTrialCase
        trial = UnlabeledTrialCase.model_validate_json(raw_input)
    except (ValidationError, ValueError):
        raise ValueError("invalid unlabeled trial case") from None

    _lstat_directory(candidate_root, "candidate root is invalid")
    candidate_root = candidate_root.resolve(strict=True)
    candidate_backend = candidate_root / "backend"
    _lstat_directory(candidate_backend, "candidate root is invalid")
    if not _contained(candidate_backend, candidate_root):
        raise ValueError("candidate root is invalid")
    if not _outside_candidate(storage, candidate_root) or not _outside_candidate(output_path, candidate_root):
        raise ValueError("trial storage and output must be external to candidate")
    if output_path.exists() or output_path.is_symlink():
        raise ValueError("output must not exist")
    storage = _secure_directory(storage, create=True, empty=True, error="storage must be empty")
    if index is not None:
        _lstat_directory(index, "stateful index is invalid")
        index = index.resolve(strict=True)
    worker_input = storage / f"validated-case-{secrets.token_hex(16)}.json"
    _write_exclusive(worker_input, _canonical_json_bytes(trial.model_dump(mode="json", exclude_unset=True)))
    _fsync_directory(storage)

    worker_script = str(Path(__file__).resolve())
    bootstrap = (
        "import runpy,sys;"
        f"sys.argv=[{worker_script!r},'--candidate-worker'];"
        f"runpy.run_path({worker_script!r},run_name='__main__')"
    )
    command = [sys.executable, "-c", bootstrap]
    event_kind = trial.event.kind
    if event_kind == "restart_resend":
        first_output = storage / f"worker-phase1-{secrets.token_hex(16)}.json"
        env = _clean_environment(candidate_backend, storage, worker_input, first_output, mode, model, index, base_url,
                                 phase="restart_prepare")
        _run_candidate(command, cwd=candidate_backend, env=env, storage=storage)
        _bounded_bytes(first_output, MAX_WORKER_OUTPUT_BYTES, "invalid candidate observation")
        worker_output = storage / f"worker-observation-{secrets.token_hex(16)}.json"
        env = _clean_environment(candidate_backend, storage, worker_input, worker_output, mode, model, index, base_url,
                                 phase="restart_replay", previous_output=first_output)
        _run_candidate(command, cwd=candidate_backend, env=env, storage=storage)
    else:
        worker_output = storage / f"worker-observation-{secrets.token_hex(16)}.json"
        env = _clean_environment(candidate_backend, storage, worker_input, worker_output, mode, model, index, base_url,
                                 phase="single")
        _run_candidate(command, cwd=candidate_backend, env=env, storage=storage)

    raw_observation = _bounded_bytes(worker_output, MAX_WORKER_OUTPUT_BYTES, "invalid candidate observation")
    try:
        worker = _WorkerObservation.model_validate_json(raw_observation)
    except (ValidationError, ValueError):
        raise ValueError("invalid candidate observation") from None
    observation = TrialObservation(**worker.model_dump(mode="python"), case_sha256=trial.case_sha256,
                                   input_sha256=hashlib.sha256(raw_input).hexdigest(), mode=mode)
    _atomic_publish(output_path, _canonical_json_bytes(observation.model_dump(mode="json")), candidate_root=candidate_root)
    return observation


def _candidate_worker() -> int:
    try:
        from fastapi.testclient import TestClient
        from sqlalchemy import select

        from app.api import routes_language
        from app.core.config import get_settings
        from app.db import get_session_factory
        from app.interpretation.contracts import ClarificationProposal, InterpretationOutcome
        from app.interpretation.local_chat import LocalChatAdapter
        from app.language_operations.contracts import LanguageResponse
        from app.main import create_app
        from app.models.artifact import GenerationArtifact
        from app.models.external_call import ExternalCall
        from app.models.job import GenerationJob, JobStatus
        from app.models.language_request import LanguageRequestRecord
        from app.models.language_turn import LanguageTurn
        from app.models.operation_request import OperationReceipt
        from app.models.project import Project, ProjectStatus
        from app.models.settings_revision import SettingsRevision
        from app.operations.contracts import OperationRequest, OperationResult, OperationTarget
        from app.schemas import ProjectCreate
        from app.services.generation_snapshots import capture_inputs, fingerprint_inputs
        from app.services.settings_history import configuration

        case = json.loads(Path(os.environ["D36_WORKER_INPUT"]).read_text(encoding="ascii"))
        initial, event = case["initial"], case["event"]
        settings = get_settings()
        settings.language_model, settings.language_base_url = os.environ["D36_MODEL"], os.environ["D36_BASE_URL"]
        settings.language_retrieval_index = Path(os.environ["D36_INDEX"]) if os.environ["D36_MODE"] == "stateful" else None
        calls = 0
        race_applied = False

        def apply_external_race() -> None:
            nonlocal race_applied
            if race_applied or event["kind"] != "revision_race":
                return
            race_applied = True
            with get_session_factory()() as race_db:
                project = race_db.get(Project, initial["project_id"])
                for key, value in event["external_settings"].items():
                    setattr(project, key, value)
                project.revision = event["external_revision"]
                race_db.add(SettingsRevision(project_id=project.id, revision=project.revision,
                                              settings_json=configuration(project), changed_fields=sorted(event["external_settings"])))
                race_db.commit()

        async def counted_complete(self: Any, messages: Any, schema: Any) -> str:
            nonlocal calls
            if calls >= MODEL_CALL_LIMIT:
                raise ValueError("model_call_limit")
            calls += 1
            async with LocalChatAdapter(settings.language_base_url, settings.language_model,
                                        timeout_seconds=PROTOCOL_DEADLINE_SECONDS,
                                        reasoning_effort=settings.language_reasoning_effort) as adapter:
                result = await adapter.complete(messages, schema)
            apply_external_race()
            return result

        routes_language._LocalAdapter.complete = counted_complete

        def make_project(item: dict[str, Any], *, primary: bool = False) -> Project:
            values = ProjectCreate(title="D36 synthetic", source_script="D36 synthetic source.",
                                   use_fake_providers=True, **item["settings"]).model_dump(exclude={"providers"})
            return Project(id=item["project_id"], revision=item["revision"],
                           status=ProjectStatus(item["project_status"]), **values)

        def seed() -> None:
            primary = {"project_id": initial["project_id"], "revision": initial["revision"],
                       "settings": initial["settings"], "project_status": initial["project_status"]}
            with get_session_factory()() as db:
                projects = [make_project(primary, primary=True), *(make_project(item) for item in initial.get("additional_projects", []))]
                db.add_all(projects)
                db.flush()
                project_map = {project.id: project for project in projects}
                defaults = {project.id: configuration(project) for project in projects}
                for history in initial["history"]:
                    owner_id = history.get("project_id") or initial["project_id"]
                    db.add(SettingsRevision(project_id=owner_id, revision=history["revision"],
                        settings_json={**defaults[owner_id], **history["settings"]},
                        changed_fields=history.get("changed_fields", []),
                        restored_from_revision=history.get("restored_from_revision")))
                for item in initial["jobs"]:
                    owner = project_map[item["project_id"]]
                    snapshot = capture_inputs(owner)
                    snapshot["project"].update(item["input_settings"])
                    db.add(GenerationJob(id=item["id"], project_id=owner.id, status=JobStatus(item["status"]),
                        kind=item["kind"], block_index=item.get("block_index"), parent_job_id=item.get("parent_job_id"),
                        cancel_requested=item["cancel_requested"], input_revision=item["input_revision"],
                        input_snapshot=snapshot, input_fingerprint=fingerprint_inputs(snapshot)))
                artifacts = list(initial.get("artifacts", []))
                next_id = max([item["id"] for item in artifacts], default=0) + 1
                for revision in initial.get("artifact_revisions", []):
                    artifacts.append({"id": next_id, "project_id": initial["project_id"], "job_id": None,
                                      "revision": revision, "file_size": 1,
                                      "file_sha256": hashlib.sha256(b"x").hexdigest()})
                    next_id += 1
                for item in artifacts:
                    relative = f"projects/{item['project_id']}/history/d36-{item['id']}/video.mp4"
                    absolute = Path(os.environ["D36_STORAGE_ROOT"]) / relative
                    absolute.parent.mkdir(parents=True, exist_ok=True)
                    content = bytes.fromhex(item.get("file_content_hex", "78"))
                    if (len(content) != item["file_size"]
                            or hashlib.sha256(content).hexdigest() != item["file_sha256"]):
                        raise ValueError("artifact identity mismatch")
                    absolute.write_bytes(content)
                    artifact = GenerationArtifact(id=item["id"], project_id=item["project_id"], job_id=item.get("job_id"),
                        revision=item.get("revision"), video_path=relative,
                        input_fingerprint=None, manifest_json={"schema_version": 1, "synthetic_placeholder": True,
                                                               "file_sha256": item["file_sha256"]})
                    db.add(artifact)
                db.flush()
                primary_project = project_map[initial["project_id"]]
                owned_artifacts = [item for item in artifacts if item["project_id"] == primary_project.id]
                if owned_artifacts:
                    current = owned_artifacts[-1]
                    primary_project.current_artifact_id = current["id"]
                    primary_project.output_video_path = f"projects/{current['project_id']}/history/d36-{current['id']}/video.mp4"
                for item in initial.get("receipts", []):
                    canonical_request = json.dumps({"operation_id": item["operation_id"], "operation_version": item["operation_version"],
                        "project_id": item["project_id"], "base_revision": item["base_revision"]},
                        ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                    result = {"operation_id": item["operation_id"], "project_id": item["project_id"],
                              "revision": item["result_revision"], "changed": item["result_revision"] != item["base_revision"]}
                    canonical_sha256 = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
                    if canonical_sha256 != item["canonical_request_sha256"] or _hash(result) != item["result_sha256"]:
                        raise ValueError("receipt identity mismatch")
                    db.add(OperationReceipt(request_id=item["request_id"], canonical_request=canonical_request,
                        operation_id=item["operation_id"], operation_version=item["operation_version"],
                        project_id=item["project_id"], base_revision=item["base_revision"],
                        result_revision=item["result_revision"], resolved_arguments={},
                        generation_requested=item["generation_requested"], job_id=item.get("job_id"),
                        result_ref=f"d36:{item['request_id']}", result_json=result))
                for item in initial.get("external_calls", []):
                    body = (bytes.fromhex(item["response_body_hex"])
                            if item.get("response_body_hex") is not None else None)
                    if body is not None and hashlib.sha256(body).hexdigest() != item["response_body_sha256"]:
                        raise ValueError("external response identity mismatch")
                    db.add(ExternalCall(id=item["id"], job_id=item["job_id"], fingerprint=item["fingerprint"],
                        provider=item["provider"], endpoint=item["endpoint"], remote_side_effect=item["remote_side_effect"],
                        status=item["status"], attempts=item["attempts"], response_status=item.get("response_status"),
                        response_body=body, response_content_type=item.get("response_content_type"),
                        provider_response_id=item.get("provider_response_id"), error_code=item.get("error_code")))
                parent: str | None = None
                for turn in initial["prior_turns"]:
                    proposal = turn.get("proposal")
                    outcome = InterpretationOutcome.model_validate({
                        "status": "proposed" if proposal and proposal["kind"] == "operation" else "needs_input",
                        "proposal": proposal,
                    })
                    response = LanguageResponse(request_id=turn["request_id"], core_request_id="seed-" + turn["request_id"],
                        project_id=turn["project_id"], base_revision=turn["base_revision"], status=turn["status"],
                        interpretation=outcome, clarification=ClarificationProposal(kind="clarification",
                            question=turn["question"], missing_fields=["arguments"]) if turn.get("question") else None,
                        dialogue_available=True)
                    if turn.get("result_revision") and proposal and proposal["kind"] == "operation":
                        response = response.model_copy(update={"result": OperationResult(operation_id=proposal["operation_id"],
                            project_id=turn["project_id"], changed=turn["settings_saved"],
                            state_revision=str(turn["result_revision"]), revision=turn["result_revision"], data={}),
                            "executed": True})
                    if proposal and proposal["kind"] == "operation":
                        response = response.model_copy(update={"prepared_request": OperationRequest(
                            operation_id=proposal["operation_id"], operation_version=proposal["operation_version"],
                            target=OperationTarget(project_id=turn["project_id"]), arguments={k: v for k, v in proposal["arguments"].items() if v is not None},
                            base_revision=turn["base_revision"], request_id=response.core_request_id,
                            generation_requested=proposal["generate_after_save"])})
                    db.add(LanguageRequestRecord(request_id=response.request_id, core_request_id=response.core_request_id,
                        input_fingerprint="0" * 64, project_id=response.project_id, base_revision=response.base_revision,
                        status=response.status, owner_token="seed", lease_until=0, created_at=0,
                        request_json=None, response_json=response.model_dump(mode="json")))
                    db.add(LanguageTurn(request_id=response.request_id, text=turn["text"],
                        parent_request_id=parent, relation=turn.get("relation")))
                    if parent is not None:
                        previous = db.get(LanguageTurn, parent)
                        previous.successor_request_id = response.request_id
                    parent = response.request_id
                db.commit()

        def file_identity(relative: str | None) -> dict[str, Any] | None:
            if relative is None:
                return None
            path = Path(os.environ["D36_STORAGE_ROOT"]) / relative
            if not path.is_file():
                return {"exists": False}
            data = path.read_bytes()
            return {"exists": True, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

        def canonical_state() -> dict[str, Any]:
            with get_session_factory()() as db:
                projects = list(db.scalars(select(Project).order_by(Project.id)))
                history = list(db.scalars(select(SettingsRevision).order_by(SettingsRevision.project_id, SettingsRevision.revision)))
                jobs = list(db.scalars(select(GenerationJob).order_by(GenerationJob.id)))
                receipts = list(db.scalars(select(OperationReceipt).order_by(OperationReceipt.request_id)))
                artifacts = list(db.scalars(select(GenerationArtifact).order_by(GenerationArtifact.id)))
                calls_rows = list(db.scalars(select(ExternalCall).order_by(ExternalCall.id)))
                requests = list(db.scalars(select(LanguageRequestRecord).order_by(LanguageRequestRecord.request_id)))
                turns = list(db.scalars(select(LanguageTurn).order_by(LanguageTurn.request_id)))
                primary = db.get(Project, initial["project_id"])
                return {
                    "primary": {"revision": primary.revision, "status": primary.status.value,
                                "settings": configuration(primary)},
                    "projects": [{"id": row.id, "revision": row.revision, "status": row.status.value,
                        "settings": configuration(row), "title_sha256": _hash(row.title),
                        "source_script_sha256": _hash(row.source_script),
                        "global_visual_style_sha256": _hash(row.global_visual_style),
                        "progress": row.progress, "current_stage": row.current_stage,
                        "current_artifact_id": row.current_artifact_id,
                        "output_video": file_identity(row.output_video_path),
                        "output_subtitle": file_identity(row.output_subtitle_path),
                        "error_sha256": _hash(row.error_message),
                        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()} for row in projects],
                    "history": [{"project_id": row.project_id, "revision": row.revision,
                        "settings": row.settings_json, "changed_fields": sorted(row.changed_fields or []),
                        "restored_from_revision": row.restored_from_revision,
                        "created_at": row.created_at.isoformat()} for row in history],
                    "jobs": [{"id": row.id, "project_id": row.project_id, "status": row.status.value,
                        "current_stage": row.current_stage, "progress": row.progress,
                        "stage_progress": row.stage_progress, "input_revision": row.input_revision,
                        "cancel_requested": row.cancel_requested, "kind": row.kind,
                        "block_index": row.block_index, "parent_job_id": row.parent_job_id,
                        "input_snapshot_sha256": _hash(row.input_snapshot), "input_fingerprint": row.input_fingerprint,
                        "plan_sha256": _hash(row.plan_json), "recovery_sha256": _hash(row.recovery_message),
                        "error_sha256": _hash(row.error_message),
                        "started_at": row.started_at.isoformat() if row.started_at else None,
                        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                        "created_at": row.created_at.isoformat()} for row in jobs],
                    "receipts": [{"request_id": row.request_id,
                        "canonical_request_sha256": hashlib.sha256(row.canonical_request.encode("utf-8")).hexdigest(),
                        "operation_id": row.operation_id, "operation_version": row.operation_version,
                        "project_id": row.project_id, "base_revision": row.base_revision,
                        "result_revision": row.result_revision, "resolved_arguments_sha256": _hash(row.resolved_arguments),
                        "generation_requested": row.generation_requested, "job_id": row.job_id,
                        "result_ref_sha256": _hash(row.result_ref), "result_sha256": _hash(row.result_json),
                        "created_at": row.created_at.isoformat()} for row in receipts],
                    "artifacts": [{"id": row.id, "project_id": row.project_id, "job_id": row.job_id,
                        "revision": row.revision, "input_fingerprint": row.input_fingerprint,
                        "video": file_identity(row.video_path), "subtitle": file_identity(row.subtitle_path),
                        "manifest_sha256": _hash(row.manifest_json),
                        "created_at": row.created_at.isoformat()} for row in artifacts],
                    "external_calls": [{"id": row.id, "job_id": row.job_id, "fingerprint": row.fingerprint,
                        "provider": row.provider, "endpoint_sha256": _hash(row.endpoint),
                        "remote_side_effect": row.remote_side_effect, "status": row.status, "attempts": row.attempts,
                        "response_status": row.response_status,
                        "response_body_sha256": hashlib.sha256(row.response_body).hexdigest() if row.response_body is not None else None,
                        "response_content_type": row.response_content_type,
                        "provider_response_id_sha256": _hash(row.provider_response_id), "error_code": row.error_code,
                        "started_at": row.started_at.isoformat(),
                        "finished_at": row.finished_at.isoformat() if row.finished_at else None} for row in calls_rows],
                    "language_requests": [{"request_id": row.request_id, "input_fingerprint": row.input_fingerprint,
                        "core_request_id": row.core_request_id, "project_id": row.project_id,
                        "base_revision": row.base_revision, "status": row.status,
                        "owner_token_sha256": _hash(row.owner_token), "lease_until": row.lease_until,
                        "created_at": row.created_at, "request_sha256": _hash(row.request_json),
                        "response_sha256": _hash(row.response_json)} for row in requests],
                    "language_turns": [{"request_id": row.request_id, "parent_request_id": row.parent_request_id,
                        "relation": row.relation, "text_sha256": _hash(row.text),
                        "successor_request_id": row.successor_request_id} for row in turns],
                }

        def redact_state(value: dict[str, Any]) -> dict[str, Any]:
            primary = value["primary"]
            result = {"state_sha256": _hash(value), "project_status": primary["status"],
                      "settings_sha256": _hash(primary["settings"])}
            for name in ("projects", "history", "jobs", "receipts", "artifacts", "external_calls", "language_requests", "language_turns"):
                result[f"{name}_sha256"] = _hash(value[name])
                singular = {"projects": "project", "history": "history", "jobs": "job", "receipts": "receipt",
                            "artifacts": "artifact", "external_calls": "external_call",
                            "language_requests": "language_request", "language_turns": "language_turn"}[name]
                result[f"{singular}_count"] = len(value[name])
            return result

        def response_projection(response: dict[str, Any], status_code: int) -> dict[str, Any]:
            failure = response.get("failure") or response.get("detail") or {}
            operation = response.get("prepared_request") or response.get("result") or {}
            mode = response.get("mode", "all_tools")
            if mode == "semantic":
                mode = "stateful" if os.environ["D36_MODE"] == "stateful" else "semantic"
            status = response.get("status", "http_error" if status_code >= 400 else "error")
            reason = failure.get("reason_code") if isinstance(failure, dict) else None
            public = {"status": status, "mode": mode, "executed": bool(response.get("executed")),
                      "requires_confirmation": bool(response.get("requires_confirmation")),
                      "operation_id": operation.get("operation_id"), "reason_code": reason,
                      "project_id": response.get("project_id"), "base_revision": response.get("base_revision"),
                      "result_revision": (response.get("result") or {}).get("revision"),
                      "job_id": (response.get("generation_result") or response.get("result") or {}).get("job_id")}
            return {**{key: public[key] for key in ("status", "mode", "executed", "requires_confirmation", "operation_id", "reason_code")},
                    "response_sha256": _hash(public)}

        def request_payload(request: dict[str, Any], *, text: str | None = None,
                            target: int | None | object = ...) -> dict[str, Any]:
            target_id = request["target_project_id"] if target is ... else target
            payload: dict[str, Any] = {"request_id": request["request_id"], "text": text or request["text"],
                "base_revision": request["base_revision"], "target": {"project_id": target_id}}
            if request.get("continuation") is not None:
                payload["continuation"] = request["continuation"]
            return payload

        phase = os.environ["D36_WORKER_PHASE"]
        client = TestClient(create_app())
        client.__enter__()
        try:
            if phase != "restart_replay":
                seed()
            request = event["request"]
            payload = request_payload(request)
            before = canonical_state()
            if event["kind"] == "concurrent_identical":
                with ThreadPoolExecutor(max_workers=2) as executor:
                    submitted = list(executor.map(
                        lambda _: client.post("/api/language/requests", json=payload), range(2)
                    ))
                response_http = submitted[0]
                response = response_http.json()
                concurrent_response = submitted[1].json()
            else:
                response_http = client.post("/api/language/requests", json=payload)
                response = response_http.json()
                concurrent_response = None
            after_submit = canonical_state()
            confirmation_response: dict[str, Any] | None = None
            duplicate_confirmation: dict[str, Any] | None = None
            replay_response: dict[str, Any] | None = None
            replay_before, replay_after = after_submit, after_submit
            calls_before_event = calls

            if phase == "restart_replay":
                previous = _WorkerObservation.model_validate_json(Path(os.environ["D36_PREVIOUS_OUTPUT"]).read_bytes())
                replay_after = canonical_state()
                output = previous.model_copy(update={
                    "after": RedactedState.model_validate(redact_state(replay_after)),
                    "model_calls": previous.model_calls + calls,
                    "replay": ReplayObservation(attempted=True, model_calls=calls,
                        state_unchanged=previous.after.state_sha256 == _hash(replay_after),
                        same_response=previous.response.response_sha256 == response_projection(
                            response, response_http.status_code
                        )["response_sha256"], failure_class=None),
                })
                Path(os.environ["D36_WORKER_OUTPUT"]).write_bytes(_canonical_json_bytes(output.model_dump(mode="json")))
                return 0

            kind = event["kind"]
            if kind in {"confirm_generation", "confirm_twice"} and response.get("confirmation_token"):
                permission = {"confirmation_token": response["confirmation_token"], "confirm_generation": True}
                confirmed_http = client.post(f"/api/language/requests/{request['request_id']}/execute", json=permission)
                confirmation_response = confirmed_http.json()
                if kind == "confirm_twice":
                    duplicate_confirmation = client.post(f"/api/language/requests/{request['request_id']}/execute", json=permission).json()
            elif kind == "resend_identical":
                replay_before = canonical_state()
                replay_response = client.post("/api/language/requests", json=payload).json()
                replay_after = canonical_state()
            elif kind == "same_id_different_body":
                replacement = request_payload(request, text=event["replacement_text"],
                    target=event.get("replacement_target_project_id", request["target_project_id"]))
                replay_before = canonical_state()
                replay_response = client.post("/api/language/requests", json=replacement).json()
                replay_after = canonical_state()
            elif kind == "concurrent_identical":
                replay_before = before
                replay_response = concurrent_response
                replay_after = after_submit
            elif kind == "switch_target":
                switched = request_payload({**request, "request_id": request["request_id"] + ".switch"},
                    text=event["replacement_text"], target=event["replacement_target_project_id"])
                switched["target"]["selected_project_id"] = event["selected_project_id_after"]
                replay_before = canonical_state()
                replay_response = client.post("/api/language/requests", json=switched).json()
                replay_after = canonical_state()

            after = canonical_state()
            collection_changes = {name: int(_hash(before[name]) != _hash(after[name])) for name in
                ("history", "jobs", "receipts", "artifacts", "external_calls", "language_requests", "language_turns")}
            cancel_before = [(item["id"], item["cancel_requested"]) for item in before["jobs"]]
            cancel_after = [(item["id"], item["cancel_requested"]) for item in after["jobs"]]
            redacted_response = response_projection(response, response_http.status_code)
            replay_projection = response_projection(replay_response, 200) if replay_response is not None else None
            output = {
                "schema_version": 1, "response": redacted_response,
                "before": redact_state(before), "after": redact_state(after),
                "effects": {"settings": int(before["primary"]["settings"] != after["primary"]["settings"]),
                    "revision": abs(after["primary"]["revision"] - before["primary"]["revision"]),
                    "jobs": collection_changes["jobs"], "cancellations": int(cancel_before != cancel_after),
                    "receipts": collection_changes["receipts"], "artifacts": collection_changes["artifacts"],
                    "external_calls": collection_changes["external_calls"], "history": collection_changes["history"],
                    "language_records": int(collection_changes["language_requests"] or collection_changes["language_turns"])},
                "model_calls": calls, "failure_class": None,
                "replay": {"attempted": replay_response is not None, "model_calls": calls - calls_before_event,
                    "state_unchanged": replay_before == replay_after,
                    "same_response": replay_projection is not None and redacted_response["response_sha256"] == replay_projection["response_sha256"],
                    "failure_class": None},
                "confirmation": {"attempted": confirmation_response is not None,
                    "duplicate_attempted": duplicate_confirmation is not None,
                    "state_sha256": _hash(after) if confirmation_response is not None else None,
                    "duplicate_same_response": (_hash(response_projection(confirmation_response, 200)) ==
                        _hash(response_projection(duplicate_confirmation, 200))) if duplicate_confirmation is not None else None,
                    "failure_class": None},
            }
            Path(os.environ["D36_WORKER_OUTPUT"]).write_bytes(_canonical_json_bytes(output))
        finally:
            client.__exit__(None, None, None)
        return 0
    except BaseException:
        return 2


def main() -> int:
    if sys.argv[1:] == ["--candidate-worker"]:
        return _candidate_worker()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("all_tools", "stateful"), required=True)
    parser.add_argument("--input", dest="input_path", type=Path, required=True)
    parser.add_argument("--output", dest="output_path", type=Path, required=True)
    parser.add_argument("--storage", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    args = parser.parse_args()
    try:
        run_trial_host(**vars(args))
    except (OSError, ValueError):
        print("Candidate trial failed without exposing trial or model content.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
