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
from app.models.language_turn import LanguageTurn
from app.models.operation_request import OperationReceipt
from app.models.project import Project, ProjectStatus
from app.models.settings_revision import SettingsRevision
from app.operations.bootstrap import operation_service
from app.operations.contracts import OperationRequest
from app.services.settings_history import configuration, record_settings
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
                "settings": _canonical(configuration(project)),
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
            "language_turns": [
                _record(row)
                for row in db.scalars(
                    select(LanguageTurn)
                    .join(
                        LanguageRequestRecord,
                        LanguageRequestRecord.request_id == LanguageTurn.request_id,
                    )
                    .where(LanguageRequestRecord.project_id == project_id)
                    .order_by(LanguageTurn.request_id)
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
        self.calls = 0

    async def complete(
        self, messages: tuple[ModelMessage, ...], schema: dict[str, Any]
    ) -> str:
        del messages, schema
        self.calls += 1
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


def _effect_state(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        key: snapshot[key]
        for key in (
            "project",
            "settings_revisions",
            "jobs",
            "receipts",
            "external_calls",
            "artifacts",
        )
    }


def _receipt(snapshot: dict[str, object], request_id: str) -> dict[str, Any]:
    matching = [
        row for row in snapshot["receipts"] if row["request_id"] == request_id
    ]
    assert len(matching) == 1
    return matching[0]


def _assert_exact_receipt_result(
    snapshot: dict[str, object], request_id: str, result: Any
) -> dict[str, Any]:
    receipt = _receipt(snapshot, request_id)
    assert receipt["result_json"] == result.model_dump(mode="json")
    return receipt


def _assert_atomic_settings_effect(
    before: dict[str, object],
    after: dict[str, object],
    request_id: str,
    result: Any,
) -> None:
    assert after["project"] == {
        **before["project"],
        "revision": before["project"]["revision"] + 1,
        "settings": {**before["project"]["settings"], "subtitle_font_size": 56},
    }
    assert after["jobs"] == before["jobs"]
    assert after["external_calls"] == before["external_calls"]
    assert after["artifacts"] == before["artifacts"]
    assert after["language_requests"] == before["language_requests"]
    assert after["language_turns"] == before["language_turns"]
    assert len(after["settings_revisions"]) == len(before["settings_revisions"]) + 1
    assert all(row in after["settings_revisions"] for row in before["settings_revisions"])
    new_history = [
        row for row in after["settings_revisions"]
        if row not in before["settings_revisions"]
    ]
    assert len(new_history) == 1
    assert new_history[0]["revision"] == result.revision
    assert new_history[0]["settings_json"] == after["project"]["settings"]
    assert new_history[0]["changed_fields"] == ["subtitle_font_size"]
    assert len(after["receipts"]) == len(before["receipts"]) + 1
    assert all(row in after["receipts"] for row in before["receipts"])
    new_receipts = [
        row for row in after["receipts"] if row not in before["receipts"]
    ]
    assert len(new_receipts) == 1
    receipt = _assert_exact_receipt_result(after, request_id, result)
    assert receipt["result_revision"] == result.revision
    assert receipt["job_id"] is None


def _assert_atomic_generation_effect(
    before: dict[str, object],
    after: dict[str, object],
    request_id: str,
    result: Any,
) -> None:
    assert after["project"]["revision"] == before["project"]["revision"]
    assert after["project"]["settings"] == before["project"]["settings"]
    assert after["project"]["status"] == "generating"
    assert (
        after["project"]["current_artifact_id"]
        == before["project"]["current_artifact_id"]
    )
    assert after["settings_revisions"] == before["settings_revisions"]
    assert [row["request_id"] for row in after["language_requests"]] == [
        row["request_id"] for row in before["language_requests"]
    ]
    assert after["language_turns"] == before["language_turns"]
    assert after["external_calls"] == before["external_calls"]
    assert after["artifacts"] == before["artifacts"]
    assert len(after["receipts"]) == len(before["receipts"]) + 1
    assert len(after["jobs"]) == len(before["jobs"]) + 1
    assert all(row in after["receipts"] for row in before["receipts"])
    assert all(row in after["jobs"] for row in before["jobs"])
    new_receipts = [
        row for row in after["receipts"] if row not in before["receipts"]
    ]
    new_jobs = [row for row in after["jobs"] if row not in before["jobs"]]
    assert len(new_receipts) == len(new_jobs) == 1
    receipt = _assert_exact_receipt_result(after, request_id, result)
    job = new_jobs[0]
    assert receipt["job_id"] == job["id"] == result.job_id
    assert job["project_id"] == receipt["project_id"]
    assert [row["job_id"] for row in new_receipts] == [row["id"] for row in new_jobs]


def test_canonical_snapshot_reopens_complete_stable_state(temp_storage) -> None:
    project_id, artifact_id = _seed_canonical_state()

    first = recovery_snapshot(project_id)
    second = recovery_snapshot(project_id)

    assert first == second
    assert first["project"]["id"] == project_id
    assert first["project"]["revision"] == 1
    assert first["project"]["status"] == "completed"
    assert first["project"]["current_artifact_id"] == artifact_id
    assert first["project"]["settings"] == {
        "visual_focus_enabled": True,
        "subtitle_mode": "sentence",
        "narration_pacing_mode": "adaptive",
        "pronunciation_overrides": [],
        "title": "D33 synthetic",
        "voicevox_url": "http://127.0.0.1:50021",
        "voicevox_speaker_id": 1,
        "voicevox_speed_scale": 1.0,
        "voicevox_pitch_scale": 0.0,
        "voicevox_intonation_scale": 1.0,
        "voicevox_volume_scale": 1.0,
        "subtitle_enabled": True,
        "subtitle_font_size": 48,
        "subtitle_position": "bottom",
        "subtitle_text_color": "#FFFFFF",
        "subtitle_outline_color": "#000000",
        "subtitle_background": True,
        "subtitle_max_chars_per_line": 36,
        "pre_margin_seconds": 0.15,
        "post_margin_seconds": 1.5,
        "min_display_seconds": 2.0,
        "narration_sentence_pause_seconds": 1.5,
        "max_slides_per_block": 1,
    }
    assert [row["revision"] for row in first["settings_revisions"]] == [1]
    assert [row["request_id"] for row in first["language_requests"]] == [
        "d33-prior-language"
    ]
    assert first["language_requests"][0]["status"] == "interpreting"
    assert first["language_turns"] == [
        {
            "request_id": "d33-prior-language",
            "parent_request_id": None,
            "relation": None,
            "text": "状態を確認して",
            "successor_request_id": None,
        }
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
def test_request_claim_crash_expires_owner_or_executes_once(
    temp_storage, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    project_id, artifact_id = _seed_canonical_state()
    adapter = _ReplyAdapter("project.subtitle-font-size.set", {"value": 56})
    service = LanguageOperationService(operation_service, adapter)
    request = _language_request(project_id, f"d33-claim-{boundary}", "字幕を56pxにして")
    original_claim = repository.claim
    before = recovery_snapshot(project_id)

    def crashing_claim(db, incoming):
        if boundary == "before":
            raise OSError("synthetic D33 boundary")
        original_claim(db, incoming)
        raise OSError("synthetic D33 boundary")

    monkeypatch.setattr(repository, "claim", crashing_claim)
    with get_session_factory()() as db, pytest.raises(
        OSError, match="synthetic D33 boundary"
    ):
        asyncio.run(service.submit(db, request))
    monkeypatch.setattr(repository, "claim", original_claim)

    crashed = recovery_snapshot(project_id)
    assert crashed["project"]["current_artifact_id"] == artifact_id
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == crashed

    if boundary == "after":
        assert _effect_state(crashed) == _effect_state(before)
        claimed = next(
            row for row in crashed["language_requests"]
            if row["request_id"] == request.request_id
        )
        assert claimed["status"] == "interpreting"
        with get_session_factory()() as db:
            record = db.get(LanguageRequestRecord, request.request_id)
            assert record is not None
            record.lease_until = 0.0
            db.commit()
        with get_session_factory()() as db:
            reconciled_response = service.get(db, request.request_id)
        assert reconciled_response.status == "error"
        assert reconciled_response.failure is not None
        assert reconciled_response.failure.reason_code == "interpretation_interrupted"
        assert reconciled_response.result is None
        assert not reconciled_response.executed
        reconciled = recovery_snapshot(project_id)
        stored = next(
            row for row in reconciled["language_requests"]
            if row["request_id"] == request.request_id
        )
        assert stored["response_json"] == reconciled_response.model_dump(mode="json")
        assert restart_twice() == (0, 0)
        assert recovery_snapshot(project_id) == reconciled
        with get_session_factory()() as db:
            second = asyncio.run(service.submit(db, request))
        assert second == reconciled_response
        assert recovery_snapshot(project_id) == reconciled
        assert restart_twice() == (0, 0)
        assert recovery_snapshot(project_id) == reconciled
        assert _effect_state(reconciled) == _effect_state(before)
        assert adapter.calls == 0
        return

    assert crashed == before
    with get_session_factory()() as db:
        first = asyncio.run(service.submit(db, request))
    assert first.status == "completed"
    assert first.result is not None
    assert first.result.resolved_arguments == {"value": 56}
    final = recovery_snapshot(project_id)
    _assert_exact_receipt_result(final, first.core_request_id, first.result)
    assert final["project"]["revision"] == 2
    assert [row["revision"] for row in final["settings_revisions"]] == [1, 2]
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == final
    with get_session_factory()() as db:
        replay = asyncio.run(service.submit(db, request))
    assert replay == first
    assert recovery_snapshot(project_id) == final
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == final
    assert adapter.calls == 1


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_settings_core_commit_is_atomic_with_history_and_receipt(
    temp_storage, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    project_id, _ = _seed_canonical_state()
    request = OperationRequest(
        request_id=f"d33-settings-commit-{boundary}",
        operation_id="project.subtitle-font-size.set",
        target={"project_id": project_id},
        arguments={"value": 56},
        base_revision=1,
    )
    before = recovery_snapshot(project_id)

    with get_session_factory()() as db:
        original_commit = db.commit

        def crashing_commit() -> None:
            if boundary == "after":
                original_commit()
            raise OSError("synthetic D33 boundary")

        monkeypatch.setattr(db, "commit", crashing_commit)
        with pytest.raises(OSError, match="synthetic D33 boundary"):
            operation_service.execute(db, request)

    crashed = recovery_snapshot(project_id)
    if boundary == "before":
        assert crashed == before
    else:
        with get_session_factory()() as db:
            persisted = operation_service.get_result(db, request.request_id)
        _assert_atomic_settings_effect(before, crashed, request.request_id, persisted)
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == crashed

    with get_session_factory()() as db:
        replay = operation_service.execute(db, request)
    final = recovery_snapshot(project_id)
    _assert_atomic_settings_effect(before, final, request.request_id, replay)
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == final
    with get_session_factory()() as db:
        assert operation_service.execute(db, request) == replay
    assert recovery_snapshot(project_id) == final
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == final


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
    before = recovery_snapshot(project_id)
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
    assert crashed == before
    assert crashed["project"]["current_artifact_id"] == artifact_id
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == crashed

    with get_session_factory()() as db:
        completed = service.execute(db, request.request_id, confirmation)
    assert completed.status == "completed"
    assert completed.result is not None
    final = recovery_snapshot(project_id)
    _assert_atomic_generation_effect(
        before, final, prepared.core_request_id, completed.result
    )
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == final
    with get_session_factory()() as db:
        replay = service.execute(db, request.request_id, confirmation)
    assert replay == completed
    assert recovery_snapshot(project_id) == final
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == final


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
    before = recovery_snapshot(project_id)

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
    if boundary == "before":
        assert crashed == before
    else:
        with get_session_factory()() as db:
            persisted = operation_service.get_result(db, core_request_id)
        _assert_atomic_generation_effect(
            before, crashed, core_request_id, persisted
        )
    assert crashed["project"]["current_artifact_id"] == artifact_id
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == crashed

    with get_session_factory()() as db:
        completed = service.execute(db, request.request_id, confirmation)
    assert completed.status == "completed"
    assert completed.result is not None
    final = recovery_snapshot(project_id)
    _assert_atomic_generation_effect(
        before, final, core_request_id, completed.result
    )
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == final
    with get_session_factory()() as db:
        replay = service.execute(db, request.request_id, confirmation)
    assert replay == completed
    assert recovery_snapshot(project_id) == final
    assert restart_twice() == (0, 0)
    assert recovery_snapshot(project_id) == final
