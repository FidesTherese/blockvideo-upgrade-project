from __future__ import annotations

import asyncio
import hashlib
import importlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evaluation.evidence_json import parse_canonical_model
from evaluation.release_candidate import freeze
from evaluation.release_candidate.fingerprints import fingerprint_files
from evaluation.tool_attestation import aggregate_fingerprints
from tests.test_d36_freeze import _make_candidate

SHA = "a" * 64
COMMIT = "b" * 40
CANDIDATE = "aaaaaaaaaaaaaaaa-bbbbbbbbbbbb"


def _module(name: str) -> Any:
    assert importlib.util.find_spec(name) is not None, f"missing Task 1 behavior: {name}"
    return importlib.import_module(name)


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"


def _fingerprint(path: str = "summary.json") -> dict[str, object]:
    return {"path": path, "size": 3, "sha256": hashlib.sha256(b"{}\n").hexdigest()}


def _binding(role: str = "python") -> dict[str, object]:
    return {"role": role, "version": "3.12.12", "executable": _fingerprint("tools/python_sandbox"), "launcher": None}


def _summary(stage: str) -> dict[str, object]:
    values: dict[str, dict[str, object]] = {
        "legacy_migration": {"from_version": 0, "to_version": 1, "integrity_ok": True, "foreign_keys_enabled": True, "rows_preserved": True, "identities_preserved": True, "backup_size": 3, "backup_sha256": SHA},
        "restore": {"restored_version": 1, "integrity_ok": True, "foreign_keys_enabled": True, "rows_equal": True, "identities_equal": True, "lease_exclusion_passed": True},
        "all_tools_startup": {"mode": "all_tools", "startup_ready": True, "health_ok": True, "request_completed": True, "model_calls": 1, "index_sha256": None},
        "stateful_startup": {"mode": "stateful", "startup_ready": True, "health_ok": True, "request_completed": True, "model_calls": 1, "index_sha256": SHA, "profile_sha256": SHA, "embedding_calls": 1, "retrieval_verified": True},
        "browser": {"narrow_width": 390, "wide_width": 1440, "waiting_ok": True, "safe_retry_ok": True, "unknown_remote_blocked": True, "migration_failed_ok": True, "keyboard_ok": True, "duplicate_post_count": 1, "horizontal_overflow": False, "playback_ok": True, "documentation_checks": True},
        "ffmpeg": {"providers_fake": True, "ffmpeg_exit_code": 0, "ffprobe_exit_code": 0, "video_present": True, "subtitle_present": True, "publication_bound": True, "duration_ms": 500},
    }
    return {"stage": stage, **values[stage]}


def _receipt(stage: str = "restore") -> dict[str, object]:
    return {"schema_version": 1, "stage": stage, "candidate_id": CANDIDATE, "git_commit": COMMIT, "freeze_sha256": SHA, "materialization_sha256": SHA, "runtime_instance_id": SHA, "runtime_source_sha256": SHA, "outcome": "passed", "tools": [_binding()], "artifacts": [_fingerprint()], "summary": _summary(stage)}


def _command() -> dict[str, object]:
    bootstrap = {"role": "python_bootstrap", "version": "3.12.12", "executable": _fingerprint("tools/python_bootstrap"), "launcher": None}
    uv = {"role": "uv", "version": "0.12.15", "executable": _fingerprint("tools/python_bootstrap"), "launcher": _fingerprint("tools/uv_module")}
    return {"name": "backend_uv_sync", "argv": ["python", "-m", "uv", "sync", "--locked", "--extra", "dev", "--extra", "retrieval", "--no-python-downloads", "--no-config"], "resolved_argv": ["tools/python_bootstrap", "-m", "uv", "sync", "--locked", "--extra", "dev", "--extra", "retrieval", "--no-python-downloads", "--no-config"], "tool_bindings": [bootstrap, uv], "cwd": "backend", "deadline_seconds": 600, "outcome": "completed", "exit_code": 0, "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:01Z", "stdout_size": 0, "stderr_size": 0, "stdout_sha256": hashlib.sha256(b"").hexdigest(), "stderr_sha256": hashlib.sha256(b"").hexdigest()}


def test_schemas_are_pure_frozen_and_json_tuples() -> None:
    contracts = _module("evaluation.smoke_contracts")
    receipt = parse_canonical_model(_bytes(_receipt()), contracts.SmokeStageReceipt, maximum=65536)
    assert receipt.summary.rows_equal is True
    assert type(receipt.tools) is tuple
    with pytest.raises(ValidationError):
        receipt.outcome = "failed"
    source = Path(contracts.__file__).read_text()
    import ast
    dependencies = {node.module for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)}
    assert not dependencies.intersection({"evaluation.blinded_runtime", "evaluation.runtime_materialization", "evaluation.browser_smoke", "evaluation.release_verification"})


@pytest.mark.parametrize("bad_path", ["C:/outside", "tools/new\nline", "../outside", "/outside"])
def test_tool_and_artifact_aliases_cannot_escape_owned_roots(bad_path: str) -> None:
    contracts = _module("evaluation.smoke_contracts")
    payload = _receipt()
    payload["tools"][0]["executable"]["path"] = bad_path
    with pytest.raises(ValueError):
        parse_canonical_model(_bytes(payload), contracts.SmokeStageReceipt, maximum=65536)


@pytest.mark.parametrize(("field", "value"), [("schema_version", True), ("schema_version", 1.0), ("stage", 1), ("candidate_id", "x" * 513), ("git_commit", "B" * 40), ("unexpected", 0)])
def test_receipt_rejects_raw_primitives_and_extra_fields(field: str, value: object) -> None:
    contracts = _module("evaluation.smoke_contracts")
    payload = _receipt()
    payload[field] = value
    with pytest.raises(ValueError):
        parse_canonical_model(_bytes(payload), contracts.SmokeStageReceipt, maximum=65536)


@pytest.mark.parametrize(("stage", "field", "value"), [("legacy_migration", "from_version", False), ("browser", "narrow_width", True), ("browser", "narrow_width", 391), ("restore", "integrity_ok", 1), ("stateful_startup", "embedding_calls", 0), ("stateful_startup", "profile_sha256", None), ("ffmpeg", "ffmpeg_exit_code", None), ("ffmpeg", "duration_ms", 60001), ("browser", "duplicate_post_count", 2)])
def test_passed_summary_requires_actual_bounded_observations(stage: str, field: str, value: object) -> None:
    contracts = _module("evaluation.smoke_contracts")
    payload = _receipt(stage)
    payload["summary"][field] = value
    with pytest.raises(ValueError):
        parse_canonical_model(_bytes(payload), contracts.SmokeStageReceipt, maximum=65536)


def test_failed_receipt_keeps_nullable_observation_but_no_complete_smoke() -> None:
    contracts = _module("evaluation.smoke_contracts")
    payload = _receipt("ffmpeg")
    payload["outcome"] = "failed"
    payload["summary"]["ffmpeg_exit_code"] = None
    assert parse_canonical_model(_bytes(payload), contracts.SmokeStageReceipt, maximum=65536).summary.ffmpeg_exit_code is None
    stages = ("legacy_migration", "restore", "all_tools_startup", "stateful_startup", "browser", "ffmpeg")
    receipts = [_receipt(stage) for stage in stages]
    manifest = {"schema_version": 1, "candidate_id": CANDIDATE, "git_commit": COMMIT, "freeze_sha256": SHA, "materialization_sha256": SHA, "runtime_instance_id": SHA, "runtime_source_sha256": SHA, "stage_receipts": receipts, **{stage + "_sha256": hashlib.sha256(_bytes(receipt)).hexdigest() for stage, receipt in zip(stages, receipts, strict=True)}}
    parse_canonical_model(_bytes(manifest), contracts.SmokeManifest, maximum=1024 * 1024)
    manifest["stage_receipts"][-1] = payload
    with pytest.raises(ValueError):
        parse_canonical_model(_bytes(manifest), contracts.SmokeManifest, maximum=1024 * 1024)


@pytest.mark.parametrize(("field", "value"), [("exit_code", None), ("deadline_seconds", 601), ("deadline_seconds", True), ("stdout_size", 2097153), ("finished_at", "2026-02-30T00:00:00Z"), ("outcome", "success")])
def test_command_evidence_is_exact_and_bounded(field: str, value: object) -> None:
    contracts = _module("evaluation.smoke_contracts")
    payload = _command()
    payload[field] = value
    with pytest.raises(ValueError):
        parse_canonical_model(_bytes(payload), contracts.CommandEvidence, maximum=65536)


@pytest.mark.parametrize("kind", ["resolved_argv", "version", "role", "executable", "launcher"])
def test_completed_command_requires_exact_native_role_aliases(kind: str) -> None:
    contracts = _module("evaluation.smoke_contracts")
    payload = _command()
    parse_canonical_model(_bytes(payload), contracts.CommandEvidence, maximum=65536)
    if kind == "resolved_argv":
        payload["resolved_argv"][0] = "tools/unbound"
    elif kind == "version":
        payload["tool_bindings"][0]["version"] = "3.13.0"
    elif kind == "role":
        payload["tool_bindings"][0]["role"] = "python"
    elif kind == "executable":
        payload["tool_bindings"][0]["executable"]["path"] = "tools/other"
    else:
        payload["tool_bindings"][1]["launcher"] = None
    with pytest.raises(ValueError):
        parse_canonical_model(_bytes(payload), contracts.CommandEvidence, maximum=65536)


def test_failed_verification_accepts_only_attempted_prefix_and_truthful_nulls() -> None:
    release = _module("evaluation.release_verification")
    payload = {"schema_version": 1, "candidate_id": CANDIDATE, "git_commit": COMMIT, "freeze_sha256": SHA, "verifier_tool_sha256": SHA, "status": "failed", "commands": [], "smoke_manifest_sha256": None, "smoke_manifest": None, "secret_scan_passed": False, "candidate_clean_before": True, "candidate_clean_after": False, "candidate_snapshot_before_sha256": SHA, "candidate_snapshot_after_sha256": None, "materialization_sha256": SHA, "runtime_instance_id": SHA, "runtime_source_sha256": SHA, "runtime_snapshot_after_sha256": None, "cleanup_status": "failed"}
    manifest = parse_canonical_model(_bytes(payload), release.VerificationManifest, maximum=16 * 1024 * 1024)
    assert manifest.commands == ()
    payload["status"] = "passed"
    with pytest.raises(ValueError):
        parse_canonical_model(_bytes(payload), release.VerificationManifest, maximum=16 * 1024 * 1024)
    payload["status"] = "failed"
    bad = _command()
    bad["name"] = "backend_import"
    payload["commands"] = [bad]
    with pytest.raises(ValueError):
        parse_canonical_model(_bytes(payload), release.VerificationManifest, maximum=16 * 1024 * 1024)


@pytest.fixture
def publication(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    candidate, commit = _make_candidate(tmp_path, extras={".gitignore": b"ignored/\n"})
    (candidate / "ignored").mkdir()
    (candidate / "ignored" / "public-fixture.txt").write_bytes(b"ignored fixture\n")
    files = fingerprint_files(candidate)
    aggregate = aggregate_fingerprints(files)
    manifest = {"schema_version": 1, "candidate_id": f"{aggregate[:16]}-{commit[:12]}", "git_commit": commit, "git_tree_clean": True, "candidate_control_sha256": SHA, "created_at": "2026-01-01T00:00:00Z", "runtime": {"python": "3.12.12"}, "schema_version_number": 1, "mode_configuration": {}, "files": [item.model_dump(mode="json") for item in files], "aggregate_sha256": aggregate}
    directory = tmp_path / "publication" / manifest["candidate_id"]
    directory.mkdir(parents=True)
    raw = _bytes(manifest)
    tool = {"schema_version": 1, "tool_name": "d36_candidate_freezer_and_trial_host", "git_commit": commit, "files": [files[0].model_dump(mode="json")], "aggregate_sha256": aggregate_fingerprints([files[0]])}
    tool_raw = _bytes(tool)
    (directory / "freeze-manifest.json").write_bytes(raw)
    (directory / "d36-tool-attestation.json").write_bytes(tool_raw)
    marker = {"schema_version": 1, "files": [{"path": name, "size": len(blob), "sha256": hashlib.sha256(blob).hexdigest()} for name, blob in [("d36-tool-attestation.json", tool_raw), ("freeze-manifest.json", raw)]]}
    (directory / ".d36-publication-state").write_bytes(_bytes(marker))
    freeze.read_frozen_candidate(directory)
    work = tmp_path / "work"
    evidence = tmp_path / "evidence"
    work.mkdir()
    evidence.mkdir()
    return candidate, directory / "freeze-manifest.json", work, evidence / "runtime-materialization.json"


def _materialize(paths: tuple[Path, Path, Path, Path]) -> tuple[Any, Path, str]:
    module = _module("evaluation.runtime_materialization")
    candidate, frozen, work, output = paths
    result = module.materialize_candidate_runtime(candidate_root=candidate, freeze_manifest_path=frozen, work_root=work, output_path=output)
    return result, work / ("runtime-" + result.runtime_instance_id), hashlib.sha256(output.read_bytes()).hexdigest()


def _cleanup(paths: tuple[Path, Path, Path, Path], runtime: Path, digest: str) -> None:
    _module("evaluation.runtime_materialization").cleanup_candidate_runtime(runtime_root=runtime, work_root=paths[2], materialization_path=paths[3], expected_materialization_sha256=digest)


def test_materializes_only_exact_tracked_bytes_and_cleans_marker_bound_idempotently(publication: tuple[Path, Path, Path, Path]) -> None:
    candidate, frozen, work, output = publication
    before = freeze._snapshot_tree(candidate)
    result, runtime, digest = _materialize(publication)
    expected = json.loads(frozen.read_bytes())["files"]
    assert [item.model_dump(mode="json") for item in result.files] == expected
    assert result.runtime_source_sha256 == json.loads(frozen.read_bytes())["aggregate_sha256"]
    actual_files = sorted(path.relative_to(runtime).as_posix() for path in runtime.rglob("*") if path.is_file())
    assert actual_files == [item["path"] for item in expected]
    assert not (runtime / "ignored").exists()
    for item in expected:
        path = runtime / item["path"]
        assert path.read_bytes() == (candidate / item["path"]).read_bytes()
        assert not path.stat().st_mode & stat.S_IWRITE
    marker_path = output.with_name(output.name + ".ownership.json")
    marker_inode = marker_path.stat().st_ino
    assert marker_inode == result.marker_inode
    assert marker_path.stat().st_size <= 4096
    assert json.loads(marker_path.read_bytes())["state"] == "active"
    _cleanup(publication, runtime, digest)
    _cleanup(publication, runtime, digest)
    assert not runtime.exists()
    assert marker_path.stat().st_ino == marker_inode
    assert json.loads(marker_path.read_bytes())["state"] == "cleaned"
    assert json.loads(output.with_name(output.name + ".cleanup.json").read_bytes())["status"] == "completed"
    assert freeze._snapshot_tree(candidate) == before
    assert work.exists()


@pytest.mark.parametrize("kind", ["source_change", "output_candidate", "output_work", "incomplete_publication"])
def test_materialization_rejects_unsafe_inputs_without_creating_runtime(publication: tuple[Path, Path, Path, Path], kind: str) -> None:
    module = _module("evaluation.runtime_materialization")
    candidate, frozen, work, output = publication
    if kind == "source_change":
        (candidate / "backend/pyproject.toml").write_bytes(b"changed committed source\n")
    elif kind == "output_candidate":
        output = candidate / "materialization.json"
    elif kind == "output_work":
        output = work / "runtime-predicted" / "materialization.json"
        output.parent.mkdir()
    else:
        (frozen.parent / ".d36-publication-state").unlink()
    with pytest.raises((ValueError, OSError)):
        module.materialize_candidate_runtime(candidate_root=candidate, freeze_manifest_path=frozen, work_root=work, output_path=output)
    assert not list(work.glob("runtime-*")) if kind != "output_work" else not list(work.glob("runtime-" + "[0-9a-f]" * 64))
    assert not output.exists()


@pytest.mark.parametrize("kind", ["extra", "writable", "replaced_file", "replaced_directory", "replaced_root", "replaced_marker", "missing_root", "missing_marker"])
def test_cleanup_refuses_drift_and_replacements_without_deleting_them(publication: tuple[Path, Path, Path, Path], kind: str) -> None:
    result, runtime, digest = _materialize(publication)
    output = publication[3]
    target = runtime / result.files[0].path
    marker = output.with_name(output.name + ".ownership.json")
    if kind == "extra":
        os.chmod(runtime, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        target = runtime / "extra"
        target.write_bytes(b"do not delete\n")
    elif kind == "writable":
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
    elif kind == "replaced_file":
        data = target.read_bytes()
        os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
        target.rename(target.with_name(target.name + ".old"))
        target.write_bytes(data)
    elif kind == "replaced_directory":
        target = runtime / "backend"
        target.rename(runtime / "backend.old")
        target.mkdir()
    elif kind == "replaced_root":
        runtime.rename(runtime.with_name(runtime.name + ".old"))
        runtime.mkdir()
        target = runtime / "unrelated"
        target.write_bytes(b"replacement\n")
    elif kind == "replaced_marker":
        raw = marker.read_bytes()
        marker.rename(marker.with_name(marker.name + ".old"))
        marker.write_bytes(raw)
        target = marker
    elif kind == "missing_root":
        runtime.rename(runtime.with_name(runtime.name + ".old"))
        target = runtime.with_name(runtime.name + ".old")
    else:
        marker.unlink()
    identity = target.stat().st_ino
    mode = target.stat().st_mode
    with pytest.raises((ValueError, OSError)):
        _cleanup(publication, runtime, digest)
    assert target.stat().st_ino == identity
    assert target.stat().st_mode == mode


def test_cleanup_refuses_hardlink_alias_without_chmod_or_unlink(publication: tuple[Path, Path, Path, Path]) -> None:
    result, runtime, digest = _materialize(publication)
    path = runtime / result.files[0].path
    alias = publication[3].parent / "external-alias"
    os.link(path, alias)
    before = alias.stat()
    with pytest.raises(ValueError):
        _cleanup(publication, runtime, digest)
    assert path.exists() and alias.exists()
    assert alias.stat().st_mode == before.st_mode
    assert alias.stat().st_ino == before.st_ino


def test_wrong_detached_hash_precedes_parsing(publication: tuple[Path, Path, Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    _, runtime, digest = _materialize(publication)
    module = _module("evaluation.runtime_materialization")
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("untrusted model parsed before detached hash")
    monkeypatch.setattr(module, "parse_canonical_model", forbidden)
    with pytest.raises(ValueError, match="digest"):
        _cleanup(publication, runtime, "0" * 64)
    assert runtime.exists() and digest != "0" * 64


@pytest.mark.parametrize("marker", [False, True])
def test_metadata_cap_plus_one_fails_closed(publication: tuple[Path, Path, Path, Path], marker: bool) -> None:
    _, runtime, digest = _materialize(publication)
    path = publication[3]
    if marker:
        path = path.with_name(path.name + ".ownership.json")
    with path.open("r+b") as stream:
        stream.truncate((4096 if marker else 16 * 1024 * 1024) + 1)
    with pytest.raises((ValueError, OSError)):
        _cleanup(publication, runtime, digest)
    assert runtime.exists()


def test_cleanup_interruption_resumes_only_recorded_remaining_subset(publication: tuple[Path, Path, Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    _, runtime, digest = _materialize(publication)
    output = publication[3]
    original = os.unlink
    count = 0
    def interrupted(path: Any, *args: Any, **kwargs: Any) -> None:
        nonlocal count
        if str(path).endswith(".json") and ".cleanup." in str(path):
            return original(path, *args, **kwargs)
        count += 1
        if count == 2:
            raise OSError("synthetic cleanup interruption")
        original(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(os, "unlink", interrupted)
        with pytest.raises((ValueError, OSError)):
            _cleanup(publication, runtime, digest)
    assert json.loads(output.with_name(output.name + ".ownership.json").read_bytes())["state"] == "cleaning"
    assert json.loads(output.with_name(output.name + ".cleanup.json").read_bytes())["status"] == "failed"
    _cleanup(publication, runtime, digest)
    assert not runtime.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX special-file/symlink behavior; Windows reparse test separate")
@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_materializer_rejects_special_ignored_files(publication: tuple[Path, Path, Path, Path], kind: str) -> None:
    module = _module("evaluation.runtime_materialization")
    candidate, frozen, work, output = publication
    path = candidate / "ignored" / "unsafe"
    if kind == "symlink":
        path.symlink_to(candidate / "backend")
    else:
        os.mkfifo(path)
    with pytest.raises(ValueError):
        module.materialize_candidate_runtime(candidate_root=candidate, freeze_manifest_path=frozen, work_root=work, output_path=output)
    assert not list(work.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="native Windows junction")
def test_materializer_rejects_junction(publication: tuple[Path, Path, Path, Path]) -> None:
    module = _module("evaluation.runtime_materialization")
    candidate, frozen, work, output = publication
    junction = candidate / "ignored" / "junction"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(candidate / "backend")], check=True, stdout=subprocess.DEVNULL)
    try:
        with pytest.raises(ValueError):
            module.materialize_candidate_runtime(candidate_root=candidate, freeze_manifest_path=frozen, work_root=work, output_path=output)
        assert not list(work.iterdir())
    finally:
        junction.rmdir()


def test_materialization_cli_redacts_argument_errors(capsys: pytest.CaptureFixture[str]) -> None:
    cli = _module("evaluation.scripts.materialize_candidate_runtime")
    assert cli.main(["cleanup", "--unexpected", "private-synthetic-path"]) == 2
    captured = capsys.readouterr()
    assert "private-synthetic-path" not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err


def test_materialization_cli_runs_and_cleanup_is_detached_bound(publication: tuple[Path, Path, Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    cli = _module("evaluation.scripts.materialize_candidate_runtime")
    candidate, frozen, work, output = publication
    assert cli.main(["--candidate-root", str(candidate), "--freeze-manifest", str(frozen), "--work-root", str(work), "--output", str(output)]) == 0
    record = json.loads(output.read_bytes())
    runtime = work / ("runtime-" + record["runtime_instance_id"])
    args = ["cleanup", "--runtime-root", str(runtime), "--work-root", str(work), "--materialization", str(output), "--expected-materialization-sha256"]
    assert cli.main([*args, "0" * 64]) == 2
    assert runtime.exists()
    assert cli.main([*args, hashlib.sha256(output.read_bytes()).hexdigest()]) == 0
    assert not runtime.exists()
    text = capsys.readouterr().out
    assert str(candidate) not in text and str(runtime) not in text


def test_interruption_after_root_removal_resumes_cleaning_empty_subset(publication: tuple[Path, Path, Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    _, runtime, digest = _materialize(publication)
    module = _module("evaluation.runtime_materialization")
    original = module._marker_update
    def interrupt(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("state") == "cleaned":
            raise OSError("synthetic publication interruption")
        return original(*args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(module, "_marker_update", interrupt)
        with pytest.raises(OSError):
            _cleanup(publication, runtime, digest)
    assert not runtime.exists()
    _cleanup(publication, runtime, digest)
    assert json.loads(publication[3].with_name(publication[3].name + ".ownership.json").read_bytes())["state"] == "cleaned"


def test_marker_creation_failure_removes_proven_empty_runtime(publication: tuple[Path, Path, Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module("evaluation.runtime_materialization")
    original = module._file_descriptor
    def fail(path: Path, **kwargs: Any) -> int:
        if kwargs.get("create") and path.name.endswith(".ownership.json"):
            raise OSError("synthetic marker creation refusal")
        return original(path, **kwargs)
    monkeypatch.setattr(module, "_file_descriptor", fail)
    with pytest.raises(OSError):
        module.materialize_candidate_runtime(candidate_root=publication[0], freeze_manifest_path=publication[1], work_root=publication[2], output_path=publication[3])
    assert not list(publication[2].iterdir())
    assert json.loads(publication[3].with_name(publication[3].name + ".cleanup.json").read_bytes())["status"] == "completed"


def test_build_interruption_removes_only_retained_partial_tree(publication: tuple[Path, Path, Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module("evaluation.runtime_materialization")
    original = module._OwnedTree.copy
    roots: list[Path] = []
    def change(tree: Any, candidate: Path, expected: Any) -> None:
        original(tree, candidate, expected)
        roots.append(tree.root)
        raise ValueError("synthetic build interruption")
    with monkeypatch.context() as patch:
        patch.setattr(module._OwnedTree, "copy", change)
        with pytest.raises(ValueError, match="interruption"):
            module.materialize_candidate_runtime(candidate_root=publication[0], freeze_manifest_path=publication[1], work_root=publication[2], output_path=publication[3])
    assert roots and not roots[0].exists()
    assert json.loads(publication[3].with_name(publication[3].name + ".cleanup.json").read_bytes())["status"] == "completed"


@pytest.mark.parametrize("kind", ["extra", "write", "content"])
def test_active_runtime_reverification_rejects_source_or_permission_drift(publication: tuple[Path, Path, Path, Path], kind: str) -> None:
    module = _module("evaluation.runtime_materialization")
    result, runtime, digest = _materialize(publication)
    arguments = {"runtime_root": runtime, "work_root": publication[2], "materialization_path": publication[3], "expected_materialization_sha256": digest}
    assert module.read_materialized_runtime(**arguments) == result
    if kind == "extra":
        os.chmod(runtime, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        (runtime / "extra").write_bytes(b"extra\n")
    else:
        path = runtime / result.files[0].path
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        if kind == "content":
            path.write_bytes(b"content drift\n")
            os.chmod(path, stat.S_IREAD)
    with pytest.raises(ValueError):
        module.read_materialized_runtime(**arguments)


def _run_owned(tmp_path: Path, code: str, *, deadline: int = 5) -> Any:
    runtime = _module("evaluation.blinded_runtime")
    assert hasattr(runtime, "run_owned_command"), "missing gated owned-command API"
    return asyncio.run(runtime.run_owned_command(argv=(sys.executable, "-B", "-c", code), cwd=tmp_path, env=runtime.clean_subprocess_environment(Path(__file__).parents[2]), stdout_path=tmp_path / "stdout", stderr_path=tmp_path / "stderr", deadline_seconds=deadline))


def test_scope_reuses_group_for_commands_without_stopping_server(tmp_path: Path) -> None:
    runtime = _module("evaluation.blinded_runtime")
    async def exercise() -> None:
        async with runtime.OwnedProcessScope() as scope:
            server = await runtime.start_owned_process(scope=scope, argv=(sys.executable, "-c", "import time; time.sleep(60)"), cwd=tmp_path, env=runtime.clean_subprocess_environment(Path(__file__).parents[2]), stdout_path=tmp_path / "server.out", stderr_path=tmp_path / "server.err", deadline_seconds=60)
            for index in range(2):
                result = await runtime.run_owned_command(scope=scope, argv=(sys.executable, "-c", "print('command')"), cwd=tmp_path, env=runtime.clean_subprocess_environment(Path(__file__).parents[2]), stdout_path=tmp_path / f"out{index}", stderr_path=tmp_path / f"err{index}", deadline_seconds=5)
                assert result.outcome == "completed" and result.exit_code == 0
                assert server.outcome is None
        assert scope.teardown_confirmed
    asyncio.run(exercise())


def test_failed_command_prevents_further_group_execution(tmp_path: Path) -> None:
    runtime = _module("evaluation.blinded_runtime")
    async def exercise() -> None:
        async with runtime.OwnedProcessScope() as scope:
            result = await runtime.run_owned_command(scope=scope, argv=(sys.executable, "-c", "raise SystemExit(7)"), cwd=tmp_path, env=runtime.clean_subprocess_environment(Path(__file__).parents[2]), stdout_path=tmp_path / "out", stderr_path=tmp_path / "err", deadline_seconds=5)
            assert result.exit_code == 7
            with pytest.raises(ValueError, match="failed"):
                await runtime.run_owned_command(scope=scope, argv=(sys.executable, "-c", "open('payload-ran','w').write('unsafe')"), cwd=tmp_path, env=runtime.clean_subprocess_environment(Path(__file__).parents[2]), stdout_path=tmp_path / "out2", stderr_path=tmp_path / "err2", deadline_seconds=5)
        assert not (tmp_path / "payload-ran").exists()
    asyncio.run(exercise())


def test_owned_command_records_real_bounded_outputs_and_nonzero_exit(tmp_path: Path) -> None:
    result = _run_owned(tmp_path, "import sys; print('ok'); sys.stderr.write('err'); sys.exit(7)")
    assert result.outcome == "completed" and result.exit_code == 7
    stdout = (tmp_path / "stdout").read_bytes()
    assert result.stdout_size == len(stdout)
    assert result.stdout_sha256 == hashlib.sha256(stdout).hexdigest()
    assert result.stderr_size == 3 and result.stderr_sha256 == hashlib.sha256(b"err").hexdigest()
    assert result.started_at.endswith("Z") and result.finished_at.endswith("Z")


@pytest.mark.skipif(os.name != "nt", reason="native Windows Job accounting loss")
def test_unconfirmed_teardown_returns_failed_actual_observations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _module("evaluation.blinded_runtime")
    original = runtime._terminate_job_confirmed
    async def lost(handle: int, *, deadline: float | None = None) -> None:
        await original(handle, deadline=deadline)
        raise ValueError("synthetic terminal accounting loss")
    monkeypatch.setattr(runtime, "_terminate_job_confirmed", lost)
    result = _run_owned(tmp_path, "print('actual')")
    assert result.outcome == "teardown_failed"
    assert result.stdout_size == len((tmp_path / "stdout").read_bytes())
    assert result.stdout_sha256 == hashlib.sha256((tmp_path / "stdout").read_bytes()).hexdigest()


@pytest.mark.parametrize("kind", ["timeout", "output_limit", "parent_exit"])
def test_native_owned_command_confirms_descendants_and_readers(tmp_path: Path, kind: str) -> None:
    child = "import time; time.sleep(60)"
    spawn = f"import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c',{child!r}]); open('child.pid','w').write(str(p.pid)); "
    code = spawn + ("time.sleep(60)" if kind == "timeout" else "sys.stdout.buffer.write(b'x'*2200000); sys.stdout.flush(); time.sleep(60)" if kind == "output_limit" else "sys.exit(0)")
    started = time.monotonic()
    result = _run_owned(tmp_path, code, deadline=1 if kind == "timeout" else 5)
    assert result.outcome == ("completed" if kind == "parent_exit" else kind)
    assert time.monotonic() - started < 12.5
    assert result.stdout_size + result.stderr_size <= 2 * 1024 * 1024
    pid = int((tmp_path / "child.pid").read_text())
    if os.name == "nt":
        import ctypes
        handle = ctypes.WinDLL("kernel32", use_last_error=True).OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.WinDLL("kernel32").CloseHandle(handle)
        assert not handle
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_scope_shares_ownership_with_long_lived_children_and_cancellation(tmp_path: Path) -> None:
    runtime = _module("evaluation.blinded_runtime")
    assert hasattr(runtime, "OwnedProcessScope"), "missing reusable owned scope"
    async def exercise() -> None:
        async with runtime.OwnedProcessScope() as scope:
            server = await runtime.start_owned_process(scope=scope, argv=(sys.executable, "-c", "import time; print('server',flush=True); time.sleep(60)"), cwd=tmp_path, env=runtime.clean_subprocess_environment(Path(__file__).parents[2]), stdout_path=tmp_path / "server.out", stderr_path=tmp_path / "server.err", deadline_seconds=60)
            command = asyncio.create_task(runtime.run_owned_command(scope=scope, argv=(sys.executable, "-c", "import time; time.sleep(60)"), cwd=tmp_path, env=runtime.clean_subprocess_environment(Path(__file__).parents[2]), stdout_path=tmp_path / "cmd.out", stderr_path=tmp_path / "cmd.err", deadline_seconds=60))
            await asyncio.sleep(0.3)
            assert server.pid > 0
            command.cancel()
            with pytest.raises(asyncio.CancelledError):
                await command
        assert scope.teardown_confirmed is True
        assert server.outcome is not None
    asyncio.run(exercise())


@pytest.mark.skipif(os.name != "nt", reason="Windows Job assignment failure")
def test_job_assignment_failure_never_releases_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _module("evaluation.blinded_runtime")
    assert hasattr(runtime, "OwnedProcessScope"), "missing reusable owned scope"
    def fail(*args: object) -> None:
        raise OSError("synthetic assignment failure")
    monkeypatch.setattr(runtime.OwnedProcessScope, "_assign_job", fail)
    result = _run_owned(tmp_path, "open('payload-ran','w').write('unsafe')")
    assert result.outcome == "launch_failed"
    assert not (tmp_path / "payload-ran").exists()


@pytest.mark.parametrize("reason", ["pressure", "accounting"])
def test_scope_stops_owned_work_on_memory_or_accounting_loss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    runtime = _module("evaluation.blinded_runtime")
    original = runtime._owned_memory_sample
    armed = False
    def sample(scope: Any = None) -> tuple[int, int]:
        if armed:
            if reason == "accounting":
                raise ValueError("synthetic accounting loss")
            return 0, 3 * 1024**3
        return original(scope)
    monkeypatch.setattr(runtime, "_owned_memory_sample", sample)
    async def exercise() -> None:
        nonlocal armed
        async with runtime.OwnedProcessScope() as scope:
            child = await runtime.start_owned_process(scope=scope, argv=(sys.executable, "-c", "import time; time.sleep(60)"), cwd=tmp_path, env=runtime.clean_subprocess_environment(Path(__file__).parents[2]), stdout_path=tmp_path / "out", stderr_path=tmp_path / "err", deadline_seconds=60)
            armed = True
            result = await child.wait()
            assert result.outcome == "memory_limit"
        assert scope.teardown_confirmed
    asyncio.run(exercise())


def test_scope_refuses_unsafe_memory_headroom_before_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _module("evaluation.blinded_runtime")
    assert hasattr(runtime, "OwnedProcessScope"), "missing memory-gated scope"
    monkeypatch.setattr(runtime, "_owned_memory_sample", lambda *args: (0, 3 * 1024**3))
    with pytest.raises(ValueError, match="memory"):
        _run_owned(tmp_path, "open('payload-ran','w').write('unsafe')")
    assert not (tmp_path / "payload-ran").exists()
