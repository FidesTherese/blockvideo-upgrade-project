"""D32 concurrency snapshots and spawned-process operation races."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from enum import Enum
from threading import Barrier
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
def test_repeated_three_process_matrix(temp_storage, mode: str) -> None:
    for _iteration in range(5):
        project_id = make_project()
        shared_id = f"d32-{mode}-{project_id}"
        barrier = Barrier(3)

        def send(index: int) -> tuple[str, dict[str, Any]]:
            request_id = (
                f"{shared_id}-{index}"
                if mode == "different-id-same-revision"
                else shared_id
            )
            delta = 2 + index if mode == "same-id-different-body" else 2
            request = adjustment(project_id, request_id=request_id, delta=delta)
            barrier.wait(timeout=10)
            process = run_process(request.model_dump(mode="json"))
            assert process.returncode == 0, process.stderr
            return process.stdout, json.loads(process.stdout)

        with ThreadPoolExecutor(max_workers=3) as pool:
            outcomes = list(pool.map(send, range(3)))

        serialized = [item[0] for item in outcomes]
        results = [item[1] for item in outcomes]
        committed = [item for item in results if item.get("revision") == 2]
        if mode == "same-id-same-body":
            assert serialized[0] == serialized[1] == serialized[2]
            assert len(committed) == 3
        else:
            reason_code = (
                "request_id_conflict"
                if mode == "same-id-different-body"
                else "stale_state"
            )
            assert len(committed) == 1
            assert sum(item.get("reason_code") == reason_code for item in results) == 2

        state = snapshot(project_id)
        receipt = state["receipts"][0]
        assert state["project"]["revision"] == 2
        assert state["project"]["settings"]["subtitle_font_size"] == receipt[
            "resolved_arguments"
        ]["value"]
        assert [row["revision"] for row in state["settings_history"]] == [1, 2]
        assert sum(row["revision"] == 2 for row in state["settings_history"]) == 1
        assert len(state["receipts"]) == 1
        assert receipt["job_id"] is None
        assert state["jobs"] == []
        assert state["external_calls"] == []
        assert state["artifacts"] == []
