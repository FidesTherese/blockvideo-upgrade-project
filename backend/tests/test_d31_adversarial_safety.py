from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from loguru import logger

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
_UNEXPECTED_ERROR = "SECRET /Users/private/source.txt"
_REQUEST_SECRET = "REQUEST_BODY_SECRET"
_INVALID_REQUEST_DETAIL = {
    "reason_code": "invalid_request",
    "message": "入力の形式・値が正しくありません。要求ID、本文、対象を確認してください。",
}


def unexpected_error_client() -> TestClient:
    app = create_app()

    @app.post("/test/unexpected-error")
    async def unexpected_error() -> None:
        raise RuntimeError(_UNEXPECTED_ERROR)

    return TestClient(app, raise_server_exceptions=False)


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


def test_unexpected_exception_response_is_fixed_and_redacted(temp_storage: Path) -> None:
    with unexpected_error_client() as client:
        response = client.post("/test/unexpected-error", content=_REQUEST_SECRET)

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["reason_code"] == "internal_error"
    assert detail["message"] == "処理に失敗しました。再読み込み後も続く場合は記録番号を確認してください。"
    assert re.fullmatch(r"[0-9a-f]{16}", detail["correlation_id"])
    assert all(value not in response.content for value in (b"SECRET", b"private", _UNEXPECTED_ERROR.encode()))


def test_unexpected_exception_log_contains_only_bounded_metadata(temp_storage: Path) -> None:
    output = StringIO()
    with unexpected_error_client() as client:
        sink_id = logger.add(output, format="{message}")
        try:
            response = client.post("/test/unexpected-error", content=_REQUEST_SECRET)
        finally:
            logger.remove(sink_id)

    correlation_id = response.json()["detail"]["correlation_id"]
    captured = output.getvalue()
    assert "RuntimeError" in captured
    assert correlation_id in captured
    assert "/test/unexpected-error" in captured
    assert all(value not in captured for value in (_UNEXPECTED_ERROR, _REQUEST_SECRET, "/Users/private/source.txt"))


@pytest.mark.parametrize("payload", [
    {"request_id": "d31-invalid-unicode", "text": "bad \ud800", "target": {}},
    {"request_id": "d31-control", "text": "bad\u0000text", "target": {}},
    {"request_id": "d31-unknown", "text": "字幕", "target": {},
     "SECRET_UNKNOWN_FIELD": "/Users/private/source.txt"},
    {"request_id": "d31-oversized", "text": "SECRET /Users/private/" + ("x" * 2001), "target": {}},
    {"request_id": "bad/SECRET/Users/private/source.txt", "text": "字幕", "target": {}},
])
def test_language_validation_returns_only_fixed_non_echo_detail(
    temp_storage: Path, payload: dict[str, Any],
) -> None:
    body = json.dumps(payload)
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/language/requests",
            content=body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": _INVALID_REQUEST_DETAIL}
    assert all(value not in response.text for value in (
        "SECRET", "private", "source.txt", "bad", "UNKNOWN_FIELD",
    ))


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
