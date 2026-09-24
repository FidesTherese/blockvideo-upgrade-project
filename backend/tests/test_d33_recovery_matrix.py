"""D33 canonical durable-state snapshots and request/core crash boundaries."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

import pytest
from sqlalchemy import select

from app.db import get_session_factory
from app.language_operations import repository
from app.interpretation.transport import ModelMessage
from app.language_operations.contracts import LanguageExecution, LanguageInput
from app.language_operations.service import LanguageOperationService
from app.models.artifact import GenerationArtifact
from app.models.external_call import ExternalCall
from app.models.job import GenerationJob, JobStatus
from app.models.language_request import LanguageRequestRecord
from app.models.operation_request import OperationReceipt
from app.models.project import Project, ProjectStatus
from app.models.settings_revision import SettingsRevision
from app.operations.bootstrap import operation_service
from app.operations.contracts import OperationRequest
from app.services.settings_history import record_settings
from app.workers.operation_dispatcher import mark_interrupted_operation_jobs


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


def recovery_snapshot(project_id: int) -> dict[str, object]:
    """Reopen SQLite and return the canonical D33 durable-state view."""
    with get_session_factory()() as db:
        project = db.get(Project, project_id)
        assert project is not None
        job_ids = select(GenerationJob.id).where(
            GenerationJob.project_id == project_id
        )
        return {
            "project": {
                "id": project.id,
                "revision": project.revision,
                "status": project.status.value,
                "current_artifact_id": project.current_artifact_id,
            },
            "settings_revisions": [
                _record(row)
                for row in db.scalars(
                    select(SettingsRevision)
                    .where(SettingsRevision.project_id == project_id)
                    .order_by(SettingsRevision.revision, SettingsRevision.id)
                )
            ],
            "language_requests": [
                _record(row)
                for row in db.scalars(
                    select(LanguageRequestRecord)
                    .where(LanguageRequestRecord.project_id == project_id)
                    .order_by(LanguageRequestRecord.request_id)
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
                    .where(ExternalCall.job_id.in_(job_ids))
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


def restart_twice() -> tuple[int, int]:
    """Run startup reconciliation twice and expose both transition counts."""
    return mark_interrupted_operation_jobs(), mark_interrupted_operation_jobs()


class _ReplyAdapter:
    def __init__(self, operation_id: str, arguments: dict[str, Any]) -> None:
        self.operation_id = operation_id
        self.arguments = arguments

    async def complete(
        self, messages: tuple[ModelMessage, ...], schema: dict[str, Any]
    ) -> str:
        del messages, schema
        return json.dumps(
            {
                "result": {
                    "kind": "operation",
                    "operation_id": self.operation_id,
                    "operation_version": 1,
                    "arguments": self.arguments,
                }
            }
        )


def _seed_canonical_state() -> tuple[int, int]:
    with get_session_factory()() as db:
        project = Project(
            title="D33 synthetic",
            source_script="合成された回復テストです。",
            subtitle_font_size=48,
            use_fake_providers=True,
        )
        db.add(project)
        db.flush()
        record_settings(db, project)
        job = GenerationJob(
            project_id=project.id,
            status=JobStatus.completed,
            current_stage="completed",
            progress=1.0,
            stage_progress=1.0,
            input_revision=project.revision,
            input_snapshot={"project": {"id": project.id, "revision": project.revision}},
            input_fingerprint="a" * 64,
        )
        db.add(job)
        db.flush()
        db.add(
            ExternalCall(
                job_id=job.id,
                fingerprint="c" * 64,
                provider="synthetic",
                endpoint="https://synthetic.invalid/d33",
                remote_side_effect=True,
                status="succeeded",
                response_status=200,
                response_body=b'{"ok":true}',
                response_content_type="application/json",
            )
        )
        artifact = GenerationArtifact(
            project_id=project.id,
            job_id=job.id,
            revision=project.revision,
            input_fingerprint=job.input_fingerprint,
            video_path=f"projects/{project.id}/history/prior.mp4",
            manifest_json={"video": {"sha256": "b" * 64}},
        )
        db.add(artifact)
        db.flush()
        project.current_artifact_id = artifact.id
        project.status = ProjectStatus.completed
        project.output_video_path = artifact.video_path
        db.commit()
        project_id = project.id
        artifact_id = artifact.id

    request = OperationRequest(
        request_id="d33-prior-receipt",
        operation_id="project.status.get",
        target={"project_id": project_id},
        arguments={},
    )
    with get_session_factory()() as db:
        operation_service.execute(db, request)

    with get_session_factory()() as db:
        response, owner, state = repository.claim(
            db,
            LanguageInput(
                request_id="d33-prior-language",
                text="状態を確認して",
                target={"project_id": project_id},
            ),
        )
        assert response.status == "interpreting"
        assert owner is not None
        assert state is not None

    return project_id, artifact_id


def _contains_type(value: Any, expected_type: type) -> bool:
    if isinstance(value, expected_type):
        return True
    if isinstance(value, dict):
        return any(_contains_type(item, expected_type) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_type(item, expected_type) for item in value)
    return False


def _language_request(project_id: int, request_id: str, text: str) -> LanguageInput:
    return LanguageInput(
        request_id=request_id,
        text=text,
        target={"project_id": project_id},
    )


def _prepare_generation(
    project_id: int, request_id: str
) -> tuple[LanguageOperationService, LanguageInput, Any]:
    request = _language_request(project_id, request_id, "動画を生成して")
    service = LanguageOperationService(
        operation_service,
        _ReplyAdapter("project.generation.start", {"kind": "full"}),
    )
    with get_session_factory()() as db:
        response = asyncio.run(service.prepare(db, request))
    assert response.status == "ready"
    assert response.requires_confirmation
    assert response.confirmation_token is not None
    return service, request, response


def _assert_request_effect_is_complete(
    snapshot: dict[str, object], request_id: str
) -> None:
    receipts = [
        row for row in snapshot["receipts"] if row["request_id"] == request_id
    ]
    if not receipts:
        return
    assert len(receipts) == 1
    receipt = receipts[0]
    if receipt["job_id"] is not None:
        assert any(row["id"] == receipt["job_id"] for row in snapshot["jobs"])
    if receipt["result_revision"] > receipt["base_revision"]:
        assert any(
            row["revision"] == receipt["result_revision"]
            for row in snapshot["settings_revisions"]
        )


def test_canonical_snapshot_reopens_complete_stable_state(temp_storage) -> None:
    project_id, artifact_id = _seed_canonical_state()

    first = recovery_snapshot(project_id)
    second = recovery_snapshot(project_id)

    assert first == second
    assert first["project"] == {
        "id": project_id,
        "revision": 1,
        "status": "completed",
        "current_artifact_id": artifact_id,
    }
    assert [row["revision"] for row in first["settings_revisions"]] == [1]
    assert [row["request_id"] for row in first["language_requests"]] == [
        "d33-prior-language"
    ]
    assert [row["request_id"] for row in first["receipts"]] == [
        "d33-prior-receipt"
    ]
    assert [row["id"] for row in first["artifacts"]] == [artifact_id]
    assert first["external_calls"][0]["response_body"] == {
        "sha256": "4062edaf750fb8074e7e83e0c9028c94e32468a8b6f1614774328ef045150f93"
    }
    assert not _contains_type(first, bytes)
    assert not _contains_type(first, Project)
    json.dumps(first, sort_keys=True, allow_nan=False)


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_request_claim_crash_replays_saved_claim_or_executes_once(
    temp_storage, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    project_id, artifact_id = _seed_canonical_state()
    service = LanguageOperationService(
        operation_service,
        _ReplyAdapter("project.subtitle-font-size.set", {"value": 56}),
    )
    request = _language_request(project_id, f"d33-claim-{boundary}", "字幕を56pxにして")
    original_claim = repository.claim
    observed: dict[str, Any] = {}

    def crashing_claim(db, incoming):
        if boundary == "before":
            raise OSError("synthetic D33 boundary")
        result = original_claim(db, incoming)
        observed["response"] = result[0]
        raise OSError("synthetic D33 boundary")

    monkeypatch.setattr(repository, "claim", crashing_claim)
    with get_session_factory()() as db, pytest.raises(
        OSError, match="synthetic D33 boundary"
    ):
        asyncio.run(service.submit(db, request))
    monkeypatch.setattr(repository, "claim", original_claim)

    crashed = recovery_snapshot(project_id)
    assert crashed["project"]["revision"] == 1
    assert crashed["project"]["current_artifact_id"] == artifact_id
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == crashed

    with get_session_factory()() as db:
        replay = asyncio.run(service.submit(db, request))
    if boundary == "after":
        assert replay == observed["response"]
        assert replay.status == "interpreting"
    else:
        assert replay.status == "completed"
        assert replay.result is not None
        assert replay.result.resolved_arguments == {"value": 56}

    final = recovery_snapshot(project_id)
    _assert_request_effect_is_complete(final, replay.core_request_id)
    assert final["project"]["current_artifact_id"] == artifact_id
    if replay.status == "completed":
        assert final["project"]["revision"] == 2
        assert [row["revision"] for row in final["settings_revisions"]] == [1, 2]
        assert sum(
            row["request_id"] == replay.core_request_id for row in final["receipts"]
        ) == 1
    else:
        assert final["project"]["revision"] == 1
        assert not any(
            row["request_id"] == replay.core_request_id for row in final["receipts"]
        )


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_core_receipt_crash_rolls_back_then_generation_confirmation_executes_once(
    temp_storage, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    from app.operations import service as core_service_module

    project_id, artifact_id = _seed_canonical_state()
    service, request, prepared = _prepare_generation(
        project_id, f"d33-receipt-{boundary}"
    )
    confirmation = LanguageExecution(
        confirmation_token=prepared.confirmation_token,
        confirm_generation=True,
    )
    original_save_receipt = core_service_module.save_receipt

    def crashing_save_receipt(*args, **kwargs):
        if boundary == "before":
            raise OSError("synthetic D33 boundary")
        original_save_receipt(*args, **kwargs)
        raise OSError("synthetic D33 boundary")

    monkeypatch.setattr(core_service_module, "save_receipt", crashing_save_receipt)
    with get_session_factory()() as db, pytest.raises(
        OSError, match="synthetic D33 boundary"
    ):
        service.execute(db, request.request_id, confirmation)
    monkeypatch.setattr(core_service_module, "save_receipt", original_save_receipt)

    crashed = recovery_snapshot(project_id)
    core_request_id = prepared.core_request_id
    assert not any(
        row["request_id"] == core_request_id for row in crashed["receipts"]
    )
    assert crashed["project"]["current_artifact_id"] == artifact_id
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == crashed

    with get_session_factory()() as db:
        replay = service.execute(db, request.request_id, confirmation)
    assert replay.status == "completed"
    assert replay.result is not None
    assert replay.result.job_id is not None
    final = recovery_snapshot(project_id)
    _assert_request_effect_is_complete(final, core_request_id)
    assert sum(row["request_id"] == core_request_id for row in final["receipts"]) == 1
    assert sum(row["id"] == replay.result.job_id for row in final["jobs"]) == 1
    assert final["project"]["current_artifact_id"] == artifact_id


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_core_commit_crash_has_no_effect_or_complete_generation_receipt(
    temp_storage, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    project_id, artifact_id = _seed_canonical_state()
    service, request, prepared = _prepare_generation(
        project_id, f"d33-core-commit-{boundary}"
    )
    confirmation = LanguageExecution(
        confirmation_token=prepared.confirmation_token,
        confirm_generation=True,
    )

    with get_session_factory()() as db:
        original_commit = db.commit
        commit_count = 0

        def crashing_commit() -> None:
            nonlocal commit_count
            commit_count += 1
            if commit_count != 2:
                original_commit()
                return
            if boundary == "after":
                original_commit()
            raise OSError("synthetic D33 boundary")

        monkeypatch.setattr(db, "commit", crashing_commit)
        with pytest.raises(OSError, match="synthetic D33 boundary"):
            service.execute(db, request.request_id, confirmation)
        assert commit_count == 2

    crashed = recovery_snapshot(project_id)
    core_request_id = prepared.core_request_id
    _assert_request_effect_is_complete(crashed, core_request_id)
    matching_receipts = [
        row for row in crashed["receipts"] if row["request_id"] == core_request_id
    ]
    assert len(matching_receipts) == (1 if boundary == "after" else 0)
    assert crashed["project"]["current_artifact_id"] == artifact_id
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == crashed

    with get_session_factory()() as db:
        replay = service.execute(db, request.request_id, confirmation)
    assert replay.status == "completed"
    assert replay.result is not None
    assert replay.result.job_id is not None
    final = recovery_snapshot(project_id)
    _assert_request_effect_is_complete(final, core_request_id)
    assert sum(row["request_id"] == core_request_id for row in final["receipts"]) == 1
    assert sum(row["id"] == replay.result.job_id for row in final["jobs"]) == 1
    assert final["project"]["current_artifact_id"] == artifact_id
