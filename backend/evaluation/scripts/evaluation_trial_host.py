"""Run one label-free trial against a detached D35 candidate subprocess."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_WORKER_OUTPUT_BYTES = 512 * 1024
PROTOCOL_DEADLINE_SECONDS = 180
MODEL_CALL_LIMIT = 4


class _StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RedactedResponse(_StrictRecord):
    status: str = Field(min_length=1, max_length=32)
    mode: str = Field(min_length=1, max_length=32)
    executed: bool
    requires_confirmation: bool
    operation_id: str | None = Field(default=None, max_length=128)
    reason_code: str | None = Field(default=None, max_length=64)
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RedactedState(_StrictRecord):
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(ge=1)
    project_status: str = Field(min_length=1, max_length=32)
    settings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    job_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    receipt_count: int = Field(ge=0)
    external_call_count: int = Field(ge=0)


class ObservedEffects(_StrictRecord):
    settings: int = Field(ge=0)
    revision: int = Field(ge=0)
    jobs: int = Field(ge=0)
    cancellations: int = Field(ge=0)
    receipts: int = Field(ge=0)
    artifacts: int = Field(ge=0)
    external_calls: int = Field(ge=0)


class ReplayObservation(_StrictRecord):
    attempted: bool
    model_calls: int = Field(ge=0, le=MODEL_CALL_LIMIT)
    state_unchanged: bool
    same_response: bool
    failure_class: str | None = Field(default=None, max_length=64)


class ConfirmationObservation(_StrictRecord):
    attempted: bool
    duplicate_attempted: bool
    state_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    duplicate_same_response: bool | None = None
    failure_class: str | None = Field(default=None, max_length=64)


class _WorkerObservation(_StrictRecord):
    schema_version: Literal[1]
    response: RedactedResponse
    before: RedactedState
    after: RedactedState
    effects: ObservedEffects
    model_calls: int = Field(ge=0, le=MODEL_CALL_LIMIT)
    failure_class: str | None = Field(default=None, max_length=64)
    replay: ReplayObservation
    confirmation: ConfirmationObservation


class TrialObservation(_WorkerObservation):
    case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["all_tools", "stateful"]


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _bounded_bytes(path: Path, limit: int, error: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(error)
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise ValueError(error)
    return value


def _outside_candidate(path: Path, candidate_root: Path) -> bool:
    try:
        path.resolve().relative_to(candidate_root.resolve())
    except ValueError:
        return True
    return False


def _clean_environment(candidate_backend: Path, storage: Path, case_path: Path, worker_output: Path,
                       mode: str, model: str, index: Path | None, base_url: str) -> dict[str, str]:
    retained = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE")
    env = {name: os.environ[name] for name in retained if name in os.environ}
    env.update({
        "PYTHONPATH": str(candidate_backend.resolve()),
        "D36_WORKER_INPUT": str(case_path.resolve()),
        "D36_WORKER_OUTPUT": str(worker_output.resolve()),
        "D36_STORAGE_ROOT": str(storage.resolve()),
        "D36_MODE": mode,
        "D36_MODEL": model,
        "D36_BASE_URL": base_url,
        "DATABASE_URL": f"sqlite:///{(storage / 'trial.db').resolve().as_posix()}",
        "STORAGE_ROOT": str(storage.resolve()),
        "LANGUAGE_MODEL": model,
        "LANGUAGE_BASE_URL": base_url,
        "LANGUAGE_REVIEW_ALL": "false",
    })
    if index is not None:
        env["D36_INDEX"] = str(index.resolve())
        env["LANGUAGE_RETRIEVAL_INDEX"] = str(index.resolve())
        env["LANGUAGE_RETRIEVAL_READINESS"] = "true"
    return env


def run_trial_host(*, candidate_root: Path, mode: str, input_path: Path, output_path: Path,
                   storage: Path, model: str, index: Path | None = None,
                   base_url: str = "http://127.0.0.1:1234/v1") -> TrialObservation:
    if mode not in {"all_tools", "stateful"}:
        raise ValueError("unsupported evaluation mode")
    if mode == "stateful" and index is None:
        raise ValueError("stateful mode requires an index")
    if mode == "all_tools" and index is not None:
        raise ValueError("all_tools mode rejects an index")
    if not model.strip():
        raise ValueError("model is required")

    raw_input = _bounded_bytes(input_path, MAX_INPUT_BYTES, "invalid unlabeled trial input")
    try:
        from evaluation.unlabeled_contracts import UnlabeledTrialCase

        trial = UnlabeledTrialCase.model_validate_json(raw_input)
    except (ValidationError, ValueError):
        raise ValueError("invalid unlabeled trial case") from None

    candidate_root = candidate_root.resolve()
    candidate_backend = candidate_root / "backend"
    if candidate_root.is_symlink() or not candidate_backend.is_dir():
        raise ValueError("candidate root is invalid")
    if not _outside_candidate(storage, candidate_root) or not _outside_candidate(output_path, candidate_root):
        raise ValueError("trial storage and output must be external to candidate")
    if output_path.exists() or output_path.is_symlink():
        raise ValueError("output must not exist")
    if storage.exists():
        if storage.is_symlink() or not storage.is_dir() or any(storage.iterdir()):
            raise ValueError("storage must be empty")
    else:
        storage.mkdir(parents=True)

    worker_input = storage / "validated-case.json"
    worker_output = storage / "worker-observation.json"
    worker_input.write_bytes(_canonical_json_bytes(trial.model_dump(mode="json")))
    env = _clean_environment(candidate_backend, storage, worker_input, worker_output, mode, model, index, base_url)
    command = [sys.executable, str(Path(__file__).resolve()), "--candidate-worker"]
    try:
        completed = subprocess.run(
            command,
            cwd=candidate_backend,
            env=env,
            capture_output=True,
            text=True,
            timeout=PROTOCOL_DEADLINE_SECONDS * MODEL_CALL_LIMIT + 30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("candidate subprocess failed") from None
    if completed.returncode != 0:
        raise ValueError("candidate subprocess failed")

    if worker_output.exists():
        raw_observation = _bounded_bytes(worker_output, MAX_WORKER_OUTPUT_BYTES, "invalid candidate observation")
    else:
        raw_observation = completed.stdout.encode("utf-8")
        if len(raw_observation) > MAX_WORKER_OUTPUT_BYTES:
            raise ValueError("invalid candidate observation")
    try:
        worker = _WorkerObservation.model_validate_json(raw_observation)
    except (ValidationError, ValueError):
        raise ValueError("invalid candidate observation") from None

    observation = TrialObservation(
        **worker.model_dump(mode="python"),
        case_sha256=trial.case_sha256,
        input_sha256=hashlib.sha256(raw_input).hexdigest(),
        mode=mode,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    try:
        temporary.write_bytes(_canonical_json_bytes(observation.model_dump(mode="json")))
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return observation


def _hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _candidate_worker() -> int:
    """Execute only after Python has rooted imports at the detached candidate backend."""
    try:
        from fastapi.testclient import TestClient
        from sqlalchemy import func, select

        from app.api import routes_language
        from app.core.config import get_settings
        from app.db import get_session_factory
        from app.interpretation.local_chat import LocalChatAdapter
        from app.main import create_app
        from app.models.artifact import GenerationArtifact
        from app.models.external_call import ExternalCall
        from app.models.job import GenerationJob, JobStatus
        from app.models.operation_request import OperationReceipt
        from app.models.project import Project, ProjectStatus
        from app.models.settings_revision import SettingsRevision
        from app.schemas import ProjectCreate

        case = json.loads(Path(os.environ["D36_WORKER_INPUT"]).read_text(encoding="ascii"))
        initial = case["initial"]
        settings = get_settings()
        settings.language_model = os.environ["D36_MODEL"]
        settings.language_base_url = os.environ["D36_BASE_URL"]
        settings.language_retrieval_index = Path(os.environ["D36_INDEX"]) if os.environ["D36_MODE"] == "stateful" else None
        calls = 0

        async def counted_complete(self: Any, messages: Any, schema: Any) -> str:
            nonlocal calls
            if calls >= MODEL_CALL_LIMIT:
                raise ValueError("model_call_limit")
            calls += 1
            async with LocalChatAdapter(
                settings.language_base_url,
                settings.language_model,
                timeout_seconds=PROTOCOL_DEADLINE_SECONDS,
                reasoning_effort=settings.language_reasoning_effort,
            ) as adapter:
                return await adapter.complete(messages, schema)

        routes_language._LocalAdapter.complete = counted_complete
        client = TestClient(create_app())
        client.__enter__()
        try:
            values = ProjectCreate(title="D36 synthetic", source_script="D36 synthetic source.", use_fake_providers=True,
                                   **initial["settings"]).model_dump(exclude={"providers"})
            project = Project(id=initial["project_id"], revision=initial["revision"],
                              status=ProjectStatus(initial["project_status"]), **values)
            with get_session_factory()() as db:
                db.add(project)
                db.flush()
                for history in initial["history"]:
                    db.add(SettingsRevision(project_id=project.id, revision=history["revision"],
                                            settings_json=history["settings"], changed_fields=[]))
                for item in initial["jobs"]:
                    db.add(GenerationJob(id=item["id"], project_id=item["project_id"], status=JobStatus(item["status"]),
                                         kind=item["kind"], cancel_requested=item["cancel_requested"],
                                         input_revision=item["input_revision"], input_snapshot={}, input_fingerprint="0" * 64))
                for number, revision in enumerate(initial["artifact_revisions"], 1):
                    db.add(GenerationArtifact(id=number, project_id=project.id, revision=revision,
                                              video_path=f"synthetic/{number}.mp4", manifest_json={"synthetic": True}))
                db.commit()

            def state() -> dict[str, Any]:
                with get_session_factory()() as db:
                    current = db.get(Project, initial["project_id"])
                    public = {
                        "revision": current.revision,
                        "project_status": current.status.value,
                        "settings": {name: getattr(current, name) for name in initial["settings"]},
                        "jobs": [(row.id, row.status.value, row.cancel_requested) for row in db.scalars(select(GenerationJob).order_by(GenerationJob.id))],
                        "artifacts": db.scalar(select(func.count()).select_from(GenerationArtifact)),
                        "receipts": db.scalar(select(func.count()).select_from(OperationReceipt)),
                        "external_calls": db.scalar(select(func.count()).select_from(ExternalCall)),
                    }
                return public

            def redacted_state(value: dict[str, Any]) -> dict[str, Any]:
                return {
                    "state_sha256": _hash(value), "revision": value["revision"],
                    "project_status": value["project_status"], "settings_sha256": _hash(value["settings"]),
                    "job_count": len(value["jobs"]), "artifact_count": value["artifacts"],
                    "receipt_count": value["receipts"], "external_call_count": value["external_calls"],
                }

            request = case["event"]["request"]
            payload = {"request_id": request["request_id"], "text": request["text"],
                       "base_revision": request["base_revision"],
                       "target": {"project_id": request["target_project_id"]}}
            if request["continuation"] is not None:
                payload["continuation"] = request["continuation"]
            before = state()
            response = client.post("/api/language/requests", json=payload).json()
            confirmation_response = None
            duplicate_confirmation = None
            event_kind = case["event"]["kind"]
            if event_kind in {"confirm_generation", "confirm_twice"} and response.get("confirmation_token"):
                permission = {"confirmation_token": response["confirmation_token"], "confirm_generation": True}
                confirmation_response = client.post("/api/language/requests/generate/execute", json=permission).json()
                if event_kind == "confirm_twice":
                    duplicate_confirmation = client.post("/api/language/requests/generate/execute", json=permission).json()
            after = state()
            calls_before_replay = calls
            replay_before = state()
            replay = client.post("/api/language/requests", json=payload).json()
            replay_after = state()
            operation = response.get("prepared_request") or response.get("result") or {}
            output = {
                "schema_version": 1,
                "response": {"status": response.get("status", "error"), "mode": response.get("mode", "all_tools"),
                             "executed": bool(response.get("executed")),
                             "requires_confirmation": bool(response.get("requires_confirmation")),
                             "operation_id": operation.get("operation_id"),
                             "reason_code": (response.get("failure") or {}).get("reason_code"),
                             "response_sha256": _hash(response)},
                "before": redacted_state(before), "after": redacted_state(after),
                "effects": {"settings": int(before["settings"] != after["settings"]),
                            "revision": abs(after["revision"] - before["revision"]),
                            "jobs": abs(len(after["jobs"]) - len(before["jobs"])),
                            "cancellations": sum(a[2] != b[2] for a, b in zip(before["jobs"], after["jobs"], strict=False)),
                            "receipts": abs(after["receipts"] - before["receipts"]),
                            "artifacts": abs(after["artifacts"] - before["artifacts"]),
                            "external_calls": abs(after["external_calls"] - before["external_calls"])},
                "model_calls": calls, "failure_class": None,
                "replay": {"attempted": True, "model_calls": calls - calls_before_replay,
                           "state_unchanged": replay_before == replay_after,
                           "same_response": _hash(response) == _hash(replay), "failure_class": None},
                "confirmation": {"attempted": confirmation_response is not None,
                                 "duplicate_attempted": duplicate_confirmation is not None,
                                 "state_sha256": _hash(after) if confirmation_response is not None else None,
                                 "duplicate_same_response": (_hash(confirmation_response) == _hash(duplicate_confirmation)
                                                             if duplicate_confirmation is not None else None),
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
