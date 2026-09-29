"""D34 startup lifecycle, degraded API, and cross-process lease regressions."""
from __future__ import annotations

import asyncio
import multiprocessing
import os
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.core.startup_status import (
    StartupStatus,
    StartupUnavailableError,
    get_startup_status,
    reset_startup_status_for_tests,
    set_startup_status,
)
from app.db import Base, get_db, get_session_factory, reset_db_for_tests
from app.main import create_app
from app.migrations import MigrationError, MigrationResult
from app.migrations.backup import sha256_file
from app.migrations.runner import restore_database_backup
from app.models.external_call import ExternalCall
from app.models.job import GenerationJob, JobStatus
from app.models.project import Project
from app.services.job_views import job_summary
from tests.fixtures.migrations.build_fixtures import build_fixture


class RecordingLease:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.release_count = 0

    def release(self) -> None:
        self.events.append("release")
        self.release_count += 1


class RecordingRegistry:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.accepting = False

    def start(self) -> None:
        self.events.append("registry_start")
        self.accepting = True

    def close(self) -> None:
        self.events.append("registry_close")
        self.accepting = False

    async def shutdown(self) -> None:
        self.events.append("registry_shutdown")


@pytest.fixture(autouse=True)
def reset_startup_status() -> None:
    reset_startup_status_for_tests()
    yield
    reset_startup_status_for_tests()


def _patch_successful_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], RecordingLease, RecordingRegistry]:
    from app import main as main_module

    events: list[str] = []
    lease = RecordingLease(events)
    registry = RecordingRegistry(events)

    def register_models() -> None:
        events.append("register")

    def acquire(database_url: str) -> RecordingLease:
        assert database_url
        events.append("acquire")
        return lease

    def migrate(database_url: str, metadata: Any, *, lease: RecordingLease) -> MigrationResult:
        assert database_url
        assert lease is not None
        assert {"projects", "generation_jobs", "language_requests"} <= set(metadata.tables)
        events.append("migrate")
        return MigrationResult("current", 1, 1, False, None)

    def init_db() -> None:
        events.append("init")

    def recover() -> int:
        events.append("recover")
        return 0

    async def dispatch() -> None:
        events.append("dispatch")
        await asyncio.Event().wait()

    def shutdown_db() -> None:
        assert get_startup_status() == StartupStatus(
            status="starting",
            reason_code=None,
            message="終了処理中です。",
            schema_version=None,
            backup_available=False,
        )
        events.append("shutdown_db")

    monkeypatch.setattr(main_module, "register_models", register_models)
    monkeypatch.setattr(main_module, "acquire_database_lease", acquire)
    monkeypatch.setattr(main_module, "migrate_database", migrate)
    monkeypatch.setattr(main_module, "init_db", init_db)
    monkeypatch.setattr(main_module, "shutdown_db", shutdown_db)
    monkeypatch.setattr(main_module, "mark_interrupted_operation_jobs", recover)
    monkeypatch.setattr(main_module, "run_operation_dispatcher", dispatch)
    monkeypatch.setattr(main_module.operation_dispatcher, "job_registry", registry)
    return events, lease, registry


def test_job_summary_derives_exact_recovery_codes_from_persisted_state_and_journal(
    temp_storage: Path,
) -> None:
    with get_session_factory()() as db:
        jobs: dict[str, GenerationJob] = {}
        for name, status, cancel_requested in [
            ("pending", JobStatus.pending, False),
            ("running", JobStatus.running, False),
            ("cancel_requested", JobStatus.running, True),
            ("failed_retryable", JobStatus.failed, False),
            ("failed_unknown_call", JobStatus.failed, False),
            ("unknown", JobStatus.unknown, False),
            ("cancelled", JobStatus.cancelled, False),
            ("completed", JobStatus.completed, False),
            ("detached_failed", JobStatus.failed, False),
        ]:
            project = Project(title=f"recovery-{name}", source_script="synthetic")
            db.add(project)
            db.flush()
            job = GenerationJob(
                project_id=project.id,
                current_stage="synthetic",
                status=status,
                cancel_requested=cancel_requested,
            )
            db.add(job)
            jobs[name] = job
        db.flush()
        db.add(
            ExternalCall(
                job_id=jobs["failed_unknown_call"].id,
                fingerprint="f" * 64,
                provider="synthetic",
                endpoint="https://provider.invalid/jobs",
                remote_side_effect=True,
                status="unknown",
            )
        )
        db.commit()

        detached_failed = jobs.pop("detached_failed")
        db.refresh(detached_failed)
        db.expunge(detached_failed)
        summaries = {name: job_summary(job) for name, job in jobs.items()}
        summaries["detached_failed"] = job_summary(detached_failed)

    expected = {
        "pending": ("wait", "wait", False, None),
        "running": ("wait", "wait", False, None),
        "cancel_requested": ("wait", "wait", False, None),
        "failed_retryable": ("safe_retry", "retry_current", True, None),
        "failed_unknown_call": (
            "external_outcome_unknown",
            "check_provider",
            False,
            "以前の外部処理の結果が未確定です。外部サービス側の履歴を確認できるまで再実行できません。",
        ),
        "unknown": (
            "external_outcome_unknown",
            "check_provider",
            False,
            "外部処理の結果が未確定です。このアプリでは結果を照会できないため、外部サービス側の履歴を確認してください。",
        ),
        "cancelled": ("safe_retry", "retry_current", True, None),
        "completed": ("completed", "none", False, None),
        "detached_failed": (
            "refresh_required",
            "refresh",
            False,
            "現在の状態を再取得してから再実行してください。",
        ),
    }
    assert {
        name: (
            summary.recovery_code,
            summary.recommended_action,
            summary.retryable,
            summary.retry_blocked_reason,
        )
        for name, summary in summaries.items()
    } == expected


@pytest.mark.parametrize(
    ("route_name", "enqueue_name"),
    [
        ("regenerate_visual", "enqueue_block_visual_rerun"),
        ("regenerate_audio", "enqueue_block_audio_rerun"),
        ("rerender_block", "enqueue_rerender"),
    ],
)
def test_block_regeneration_responses_include_required_recovery_contract(
    monkeypatch: pytest.MonkeyPatch,
    route_name: str,
    enqueue_name: str,
) -> None:
    from app.api import routes_blocks
    from app.models.block import Block

    block = Block(id=5, project_id=7, index=0, source_text="synthetic")
    project = Project(id=7, title="synthetic", source_script="synthetic")
    job = GenerationJob(
        id=11,
        project_id=7,
        current_stage="queued",
        status=JobStatus.pending,
        progress=0.0,
        stage_progress=0.0,
        cancel_requested=False,
    )

    class FakeDb:
        def get(self, model: type[Any], identifier: int) -> Any:
            return {Block: block, Project: project, GenerationJob: job}[model]

    async def enqueue(*_args: Any) -> GenerationJob:
        return job

    monkeypatch.setattr(routes_blocks, "ensure_project_idle", lambda *_args: None)
    monkeypatch.setattr(routes_blocks, "ensure_render_assets_ready", lambda *_args: None)
    monkeypatch.setattr(routes_blocks, enqueue_name, enqueue)

    response = asyncio.run(getattr(routes_blocks, route_name)(block.id, FakeDb()))

    assert response.job.recovery_code == "wait"
    assert response.job.recommended_action == "wait"
    assert response.job.retryable is False


def test_lifespan_registers_leases_migrates_then_initializes_before_database_users(
    temp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events, lease, _registry = _patch_successful_lifecycle(monkeypatch)
    application = create_app()

    async def exercise() -> None:
        async with application.router.lifespan_context(application):
            await asyncio.sleep(0)
            assert get_startup_status() == StartupStatus(
                status="ready",
                reason_code=None,
                message="起動が完了しました。",
                schema_version=1,
                backup_available=False,
            )
            assert events == [
                "register",
                "acquire",
                "migrate",
                "init",
                "recover",
                "registry_start",
                "dispatch",
            ]
            assert lease.release_count == 0

    asyncio.run(exercise())

    assert events[-4:] == [
        "registry_close",
        "registry_shutdown",
        "shutdown_db",
        "release",
    ]
    assert lease.release_count == 1
    with pytest.raises(StartupUnavailableError):
        next(get_db())


@pytest.mark.parametrize(
    "reason_code",
    [
        "database_lease_unavailable",
        "schema_too_new",
        "unsupported_database",
        "unsupported_legacy_schema",
        "backup_failed",
        "backup_invalid",
        "migration_failed",
        "migration_verification_failed",
    ],
)
def test_migration_failure_keeps_status_routes_readable_and_database_routes_fixed_503(
    temp_storage: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason_code: str,
) -> None:
    from app import main as main_module

    events: list[str] = []
    lease = RecordingLease(events)
    monkeypatch.setattr(main_module, "register_models", lambda: events.append("register"))
    monkeypatch.setattr(
        main_module,
        "acquire_database_lease",
        lambda _database_url: events.append("acquire") or lease,
    )

    def fail_migration(*_args: Any, **_kwargs: Any) -> None:
        events.append("migrate")
        raise MigrationError(reason_code)  # type: ignore[arg-type]

    monkeypatch.setattr(main_module, "migrate_database", fail_migration)
    monkeypatch.setattr(main_module, "init_db", lambda: pytest.fail("init must not run"))
    monkeypatch.setattr(main_module, "shutdown_db", lambda: events.append("shutdown_db"))
    monkeypatch.setattr(
        main_module,
        "mark_interrupted_operation_jobs",
        lambda: pytest.fail("recovery must not run"),
    )
    monkeypatch.setattr(
        main_module,
        "run_operation_dispatcher",
        lambda: pytest.fail("dispatcher must not run"),
    )

    with TestClient(create_app()) as client:
        assert client.get("/api/startup").json() == {
            "status": "migration_failed",
            "reason_code": reason_code,
            "message": "データベースの移行に失敗しました。管理者に確認してください。",
            "schema_version": None,
            "backup_available": False,
        }
        assert client.get("/api/health").json()["status"] == "degraded"
        response = client.get("/api/projects")
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "5"
        assert response.json() == {
            "detail": {
                "reason_code": "startup_unavailable",
                "message": "データベースを利用できません。起動状態を確認してください。",
            }
        }
        assert lease.release_count == 0

    assert events == ["register", "acquire", "migrate", "shutdown_db", "release"]
    assert get_startup_status() == StartupStatus(
        status="starting",
        reason_code=None,
        message="終了処理中です。",
        schema_version=None,
        backup_available=False,
    )
    assert lease.release_count == 1


def test_post_acquisition_startup_error_releases_lease_once(
    temp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main as main_module

    events, lease, _registry = _patch_successful_lifecycle(monkeypatch)

    def fail_init() -> None:
        events.append("init")
        raise RuntimeError("synthetic init failure")

    monkeypatch.setattr(main_module, "init_db", fail_init)

    with pytest.raises(RuntimeError, match="synthetic init failure"):
        with TestClient(create_app()):
            pass

    assert events == [
        "register",
        "acquire",
        "migrate",
        "init",
        "shutdown_db",
        "release",
    ]
    assert lease.release_count == 1


def test_registry_shutdown_error_still_releases_lease_once(
    temp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events, lease, registry = _patch_successful_lifecycle(monkeypatch)

    async def fail_shutdown() -> None:
        events.append("registry_shutdown")
        raise RuntimeError("synthetic shutdown failure")

    registry.shutdown = fail_shutdown  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="synthetic shutdown failure"):
        with TestClient(create_app()):
            pass

    assert events[-4:] == [
        "registry_close",
        "registry_shutdown",
        "shutdown_db",
        "release",
    ]
    assert lease.release_count == 1


def test_lease_acquisition_failure_aborts_without_database_users_or_release(
    temp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main as main_module

    events: list[str] = []
    monkeypatch.setattr(main_module, "register_models", lambda: events.append("register"))

    def fail_acquire(_database_url: str) -> None:
        events.append("acquire")
        raise MigrationError("database_lease_unavailable")

    monkeypatch.setattr(main_module, "acquire_database_lease", fail_acquire)
    monkeypatch.setattr(
        main_module, "migrate_database", lambda *_args, **_kwargs: pytest.fail("no migration")
    )
    monkeypatch.setattr(main_module, "init_db", lambda: pytest.fail("no init"))
    monkeypatch.setattr(
        main_module,
        "mark_interrupted_operation_jobs",
        lambda: pytest.fail("no recovery"),
    )
    monkeypatch.setattr(
        main_module,
        "run_operation_dispatcher",
        lambda: pytest.fail("no dispatcher"),
    )

    with pytest.raises(MigrationError, match="database_lease_unavailable"):
        with TestClient(create_app()):
            pass

    assert events == ["register", "acquire"]


def test_offline_restore_between_lifespans_reopens_restored_database_inode(
    temp_storage: Path,
) -> None:
    database = temp_storage / "blockvideo.db"
    reset_db_for_tests()
    database.unlink(missing_ok=True)
    build_fixture("d30_v0", database, Base.metadata)
    application = create_app()

    with TestClient(application):
        with get_session_factory()() as db:
            project = db.get(Project, 101)
            assert project is not None
            assert project.title == "fixture-project"
            project.title = "state-from-replaced-inode"
            db.commit()

    with pytest.raises(StartupUnavailableError):
        next(get_db())

    backup = next(
        path
        for path in (database.parent / ".backups").iterdir()
        if not path.name.endswith(".metadata.json")
    )
    backup_sha256 = sha256_file(backup)
    restore_database_backup(
        f"sqlite:///{database.as_posix()}",
        backup,
        backup_sha256,
        Base.metadata,
    )
    assert sha256_file(database) == backup_sha256

    with TestClient(application):
        with get_session_factory()() as db:
            project = db.get(Project, 101)
            assert project is not None
            assert project.title == "fixture-project"


def _hold_application_lifespan(
    database_url: str,
    storage_root: str,
    ready: multiprocessing.Queue,
    stop: multiprocessing.synchronize.Event,
) -> None:
    os.environ["DATABASE_URL"] = database_url
    os.environ["STORAGE_ROOT"] = storage_root
    from app.core.config import reset_settings_cache
    from app.db import reset_db_for_tests

    reset_settings_cache()
    reset_db_for_tests()
    try:
        with TestClient(create_app()):
            ready.put(None)
            stop.wait(timeout=30)
    except Exception as exc:
        ready.put((exc.__class__.__name__, str(exc)))
        raise


def test_second_application_process_is_excluded_until_first_shutdown(
    temp_storage: Path,
) -> None:
    database = temp_storage / "process-exclusion.db"
    database_url = f"sqlite:///{database.as_posix()}"
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    stop = context.Event()
    process = context.Process(
        target=_hold_application_lifespan,
        args=(database_url, str(temp_storage), ready, stop),
    )
    process.start()
    try:
        assert ready.get(timeout=30) is None
        os.environ["DATABASE_URL"] = database_url
        from app.core.config import reset_settings_cache
        from app.db import reset_db_for_tests

        reset_settings_cache()
        reset_db_for_tests()
        with pytest.raises(MigrationError, match="database_lease_unavailable"):
            with TestClient(create_app()):
                pass
    finally:
        stop.set()
        process.join(timeout=30)
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)

    assert process.exitcode == 0
    set_startup_status(
        StartupStatus(
            status="starting",
            reason_code=None,
            message="起動処理中です。",
            schema_version=None,
            backup_available=False,
        )
    )
    with TestClient(create_app()) as client:
        assert client.get("/api/startup").json()["status"] == "ready"
