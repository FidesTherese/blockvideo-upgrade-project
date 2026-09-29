from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

CANDIDATE_SUBJECT = "[DONE] Mission 35 Add recovery-oriented operational UI"
CONTROL_KEYS = {
    "git_commit",
    "git_commit_subject",
    "git_tree_clean",
    "schema_version",
}
REQUIRED_CANDIDATE_FILES = {
    ".gitignore": b".pytest_cache/\nrelease-evidence/\n",
    "backend/app/core/config.py": b"LANGUAGE_RETRIEVAL_ALL_TOOLS = True\n",
    "backend/app/migrations/schema.py": b"CURRENT_SCHEMA_VERSION = 1\n",
    "backend/app/operations/definitions.json": b"[]\n",
    "backend/app/operations/search_scope.json": b"{}\n",
    "backend/app/retrieval/e5-profile.json": b'{"profile":"e5"}\n',
    "backend/app/retrieval/nomic-profile.json": b'{"profile":"nomic"}\n',
    "backend/pyproject.toml": b'[project]\nrequires-python = ">=3.12"\n',
    "backend/tests/test_candidate.py": b"def test_candidate(): assert True\n",
    "backend/uv.lock": b"version = 1\n",
    "docs/DTD.md": b"candidate design\n",
    "docs/plan-c/work-unit-36.md": b"candidate freeze contract\n",
    "frontend/package.json": b'{"engines":{"node":">=20"}}\n',
    "frontend/pnpm-lock.yaml": b"lockfileVersion: '9.0'\n",
    "frontend/src/main.tsx": b"export {};\n",
    "specification.md": b"candidate specification\n",
}


def _run(*argv: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _make_candidate(
    root: Path,
    *,
    timestamp: int = 1_700_000_000,
    subject: str = CANDIDATE_SUBJECT,
    omit: set[str] | None = None,
    extras: dict[str, bytes] | None = None,
    detach: bool = True,
) -> tuple[Path, str]:
    candidate = root / "candidate"
    candidate.mkdir()
    _run("git", "init", "-q", cwd=candidate)
    _run("git", "config", "user.email", "d36@example.invalid", cwd=candidate)
    _run("git", "config", "user.name", "D36 Test", cwd=candidate)
    files = {**REQUIRED_CANDIDATE_FILES, **(extras or {})}
    for relative, content in files.items():
        if relative in (omit or set()):
            continue
        path = candidate / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    _run("git", "add", "-f", ".", cwd=candidate)
    commit_env = {
        **os.environ,
        "GIT_AUTHOR_DATE": f"{timestamp} +0000",
        "GIT_COMMITTER_DATE": f"{timestamp} +0000",
    }
    _run("git", "commit", "-q", "-m", subject, cwd=candidate, env=commit_env)
    commit = _run("git", "rev-parse", "HEAD", cwd=candidate)
    if detach:
        _run("git", "checkout", "-q", "--detach", commit, cwd=candidate)
    return candidate, commit


def _control(commit: str, **updates: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": 1,
        "git_commit": commit,
        "git_commit_subject": CANDIDATE_SUBJECT,
        "git_tree_clean": True,
    }
    value.update(updates)
    return value


def _write_control(root: Path, value: dict[str, Any], *, canonical: bool = True) -> tuple[Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "candidate-control.json"
    raw = _canonical_bytes(value) if canonical else json.dumps(value, indent=2).encode("utf-8")
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def _freeze_api() -> tuple[Any, Any, Any]:
    try:
        freeze = importlib.import_module("evaluation.release_candidate.freeze")
        fingerprints = importlib.import_module("evaluation.release_candidate.fingerprints")
        attestation = importlib.import_module("evaluation.tool_attestation")
    except ModuleNotFoundError as exc:
        pytest.fail(f"D36 freezer module is missing: {exc}")
    return freeze, fingerprints, attestation


def _freeze(tmp_path: Path, candidate: Path, commit: str, *, output_name: str = "output") -> Any:
    freeze, _, _ = _freeze_api()
    control_path, digest = _write_control(tmp_path, _control(commit))
    return freeze.freeze_candidate(
        candidate_root=candidate,
        candidate_control_path=control_path,
        expected_candidate_control_sha256=digest,
        output_root=tmp_path / output_name,
    )


def _tree_snapshot(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if ".git" in path.relative_to(root).parts or not path.is_file():
            continue
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_freezer_module_is_available() -> None:
    freeze, fingerprints, attestation = _freeze_api()
    assert callable(freeze.freeze_candidate)
    assert callable(fingerprints.fingerprint_files)
    assert callable(attestation.canonical_json_bytes)


def test_same_inputs_produce_byte_identical_manifest_with_commit_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate, commit = _make_candidate(tmp_path)
    freeze, _, _ = _freeze_api()
    control_path, digest = _write_control(tmp_path, _control(commit))
    monkeypatch.setenv("TZ", "Pacific/Honolulu")
    if hasattr(os, "tzset"):
        os.tzset()
    first = freeze.freeze_candidate(
        candidate_root=candidate,
        candidate_control_path=control_path,
        expected_candidate_control_sha256=digest,
        output_root=tmp_path / "one",
    )
    monkeypatch.setenv("TZ", "Europe/Paris")
    if hasattr(os, "tzset"):
        os.tzset()
    second = freeze.freeze_candidate(
        candidate_root=candidate,
        candidate_control_path=control_path,
        expected_candidate_control_sha256=digest,
        output_root=tmp_path / "two",
    )
    first_bytes = (tmp_path / "one" / first.candidate_id / "freeze-manifest.json").read_bytes()
    second_bytes = (tmp_path / "two" / second.candidate_id / "freeze-manifest.json").read_bytes()
    expected_time = datetime.fromtimestamp(1_700_000_000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert first.created_at == expected_time
    assert first_bytes == second_bytes
    assert first_bytes.endswith(b"\n")
    assert b"+00:00" not in first_bytes and b".000" not in first_bytes
    assert hashlib.sha256(first_bytes).hexdigest() == hashlib.sha256(second_bytes).hexdigest()


def test_commit_timestamp_changes_created_at_and_manifest_hash(tmp_path: Path) -> None:
    first_root, second_root = tmp_path / "first", tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_candidate, first_commit = _make_candidate(first_root, timestamp=1_700_000_000)
    second_candidate, second_commit = _make_candidate(second_root, timestamp=1_700_000_001)
    first = _freeze(first_root, first_candidate, first_commit)
    second = _freeze(second_root, second_candidate, second_commit)
    first_bytes = (first_root / "output" / first.candidate_id / "freeze-manifest.json").read_bytes()
    second_bytes = (second_root / "output" / second.candidate_id / "freeze-manifest.json").read_bytes()
    assert first.created_at == "2023-11-14T22:13:20Z"
    assert second.created_at == "2023-11-14T22:13:21Z"
    assert hashlib.sha256(first_bytes).digest() != hashlib.sha256(second_bytes).digest()


def test_manifest_binds_control_hash_candidate_id_and_strict_contracts(tmp_path: Path) -> None:
    candidate, commit = _make_candidate(tmp_path)
    freeze, _, _ = _freeze_api()
    control_path, digest = _write_control(tmp_path, _control(commit))
    manifest = freeze.freeze_candidate(
        candidate_root=candidate,
        candidate_control_path=control_path,
        expected_candidate_control_sha256=digest,
        output_root=tmp_path / "output",
    )
    assert manifest.git_commit == commit
    assert manifest.git_tree_clean is True
    assert manifest.candidate_control_sha256 == digest
    assert manifest.candidate_id == f"{manifest.aggregate_sha256[:16]}-{commit[:12]}"
    assert manifest.schema_version_number == 1
    assert isinstance(manifest.files, list)
    assert set(manifest.mode_configuration) == {"all_tools", "stateful"}
    assert all("\\" not in item.path and not Path(item.path).is_absolute() for item in manifest.files)
    payload = json.loads((tmp_path / "output" / manifest.candidate_id / "freeze-manifest.json").read_bytes())
    assert payload == manifest.model_dump(mode="json")
    with pytest.raises(ValidationError):
        freeze.FreezeManifest.model_validate({**payload, "unknown": True})


@pytest.mark.parametrize(
    ("expected_digest", "control_transform", "canonical"),
    [
        ("0" * 64, lambda value: value, True),
        ("ABC", lambda value: value, True),
        ("dda5", lambda value: value, True),
        (None, lambda value: {**value, "extra": True}, True),
        (None, lambda value: {key: item for key, item in value.items() if key != "git_commit"}, True),
        (None, lambda value: {**value, "git_tree_clean": False}, True),
        (None, lambda value: value, False),
    ],
)
def test_invalid_candidate_control_fails_without_output(
    tmp_path: Path,
    expected_digest: str | None,
    control_transform: Any,
    canonical: bool,
) -> None:
    candidate, commit = _make_candidate(tmp_path)
    freeze, _, _ = _freeze_api()
    path, actual = _write_control(tmp_path, control_transform(_control(commit)), canonical=canonical)
    with pytest.raises((ValueError, ValidationError)):
        freeze.freeze_candidate(
            candidate_root=candidate,
            candidate_control_path=path,
            expected_candidate_control_sha256=expected_digest or actual,
            output_root=tmp_path / "output",
        )
    assert not (tmp_path / "output").exists()


def test_control_is_read_once_and_hash_checked_before_fingerprinting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate, commit = _make_candidate(tmp_path)
    freeze, fingerprints, _ = _freeze_api()
    path, _ = _write_control(tmp_path, _control(commit))
    called = False

    def forbidden(_: Path) -> list[Any]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(freeze, "fingerprint_files", forbidden)
    with pytest.raises(ValueError, match="candidate-control SHA-256"):
        freeze.freeze_candidate(
            candidate_root=candidate,
            candidate_control_path=path,
            expected_candidate_control_sha256="f" * 64,
            output_root=tmp_path / "output",
        )
    assert not called
    assert callable(fingerprints.fingerprint_files)


def test_dirty_untracked_attached_stale_and_subject_mismatch_are_rejected(tmp_path: Path) -> None:
    freeze, _, _ = _freeze_api()
    cases: list[tuple[Path, str, dict[str, Any]]] = []

    dirty_root = tmp_path / "dirty"
    dirty_root.mkdir()
    dirty, dirty_commit = _make_candidate(dirty_root)
    (dirty / "backend/app/core/config.py").write_text("changed\n", encoding="utf-8")
    cases.append((dirty, dirty_commit, _control(dirty_commit)))

    untracked_root = tmp_path / "untracked"
    untracked_root.mkdir()
    untracked, untracked_commit = _make_candidate(untracked_root)
    (untracked / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    cases.append((untracked, untracked_commit, _control(untracked_commit)))

    attached_root = tmp_path / "attached"
    attached_root.mkdir()
    attached, attached_commit = _make_candidate(attached_root, detach=False)
    cases.append((attached, attached_commit, _control(attached_commit)))

    stale_root = tmp_path / "stale"
    stale_root.mkdir()
    stale, stale_commit = _make_candidate(stale_root)
    cases.append((stale, stale_commit, _control("0" * 40)))

    subject_root = tmp_path / "subject"
    subject_root.mkdir()
    subject, subject_commit = _make_candidate(subject_root, subject="wrong subject")
    cases.append((subject, subject_commit, _control(subject_commit)))

    for index, (candidate, _, control) in enumerate(cases):
        control_path, digest = _write_control(tmp_path / f"control-{index}", control)
        with pytest.raises(ValueError):
            freeze.freeze_candidate(
                candidate_root=candidate,
                candidate_control_path=control_path,
                expected_candidate_control_sha256=digest,
                output_root=tmp_path / f"output-{index}",
            )
        assert not (tmp_path / f"output-{index}").exists()


def test_candidate_allowlist_is_sorted_and_excludes_tools_secrets_and_runtime(tmp_path: Path) -> None:
    excluded = {
        ".env": b"SECRET=value\n",
        "backend/evaluation/final_protocol.json": b"later protocol",
        "backend/evaluation/release_candidate/freeze.py": b"later freezer",
        "backend/evaluation/scripts/evaluation_trial_host.py": b"later host",
        "backend/evaluation/tool_attestation.py": b"later attestation",
        "backend/node_modules/dependency/index.js": b"generated",
        "backend/storage/runtime.db": b"sqlite",
        "evaluation/d24/held-out.jsonl": b"private held-out text",
        "frontend/dist/bundle.js": b"generated",
        "frontend/node_modules/react/index.js": b"generated",
        "model-weights/model.onnx": b"weights",
        "release-evidence/old.json": b"runtime evidence",
        "storage/video.mp4": b"media",
    }
    candidate, _ = _make_candidate(tmp_path, extras=excluded)
    _, fingerprints, _ = _freeze_api()
    files = fingerprints.fingerprint_files(candidate)
    paths = [item.path for item in files]
    assert paths == sorted(paths)
    assert "backend/app/core/config.py" in paths
    assert "frontend/src/main.tsx" in paths
    assert "backend/tests/test_candidate.py" in paths
    assert "docs/DTD.md" in paths
    assert not set(excluded).intersection(paths)


def test_allowlisted_byte_change_changes_aggregate(tmp_path: Path) -> None:
    candidate, _ = _make_candidate(tmp_path)
    _, fingerprints, _ = _freeze_api()
    before = fingerprints.aggregate_fingerprints(fingerprints.fingerprint_files(candidate))
    path = candidate / "backend/app/core/config.py"
    path.write_bytes(path.read_bytes() + b"changed\n")
    after = fingerprints.aggregate_fingerprints(fingerprints.fingerprint_files(candidate))
    assert before != after


@pytest.mark.parametrize(
    "missing",
    [
        "backend/app/operations/definitions.json",
        "backend/app/operations/search_scope.json",
        "backend/app/retrieval/e5-profile.json",
        "backend/app/retrieval/nomic-profile.json",
        "backend/pyproject.toml",
        "backend/uv.lock",
        "frontend/package.json",
        "frontend/pnpm-lock.yaml",
    ],
)
def test_missing_candidate_inputs_fail_closed(tmp_path: Path, missing: str) -> None:
    candidate, _ = _make_candidate(tmp_path, omit={missing})
    _, fingerprints, _ = _freeze_api()
    with pytest.raises(ValueError, match="required candidate file"):
        fingerprints.fingerprint_files(candidate)


def test_candidate_is_unchanged_including_ignored_inventory(tmp_path: Path) -> None:
    candidate, commit = _make_candidate(tmp_path)
    before_files = _tree_snapshot(candidate)
    before_status = _run("git", "status", "--porcelain=v1", "--ignored", cwd=candidate)
    _freeze(tmp_path, candidate, commit)
    assert _tree_snapshot(candidate) == before_files
    assert _run("git", "status", "--porcelain=v1", "--ignored", cwd=candidate) == before_status


def test_snapshot_does_not_read_excluded_secret_or_held_out_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate, commit = _make_candidate(
        tmp_path,
        extras={
            ".env": b"SECRET=must-not-be-read\n",
            "evaluation/d24/held-out-private.jsonl": b"held-out body",
        },
    )
    freeze, _, _ = _freeze_api()
    original = freeze._read_regular_once

    def guarded(path: Path, *, maximum: int, label: str) -> bytes:
        relative = path.relative_to(candidate).as_posix() if path.is_relative_to(candidate) else ""
        if relative == ".env" or "held-out" in relative:
            raise AssertionError(f"excluded bytes were read: {relative}")
        return original(path, maximum=maximum, label=label)

    monkeypatch.setattr(freeze, "_read_regular_once", guarded)
    control_path, digest = _write_control(tmp_path, _control(commit))
    freeze.freeze_candidate(
        candidate_root=candidate,
        candidate_control_path=control_path,
        expected_candidate_control_sha256=digest,
        output_root=tmp_path / "output",
    )


def test_candidate_mutation_during_freeze_removes_partial_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate, commit = _make_candidate(tmp_path)
    freeze, _, _ = _freeze_api()
    control_path, digest = _write_control(tmp_path, _control(commit))
    original = freeze.fingerprint_files

    def mutating(root: Path) -> list[Any]:
        result = original(root)
        ignored = root / ".pytest_cache" / "mutation"
        ignored.parent.mkdir()
        ignored.write_text("changed", encoding="utf-8")
        return result

    monkeypatch.setattr(freeze, "fingerprint_files", mutating)
    with pytest.raises(ValueError, match="candidate changed"):
        freeze.freeze_candidate(
            candidate_root=candidate,
            candidate_control_path=control_path,
            expected_candidate_control_sha256=digest,
            output_root=tmp_path / "output",
        )
    assert not (tmp_path / "output").exists()


def test_existing_destination_and_tracked_output_root_are_refused(tmp_path: Path) -> None:
    candidate, commit = _make_candidate(tmp_path)
    manifest = _freeze(tmp_path, candidate, commit)
    with pytest.raises(ValueError, match="output"):
        _freeze(tmp_path, candidate, commit)
    assert (tmp_path / "output" / manifest.candidate_id / "freeze-manifest.json").is_file()

    tracked = tmp_path / "tracked-output"
    tracked.mkdir()
    _run("git", "init", "-q", cwd=tracked)
    _run("git", "config", "user.email", "d36@example.invalid", cwd=tracked)
    _run("git", "config", "user.name", "D36 Test", cwd=tracked)
    (tracked / "evidence").mkdir()
    (tracked / "evidence" / ".keep").write_text("tracked", encoding="utf-8")
    _run("git", "add", ".", cwd=tracked)
    _run("git", "commit", "-q", "-m", "tracked output", cwd=tracked)
    freeze, _, _ = _freeze_api()
    control_path, digest = _write_control(tmp_path / "tracked-control", _control(commit))
    with pytest.raises(ValueError, match="tracked output"):
        freeze.freeze_candidate(
            candidate_root=candidate,
            candidate_control_path=control_path,
            expected_candidate_control_sha256=digest,
            output_root=tracked / "evidence",
        )


def test_tool_attestation_rechecks_sources_for_cross_file_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, attestation = _freeze_api()
    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("B = 1\n", encoding="utf-8")
    original = attestation.fingerprint_file
    calls = 0

    def mutating(root: Path, relative: str) -> Any:
        nonlocal calls
        result = original(root, relative)
        calls += 1
        if calls == 1:
            (root / "a.py").write_text("A = 2\n", encoding="utf-8")
        return result

    monkeypatch.setattr(attestation, "fingerprint_file", mutating)
    with pytest.raises(ValueError, match="changed while attesting"):
        attestation.attest_tool(
            repo_root=tmp_path,
            tool_name="test_tool",
            git_commit="a" * 40,
            source_paths=("a.py", "b.py"),
        )


def test_post_publish_verification_failure_removes_atomic_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate, commit = _make_candidate(tmp_path)
    freeze, _, _ = _freeze_api()
    control_path, digest = _write_control(tmp_path, _control(commit))
    original = freeze._read_regular_once

    def corrupt_published(path: Path, *, maximum: int, label: str) -> bytes:
        value = original(path, maximum=maximum, label=label)
        return b"corrupt" if label == "freeze manifest" else value

    monkeypatch.setattr(freeze, "_read_regular_once", corrupt_published)
    with pytest.raises(ValueError, match="published freeze manifest changed"):
        freeze.freeze_candidate(
            candidate_root=candidate,
            candidate_control_path=control_path,
            expected_candidate_control_sha256=digest,
            output_root=tmp_path / "output",
        )
    assert not (tmp_path / "output").exists()


def test_d36_tool_attestation_has_exact_allowlist_and_valid_aggregate(tmp_path: Path) -> None:
    candidate, commit = _make_candidate(tmp_path)
    manifest = _freeze(tmp_path, candidate, commit)
    _, _, attestation = _freeze_api()
    path = tmp_path / "output" / manifest.candidate_id / "d36-tool-attestation.json"
    raw = path.read_bytes()
    parsed = attestation.ToolAttestation.model_validate_json(raw)
    expected = {
        "backend/evaluation/final_protocol.json",
        "backend/evaluation/release_candidate/__init__.py",
        "backend/evaluation/release_candidate/contracts.py",
        "backend/evaluation/release_candidate/fingerprints.py",
        "backend/evaluation/release_candidate/freeze.py",
        "backend/evaluation/scripts/evaluation_trial_host.py",
        "backend/evaluation/scripts/freeze_candidate.py",
        "backend/evaluation/tool_attestation.py",
        "backend/evaluation/unlabeled_contracts.py",
    }
    assert isinstance(parsed.files, list)
    assert {item.path for item in parsed.files} == expected
    assert parsed.tool_name == "d36_candidate_freezer_and_trial_host"
    assert parsed.aggregate_sha256 == attestation.aggregate_fingerprints(parsed.files)
    assert raw == attestation.canonical_json_bytes(parsed.model_dump(mode="json")) + b"\n"
    with pytest.raises(ValidationError):
        attestation.ToolAttestation.model_validate({**parsed.model_dump(), "extra": True})


def test_cli_writes_only_manifest_and_attestation(tmp_path: Path) -> None:
    candidate, commit = _make_candidate(tmp_path)
    control_path, digest = _write_control(tmp_path, _control(commit))
    backend = Path(__file__).parents[1]
    output = tmp_path / "cli-output"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evaluation.scripts.freeze_candidate",
            "--candidate-root",
            str(candidate),
            "--candidate-control",
            str(control_path),
            "--expected-candidate-control-sha256",
            digest,
            "--output-root",
            str(output),
        ],
        cwd=backend,
        check=True,
        capture_output=True,
        text=True,
    )
    response = json.loads(completed.stdout)
    candidate_output = output / response["candidate_id"]
    assert {path.name for path in candidate_output.iterdir()} == {
        "d36-tool-attestation.json",
        "freeze-manifest.json",
    }
    assert response == {
        "candidate_id": response["candidate_id"],
        "freeze_manifest": f"{response['candidate_id']}/freeze-manifest.json",
        "tool_attestation": f"{response['candidate_id']}/d36-tool-attestation.json",
    }
