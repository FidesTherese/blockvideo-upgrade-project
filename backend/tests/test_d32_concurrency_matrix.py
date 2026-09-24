"""D32 concurrency snapshots and spawned-process operation races."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier, Event, Lock
import time
from typing import Any

import pytest

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session_factory
from app.interpretation.transport import ModelMessage
from app.language_operations import repository as language_repository
from app.language_operations.contracts import (
    LanguageError,
    LanguageExecution,
    LanguageInput,
    LanguageResponse,
)
from app.language_operations.service import LanguageOperationService
from app.models.artifact import GenerationArtifact
from app.models.external_call import ExternalCall
from app.models.job import GenerationJob
from app.models.language_request import LanguageRequestRecord
from app.models.language_turn import LanguageTurn
from app.models.operation_request import OperationReceipt
from app.models.project import Project
from app.models.settings_revision import SettingsRevision
from app.operations.bootstrap import operation_service
from app.operations.contracts import OperationRequest, OperationResult
from app.operations.errors import OperationError
from app.services import artifact_store
from app.services.generation_snapshots import GenerationCancelled, capture_inputs
from app.services.paths import project_dir
from app.services.settings_history import configuration
from app.workers.job_runner import JobRegistry
from tests.test_language_dialogue import ask, reply
from tests.test_language_operations import create
from tests.test_language_operations import harness as harness  # noqa: F401
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


class _DialogueRaceAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._lock = Lock()

    async def complete(
        self, messages: tuple[ModelMessage, ...], schema: dict[str, Any]
    ) -> str:
        del schema
        text = json.loads(messages[1].content)["request"]
        with self._lock:
            self.calls.append(text)
        value = {"56px": 56, "58px": 58}[text]
        return json.dumps(
            {
                "result": {
                    "kind": "operation",
                    "operation_id": "project.subtitle-font-size.set",
                    "operation_version": 1,
                    "arguments": {"value": value},
                }
            }
        )


def _run_dialogue_race(
    service: LanguageOperationService,
    requests: list[LanguageInput],
) -> list[LanguageResponse | LanguageError]:
    def send(request: LanguageInput) -> LanguageResponse | LanguageError:
        with get_session_factory()() as db:
            try:
                return asyncio.run(service.submit(db, request))
            except LanguageError as error:
                return error

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        futures = [pool.submit(send, request) for request in requests]
        return [future.result(timeout=30) for future in futures]


def _synchronized_claim(
    barrier: Barrier,
) -> tuple[
    Callable[[Session, LanguageInput], tuple[LanguageResponse, str | None, Any]],
    Callable[[Session, LanguageInput], tuple[LanguageResponse, str | None, Any]],
]:
    original = language_repository.claim

    def claim(
        db: Session, request: LanguageInput
    ) -> tuple[LanguageResponse, str | None, Any]:
        barrier.wait(timeout=20)
        return original(db, request)

    return original, claim


def _successor(parent_request_id: str) -> tuple[str, LanguageTurn]:
    with get_session_factory()() as db:
        parent = db.get(LanguageTurn, parent_request_id)
        assert parent is not None
        children = db.scalars(
            select(LanguageTurn).where(
                LanguageTurn.parent_request_id == parent_request_id
            )
        ).all()
        assert len(children) == 1
        assert parent.successor_request_id == children[0].request_id
        return parent.successor_request_id, children[0]


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


def test_dialogue_three_way_race_has_one_durable_successor(
    harness, monkeypatch
) -> None:
    client, parent_adapter, service = harness
    for iteration in range(5):
        project_id = create(client)
        parent = ask(
            client,
            parent_adapter,
            project_id,
            request_id=f"d32-dialogue-parent-{iteration}",
        )
        race_adapter = _DialogueRaceAdapter()
        service.adapter = race_adapter
        payloads = [
            reply(
                parent,
                text,
                request_id=f"d32-dialogue-{relation}-{iteration}",
                relation=relation,
            )
            for relation, text in (
                ("answer", "56px"),
                ("correction", "58px"),
                ("dismiss", "取り下げる"),
            )
        ]
        requests = [LanguageInput.model_validate(payload) for payload in payloads]
        barrier = Barrier(len(requests))
        original_claim, synchronized_claim = _synchronized_claim(barrier)
        monkeypatch.setattr(language_repository, "claim", synchronized_claim)

        results = _run_dialogue_race(service, requests)
        monkeypatch.setattr(language_repository, "claim", original_claim)

        assert all(isinstance(result, LanguageResponse) for result in results)
        responses = [result for result in results if isinstance(result, LanguageResponse)]
        winners = [
            response
            for response in responses
            if response.status in {"completed", "dismissed"}
        ]
        blocked = [response for response in responses if response.status == "blocked"]
        assert len(winners) == 1
        assert len(blocked) == 2
        assert all(
            response.failure is not None
            and response.failure.reason_code == "dialogue_superseded"
            for response in blocked
        )

        winner = winners[0]
        winner_index = responses.index(winner)
        winner_payload = payloads[winner_index]
        response_by_id = {response.request_id: response for response in responses}
        losing_payloads = [
            payload for payload in payloads if payload["request_id"] != winner.request_id
        ]
        successor_request_id, successor = _successor(parent["request_id"])
        assert successor_request_id == winner.request_id
        assert successor.relation == winner.relation
        with get_session_factory()() as parent_db:
            assert (
                service.get(parent_db, parent["request_id"]).superseded_by
                == winner.request_id
            )

        state = snapshot(project_id)
        request_rows = {
            row["request_id"]: row for row in state["language_requests"]
        }
        assert set(request_rows) == {
            parent["request_id"],
            *(payload["request_id"] for payload in payloads),
        }
        assert request_rows[parent["request_id"]]["status"] == parent["status"]
        assert request_rows[parent["request_id"]]["response_json"] == parent
        for response in responses:
            record = request_rows[response.request_id]
            assert record["project_id"] == project_id
            assert record["status"] == response.status
            assert record["response_json"] == response.model_dump(mode="json")

        turn_rows = {row["request_id"]: row for row in state["language_turns"]}
        assert set(turn_rows) == {parent["request_id"], winner.request_id}
        assert turn_rows[parent["request_id"]] == {
            "request_id": parent["request_id"],
            "parent_request_id": None,
            "relation": None,
            "text": "字幕を大きくして",
            "successor_request_id": winner.request_id,
        }
        assert turn_rows[winner.request_id] == {
            "request_id": winner.request_id,
            "parent_request_id": parent["request_id"],
            "relation": winner_payload["continuation"]["relation"],
            "text": winner_payload["text"],
            "successor_request_id": None,
        }
        assert state["jobs"] == []
        assert state["external_calls"] == []
        assert state["artifacts"] == []
        if winner.status == "dismissed":
            assert winner.relation == "dismiss"
            assert state["project"]["revision"] == 1
            assert state["project"]["settings"]["subtitle_font_size"] == 48
            assert [row["revision"] for row in state["settings_history"]] == [1]
            assert state["receipts"] == []
            assert race_adapter.calls == []
        else:
            assert winner.relation in {"answer", "correction"}
            assert winner.result is not None
            committed_value = winner.result.resolved_arguments["value"]
            assert committed_value in {56, 58}
            assert state["project"]["revision"] == 2
            assert state["project"]["settings"]["subtitle_font_size"] == committed_value
            assert [row["revision"] for row in state["settings_history"]] == [1, 2]
            assert len(state["receipts"]) == 1
            assert state["receipts"][0]["result_json"] == winner.result.model_dump(
                mode="json"
            )
            assert race_adapter.calls == [winner_payload["text"]]

        calls_before_replay = list(race_adapter.calls)
        with get_session_factory()() as replay_db:
            replay = asyncio.run(
                service.submit(replay_db, LanguageInput.model_validate(winner_payload))
            )
        assert replay.model_dump(mode="json") == winner.model_dump(mode="json")
        for losing_payload in losing_payloads:
            expected = response_by_id[losing_payload["request_id"]]
            assert expected.status == "blocked"
            assert expected.failure is not None
            assert expected.failure.reason_code == "dialogue_superseded"
            with get_session_factory()() as replay_db:
                replay = asyncio.run(
                    service.submit(
                        replay_db, LanguageInput.model_validate(losing_payload)
                    )
                )
            assert replay.model_dump(mode="json") == request_rows[
                losing_payload["request_id"]
            ]["response_json"]
            assert replay.model_dump(mode="json") == expected.model_dump(mode="json")
        assert race_adapter.calls == calls_before_replay
        assert snapshot(project_id) == state
        assert _successor(parent["request_id"])[0] == winner.request_id
        with get_session_factory()() as parent_db:
            assert service.get(parent_db, parent["request_id"]).superseded_by == winner.request_id

        service.adapter = parent_adapter


def test_dialogue_same_successor_id_changed_body_race_replays_only_winner(
    harness, monkeypatch
) -> None:
    client, parent_adapter, service = harness
    for iteration in range(5):
        project_id = create(client)
        parent = ask(
            client,
            parent_adapter,
            project_id,
            request_id=f"d32-dialogue-conflict-parent-{iteration}",
        )
        race_adapter = _DialogueRaceAdapter()
        service.adapter = race_adapter
        request_id = f"d32-dialogue-shared-{iteration}"
        payloads = [
            reply(parent, text, request_id=request_id)
            for text in ("56px", "58px")
        ]
        requests = [LanguageInput.model_validate(payload) for payload in payloads]
        barrier = Barrier(len(requests))
        original_claim, synchronized_claim = _synchronized_claim(barrier)
        monkeypatch.setattr(language_repository, "claim", synchronized_claim)

        results = _run_dialogue_race(service, requests)
        monkeypatch.setattr(language_repository, "claim", original_claim)

        winners = [result for result in results if isinstance(result, LanguageResponse)]
        conflicts = [result for result in results if isinstance(result, LanguageError)]
        assert len(winners) == 1
        assert len(conflicts) == 1
        assert conflicts[0].code == "request_id_conflict"
        winner = winners[0]
        assert winner.status == "completed"
        assert winner.result is not None
        committed_value = winner.result.resolved_arguments["value"]
        winner_payload = next(
            payload for payload in payloads if payload["text"] == f"{committed_value}px"
        )
        losing_payload = next(payload for payload in payloads if payload is not winner_payload)

        successor_request_id, successor = _successor(parent["request_id"])
        assert successor_request_id == request_id
        assert successor.text == winner_payload["text"]
        state = snapshot(project_id)
        request_rows = {
            row["request_id"]: row for row in state["language_requests"]
        }
        assert set(request_rows) == {parent["request_id"], request_id}
        assert request_rows[parent["request_id"]]["status"] == parent["status"]
        assert request_rows[parent["request_id"]]["response_json"] == parent
        assert request_rows[request_id]["project_id"] == project_id
        assert request_rows[request_id]["status"] == winner.status
        assert request_rows[request_id]["response_json"] == winner.model_dump(
            mode="json"
        )
        turn_rows = {row["request_id"]: row for row in state["language_turns"]}
        assert turn_rows == {
            parent["request_id"]: {
                "request_id": parent["request_id"],
                "parent_request_id": None,
                "relation": None,
                "text": "字幕を大きくして",
                "successor_request_id": request_id,
            },
            request_id: {
                "request_id": request_id,
                "parent_request_id": parent["request_id"],
                "relation": "answer",
                "text": winner_payload["text"],
                "successor_request_id": None,
            },
        }
        assert state["project"]["revision"] == 2
        assert state["project"]["settings"]["subtitle_font_size"] == committed_value
        assert [row["revision"] for row in state["settings_history"]] == [1, 2]
        assert len(state["receipts"]) == 1
        assert state["receipts"][0]["result_json"] == winner.result.model_dump(
            mode="json"
        )
        assert state["jobs"] == []
        assert state["external_calls"] == []
        assert state["artifacts"] == []
        assert race_adapter.calls == [winner_payload["text"]]

        with get_session_factory()() as replay_db:
            replay = asyncio.run(
                service.submit(replay_db, LanguageInput.model_validate(winner_payload))
            )
        assert replay.model_dump(mode="json") == winner.model_dump(mode="json")
        assert race_adapter.calls == [winner_payload["text"]]
        with get_session_factory()() as conflict_db:
            with pytest.raises(LanguageError, match="別の内容") as conflict:
                asyncio.run(
                    service.submit(
                        conflict_db, LanguageInput.model_validate(losing_payload)
                    )
                )
        assert conflict.value.code == "request_id_conflict"
        assert snapshot(project_id) == state
        assert _successor(parent["request_id"])[0] == request_id

        service.adapter = parent_adapter


def test_confirmation_vs_setting_has_one_revision_bound_winner(
    harness, monkeypatch
) -> None:
    client, adapter, service = harness
    from app.operations import service as operation_service_module

    original_atomic_write = operation_service_module.atomic_write
    for iteration in range(5):
        project_id = create(client)
        adapter.operation("project.generation.start", {"kind": "full"})
        language_request = LanguageInput(
            request_id=f"d32-confirmation-{iteration}",
            text="動画を作り直して",
            target={"project_id": project_id},
        )
        with get_session_factory()() as prepare_db:
            prepared = asyncio.run(service.prepare(prepare_db, language_request))
        assert prepared.status == "ready"
        assert prepared.requires_confirmation
        assert prepared.confirmation_token is not None
        confirmation = LanguageExecution(
            confirmation_token=prepared.confirmation_token,
            confirm_generation=True,
        )
        setting_request = adjustment(
            project_id,
            request_id=f"d32-setting-{iteration}",
            delta=2,
        )
        barrier = Barrier(2)

        @contextmanager
        def synchronized_atomic_write(db: Session) -> Iterator[None]:
            barrier.wait(timeout=20)
            with original_atomic_write(db):
                yield

        monkeypatch.setattr(
            operation_service_module, "atomic_write", synchronized_atomic_write
        )

        def confirm_generation() -> LanguageResponse:
            with get_session_factory()() as db:
                return service.execute(db, language_request.request_id, confirmation)

        def update_setting() -> OperationResult | OperationError:
            with get_session_factory()() as db:
                try:
                    return service.core.execute(db, setting_request)
                except OperationError as error:
                    return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            confirmation_future = pool.submit(confirm_generation)
            setting_future = pool.submit(update_setting)
            confirmation_result = confirmation_future.result(timeout=30)
            setting_result = setting_future.result(timeout=30)
        monkeypatch.setattr(
            operation_service_module, "atomic_write", original_atomic_write
        )

        state = snapshot(project_id)
        assert state["external_calls"] == []
        assert state["artifacts"] == []
        assert len(state["receipts"]) == 1
        if confirmation_result.status == "completed":
            assert confirmation_result.result is not None
            assert confirmation_result.result.job_id is not None
            assert isinstance(setting_result, OperationError)
            assert setting_result.reason_code in {"project_busy", "stale_state"}
            assert state["project"]["revision"] == 1
            assert state["project"]["settings"]["subtitle_font_size"] == 48
            assert [row["revision"] for row in state["settings_history"]] == [1]
            assert len(state["jobs"]) == 1
            assert state["jobs"][0]["id"] == confirmation_result.result.job_id
            assert state["jobs"][0]["status"] == "pending"
            assert state["receipts"][0]["request_id"] == prepared.core_request_id
            assert state["receipts"][0]["result_json"] == (
                confirmation_result.result.model_dump(mode="json")
            )
            with get_session_factory()() as replay_db:
                replay = service.execute(
                    replay_db, language_request.request_id, confirmation
                )
            assert replay.model_dump(mode="json") == confirmation_result.model_dump(
                mode="json"
            )
            with get_session_factory()() as losing_db:
                with pytest.raises(OperationError) as repeated_loser:
                    service.core.execute(losing_db, setting_request)
            assert repeated_loser.value.reason_code in {"project_busy", "stale_state"}
        else:
            assert confirmation_result.status == "blocked"
            assert confirmation_result.failure is not None
            assert confirmation_result.failure.reason_code in {
                "stale_state",
                "dialogue_stale",
            }
            assert isinstance(setting_result, OperationResult)
            assert setting_result.revision == 2
            assert state["project"]["revision"] == 2
            assert state["project"]["settings"]["subtitle_font_size"] == 50
            assert [row["revision"] for row in state["settings_history"]] == [1, 2]
            assert state["jobs"] == []
            assert state["receipts"][0]["request_id"] == setting_request.request_id
            assert state["receipts"][0]["result_json"] == setting_result.model_dump(
                mode="json"
            )
            with get_session_factory()() as replay_db:
                replay = service.core.execute(replay_db, setting_request)
            assert replay == setting_result
            with get_session_factory()() as losing_db:
                with pytest.raises(LanguageError) as repeated_loser:
                    service.execute(
                        losing_db, language_request.request_id, confirmation
                    )
            assert repeated_loser.value.code == "request_not_ready"
        assert snapshot(project_id) == state


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_first", (True, False))
async def test_cancel_vs_publication_preserves_prior_artifact_and_terminalizes_once(
    temp_storage: Path, monkeypatch, cancel_first: bool
) -> None:
    async def accept_synthetic_probe(path: Path) -> dict[str, Any]:
        return {
            **artifact_store.file_identity(path),
            "duration_ms": 1000,
            "width": 320,
            "height": 180,
        }

    monkeypatch.setattr(artifact_store, "validate_video", accept_synthetic_probe)
    project_id = make_project()
    prior_request = OperationRequest(
        operation_id="project.generation.start",
        target={"project_id": project_id},
        arguments={"kind": "full"},
        request_id="d32-prior-publication",
        base_revision=1,
    )
    with get_session_factory()() as db:
        prior_result = operation_service.execute(db, prior_request)
        prior_job = db.get(GenerationJob, prior_result.job_id)
        assert prior_job is not None
        prior_job.status = "running"
        db.commit()
        settled_inputs = capture_inputs(db.get(Project, project_id))
    prior_candidate = (
        project_dir(project_id)
        / "history"
        / f"job-{prior_result.job_id:08d}"
        / "video.pending.mp4"
    )
    prior_candidate.parent.mkdir(parents=True, exist_ok=True)
    prior_candidate.write_bytes(b"d32-prior-video")
    prior_artifact = await artifact_store.publish_artifact(
        prior_result.job_id,
        prior_candidate,
        None,
        settled_inputs=settled_inputs,
        materials=[],
        cancel_check=lambda: False,
    )

    next_request = OperationRequest(
        operation_id="project.generation.start",
        target={"project_id": project_id},
        arguments={"kind": "full"},
        request_id="d32-racing-publication",
        base_revision=1,
    )
    with get_session_factory()() as db:
        next_result = operation_service.execute(db, next_request)
        next_job_id = next_result.job_id
        assert next_job_id is not None
        next_job = db.get(GenerationJob, next_job_id)
        assert next_job is not None
        next_inputs = dict(next_job.input_snapshot)
    candidate = (
        project_dir(project_id)
        / "history"
        / f"job-{next_job_id:08d}"
        / "video.pending.mp4"
    )
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b"d32-racing-video")

    publication_barrier = Barrier(2)
    cancellation_committed = Event()
    publication_committed = Event()
    original_publication_write = artifact_store.atomic_write

    @contextmanager
    def synchronized_publication_write(db: Session) -> Iterator[None]:
        publication_barrier.wait(timeout=20)
        if cancel_first:
            assert cancellation_committed.wait(timeout=20)
        with original_publication_write(db):
            yield
        publication_committed.set()

    monkeypatch.setattr(
        artifact_store, "atomic_write", synchronized_publication_write
    )
    registry = JobRegistry()
    cancellation_observation: list[tuple[str, bool]] = []

    async def publish(cancel_check: Callable[[], bool]) -> GenerationArtifact:
        return await artifact_store.publish_artifact(
            next_job_id,
            candidate,
            None,
            settled_inputs=next_inputs,
            materials=[],
            cancel_check=cancel_check,
        )

    def cancel_at_boundary() -> bool:
        publication_barrier.wait(timeout=20)
        if not cancel_first:
            assert publication_committed.wait(timeout=20)
        result = registry.request_cancel(next_job_id)
        with get_session_factory()() as db:
            observed = db.get(GenerationJob, next_job_id)
            assert observed is not None
            cancellation_observation.append(
                (observed.status.value, observed.cancel_requested)
            )
        cancellation_committed.set()
        return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        cancel_future = pool.submit(cancel_at_boundary)
        task = registry.submit(next_job_id, publish)
        await asyncio.wait_for(task, timeout=30)
        cancel_result = cancel_future.result(timeout=30)

    assert cancel_result is cancel_first
    assert cancellation_observation == [
        ("running", True) if cancel_first else ("completed", False)
    ]

    monkeypatch.setattr(
        artifact_store, "atomic_write", original_publication_write
    )
    state = snapshot(project_id)
    jobs = {row["id"]: row for row in state["jobs"]}
    artifacts = {row["id"]: row for row in state["artifacts"]}
    receipts = {row["request_id"]: row for row in state["receipts"]}
    assert state["external_calls"] == []
    assert set(receipts) == {prior_request.request_id, next_request.request_id}
    assert receipts[prior_request.request_id]["job_id"] == prior_result.job_id
    assert receipts[next_request.request_id]["job_id"] == next_job_id
    assert all(row["project_id"] == project_id for row in receipts.values())
    assert all(
        row["job_id"] is None or row["job_id"] in jobs for row in receipts.values()
    )
    assert prior_artifact.id in artifacts
    assert artifacts[prior_artifact.id]["job_id"] == prior_result.job_id
    assert all(row["project_id"] == project_id for row in artifacts.values())
    assert all(
        row["job_id"] is None or row["job_id"] in jobs
        for row in artifacts.values()
    )
    if cancel_result:
        assert jobs[next_job_id]["status"] == "cancelled"
        assert jobs[next_job_id]["cancel_requested"] is True
        assert state["project"]["status"] == "cancelled"
        assert set(artifacts) == {prior_artifact.id}
        assert state["project"]["current_artifact_id"] == prior_artifact.id
    else:
        assert jobs[next_job_id]["status"] == "completed"
        assert jobs[next_job_id]["cancel_requested"] is False
        assert state["project"]["status"] == "completed"
        assert len(artifacts) == 2
        new_artifact = next(
            row for row in artifacts.values() if row["job_id"] == next_job_id
        )
        assert state["project"]["current_artifact_id"] == new_artifact["id"]
    assert artifact_store.artifact_file_path(prior_artifact).read_bytes() == (
        b"d32-prior-video"
    )
    assert registry.request_cancel(next_job_id) is False
    final_candidate = candidate.with_name("video.mp4")
    if cancel_result:
        with pytest.raises(GenerationCancelled):
            await artifact_store.publish_artifact(
                next_job_id,
                final_candidate,
                None,
                settled_inputs=next_inputs,
                materials=[],
                cancel_check=lambda: False,
            )
    else:
        await artifact_store.publish_artifact(
            next_job_id,
            final_candidate,
            None,
            settled_inputs=next_inputs,
            materials=[],
            cancel_check=lambda: False,
        )
    assert snapshot(project_id) == state
