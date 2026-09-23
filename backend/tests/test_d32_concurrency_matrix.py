"""D32 concurrency snapshots and spawned-process operation races."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from enum import Enum
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import pytest

from sqlalchemy import select

from app.db import get_session_factory
from app.models.artifact import GenerationArtifact
from app.models.external_call import ExternalCall
from app.models.job import GenerationJob
from app.models.operation_request import OperationReceipt
from app.models.project import Project
from app.models.settings_revision import SettingsRevision
from app.services.settings_history import configuration
from tests.test_operation_processes import adjustment, make_project, run_process


_PROCESS_RACE_WORKER = r"""
import json
from pathlib import Path
import sys
import time

from app.db import get_session_factory
from app.operations.bootstrap import build_operation_service
from app.operations.contracts import OperationRequest
from app.operations.errors import OperationError

request = OperationRequest.model_validate(json.loads(sys.argv[1]))
ready_path = Path(sys.argv[2])
release_path = Path(sys.argv[3])
service = build_operation_service()
with get_session_factory()() as db:
    ready_path.write_text("ready", encoding="ascii")
    deadline = time.monotonic() + 30
    while not release_path.exists():
        if time.monotonic() >= deadline:
            raise SystemExit("parent did not release process race")
        time.sleep(0.01)
    try:
        result = service.execute(db, request)
        print(json.dumps(result.model_dump(mode="json")))
    except OperationError as error:
        print(json.dumps({"reason_code": error.reason_code}))
"""


def _run_process_race(
    requests: list[dict[str, Any]], rendezvous_dir: Path
) -> list[subprocess.CompletedProcess[str]]:
    rendezvous_dir.mkdir()
    release_path = rendezvous_dir / "release"
    processes: list[subprocess.Popen[str]] = []
    try:
        for index, request in enumerate(requests):
            ready_path = rendezvous_dir / f"ready-{index}"
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        _PROCESS_RACE_WORKER,
                        json.dumps(request),
                        str(ready_path),
                        str(release_path),
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=Path(__file__).resolve().parents[1],
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    ),
                )
            )

        ready_paths = [rendezvous_dir / f"ready-{index}" for index in range(len(requests))]
        deadline = time.monotonic() + 30
        while not all(path.exists() for path in ready_paths):
            exited = [process.returncode for process in processes if process.poll() is not None]
            if exited:
                raise AssertionError(f"race worker exited before rendezvous: {exited}")
            if time.monotonic() >= deadline:
                raise AssertionError("race workers did not reach rendezvous")
            time.sleep(0.01)

        release_path.write_text("release", encoding="ascii")
        completed: list[subprocess.CompletedProcess[str]] = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=40)
            completed.append(
                subprocess.CompletedProcess(
                    process.args, process.returncode, stdout=stdout, stderr=stderr
                )
            )
        return completed
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()


def _canonical_adjustment(project_id: int, delta: int) -> str:
    return json.dumps(
        {
            "arguments": {"delta": delta},
            "base_revision": 1,
            "generation_requested": False,
            "observed_state_revision": None,
            "operation_id": "project.subtitle-font-size.adjust",
            "operation_version": 1,
            "project_id": project_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _canonical(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _record(row: Any) -> dict[str, Any]:
    return {
        column.name: _canonical(getattr(row, column.name))
        for column in row.__table__.columns
    }


def snapshot(project_id: int) -> dict[str, object]:
    """Reopen the database and return a deterministic, JSON-safe durable-state view."""
    with get_session_factory()() as db:
        project = db.get(Project, project_id)
        assert project is not None
        return {
            "project": {
                "id": project.id,
                "revision": project.revision,
                "settings": _canonical(configuration(project)),
                "status": project.status.value,
                "current_artifact_id": project.current_artifact_id,
            },
            "settings_history": [
                _record(row)
                for row in db.scalars(
                    select(SettingsRevision)
                    .where(SettingsRevision.project_id == project_id)
                    .order_by(SettingsRevision.revision, SettingsRevision.id)
                )
            ],
            "jobs": [
                _record(row)
                for row in db.scalars(
                    select(GenerationJob)
                    .where(GenerationJob.project_id == project_id)
                    .order_by(GenerationJob.id)
                )
            ],
            "receipts": [
                _record(row)
                for row in db.scalars(
                    select(OperationReceipt)
                    .where(OperationReceipt.project_id == project_id)
                    .order_by(OperationReceipt.request_id)
                )
            ],
            "external_calls": [
                _record(row)
                for row in db.scalars(
                    select(ExternalCall)
                    .where(
                        ExternalCall.job_id.in_(
                            select(GenerationJob.id).where(
                                GenerationJob.project_id == project_id
                            )
                        )
                    )
                    .order_by(ExternalCall.id)
                )
            ],
            "artifacts": [
                _record(row)
                for row in db.scalars(
                    select(GenerationArtifact)
                    .where(GenerationArtifact.project_id == project_id)
                    .order_by(GenerationArtifact.id)
                )
            ],
        }


def test_snapshot_reopens_complete_canonical_state(temp_storage) -> None:
    project_id = make_project()
    request = adjustment(project_id, request_id=f"d32-snapshot-{project_id}", generate=True)
    process = run_process(request.model_dump(mode="json"))
    assert process.returncode == 0, process.stderr

    first = snapshot(project_id)
    second = snapshot(project_id)

    assert first == second
    assert first["project"]["revision"] == 2
    assert [row["revision"] for row in first["settings_history"]] == [1, 2]
    assert len(first["receipts"]) == 1
    assert len(first["jobs"]) == 1
    assert first["jobs"][0]["status"] == "pending"
    assert first["external_calls"] == []
    assert first["artifacts"] == []
    json.dumps(first, sort_keys=True, allow_nan=False)


@pytest.mark.parametrize(
    "mode",
    ("same-id-same-body", "same-id-different-body", "different-id-same-revision"),
)
def test_repeated_three_process_matrix(temp_storage, tmp_path: Path, mode: str) -> None:
    for iteration in range(5):
        project_id = make_project()
        before = snapshot(project_id)
        shared_id = f"d32-{mode}-{project_id}"
        requests = []
        for index in range(3):
            request_id = (
                f"{shared_id}-{index}"
                if mode == "different-id-same-revision"
                else shared_id
            )
            delta = 2 + index if mode == "same-id-different-body" else 2
            request = adjustment(project_id, request_id=request_id, delta=delta)
            requests.append(request.model_dump(mode="json"))

        processes = _run_process_race(
            requests, tmp_path / f"{mode}-{iteration}"
        )
        for process in processes:
            assert process.returncode == 0, process.stderr
        serialized = [process.stdout for process in processes]
        results = [json.loads(process.stdout) for process in processes]
        successful = [item for item in results if item.get("revision") == 2]
        if mode == "same-id-same-body":
            assert serialized[0] == serialized[1] == serialized[2]
            assert len(successful) == 3
        else:
            reason_code = (
                "request_id_conflict"
                if mode == "same-id-different-body"
                else "stale_state"
            )
            assert len(successful) == 1
            assert sum(item.get("reason_code") == reason_code for item in results) == 2

        state = snapshot(project_id)
        assert before["receipts"] == []
        assert before["jobs"] == state["jobs"] == []
        assert before["external_calls"] == state["external_calls"] == []
        assert before["artifacts"] == state["artifacts"] == []
        assert len(state["receipts"]) == 1
        receipt = state["receipts"][0]
        winner = successful[0]

        assert state["project"]["id"] == before["project"]["id"]
        assert state["project"]["revision"] == before["project"]["revision"] + 1
        assert state["project"]["status"] == before["project"]["status"]
        assert before["project"]["current_artifact_id"] is None
        assert state["project"]["current_artifact_id"] is None
        expected_settings = dict(before["project"]["settings"])
        expected_settings["subtitle_font_size"] = receipt["resolved_arguments"]["value"]
        assert state["project"]["settings"] == expected_settings

        assert before["settings_history"] == []
        assert [row["revision"] for row in state["settings_history"]] == [1, 2]
        baseline, result = state["settings_history"]
        assert baseline["project_id"] == result["project_id"] == project_id
        assert baseline["revision"] == before["project"]["revision"] == 1
        assert baseline["settings_json"] == before["project"]["settings"]
        assert baseline["changed_fields"] == []
        assert result["revision"] == state["project"]["revision"] == 2
        assert result["settings_json"] == state["project"]["settings"]
        assert result["changed_fields"] == ["subtitle_font_size"]
        assert result["restored_from_revision"] is None

        assert receipt["project_id"] == project_id
        assert receipt["job_id"] is None
        assert receipt["result_json"] == winner
        winning_delta = (
            receipt["resolved_arguments"]["value"]
            - before["project"]["settings"]["subtitle_font_size"]
        )
        assert receipt["canonical_request"] == _canonical_adjustment(
            project_id, winning_delta
        )
        for replay in successful:
            assert replay == receipt["result_json"]

        assert all(row["project_id"] == project_id for row in state["settings_history"])
        assert all(row["project_id"] == project_id for row in state["receipts"])
        assert state["project"]["current_artifact_id"] not in {
            row["id"] for row in state["artifacts"]
        }
