"""Unattended (YOLO) requests: no confirmation or clarification, guesses reported."""
from __future__ import annotations

import json

from app.interpretation.service import system_prompt
from app.models.job import GenerationJob
from app.operations.bootstrap import operation_service
from tests.test_language_operations import count, create, harness, language_input, submit  # noqa: F401

ALL_OPERATIONS = {item.operation_id for item in operation_service.list_definitions()}


def _reply(adapter, operation_id: str, arguments: dict, *, generate: bool = False, version: int = 1) -> None:
    adapter.response = json.dumps({"result": {"kind": "operation", "operation_id": operation_id,
                                              "operation_version": version, "arguments": arguments,
                                              "generate_after_save": generate}})


def test_yolo_prompt_adds_guessing_rules_without_changing_normal_mode() -> None:
    normal, yolo = system_prompt(ALL_OPERATIONS), system_prompt(ALL_OPERATIONS, "yolo")
    assert "【自動実行モード】" in yolo and "【自動実行モード】" not in normal
    assert yolo.startswith(normal)


def test_yolo_starts_generation_without_confirmation(harness) -> None:  # noqa: F811
    client, adapter, _ = harness
    project_id = create(client)
    _reply(adapter, "project.generation.start", {"kind": "full"})
    before = count(GenerationJob)

    response = submit(client, language_input(project_id, text="動画を作り直して", mode="yolo"))

    assert response["status"] == "completed" and response["executed"] is True
    assert response["execution_mode"] == "yolo"
    assert response["yolo_report"]["auto_confirmed"] == ["project.generation.start"]
    assert count(GenerationJob) == before + 1
    assert adapter.calls and "【自動実行モード】" not in json.dumps(adapter.calls[0]["prompt"], ensure_ascii=False)


def test_yolo_saves_then_generates_in_one_request(harness) -> None:  # noqa: F811
    client, adapter, _ = harness
    project_id = create(client)
    _reply(adapter, "project.subtitle-font-size.set", {"value": 64}, generate=True)
    before = count(GenerationJob)

    response = submit(client, language_input(project_id, text="字幕を64pxにして動画も作り直して", mode="yolo"))

    assert response["status"] == "completed", response
    assert response["result"] is not None and response["generation_result"] is not None
    assert response["yolo_report"]["auto_confirmed"] == ["project.subtitle-font-size.set", "project.generation.start"]
    assert count(GenerationJob) == before + 1
    assert client.get(f"/api/projects/{project_id}").json()["subtitle_font_size"] == 64


def test_yolo_guesses_where_normal_mode_asks(harness) -> None:  # noqa: F811
    client, adapter, _ = harness
    project_id = create(client)
    _reply(adapter, "project.subtitle-font-size.adjust", {"delta": 4})

    normal = submit(client, language_input(project_id, request_id="nl-normal", text="字幕を大きくして"))
    assert normal["status"] == "needs_input" and normal["diagnostics"]["guard_code"] == "subtitle_value"

    response = submit(client, language_input(project_id, request_id="nl-yolo", text="字幕を大きくして", mode="yolo"))
    assert response["status"] == "completed"
    assert response["yolo_report"]["bypassed_guards"] == ["subtitle_value"]
    assert client.get(f"/api/projects/{project_id}").json()["subtitle_font_size"] == 52


def test_yolo_never_overrides_an_explicit_negation(harness) -> None:  # noqa: F811
    client, adapter, _ = harness
    project_id = create(client)
    _reply(adapter, "project.generation.start", {"kind": "full"})
    before = count(GenerationJob)

    response = submit(client, language_input(project_id, text="動画は生成しないで", mode="yolo"))

    assert response["status"] == "dismissed"
    assert count(GenerationJob) == before


def test_normal_mode_still_requires_generation_confirmation(harness) -> None:  # noqa: F811
    client, adapter, _ = harness
    project_id = create(client)
    _reply(adapter, "project.generation.start", {"kind": "full"})
    before = count(GenerationJob)

    response = submit(client, language_input(project_id, text="動画を作り直して"))

    assert response["status"] == "ready" and response["requires_confirmation"] is True
    assert response["execution_mode"] == "normal" and response["yolo_report"] is None
    assert count(GenerationJob) == before


def test_yolo_can_be_disabled_by_the_server(harness) -> None:  # noqa: F811
    client, adapter, service = harness
    service.yolo_enabled = False
    project_id = create(client)
    _reply(adapter, "project.generation.start", {"kind": "full"})

    response = submit(client, language_input(project_id, text="動画を作り直して", mode="yolo"))

    assert response["status"] == "error" and response["failure"]["reason_code"] == "yolo_disabled"
    assert not adapter.calls
