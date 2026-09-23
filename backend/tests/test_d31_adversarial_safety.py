from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.language_operations.contracts import LanguageInput, LanguageResponse
from app.language_operations.intent_guard import negative_control_reason, normalized_intent
from app.language_operations.service import LanguageOperationService
from app.main import create_app
from app.models.job import GenerationJob, JobStatus
from app.operations.bootstrap import operation_service
from evaluation.comparison_fixture import observe as observe_state
from tests.test_language_operations import ReplyAdapter, create
from tests.test_semantic_interpretation import Replies, build_setup

_RETRY_PROPOSAL = {
    "kind": "operation",
    "operation_id": "project.generation.retry",
    "operation_version": 1,
    "arguments": {"job_id": 7},
}


def seed_failed_job(project_id: int) -> None:
    with get_session_factory()() as db:
        db.add(GenerationJob(
            id=7,
            project_id=project_id,
            status=JobStatus.failed,
            input_revision=1,
        ))
        db.commit()


async def submit_negative_retry(
    service: LanguageOperationService, project_id: int,
) -> tuple[LanguageResponse, dict[str, Any], dict[str, Any]]:
    with get_session_factory()() as db:
        before = observe_state(db, project_id)
        response = await service.submit(db, LanguageInput(
            request_id="d31-negative-retry",
            text="ジョブ7は再試行しないで",
            target={"project_id": project_id},
            base_revision=1,
        ))
        after = observe_state(db, project_id)
    return response, before, after


def assert_negative_retry_veto(response: Any, before: dict[str, Any], after: dict[str, Any]) -> None:
    assert response.status == "dismissed"
    assert response.prepared_request is None
    assert response.confirmation_token is None
    assert response.diagnostics.guard_code == "negative_intent"
    assert response.interpretation.status == "proposed"
    assert response.interpretation.proposal.model_dump(mode="json", exclude_defaults=True) == _RETRY_PROPOSAL
    assert after == before


@pytest.mark.parametrize(("raw", "expected"), [
    ("  ジョブ７を\u3000再試行しないで  ", "ジョブ7を 再試行しないで"),
    ("DON’T   RETRY job 7", "don't retry job 7"),
])
def test_normalized_intent(raw: str, expected: str) -> None:
    assert normalized_intent(raw) == expected


@pytest.mark.parametrize(("text", "operation_id", "expected"), [
    ("ジョブ7は再試行しないで", "project.generation.retry", "explicit_negative_intent"),
    ("ジョブ7は再試行しないで", "project.generation.cancel", None),
    ("キャンセルしないで", "project.generation.cancel", "explicit_negative_intent"),
    ("動画を生成しないで", "project.generation.start", "explicit_negative_intent"),
    ("何もしないで", "project.settings.update", "explicit_negative_intent"),
    ("字幕を56pxにして", "project.settings.update", None),
    ("Do not retry job 7", "project.generation.retry", "explicit_negative_intent"),
    ("DON’T RETRY job 7", "project.generation.retry", "explicit_negative_intent"),
    ("Do not cancel job 7", "project.generation.cancel", "explicit_negative_intent"),
    ("Don't cancel job 7", "project.generation.cancel", "explicit_negative_intent"),
    ("Do not generate a video", "project.generation.start", "explicit_negative_intent"),
    ("Don't generate a video", "project.generation.start", "explicit_negative_intent"),
    ("Do nothing", "project.settings.update", "explicit_negative_intent"),
    ("Do not execute", "project.settings.restore", "explicit_negative_intent"),
    ("Don't execute", "project.subtitle-font-size.set", "explicit_negative_intent"),
    ("ジョブ7を再試行して", "project.generation.retry", None),
    ("Retry job 7", "project.generation.retry", None),
    ("何もしないで", "project.status.get", None),
])
def test_negative_control_reason(text: str, operation_id: str, expected: str | None) -> None:
    assert negative_control_reason(text, operation_id) == expected


async def test_all_tools_vetoes_negative_retry_proposal_without_state_change(temp_storage: Path) -> None:
    client = TestClient(create_app())
    try:
        project_id = create(client)
    finally:
        client.close()
    seed_failed_job(project_id)
    adapter = ReplyAdapter()
    adapter.operation("project.generation.retry", {"job_id": 7})

    response, before, after = await submit_negative_retry(
        LanguageOperationService(operation_service, adapter), project_id,
    )

    assert_negative_retry_veto(response, before, after)


async def test_stateful_semantic_candidate_cannot_bypass_negative_retry_veto(
    temp_storage: Path, tmp_path: Path,
) -> None:
    runner, *_ = build_setup(tmp_path)
    client = TestClient(create_app())
    try:
        project_id = create(client)
    finally:
        client.close()
    seed_failed_job(project_id)

    adapter = Replies([_RETRY_PROPOSAL])
    response, before, after = await submit_negative_retry(
        LanguageOperationService(
            operation_service,
            adapter,
            semantic=runner,
            readiness_annotations=True,
        ),
        project_id,
    )

    assert response.mode == "semantic"
    assert response.diagnostics.retrieval is not None
    assert all(stage.candidate_state is not None for stage in response.diagnostics.retrieval.stages)
    retry_candidate = next(
        candidate
        for candidate in adapter.calls[0]["candidates"]
        if candidate["operation_id"] == "project.generation.retry"
    )
    assert retry_candidate["readiness_hint"]["project_id"] == project_id
    assert_negative_retry_veto(response, before, after)
