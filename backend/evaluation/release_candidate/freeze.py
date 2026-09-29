"""Deterministically freeze one clean detached D35 candidate checkout."""
from __future__ import annotations

import ast
import errno
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
    FreezeManifest,
)
from evaluation.release_candidate.fingerprints import (
    aggregate_fingerprints,
    fingerprint_files,
)
from evaluation.tool_attestation import ToolAttestation, attest_tool, canonical_json_bytes

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
_CLAIM_TOKEN_NAME = ".d36-publication-claim"
_COMPLETED_MARKER_NAME = ".d36-publication-complete"
_COMPLETED_MARKER_BYTES = b"d36-publication-complete-v1\n"
_CLAIM_TOKEN_BYTES = 32
_MAX_CLAIM_TOKEN_BYTES = 64
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
class _PublicationClaim:
    path: Path
    resolved_parent: Path
    device: int
    inode: int
    token: bytes
    token_identity: _FileIdentity


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


def _write_fsynced(path: Path, value: bytes) -> _FileIdentity:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        written = 0
        while written < len(value):
            written += os.write(descriptor, value[written:])
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = _FileIdentity(path=path, device=metadata.st_dev, inode=metadata.st_ino)
    if not _file_identity_matches(identity):
        raise ValueError("written file identity changed")
    return identity


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


def _unlink_recorded_file(identity: _FileIdentity) -> None:
    if not _file_identity_matches(identity):
        return
    try:
        identity.path.unlink()
    except FileNotFoundError:
        pass


def _publish_file_no_replace(
    source: Path, destination: Path, value: bytes
) -> _FileIdentity:
    source_identity = _file_identity(source)
    try:
        os.link(source, destination)
    except OSError as exc:
        if exc.errno not in {errno.EACCES, errno.EPERM, errno.EXDEV, errno.ENOTSUP}:
            raise
        return _write_fsynced(destination, value)
    destination_identity = _file_identity(destination)
    if (destination_identity.device, destination_identity.inode) != (
        source_identity.device,
        source_identity.inode,
    ):
        raise ValueError("published file identity changed")
    return destination_identity


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


def _assert_claim_owned(claim: _PublicationClaim) -> None:
    try:
        if claim.path.parent.resolve(strict=True) != claim.resolved_parent:
            raise _ownership_lost()
        if _directory_identity(claim.path) != (claim.device, claim.inode):
            raise _ownership_lost()
        if not _file_identity_matches(claim.token_identity):
            raise _ownership_lost()
        token = _read_regular_once(
            claim.path / _CLAIM_TOKEN_NAME,
            maximum=_MAX_CLAIM_TOKEN_BYTES,
            label="publication claim token",
        )
        if token != claim.token or not _file_identity_matches(claim.token_identity):
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
    token_identity = _write_fsynced(path / _CLAIM_TOKEN_NAME, token)
    _fsync_directory(path)
    claim = _PublicationClaim(
        path=path,
        resolved_parent=resolved_parent,
        device=device,
        inode=inode,
        token=token,
        token_identity=token_identity,
    )
    _assert_claim_owned(claim)
    return claim


def _publish_owned(
    claim: _PublicationClaim, source: Path, destination_name: str, value: bytes
) -> _FileIdentity:
    _assert_claim_owned(claim)
    try:
        identity = _publish_file_no_replace(
            source, claim.path / destination_name, value
        )
    finally:
        _assert_claim_owned(claim)
    return identity


def _read_owned(
    claim: _PublicationClaim, name: str, *, maximum: int, label: str
) -> bytes:
    _assert_claim_owned(claim)
    try:
        return _read_regular_once(claim.path / name, maximum=maximum, label=label)
    finally:
        _assert_claim_owned(claim)


def _finish_claim(claim: _PublicationClaim) -> None:
    _assert_claim_owned(claim)
    claimed_names = {
        _CLAIM_TOKEN_NAME,
        "freeze-manifest.json",
        "d36-tool-attestation.json",
    }
    completed_names = {
        _COMPLETED_MARKER_NAME,
        "freeze-manifest.json",
        "d36-tool-attestation.json",
    }
    try:
        if {entry.name for entry in os.scandir(claim.path)} != claimed_names:
            raise _ownership_lost()
        completed_identity = _write_fsynced(
            claim.path / _COMPLETED_MARKER_NAME,
            _COMPLETED_MARKER_BYTES,
        )
        if (
            _read_regular_once(
                completed_identity.path,
                maximum=len(_COMPLETED_MARKER_BYTES),
                label="publication completion marker",
            )
            != _COMPLETED_MARKER_BYTES
            or not _file_identity_matches(completed_identity)
        ):
            raise _ownership_lost()
        _assert_claim_owned(claim)
        _unlink_recorded_file(claim.token_identity)
        if claim.token_identity.path.exists():
            raise _ownership_lost()
        if {entry.name for entry in os.scandir(claim.path)} != completed_names:
            raise _ownership_lost()
        if _directory_identity(claim.path) != (claim.device, claim.inode):
            raise _ownership_lost()
        if claim.path.parent.resolve(strict=True) != claim.resolved_parent:
            raise _ownership_lost()
    except PublicationOwnershipLost:
        raise
    except (OSError, ValueError):
        raise _ownership_lost() from None
    _fsync_directory(claim.path)
    _fsync_directory(claim.resolved_parent)


def _cleanup_claim(
    claim: _PublicationClaim,
    published: tuple[_FileIdentity, ...],
    staging: tuple[_FileIdentity, ...],
) -> None:
    _assert_claim_owned(claim)
    for identity in (*published, *staging):
        _assert_claim_owned(claim)
        _unlink_recorded_file(identity)
        _assert_claim_owned(claim)
    _fsync_directory(claim.path)
    _fsync_directory(claim.resolved_parent)


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


def read_frozen_candidate(directory: Path) -> tuple[FreezeManifest, ToolAttestation]:
    expected_names = {
        _COMPLETED_MARKER_NAME,
        "freeze-manifest.json",
        "d36-tool-attestation.json",
    }
    try:
        publication = _require_directory(directory, "completed publication")
        publication_identity = _directory_identity(publication)
        if {entry.name for entry in os.scandir(publication)} != expected_names:
            raise ValueError("completed publication entries are invalid")
        marker_identity = _file_identity(publication / _COMPLETED_MARKER_NAME)
        marker = _read_regular_once(
            publication / _COMPLETED_MARKER_NAME,
            maximum=len(_COMPLETED_MARKER_BYTES),
            label="publication completion marker",
        )
        if marker != _COMPLETED_MARKER_BYTES:
            raise ValueError("publication completion marker is invalid")
        manifest_raw = _read_regular_once(
            publication / "freeze-manifest.json",
            maximum=_MAX_FREEZE_MANIFEST_BYTES,
            label="freeze manifest",
        )
        manifest = FreezeManifest.model_validate_json(manifest_raw, strict=True)
        if (
            manifest_raw
            != canonical_json_bytes(manifest.model_dump(mode="json")) + b"\n"
            or publication.name != manifest.candidate_id
        ):
            raise ValueError("freeze manifest is not canonical")
        attestation_raw = _read_regular_once(
            publication / "d36-tool-attestation.json",
            maximum=_MAX_TOOL_ATTESTATION_BYTES,
            label="tool attestation",
        )
        attestation = ToolAttestation.model_validate_json(attestation_raw, strict=True)
        _verify_canonical_attestation(attestation_raw, attestation)
        if (
            _directory_identity(publication) != publication_identity
            or {entry.name for entry in os.scandir(publication)} != expected_names
        ):
            raise ValueError("completed publication entries changed")
        if (
            not _file_identity_matches(marker_identity)
            or _read_regular_once(
                publication / _COMPLETED_MARKER_NAME,
                maximum=len(_COMPLETED_MARKER_BYTES),
                label="publication completion marker",
            )
            != marker
            or not _file_identity_matches(marker_identity)
        ):
            raise ValueError("publication completion marker changed")
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
    root: Path | None = None
    created_root = False
    staging: list[_FileIdentity] = []
    published: list[_FileIdentity] = []
    claimed: _PublicationClaim | None = None
    try:
        root, created_root = _validate_output_root(output_root, candidate, tool_root)
        final = root / manifest.candidate_id
        token = secrets.token_hex(16)
        staged_manifest = root / f".{manifest.candidate_id}.{token}.freeze-manifest.tmp"
        staged_attestation = root / f".{manifest.candidate_id}.{token}.tool-attestation.tmp"
        staging.append(_write_fsynced(staged_manifest, manifest_bytes))
        staging.append(_write_fsynced(staged_attestation, attestation_bytes))
        if _read_regular_once(
            staged_manifest, maximum=len(manifest_bytes), label="staged freeze manifest"
        ) != manifest_bytes:
            raise ValueError("written freeze manifest failed verification")
        staged_tool_bytes = _read_regular_once(
            staged_attestation,
            maximum=len(attestation_bytes),
            label="staged tool attestation",
        )
        _verify_canonical_attestation(staged_tool_bytes, attestation)
        if FreezeManifest.model_validate_json(manifest_bytes, strict=True) != manifest:
            raise ValueError("written freeze manifest failed verification")
        rechecked_commit, rechecked_timestamp = _candidate_identity(candidate, control)
        if rechecked_commit != commit or rechecked_timestamp != timestamp:
            raise ValueError("candidate identity changed during freeze")
        if _snapshot_tree(candidate) != initial_snapshot:
            raise ValueError("candidate changed during freeze")

        try:
            claimed = _claim_publication_directory(final)
        except FileExistsError as exc:
            raise ValueError("output destination already exists") from exc
        _fsync_directory(root)
        published.append(
            _publish_owned(
                claimed, staged_manifest, "freeze-manifest.json", manifest_bytes
            )
        )
        published.append(
            _publish_owned(
                claimed,
                staged_attestation,
                "d36-tool-attestation.json",
                attestation_bytes,
            )
        )
        _fsync_directory(claimed.path)
        _fsync_directory(root)

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
        _finish_claim(claimed)
        claimed = None
        return manifest
    finally:
        if claimed is not None:
            _cleanup_claim(claimed, tuple(published), tuple(staging))
        else:
            for staged in staging:
                _unlink_recorded_file(staged)
        if created_root and root is not None and root.exists():
            try:
                root.rmdir()
            except OSError:
                pass
