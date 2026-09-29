"""Deterministically freeze one clean detached D35 candidate checkout."""
from __future__ import annotations

import ast
import hashlib
import os
import platform
import re
import secrets
import stat
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pydantic
from pydantic import ValidationError

from evaluation.release_candidate.contracts import (
    CANDIDATE_COMMIT_SUBJECT,
    CandidateControl,
    CompletionMarker,
    FreezeManifest,
)
from evaluation.release_candidate.fingerprints import (
    aggregate_fingerprints,
    fingerprint_files,
)
from evaluation.tool_attestation import (
    FileFingerprint,
    ToolAttestation,
    attest_tool,
    canonical_json_bytes,
)

_MAX_CONTROL_BYTES = 4096
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REPARSE_POINT = 0x400
_TOOL_NAME = "d36_candidate_freezer_and_trial_host"
_TOOL_SOURCE_PATHS = (
    "backend/evaluation/final_protocol.json",
    "backend/evaluation/release_candidate/__init__.py",
    "backend/evaluation/release_candidate/contracts.py",
    "backend/evaluation/release_candidate/fingerprints.py",
    "backend/evaluation/release_candidate/freeze.py",
    "backend/evaluation/scripts/evaluation_trial_host.py",
    "backend/evaluation/scripts/freeze_candidate.py",
    "backend/evaluation/tool_attestation.py",
    "backend/evaluation/unlabeled_contracts.py",
)
_PUBLICATION_STATE_NAME = ".d36-publication-state"
_CLAIM_TOKEN_BYTES = 32
_MAX_PUBLICATION_STATE_BYTES = 1024
_MAX_FREEZE_MANIFEST_BYTES = 16 * 1024 * 1024
_MAX_TOOL_ATTESTATION_BYTES = 1024 * 1024


class PublicationOwnershipLost(ValueError):
    """The claimed publication directory is no longer owned by this invocation."""


@dataclass(frozen=True)
class _FileIdentity:
    path: Path
    device: int
    inode: int


@dataclass(frozen=True)
class _RetainedPublicationFile:
    name: str
    descriptor: int
    identity: _FileIdentity


@dataclass(frozen=True)
class _PublicationClaim:
    path: Path
    resolved_parent: Path
    device: int
    inode: int
    token: bytes
    files: tuple[_RetainedPublicationFile, ...]

    def file(self, name: str) -> _RetainedPublicationFile:
        return next(file for file in self.files if file.name == name)


_MODE_CONFIGURATION: dict[str, object] = {
    "all_tools": {
        "retrieval_index_required": False,
        "readiness_annotations": False,
    },
    "stateful": {
        "all_tools_fallback": True,
        "retrieval_index_required": True,
        "readiness_annotations": True,
    },
}


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT)


def _require_directory(path: Path, label: str) -> Path:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} must be a regular directory")
    return path.resolve(strict=True)


def _read_regular_once(path: Path, *, maximum: int, label: str) -> bytes:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _is_reparse(opened):
            raise ValueError(f"{label} must be a regular file")
        chunks: list[bytes] = []
        total = 0
        while total <= maximum:
            chunk = os.read(descriptor, min(65536, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (metadata.st_dev, metadata.st_ino, metadata.st_size)
    if identity != (opened.st_dev, opened.st_ino, opened.st_size):
        raise ValueError(f"{label} changed while reading")
    if identity != (final.st_dev, final.st_ino, final.st_size):
        raise ValueError(f"{label} changed while reading")
    value = b"".join(chunks)
    if len(value) > maximum or len(value) != opened.st_size:
        raise ValueError(f"{label} exceeds {maximum} bytes")
    return value


def _git(candidate_root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(candidate_root), *arguments],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    )


def _candidate_identity(candidate_root: Path, control: CandidateControl) -> tuple[str, int]:
    inside = _git(candidate_root, "rev-parse", "--is-inside-work-tree").stdout.strip()
    if inside != "true":
        raise ValueError("candidate root is not a Git worktree")
    symbolic = _git(candidate_root, "symbolic-ref", "-q", "HEAD", check=False)
    if symbolic.returncode == 0:
        raise ValueError("candidate checkout must be detached")
    commit = _git(candidate_root, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
    subject = _git(candidate_root, "show", "-s", "--format=%s", "HEAD").stdout.rstrip("\r\n")
    status = _git(candidate_root, "status", "--porcelain=v1", "--untracked-files=all").stdout
    if commit != control.git_commit:
        raise ValueError("candidate commit does not match candidate control")
    if subject != control.git_commit_subject or subject != CANDIDATE_COMMIT_SUBJECT:
        raise ValueError("candidate commit subject does not match candidate control")
    if status:
        raise ValueError("candidate checkout is not clean")
    raw_timestamp = _git(candidate_root, "show", "-s", "--format=%ct", "HEAD").stdout.strip()
    if not raw_timestamp.isascii() or not raw_timestamp.isdecimal():
        raise ValueError("candidate commit timestamp is invalid")
    timestamp = int(raw_timestamp)
    if timestamp < 0:
        raise ValueError("candidate commit timestamp is invalid")
    return commit, timestamp


def _snapshot_tree(root: Path) -> str:
    entries: list[dict[str, Any]] = []

    def visit(directory: Path, relative: str) -> None:
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            if not relative and entry.name == ".git":
                continue
            child_relative = f"{relative}/{entry.name}" if relative else entry.name
            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                raise ValueError(f"candidate contains unsafe path: {child_relative}")
            if stat.S_ISDIR(metadata.st_mode):
                entries.append({"path": child_relative.replace("\\", "/"), "type": "directory"})
                visit(Path(entry.path), child_relative)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"candidate contains special file: {child_relative}")
            entries.append(
                {
                    "path": child_relative.replace("\\", "/"),
                    "type": "file",
                    "size": metadata.st_size,
                    "modified_ns": metadata.st_mtime_ns,
                    "changed_ns": metadata.st_ctime_ns,
                    "device": metadata.st_dev,
                    "inode": metadata.st_ino,
                }
            )

    visit(root, "")
    return hashlib.sha256(canonical_json_bytes(entries)).hexdigest()


def _load_control(path: Path, expected_sha256: str) -> tuple[CandidateControl, str]:
    if not _SHA256.fullmatch(expected_sha256):
        raise ValueError("expected candidate-control SHA-256 must be lowercase 64-hex")
    raw = _read_regular_once(path, maximum=_MAX_CONTROL_BYTES, label="candidate control")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError("candidate-control SHA-256 mismatch")
    try:
        control = CandidateControl.model_validate_json(raw, strict=True)
    except ValidationError:
        raise
    if canonical_json_bytes(control.model_dump(mode="json")) != raw:
        raise ValueError("candidate control must be canonical JSON without a newline")
    return control, actual


def _detect_schema_version(candidate_root: Path) -> int:
    source = _git(
        candidate_root,
        "show",
        "HEAD:backend/app/migrations/schema.py",
    ).stdout
    try:
        tree = ast.parse(source, filename="backend/app/migrations/schema.py")
    except SyntaxError as exc:
        raise ValueError("candidate migration source is malformed") from exc
    migration_functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "apply_v0_to_v1"
    ]
    if len(migration_functions) != 1:
        raise ValueError("candidate migration source must define apply_v0_to_v1 once")
    assignments: list[int] = []
    for node in ast.walk(migration_functions[0]):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        receiver = node.func.value
        if (
            node.func.attr != "execute"
            or not isinstance(receiver, ast.Name)
            or receiver.id != "connection"
            or len(node.args) != 1
            or node.keywords
        ):
            continue
        argument = node.args[0]
        if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
            continue
        if argument.value == "PRAGMA user_version":
            continue
        if argument.value.startswith("PRAGMA user_version"):
            match = re.fullmatch(r"PRAGMA user_version=([0-9]+)", argument.value)
            if match is None:
                raise ValueError("candidate migration source has malformed schema version")
            assignments.append(int(match.group(1)))
    if len(assignments) != 1:
        raise ValueError("candidate migration source must declare one schema version")
    if assignments[0] != 1:
        raise ValueError("candidate schema version is unsupported")
    return assignments[0]


def _created_at(timestamp: int) -> str:
    try:
        return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("candidate commit timestamp is out of range") from exc


def _tool_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _tool_commit(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD^{commit}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="ascii",
    )
    commit = completed.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("tooling Git commit is invalid")
    return commit


def _runtime_versions() -> dict[str, str]:
    git_version = subprocess.run(
        ["git", "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="ascii",
    ).stdout.strip()
    return {
        "git": git_version,
        "pydantic": pydantic.__version__,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
    }


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_output_root(
    output_root: Path, candidate_root: Path, tool_repo_root: Path
) -> tuple[Path, bool]:
    absolute = output_root.absolute()
    existing = absolute
    while not existing.exists():
        if existing.parent == existing:
            raise ValueError("output root has no existing parent")
        existing = existing.parent
    _require_directory(existing, "output parent")
    resolved_parent = existing.resolve(strict=True)
    resolved = resolved_parent.joinpath(*absolute.relative_to(existing).parts)
    if _path_is_within(resolved, candidate_root):
        raise ValueError("output root must be external to the candidate")
    if absolute.exists():
        _require_directory(absolute, "output root")
    release_evidence = tool_repo_root / "release-evidence"
    if _path_is_within(resolved, tool_repo_root) and not _path_is_within(
        resolved, release_evidence
    ):
        raise ValueError("in-repository output must be under release-evidence")
    created = False
    if not absolute.exists():
        absolute.mkdir(parents=True, exist_ok=False)
        created = True
    return absolute.resolve(strict=True), created


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _file_identity(path: Path) -> _FileIdentity:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISREG(
        metadata.st_mode
    ):
        raise ValueError("recorded publication file must be regular")
    return _FileIdentity(path=path, device=metadata.st_dev, inode=metadata.st_ino)


def _file_identity_matches(identity: _FileIdentity) -> bool:
    try:
        current = _file_identity(identity.path)
    except (OSError, ValueError):
        return False
    return (current.device, current.inode) == (identity.device, identity.inode)


def _open_retained(path: Path) -> _RetainedPublicationFile:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or _is_reparse(metadata):
            raise ValueError("publication file must be regular")
        identity = _FileIdentity(path=path, device=metadata.st_dev, inode=metadata.st_ino)
        if not _file_identity_matches(identity):
            raise ValueError("publication file identity changed")
        return _RetainedPublicationFile(
            name=path.name,
            descriptor=descriptor,
            identity=identity,
        )
    except BaseException:
        os.close(descriptor)
        raise


def _assert_retained_identity(file: _RetainedPublicationFile) -> os.stat_result:
    metadata = os.fstat(file.descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or _is_reparse(metadata)
        or (metadata.st_dev, metadata.st_ino)
        != (file.identity.device, file.identity.inode)
    ):
        raise _ownership_lost()
    return metadata


def _write_retained(file: _RetainedPublicationFile, value: bytes) -> None:
    _assert_retained_identity(file)
    os.ftruncate(file.descriptor, 0)
    os.lseek(file.descriptor, 0, os.SEEK_SET)
    written = 0
    while written < len(value):
        written += os.write(file.descriptor, value[written:])
    os.fsync(file.descriptor)
    metadata = _assert_retained_identity(file)
    if metadata.st_size != len(value):
        raise _ownership_lost()


def _read_retained(
    file: _RetainedPublicationFile, maximum: int, *, label: str
) -> bytes:
    initial = _assert_retained_identity(file)
    os.lseek(file.descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while total <= maximum:
        chunk = os.read(file.descriptor, min(65536, maximum + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    final = _assert_retained_identity(file)
    value = b"".join(chunks)
    if len(value) > maximum or len(value) != initial.st_size or len(value) != final.st_size:
        raise ValueError(f"{label} exceeds {maximum} bytes or changed while reading")
    return value


def _ownership_lost() -> PublicationOwnershipLost:
    return PublicationOwnershipLost(
        "publication directory ownership lost; moved partial may require operator cleanup"
    )


def _directory_identity(path: Path) -> tuple[int, int]:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISDIR(
        metadata.st_mode
    ):
        raise _ownership_lost()
    return metadata.st_dev, metadata.st_ino


def _assert_claim_owned(
    claim: _PublicationClaim, expected_state: bytes | None = None
) -> None:
    expected_names = {file.name for file in claim.files}
    try:
        if claim.path.parent.resolve(strict=True) != claim.resolved_parent:
            raise _ownership_lost()
        if _directory_identity(claim.path) != (claim.device, claim.inode):
            raise _ownership_lost()
        if {entry.name for entry in os.scandir(claim.path)} != expected_names:
            raise _ownership_lost()
        for file in claim.files:
            _assert_retained_identity(file)
            if not _file_identity_matches(file.identity):
                raise _ownership_lost()
        state = claim.file(_PUBLICATION_STATE_NAME)
        state_bytes = _read_retained(
            state,
            _MAX_PUBLICATION_STATE_BYTES,
            label="publication state",
        )
        if state_bytes != (claim.token if expected_state is None else expected_state):
            raise _ownership_lost()
        if {entry.name for entry in os.scandir(claim.path)} != expected_names:
            raise _ownership_lost()
        if _directory_identity(claim.path) != (claim.device, claim.inode):
            raise _ownership_lost()
        if claim.path.parent.resolve(strict=True) != claim.resolved_parent:
            raise _ownership_lost()
    except PublicationOwnershipLost:
        raise
    except (OSError, ValueError):
        raise _ownership_lost() from None


def _claim_publication_directory(path: Path) -> _PublicationClaim:
    path.mkdir(mode=0o700, exist_ok=False)
    device, inode = _directory_identity(path)
    resolved_parent = path.parent.resolve(strict=True)
    token = secrets.token_bytes(_CLAIM_TOKEN_BYTES)
    files: list[_RetainedPublicationFile] = []
    try:
        for name in (
            _PUBLICATION_STATE_NAME,
            "freeze-manifest.json",
            "d36-tool-attestation.json",
        ):
            files.append(_open_retained(path / name))
        claim = _PublicationClaim(
            path=path,
            resolved_parent=resolved_parent,
            device=device,
            inode=inode,
            token=token,
            files=tuple(files),
        )
        _write_retained(claim.file(_PUBLICATION_STATE_NAME), token)
        _assert_claim_owned(claim)
        return claim
    except BaseException:
        for file in files:
            try:
                os.close(file.descriptor)
            except OSError:
                pass
        raise


def _write_owned(
    claim: _PublicationClaim, name: str, value: bytes
) -> None:
    _assert_claim_owned(claim)
    try:
        _write_retained(claim.file(name), value)
    finally:
        _assert_claim_owned(claim)


def _read_owned(
    claim: _PublicationClaim, name: str, *, maximum: int, label: str
) -> bytes:
    _assert_claim_owned(claim)
    try:
        return _read_retained(claim.file(name), maximum, label=label)
    finally:
        _assert_claim_owned(claim)


def _finish_claim(claim: _PublicationClaim, completion_marker_bytes: bytes) -> None:
    state = claim.file(_PUBLICATION_STATE_NAME)
    _assert_claim_owned(claim)
    try:
        _write_retained(state, completion_marker_bytes)
    finally:
        _assert_claim_owned(claim, completion_marker_bytes)
    _assert_claim_owned(claim, completion_marker_bytes)
    try:
        if (
            _read_retained(
                state,
                _MAX_PUBLICATION_STATE_BYTES,
                label="publication state",
            )
            != completion_marker_bytes
        ):
            raise _ownership_lost()
    finally:
        _assert_claim_owned(claim, completion_marker_bytes)


def _close_claim(claim: _PublicationClaim) -> None:
    for file in claim.files:
        try:
            os.close(file.descriptor)
        except OSError:
            pass


def _verify_canonical_attestation(raw: bytes, expected: ToolAttestation) -> None:
    try:
        parsed = ToolAttestation.model_validate_json(raw, strict=True)
    except ValidationError as exc:
        raise ValueError("published tool attestation is invalid") from exc
    canonical = canonical_json_bytes(parsed.model_dump(mode="json")) + b"\n"
    if raw != canonical or parsed != expected:
        raise ValueError("published tool attestation changed")
    if aggregate_fingerprints(parsed.files) != parsed.aggregate_sha256:
        raise ValueError("published tool attestation aggregate mismatch")


def _completion_marker(manifest_raw: bytes, attestation_raw: bytes) -> CompletionMarker:
    return CompletionMarker(
        schema_version=1,
        files=[
            FileFingerprint(
                path="d36-tool-attestation.json",
                sha256=hashlib.sha256(attestation_raw).hexdigest(),
                size=len(attestation_raw),
            ),
            FileFingerprint(
                path="freeze-manifest.json",
                sha256=hashlib.sha256(manifest_raw).hexdigest(),
                size=len(manifest_raw),
            ),
        ],
    )


def _completion_marker_bytes(manifest_raw: bytes, attestation_raw: bytes) -> bytes:
    marker = _completion_marker(manifest_raw, attestation_raw)
    return canonical_json_bytes(marker.model_dump(mode="json")) + b"\n"


def read_frozen_candidate(directory: Path) -> tuple[FreezeManifest, ToolAttestation]:
    expected_names = {
        _PUBLICATION_STATE_NAME,
        "freeze-manifest.json",
        "d36-tool-attestation.json",
    }
    try:
        publication = _require_directory(directory, "completed publication")
        publication_identity = _directory_identity(publication)
        if {entry.name for entry in os.scandir(publication)} != expected_names:
            raise ValueError("completed publication entries are invalid")
        marker_identity = _file_identity(publication / _PUBLICATION_STATE_NAME)
        manifest_identity = _file_identity(publication / "freeze-manifest.json")
        attestation_identity = _file_identity(publication / "d36-tool-attestation.json")
        marker_raw = _read_regular_once(
            publication / _PUBLICATION_STATE_NAME,
            maximum=_MAX_PUBLICATION_STATE_BYTES,
            label="publication state",
        )
        marker = CompletionMarker.model_validate_json(marker_raw, strict=True)
        if marker_raw != canonical_json_bytes(marker.model_dump(mode="json")) + b"\n":
            raise ValueError("publication completion marker is invalid")
        manifest_raw = _read_regular_once(
            publication / "freeze-manifest.json",
            maximum=_MAX_FREEZE_MANIFEST_BYTES,
            label="freeze manifest",
        )
        manifest = FreezeManifest.model_validate_json(manifest_raw, strict=True)
        manifest_aggregate = aggregate_fingerprints(manifest.files)
        expected_candidate_id = f"{manifest_aggregate[:16]}-{manifest.git_commit[:12]}"
        if (
            manifest_raw
            != canonical_json_bytes(manifest.model_dump(mode="json")) + b"\n"
            or manifest.aggregate_sha256 != manifest_aggregate
            or manifest.candidate_id != expected_candidate_id
            or publication.name != expected_candidate_id
        ):
            raise ValueError("freeze manifest is not canonical or content-addressed")
        attestation_raw = _read_regular_once(
            publication / "d36-tool-attestation.json",
            maximum=_MAX_TOOL_ATTESTATION_BYTES,
            label="tool attestation",
        )
        attestation = ToolAttestation.model_validate_json(attestation_raw, strict=True)
        _verify_canonical_attestation(attestation_raw, attestation)
        if marker != _completion_marker(manifest_raw, attestation_raw):
            raise ValueError("publication completion marker does not bind artifacts")
        if (
            _directory_identity(publication) != publication_identity
            or {entry.name for entry in os.scandir(publication)} != expected_names
        ):
            raise ValueError("completed publication entries changed")
        if (
            not _file_identity_matches(marker_identity)
            or not _file_identity_matches(manifest_identity)
            or not _file_identity_matches(attestation_identity)
            or _read_regular_once(
                publication / _PUBLICATION_STATE_NAME,
                maximum=_MAX_PUBLICATION_STATE_BYTES,
                label="publication state",
            )
            != marker_raw
            or _read_regular_once(
                publication / "freeze-manifest.json",
                maximum=_MAX_FREEZE_MANIFEST_BYTES,
                label="freeze manifest",
            )
            != manifest_raw
            or _read_regular_once(
                publication / "d36-tool-attestation.json",
                maximum=_MAX_TOOL_ATTESTATION_BYTES,
                label="tool attestation",
            )
            != attestation_raw
            or not _file_identity_matches(marker_identity)
            or not _file_identity_matches(manifest_identity)
            or not _file_identity_matches(attestation_identity)
        ):
            raise ValueError("completed publication artifacts changed")
        return manifest, attestation
    except (OSError, ValidationError, ValueError) as exc:
        raise ValueError("completed publication is invalid") from exc


def freeze_candidate(
    *,
    candidate_root: Path,
    candidate_control_path: Path,
    expected_candidate_control_sha256: str,
    output_root: Path,
) -> FreezeManifest:
    control, control_sha256 = _load_control(
        candidate_control_path, expected_candidate_control_sha256
    )
    candidate = _require_directory(candidate_root, "candidate root")
    commit, timestamp = _candidate_identity(candidate, control)
    initial_snapshot = _snapshot_tree(candidate)
    files = fingerprint_files(candidate)
    aggregate = aggregate_fingerprints(files)
    schema_version = _detect_schema_version(candidate)
    manifest = FreezeManifest(
        schema_version=1,
        candidate_id=f"{aggregate[:16]}-{commit[:12]}",
        git_commit=commit,
        git_tree_clean=True,
        candidate_control_sha256=control_sha256,
        created_at=_created_at(timestamp),
        runtime=_runtime_versions(),
        schema_version_number=schema_version,
        mode_configuration=_MODE_CONFIGURATION,
        files=files,
        aggregate_sha256=aggregate,
    )
    tool_root = _tool_repo_root()
    attestation = attest_tool(
        repo_root=tool_root,
        tool_name=_TOOL_NAME,
        git_commit=_tool_commit(tool_root),
        source_paths=_TOOL_SOURCE_PATHS,
    )
    manifest_bytes = canonical_json_bytes(manifest.model_dump(mode="json")) + b"\n"
    attestation_bytes = canonical_json_bytes(attestation.model_dump(mode="json")) + b"\n"
    completion_marker_bytes = _completion_marker_bytes(manifest_bytes, attestation_bytes)
    root, _ = _validate_output_root(output_root, candidate, tool_root)
    final = root / manifest.candidate_id
    if FreezeManifest.model_validate_json(manifest_bytes, strict=True) != manifest:
        raise ValueError("freeze manifest failed verification")
    _verify_canonical_attestation(attestation_bytes, attestation)
    rechecked_commit, rechecked_timestamp = _candidate_identity(candidate, control)
    if rechecked_commit != commit or rechecked_timestamp != timestamp:
        raise ValueError("candidate identity changed during freeze")
    if _snapshot_tree(candidate) != initial_snapshot:
        raise ValueError("candidate changed during freeze")

    try:
        claimed = _claim_publication_directory(final)
    except FileExistsError as exc:
        raise ValueError("output destination already exists") from exc
    try:
        _write_owned(claimed, "freeze-manifest.json", manifest_bytes)
        _write_owned(
            claimed,
            "d36-tool-attestation.json",
            attestation_bytes,
        )
        published_manifest = _read_owned(
            claimed,
            "freeze-manifest.json",
            maximum=len(manifest_bytes),
            label="freeze manifest",
        )
        if published_manifest != manifest_bytes:
            raise ValueError("published freeze manifest changed")
        published_attestation = _read_owned(
            claimed,
            "d36-tool-attestation.json",
            maximum=len(attestation_bytes),
            label="tool attestation",
        )
        _verify_canonical_attestation(published_attestation, attestation)
        _finish_claim(claimed, completion_marker_bytes)
    finally:
        _close_claim(claimed)

    try:
        if _directory_identity(final) != (claimed.device, claimed.inode):
            raise _ownership_lost()
        _fsync_directory(final)
        if _directory_identity(final) != (claimed.device, claimed.inode):
            raise _ownership_lost()
        _fsync_directory(root)
    except PublicationOwnershipLost:
        raise
    except (OSError, ValueError):
        raise _ownership_lost() from None
    published = read_frozen_candidate(final)
    if published != (manifest, attestation):
        raise ValueError("completed publication changed")
    return manifest
