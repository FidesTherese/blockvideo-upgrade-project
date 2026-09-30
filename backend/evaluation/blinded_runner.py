"""Crash-safe external D37 blinded evaluator orchestration."""
from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from evaluation.blinded_contracts import (
    EvaluationProtocol,
    case_category_bindings,
    opaque_case_token,
    token_key,
)
from evaluation.blinded_scoring import TrialScore, score_trial
from evaluation.contracts import Case
from evaluation.corpus import load_cases, load_review
from evaluation.release_candidate.freeze import read_frozen_candidate
from evaluation.release_candidate.fingerprints import aggregate_fingerprints
from evaluation.release_candidate.contracts import FreezeManifest
from evaluation.result_contracts import (
    CategoryResult,
    EvaluationResultBundle,
    ExcludedCaseToken,
    ModeResult,
    approval_partition,
)
from evaluation.sealed_evidence import seal_evidence
from evaluation.scripts.evaluation_trial_host import TrialObservation
from evaluation.tool_attestation import (
    FileFingerprint,
    ToolAttestation,
    aggregate_fingerprints as aggregate_tool_fingerprints,
    attest_tool,
    canonical_json_bytes,
    fingerprint_committed_file,
    fingerprint_file,
    validate_git_repository,
)
from evaluation.unlabeled_contracts import (
    UnlabeledTrialCase,
    canonical_case_sha256,
)

_D36_HOST_PATH = "backend/evaluation/scripts/evaluation_trial_host.py"
_D36_SOURCE_PATHS = (
    "backend/evaluation/final_protocol.json",
    "backend/evaluation/release_candidate/__init__.py",
    "backend/evaluation/release_candidate/contracts.py",
    "backend/evaluation/release_candidate/fingerprints.py",
    "backend/evaluation/release_candidate/freeze.py",
    _D36_HOST_PATH,
    "backend/evaluation/scripts/freeze_candidate.py",
    "backend/evaluation/tool_attestation.py",
    "backend/evaluation/unlabeled_contracts.py",
)
_D37_REQUIRED_PATHS = (
    "backend/app/operations/definitions.json",
    "backend/pyproject.toml",
    "backend/scripts/run_blinded_evaluation.py",
    "backend/uv.lock",
)
_PUBLIC_RESULT_NAME = "result-bundle.json"
_PARTIAL_NAME = "partial-result.json"
_PROTOCOL_NAME = "protocol.json"
_REPARSE_POINT = 0x400
_MAX_JSON_BYTES = 16 * 1024 * 1024
_HOST_WATCHDOG_SECONDS = 180 * 4 + 30
_HOST_OUTPUT_CAP_BYTES = 2 * 1024 * 1024
_HOST_PIPE_DRAIN_GRACE_SECONDS = 1.0
_HOST_TEARDOWN_SECONDS = 10.0
_FILE_SHARE_READ = 0x1
_FILE_SHARE_WRITE = 0x2
_GENERIC_READ = 0x80000000
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_DIRECTORY = 0x10
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_TEMP_PATTERN = re.compile(r"^\.(?P<final>[^/\\]+)\.tmp-[0-9a-f]{64}$")
_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MODES = ("all_tools", "stateful")


class _TrialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1]
    protocol_sha256: str
    case_token: str
    category_token: str
    mode: Literal["all_tools", "stateful"]
    outcome: Literal["completed", "transport_failure", "deadline_failure"]
    score: TrialScore | None
    candidate_snapshot_sha256: str | None


@dataclass
class _CandidateAnchor:
    canonical_path: Path
    execution_path: Path
    identity: tuple[int, int]
    descriptor: int | None = None
    handle: int | None = None
    closed: bool = False


class _RunContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    manifest: FreezeManifest
    d36_attestation: ToolAttestation
    d37_attestation: ToolAttestation
    freeze_sha256: str
    tool_root: Path
    candidate_anchor: _CandidateAnchor


def _tool_repo_root() -> Path:
    return Path(__file__).parents[2]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_file_bytes(value: BaseModel | dict[str, object]) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT)


def _validate_directory(path: Path, description: str) -> Path:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISDIR(
        metadata.st_mode
    ):
        raise ValueError(f"{description} must be a non-symlink, non-reparse directory")
    resolved = path.resolve(strict=True)
    if resolved != path.absolute():
        raise ValueError(f"{description} has an unsafe path component")
    return resolved


def _create_directory_tree(path: Path, description: str) -> Path:
    absolute = path.absolute()
    missing: list[str] = []
    current = absolute
    while True:
        try:
            _validate_directory(current, description)
            break
        except FileNotFoundError:
            if current.parent == current:
                raise ValueError(f"{description} has no existing directory ancestor") from None
            missing.append(current.name)
            current = current.parent
    for name in reversed(missing):
        if not name or name in {".", ".."} or Path(name).name != name:
            raise ValueError(f"{description} contains an unsafe component")
        child = current / name
        try:
            child.mkdir()
        except FileExistsError:
            pass
        current = _validate_directory(child, description)
    return _validate_directory(absolute, description)


def _require_directory(path: Path, description: str, *, create: bool = False) -> Path:
    return (
        _create_directory_tree(path, description)
        if create
        else _validate_directory(path.absolute(), description)
    )


def _ensure_writable_directory(root: Path, *parts: str) -> Path:
    current = _validate_directory(root.absolute(), "evaluation output")
    for part in parts:
        if not part or part in {".", ".."} or Path(part).name != part:
            raise ValueError("evaluation output directory component is invalid")
        child = current / part
        try:
            child.mkdir()
        except FileExistsError:
            pass
        current = _validate_directory(child, "evaluation output directory")
    return current


def _read_regular(path: Path, *, maximum: int = _MAX_JSON_BYTES) -> bytes:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISREG(
        metadata.st_mode
    ):
        raise ValueError("input must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_reparse(opened)
            or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
        ):
            raise ValueError("input identity changed")
        value = os.read(descriptor, maximum + 1)
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = path.lstat()
    identities = {
        (metadata.st_dev, metadata.st_ino, metadata.st_size),
        (opened.st_dev, opened.st_ino, opened.st_size),
        (final.st_dev, final.st_ino, final.st_size),
        (after.st_dev, after.st_ino, after.st_size),
    }
    if (
        len(value) > maximum
        or len(value) != opened.st_size
        or len(identities) != 1
        or stat.S_ISLNK(after.st_mode)
        or _is_reparse(after)
        or not stat.S_ISREG(after.st_mode)
    ):
        raise ValueError("input changed or exceeds its size limit")
    return value


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_exclusive(path: Path, value: bytes) -> None:
    _validate_directory(path.parent.absolute(), "exclusive output parent")
    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(value):
            offset += os.write(descriptor, value[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _write_atomic(path: Path, value: bytes) -> None:
    parent = _validate_directory(path.parent.absolute(), "output parent")
    try:
        current = path.lstat()
    except FileNotFoundError:
        current = None
    if current is not None and (
        stat.S_ISLNK(current.st_mode)
        or _is_reparse(current)
        or not stat.S_ISREG(current.st_mode)
    ):
        raise ValueError("output must be a regular non-link file")
    temporary = parent / f".{path.name}.tmp-{secrets.token_hex(32)}"
    descriptor = os.open(
        temporary,
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        offset = 0
        while offset < len(value):
            offset += os.write(descriptor, value[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        _fsync_directory(parent)
        if _read_regular(path, maximum=len(value)) != value:
            raise ValueError("atomic output changed after publication")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _publish_immutable(path: Path, value: bytes, description: str) -> Path:
    parent = _validate_directory(path.parent.absolute(), f"{description} parent")
    if path.parent.absolute() != parent:
        raise ValueError(f"{description} parent identity changed")
    temporary = parent / f".{path.name}.tmp-{secrets.token_hex(32)}"
    flags = (
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(temporary, flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _is_reparse(opened):
            raise ValueError(f"{description} temporary is not a regular file")
        offset = 0
        while offset < len(value):
            offset += os.write(descriptor, value[offset:])
        os.fsync(descriptor)
        final = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino) != (final.st_dev, final.st_ino)
            or final.st_size != len(value)
        ):
            raise ValueError(f"{description} temporary identity changed")
    finally:
        os.close(descriptor)
    try:
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            try:
                existing = _read_regular(path, maximum=len(value))
            except (OSError, ValueError) as error:
                raise ValueError(f"existing {description} is invalid") from error
            if existing != value:
                raise ValueError(
                    f"existing {description} bytes do not match this run"
                ) from None
        else:
            temporary_stat = temporary.lstat()
            published_stat = path.lstat()
            if (
                stat.S_ISLNK(published_stat.st_mode)
                or _is_reparse(published_stat)
                or not stat.S_ISREG(published_stat.st_mode)
                or (temporary_stat.st_dev, temporary_stat.st_ino)
                != (published_stat.st_dev, published_stat.st_ino)
            ):
                raise ValueError(f"{description} publication identity changed")
            _fsync_directory(parent)
        if _read_regular(path, maximum=len(value)) != value:
            raise ValueError(f"{description} bytes changed after publication")
        return path
    finally:
        try:
            metadata = temporary.lstat()
            if stat.S_ISREG(metadata.st_mode) and not _is_reparse(metadata):
                temporary.unlink()
                _fsync_directory(parent)
        except FileNotFoundError:
            pass


def _write_or_validate_immutable(path: Path, expected: bytes, description: str) -> Path:
    return _publish_immutable(path, expected, description)


def write_run_protocol_exclusive(
    output_root: Path, protocol: EvaluationProtocol
) -> Path:
    """Create the canonical protocol once, or validate exact bytes on resume."""
    root = _require_directory(output_root, "evaluation output", create=True)
    path = root / _PROTOCOL_NAME
    expected = _canonical_file_bytes(protocol)
    return _write_or_validate_immutable(path, expected, "protocol")


def _unlabeled_bytes(case: UnlabeledTrialCase) -> bytes:
    return canonical_json_bytes(case.model_dump(mode="json", exclude_unset=True))


def _assert_no_forbidden_wire_keys(value: object) -> None:
    forbidden = {
        "expected",
        "known_limitation",
        "rationale",
        "rule_ids",
        "review",
        "decision",
        "score",
        "labels",
    }
    if isinstance(value, dict):
        if set(value) & forbidden:
            raise ValueError("unlabeled case projection contains private evaluation fields")
        for item in value.values():
            _assert_no_forbidden_wire_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_wire_keys(item)


def _wire_settings(value: dict[str, object]) -> dict[str, object]:
    return {
        "subtitle_font_size": value["subtitle_font_size"],
        "voicevox_speed_scale": value["voicevox_speed_scale"],
        "voicevox_speaker_id": value["voicevox_speaker_id"],
        "pronunciation_overrides": tuple(value["pronunciation_overrides"]),
        "narration_pacing_mode": value["narration_pacing_mode"],
        "narration_sentence_pause_seconds": value[
            "narration_sentence_pause_seconds"
        ],
    }


def _wire_prior_turn(value: dict[str, object]) -> dict[str, object]:
    allowed = {
        "request_id",
        "project_id",
        "base_revision",
        "status",
        "question",
        "result_revision",
        "settings_saved",
        "proposal",
        "text",
        "relation",
        "parent_request_id",
        "successor_request_id",
    }
    turn = {key: item for key, item in value.items() if key in allowed}
    proposal = turn.get("proposal")
    if isinstance(proposal, dict):
        proposal = dict(proposal)
        if proposal.get("kind") == "clarification" and isinstance(
            proposal.get("missing_fields"), list
        ):
            proposal["missing_fields"] = tuple(proposal["missing_fields"])
        arguments = proposal.get("arguments")
        if isinstance(arguments, dict):
            arguments = dict(arguments)
            if isinstance(arguments.get("pronunciation_overrides"), list):
                arguments["pronunciation_overrides"] = tuple(
                    arguments["pronunciation_overrides"]
                )
            settings = arguments.get("settings")
            if isinstance(settings, dict):
                arguments["settings"] = {
                    **settings,
                    **(
                        {
                            "pronunciation_overrides": tuple(
                                settings["pronunciation_overrides"]
                            )
                        }
                        if "pronunciation_overrides" in settings
                        else {}
                    ),
                }
            proposal["arguments"] = arguments
        turn["proposal"] = proposal
    return turn


def case_to_unlabeled(case: Case) -> UnlabeledTrialCase:
    """Project one label-bearing D24 case through an explicit wire allowlist."""
    if case.split != "held_out" or not case.tags:
        raise ValueError("only categorized held-out cases can be projected")
    request = case.request.model_dump(mode="json")
    event: dict[str, object] = {"kind": case.event.kind, "request": request}
    details = case.event.details
    if case.event.kind == "same_id_different_body":
        event.update(
            {
                "replacement_text": details["replacement_text"],
                "replacement_target_project_id": details.get(
                    "replacement_target_project_id"
                ),
            }
        )
    elif case.event.kind == "revision_race":
        event.update(
            {
                "external_revision": details["external_revision"],
                "external_settings": {
                    **details["external_settings"],
                    **(
                        {
                            "pronunciation_overrides": tuple(
                                details["external_settings"]["pronunciation_overrides"]
                            )
                        }
                        if "pronunciation_overrides" in details["external_settings"]
                        else {}
                    ),
                },
            }
        )
    elif case.event.kind == "switch_target":
        event.update(
            {
                "selected_project_id_after": details["selected_project_id_after"],
                "replacement_text": details["replacement_text"],
                "replacement_target_project_id": details[
                    "replacement_target_project_id"
                ],
            }
        )
    initial = {
        "project_id": case.initial.project_id,
        "revision": case.initial.revision,
        "settings": _wire_settings(case.initial.settings),
        "project_status": case.initial.project_status,
        "jobs": tuple(
            {
                **item,
                "input_settings": _wire_settings(item["input_settings"]),
            }
            for item in case.initial.jobs
        ),
        "history": tuple(
            {**item, "settings": _wire_settings(item["settings"])}
            for item in case.initial.history
        ),
        "artifact_revisions": tuple(case.initial.artifact_revisions),
        "prior_turns": tuple(_wire_prior_turn(item) for item in case.initial.prior_turns),
    }
    payload: dict[str, object] = {
        "schema_version": 1,
        "case_id": case.case_id,
        "group_id": case.group_id,
        "category": case.tags[0],
        "split": "held_out",
        "event": event,
        "initial": initial,
    }
    payload["case_sha256"] = canonical_case_sha256(payload)
    projected = UnlabeledTrialCase.model_validate(payload, strict=True)
    serialized = _unlabeled_bytes(projected)
    decoded = json.loads(serialized)
    _assert_no_forbidden_wire_keys(decoded)
    if UnlabeledTrialCase.model_validate_json(serialized, strict=True) != projected:
        raise ValueError("unlabeled case did not survive strict serialization")
    return projected


def _git(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    )
    if completed.returncode != 0:
        raise ValueError("Git identity validation failed")
    return completed.stdout


def _d37_source_paths(root: Path) -> tuple[str, ...]:
    tracked = _git(root, "ls-files", "-z").split(b"\0")
    paths: set[str] = set(_D37_REQUIRED_PATHS)
    for raw in tracked:
        if not raw:
            continue
        try:
            relative = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("tracked source path is not UTF-8") from None
        if (
            relative.startswith("backend/evaluation/")
            and relative.endswith(".py")
        ) or (
            relative.startswith("backend/app/") and relative.endswith(".py")
        ):
            paths.add(relative)
    missing = paths - {
        raw.decode("utf-8") for raw in tracked if raw
    }
    if missing:
        raise ValueError("D37 runtime attestation source is not tracked")
    return tuple(sorted(paths))


_D37_SOURCE_PATHS = tuple(
    sorted(
        {
            *_D37_REQUIRED_PATHS,
            "backend/evaluation/__init__.py",
            "backend/evaluation/blinded_contracts.py",
            "backend/evaluation/blinded_runner.py",
            "backend/evaluation/blinded_scoring.py",
            "backend/evaluation/result_contracts.py",
            "backend/evaluation/sealed_evidence.py",
        }
    )
)


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("read_operation_count", ctypes.c_uint64),
        ("write_operation_count", ctypes.c_uint64),
        ("other_operation_count", ctypes.c_uint64),
        ("read_transfer_count", ctypes.c_uint64),
        ("write_transfer_count", ctypes.c_uint64),
        ("other_transfer_count", ctypes.c_uint64),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("per_process_user_time_limit", ctypes.c_int64),
        ("per_job_user_time_limit", ctypes.c_int64),
        ("limit_flags", ctypes.c_uint32),
        ("minimum_working_set_size", ctypes.c_size_t),
        ("maximum_working_set_size", ctypes.c_size_t),
        ("active_process_limit", ctypes.c_uint32),
        ("affinity", ctypes.c_size_t),
        ("priority_class", ctypes.c_uint32),
        ("scheduling_class", ctypes.c_uint32),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("basic_limit_information", _BasicLimitInformation),
        ("io_info", _IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory_used", ctypes.c_size_t),
        ("peak_job_memory_used", ctypes.c_size_t),
    ]


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("file_attributes", ctypes.c_uint32),
        ("creation_time_low", ctypes.c_uint32),
        ("creation_time_high", ctypes.c_uint32),
        ("last_access_time_low", ctypes.c_uint32),
        ("last_access_time_high", ctypes.c_uint32),
        ("last_write_time_low", ctypes.c_uint32),
        ("last_write_time_high", ctypes.c_uint32),
        ("volume_serial_number", ctypes.c_uint32),
        ("file_size_high", ctypes.c_uint32),
        ("file_size_low", ctypes.c_uint32),
        ("number_of_links", ctypes.c_uint32),
        ("file_index_high", ctypes.c_uint32),
        ("file_index_low", ctypes.c_uint32),
    ]


def _windows_directory_identity(handle: int) -> tuple[int, int]:
    information = _ByHandleFileInformation()
    get_information = ctypes.WinDLL("kernel32", use_last_error=True).GetFileInformationByHandle
    get_information.argtypes = [ctypes.c_void_p, ctypes.POINTER(_ByHandleFileInformation)]
    get_information.restype = ctypes.c_int
    if not get_information(ctypes.c_void_p(handle), ctypes.byref(information)):
        error = ctypes.get_last_error()
        raise OSError(error, "GetFileInformationByHandle failed for candidate directory")
    if (
        not information.file_attributes & _FILE_ATTRIBUTE_DIRECTORY
        or information.file_attributes & _REPARSE_POINT
    ):
        raise ValueError("candidate anchor must be a non-reparse directory")
    file_index = (information.file_index_high << 32) | information.file_index_low
    return information.volume_serial_number, file_index


def _windows_open_candidate_directory(path: Path) -> int:
    create_file = ctypes.WinDLL("kernel32", use_last_error=True).CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    handle = create_file(
        str(path),
        _GENERIC_READ,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        error = ctypes.get_last_error()
        raise OSError(error, "CreateFileW failed for candidate directory")
    return int(handle)


def _windows_close_handle(handle: int) -> None:
    close_handle = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    if not close_handle(ctypes.c_void_p(handle)):
        error = ctypes.get_last_error()
        raise OSError(error, "CloseHandle failed for candidate directory")


def _open_candidate_anchor(candidate_root: Path) -> _CandidateAnchor:
    canonical = _canonical_candidate_root(candidate_root)
    if os.name == "nt":
        handle = _windows_open_candidate_directory(canonical)
        try:
            identity = _windows_directory_identity(handle)
        except BaseException:
            _windows_close_handle(handle)
            raise
        return _CandidateAnchor(
            canonical_path=canonical,
            execution_path=canonical,
            identity=identity,
            handle=handle,
        )
    if os.name != "posix" or not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("candidate directory anchoring is unsupported on this platform")
    descriptor = os.open(canonical, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(metadata):
            raise ValueError("candidate anchor must be a non-reparse directory")
        execution = Path(f"/proc/{os.getpid()}/fd/{descriptor}")
        if not execution.exists() or execution.resolve(strict=True) != canonical:
            raise ValueError("stable candidate fd path is unavailable on this POSIX host")
        return _CandidateAnchor(
            canonical_path=canonical,
            execution_path=execution,
            identity=(metadata.st_dev, metadata.st_ino),
            descriptor=descriptor,
        )
    except BaseException:
        os.close(descriptor)
        raise


def _close_candidate_anchor(anchor: _CandidateAnchor) -> None:
    if anchor.closed:
        return
    anchor.closed = True
    if anchor.handle is not None:
        handle = anchor.handle
        anchor.handle = None
        _windows_close_handle(handle)
    if anchor.descriptor is not None:
        descriptor = anchor.descriptor
        anchor.descriptor = None
        os.close(descriptor)


def _candidate_path_identity(path: Path) -> tuple[int, int]:
    if os.name == "nt":
        handle = _windows_open_candidate_directory(path)
        try:
            return _windows_directory_identity(handle)
        finally:
            _windows_close_handle(handle)
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISDIR(
        metadata.st_mode
    ):
        raise ValueError("candidate root must remain a non-link directory")
    return metadata.st_dev, metadata.st_ino


def _assert_candidate_anchor(anchor: _CandidateAnchor) -> None:
    if anchor.closed:
        raise ValueError("candidate directory anchor is closed")
    if anchor.handle is not None:
        retained = _windows_directory_identity(anchor.handle)
    elif anchor.descriptor is not None:
        metadata = os.fstat(anchor.descriptor)
        if not stat.S_ISDIR(metadata.st_mode) or _is_reparse(metadata):
            raise ValueError("candidate directory anchor changed type")
        retained = metadata.st_dev, metadata.st_ino
    else:
        raise ValueError("candidate directory anchor is unavailable")
    if retained != anchor.identity or _candidate_path_identity(anchor.canonical_path) != anchor.identity:
        raise ValueError("candidate directory identity changed during evaluation")


def _canonical_candidate_root(candidate_root: Path) -> Path:
    supplied = candidate_root.absolute()
    metadata = supplied.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISDIR(
        metadata.st_mode
    ):
        raise ValueError("candidate root must be a non-link directory")
    resolved = supplied.resolve(strict=True)
    if resolved != supplied:
        raise ValueError("candidate root contains an unsafe path component")
    backend = resolved / "backend"
    _validate_directory(backend, "candidate backend")
    return resolved


def _validate_candidate(candidate_root: Path, manifest: Any) -> None:
    root = _canonical_candidate_root(candidate_root)
    if _git(root, "branch", "--show-current").strip():
        raise ValueError("candidate must be a detached checkout")
    commit = validate_git_repository(root, expected_commit=manifest.git_commit)
    actual = [fingerprint_committed_file(root, commit, item.path) for item in manifest.files]
    if actual != manifest.files or aggregate_fingerprints(actual) != manifest.aggregate_sha256:
        raise ValueError("candidate bytes do not match the frozen manifest")
    validate_git_repository(root, expected_commit=manifest.git_commit)


def _verify_tool_sources(root: Path, attestation: ToolAttestation) -> None:
    if not attestation.files:
        raise ValueError("tool attestation is empty")
    _git(root, "cat-file", "-e", f"{attestation.git_commit}^{{commit}}")
    actual = [fingerprint_file(root, item.path) for item in attestation.files]
    if actual != attestation.files or aggregate_tool_fingerprints(actual) != (
        attestation.aggregate_sha256
    ):
        raise ValueError("tool source bytes do not match their attestation")
    for item in attestation.files:
        committed = _git(root, "show", f"{attestation.git_commit}:{item.path}")
        if len(committed) != item.size or _sha256_bytes(committed) != item.sha256:
            raise ValueError("tool attestation does not match its declared commit")


def _load_run_context(
    candidate_root: Path,
    freeze_manifest: Path,
    candidate_anchor: _CandidateAnchor,
) -> _RunContext:
    if freeze_manifest.name != "freeze-manifest.json":
        raise ValueError("freeze manifest must belong to a completed D36 publication")
    publication = freeze_manifest.parent
    manifest, d36_attestation = read_frozen_candidate(publication)
    if freeze_manifest.resolve(strict=True) != (
        publication.resolve(strict=True) / "freeze-manifest.json"
    ):
        raise ValueError("freeze manifest path is invalid")
    raw = _read_regular(freeze_manifest)
    expected_raw = _canonical_file_bytes(manifest)
    if raw != expected_raw:
        raise ValueError("freeze manifest bytes are not canonical")
    if d36_attestation.tool_name != "d36_candidate_freezer_and_trial_host":
        raise ValueError("D36 trial tool attestation has the wrong identity")
    if tuple(item.path for item in d36_attestation.files) != _D36_SOURCE_PATHS:
        raise ValueError("D36 trial tool attestation has the wrong source allowlist")
    tool_root = _tool_repo_root().resolve(strict=True)
    _verify_tool_sources(tool_root, d36_attestation)
    tool_commit = validate_git_repository(tool_root)
    d37_attestation = attest_tool(
        repo_root=tool_root,
        tool_name="d37_blinded_evaluator",
        git_commit=tool_commit,
        source_paths=_d37_source_paths(tool_root),
    )
    _assert_candidate_anchor(candidate_anchor)
    _validate_candidate(candidate_root, manifest)
    _assert_candidate_anchor(candidate_anchor)
    return _RunContext(
        manifest=manifest,
        d36_attestation=d36_attestation,
        d37_attestation=d37_attestation,
        freeze_sha256=_sha256_bytes(raw),
        tool_root=tool_root,
        candidate_anchor=candidate_anchor,
    )


def _validate_run_context(
    candidate_root: Path, freeze_manifest: Path, expected: _RunContext
) -> None:
    try:
        _assert_candidate_anchor(expected.candidate_anchor)
        current = _load_run_context(
            candidate_root, freeze_manifest, expected.candidate_anchor
        )
        _assert_candidate_anchor(expected.candidate_anchor)
    except (OSError, ValueError) as error:
        raise ValueError(
            "candidate, freeze, or tool identity changed during evaluation"
        ) from error
    if (
        current.manifest != expected.manifest
        or current.d36_attestation != expected.d36_attestation
        or current.d37_attestation != expected.d37_attestation
        or current.freeze_sha256 != expected.freeze_sha256
    ):
        raise ValueError("candidate, freeze, or tool identity changed during evaluation")


def _fingerprint_directory(root: Path) -> str:
    directory = _require_directory(root, "stateful index")
    files: list[FileFingerprint] = []
    for current, directories, names in os.walk(directory, topdown=True, followlinks=False):
        current_path = Path(current)
        _require_directory(current_path, "stateful index directory")
        for name in sorted(directories):
            _require_directory(current_path / name, "stateful index directory")
        directories.sort()
        for name in sorted(names):
            path = current_path / name
            relative = path.relative_to(directory).as_posix()
            PurePosixPath(relative)
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISREG(
                metadata.st_mode
            ):
                raise ValueError("stateful index contains a non-regular entry")
            content = _read_regular(path)
            files.append(
                FileFingerprint(
                    path=relative, sha256=_sha256_bytes(content), size=len(content)
                )
            )
    if not files:
        raise ValueError("stateful index must contain at least one regular file")
    return aggregate_tool_fingerprints(files)


def _model_configuration_sha256(model: str) -> str:
    if not model or model != model.strip() or len(model) > 256:
        raise ValueError("model identifier is invalid")
    return _sha256_bytes(canonical_json_bytes({"model": model}))


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return False
    return True


def _paths_overlap(left: Path, right: Path) -> bool:
    return _path_is_within(left, right) or _path_is_within(right, left)


def _validate_output_location(output_root: Path, protected_roots: tuple[Path, ...]) -> Path:
    output = output_root.absolute().resolve(strict=False)
    for protected in protected_roots:
        if _paths_overlap(output, protected):
            raise ValueError("evaluation output overlaps a protected root")
    return output


def _validate_run_artifacts(
    root: Path, protocol_raw: bytes, tool_attestation_raw: bytes
) -> None:
    if _read_regular(root / _PROTOCOL_NAME, maximum=len(protocol_raw)) != protocol_raw:
        raise ValueError("immutable protocol changed during evaluation")
    if _read_regular(
        root / "tool-attestation.json", maximum=len(tool_attestation_raw)
    ) != tool_attestation_raw:
        raise ValueError("immutable D37 tool attestation changed during evaluation")


def _partial_payload(
    case_tokens: tuple[str, ...], records: list[_TrialRecord], active: str | None
) -> dict[str, object]:
    by_case: dict[str, list[_TrialRecord]] = defaultdict(list)
    for record in records:
        by_case[record.case_token].append(record)
    completed = sorted(
        token
        for token, items in by_case.items()
        if len(items) == 2 and all(item.outcome == "completed" for item in items)
    )
    failed = sorted(
        token
        for token, items in by_case.items()
        if len(items) == 2 and any(item.outcome != "completed" for item in items)
    )
    started = sorted(
        token
        for token, items in by_case.items()
        if token not in completed and token not in failed and items
    )
    if active is not None and active not in completed and active not in failed:
        started = sorted(set(started) | {active})
    remaining = sorted(set(case_tokens) - set(completed) - set(failed) - set(started))
    return {
        "schema_version": 1,
        "started_case_tokens": started,
        "completed_case_tokens": completed,
        "failed_case_tokens": failed,
        "remaining_case_tokens": remaining,
    }


def _write_partial(
    root: Path,
    case_tokens: tuple[str, ...],
    records: list[_TrialRecord],
    active: str | None = None,
) -> None:
    _write_atomic(
        root / _PARTIAL_NAME,
        _canonical_file_bytes(_partial_payload(case_tokens, records, active)),
    )


def _record_path(root: Path, group_ordinal: int, case_token: str, mode: str) -> Path:
    return (
        root
        / "groups"
        / f"{group_ordinal:06d}"
        / "cases"
        / case_token
        / mode
        / "trial-result.json"
    )


def _load_trial_record(path: Path, protocol_sha256: str) -> _TrialRecord:
    raw = _read_regular(path)
    record = _TrialRecord.model_validate_json(raw, strict=True)
    if raw != _canonical_file_bytes(record) or record.protocol_sha256 != protocol_sha256:
        raise ValueError("completed trial record is invalid")
    return record


def _safe_directory_entries(path: Path, description: str) -> list[os.DirEntry[str]]:
    _validate_directory(path.absolute(), description)
    entries = sorted(os.scandir(path), key=lambda entry: entry.name)
    for entry in entries:
        metadata = entry.stat(follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ValueError(f"{description} contains an unsafe entry")
    return entries


def _is_valid_interrupted_temp(entry: os.DirEntry[str]) -> bool:
    match = _TEMP_PATTERN.fullmatch(entry.name)
    if match is None:
        return False
    metadata = entry.stat(follow_symlinks=False)
    return stat.S_ISREG(metadata.st_mode) and not _is_reparse(metadata)


def _load_records(root: Path, protocol_sha256: str) -> list[_TrialRecord]:
    root = _validate_directory(root.absolute(), "evaluation output")
    groups = root / "groups"
    try:
        group_entries = _safe_directory_entries(groups, "trial groups")
    except FileNotFoundError:
        return []
    paths: list[Path] = []
    for group in group_entries:
        metadata = group.stat(follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode) or not re.fullmatch(r"[0-9]{6}", group.name):
            raise ValueError("trial groups contain an invalid entry")
        cases = Path(group.path) / "cases"
        for case in _safe_directory_entries(cases, "trial cases"):
            metadata = case.stat(follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode) or _TOKEN_PATTERN.fullmatch(case.name) is None:
                raise ValueError("trial cases contain an invalid entry")
            for mode in _safe_directory_entries(Path(case.path), "trial modes"):
                metadata = mode.stat(follow_symlinks=False)
                if not stat.S_ISDIR(metadata.st_mode) or mode.name not in _MODES:
                    raise ValueError("trial modes contain an invalid entry")
                for child in _safe_directory_entries(Path(mode.path), "trial mode"):
                    child_metadata = child.stat(follow_symlinks=False)
                    if child.name == "trial-result.json":
                        if not stat.S_ISREG(child_metadata.st_mode):
                            raise ValueError("completed trial record is not regular")
                        paths.append(Path(child.path))
                    elif child.name in {"input.json", "attempts"}:
                        expected_directory = child.name == "attempts"
                        if expected_directory != stat.S_ISDIR(child_metadata.st_mode):
                            raise ValueError("trial mode entry has the wrong type")
                    elif not _is_valid_interrupted_temp(child):
                        raise ValueError("trial mode contains an invalid entry")
    records = [_load_trial_record(path, protocol_sha256) for path in paths]
    identities = {(record.case_token, record.mode) for record in records}
    if len(identities) != len(records):
        raise ValueError("duplicate completed trial records")
    return records


def _next_attempt(mode_root: Path) -> Path:
    root = _validate_directory(mode_root.absolute(), "trial mode")
    attempts = _ensure_writable_directory(root, "attempts")
    existing = []
    for entry in _safe_directory_entries(attempts, "trial attempts"):
        metadata = entry.stat(follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode) or not re.fullmatch(r"[0-9]{6}", entry.name):
            raise ValueError("trial attempts contain an invalid entry")
        existing.append(int(entry.name))
    name = f"{max(existing, default=0) + 1:06d}"
    return _ensure_writable_directory(attempts, name)


def _clean_subprocess_environment(tool_root: Path) -> dict[str, str]:
    retained = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    environment = {name: os.environ[name] for name in retained if name in os.environ}
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(tool_root / "backend"),
        }
    )
    return environment


def _open_exclusive_regular(path: Path, description: str) -> int:
    _validate_directory(path.parent.absolute(), f"{description} parent")
    descriptor = os.open(
        path,
        os.O_CREAT
        | os.O_EXCL
        | os.O_WRONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or _is_reparse(metadata):
        os.close(descriptor)
        raise ValueError(f"{description} must be a regular file")
    return descriptor


async def _bounded_stream(
    stream: asyncio.StreamReader,
    descriptor: int,
    overflow: asyncio.Event,
    budget: list[int],
    budget_lock: asyncio.Lock,
) -> None:
    try:
        while chunk := await stream.read(65536):
            async with budget_lock:
                remaining = _HOST_OUTPUT_CAP_BYTES - budget[0]
                written = chunk[: max(0, remaining)]
                budget[0] += len(written)
                if len(chunk) > remaining:
                    overflow.set()
            offset = 0
            while offset < len(written):
                offset += os.write(descriptor, written[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _attach_windows_job(process: asyncio.subprocess.Process) -> None:
    if os.name != "nt":
        return
    create_job = ctypes.WinDLL("kernel32", use_last_error=True).CreateJobObjectW
    create_job.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    create_job.restype = ctypes.c_void_p
    job = create_job(None, None)
    invalid_handle = ctypes.c_void_p(-1).value
    if job in (None, invalid_handle):
        error = ctypes.get_last_error()
        raise OSError(error, "CreateJobObjectW failed for trial host")
    job_handle = int(job)
    try:
        information = _ExtendedLimitInformation()
        information.basic_limit_information.limit_flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        set_information = ctypes.WinDLL(
            "kernel32", use_last_error=True
        ).SetInformationJobObject
        set_information.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        set_information.restype = ctypes.c_int
        if not set_information(
            ctypes.c_void_p(job_handle),
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            error = ctypes.get_last_error()
            raise OSError(error, "SetInformationJobObject failed for trial host")
        open_process = ctypes.WinDLL("kernel32", use_last_error=True).OpenProcess
        open_process.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        open_process.restype = ctypes.c_void_p
        process_handle = open_process(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, 0, process.pid
        )
        if process_handle in (None, invalid_handle):
            error = ctypes.get_last_error()
            raise OSError(error, "OpenProcess failed for trial host")
        try:
            assign = ctypes.WinDLL(
                "kernel32", use_last_error=True
            ).AssignProcessToJobObject
            assign.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            assign.restype = ctypes.c_int
            if not assign(
                ctypes.c_void_p(job_handle), ctypes.c_void_p(process_handle)
            ):
                error = ctypes.get_last_error()
                raise OSError(error, "AssignProcessToJobObject failed for trial host")
        finally:
            _windows_close_handle(int(process_handle))
        setattr(process, "_d37_job_handle", job_handle)
    except BaseException:
        _windows_close_handle(job_handle)
        raise


async def _release_windows_bootstrap(process: asyncio.subprocess.Process) -> None:
    if os.name != "nt":
        return
    if process.stdin is None:
        raise ValueError("trial host bootstrap pipe is unavailable")
    process.stdin.write(b"1")
    await process.stdin.drain()
    process.stdin.close()
    await process.stdin.wait_closed()


def _close_windows_job(process: asyncio.subprocess.Process) -> None:
    handle = getattr(process, "_d37_job_handle", None)
    if handle is None:
        return
    setattr(process, "_d37_job_handle", None)
    _windows_close_handle(handle)


async def _wait_for_parent_exit(process: asyncio.subprocess.Process) -> int:
    while process.returncode is None:
        await asyncio.sleep(0.01)
    return process.returncode


async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
    if os.name == "nt" and getattr(process, "_d37_job_handle", None) is not None:
        _close_windows_job(process)
    elif os.name == "nt" and hasattr(process, "pid") and process.returncode is None:
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    elif os.name == "posix" and hasattr(process, "pid"):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.returncode is None:
        process.kill()
    try:
        await asyncio.wait_for(process.wait(), timeout=_HOST_TEARDOWN_SECONDS)
    except TimeoutError:
        if process.returncode is None:
            process.kill()
        raise ValueError("trial host process teardown could not be confirmed") from None


async def _invoke_trial_host(
    *,
    tool_root: Path,
    candidate_root: Path,
    mode: str,
    input_path: Path,
    output_path: Path,
    storage: Path,
    model: str,
    index: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> str:
    arguments = [
        sys.executable,
        "-B",
        "-m",
        "evaluation.scripts.evaluation_trial_host",
        "--candidate-root",
        str(candidate_root),
        "--mode",
        mode,
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--storage",
        str(storage),
        "--model",
        model,
    ]
    if mode == "stateful":
        arguments.extend(("--index", str(index)))
    process_options: dict[str, object] = {}
    launch_arguments = arguments
    process_stdin: int = asyncio.subprocess.DEVNULL
    if os.name == "posix":
        process_options["start_new_session"] = True
    elif os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        bootstrap = (
            "import subprocess,sys; "
            "ready=sys.stdin.buffer.read(1); "
            "raise SystemExit(125) if ready != b'1' else "
            "SystemExit(subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL))"
        )
        launch_arguments = [sys.executable, "-B", "-c", bootstrap, *arguments]
        process_stdin = asyncio.subprocess.PIPE
    stdout_descriptor = _open_exclusive_regular(stdout_path, "trial stdout")
    try:
        stderr_descriptor = _open_exclusive_regular(stderr_path, "trial stderr")
    except BaseException:
        os.close(stdout_descriptor)
        raise
    try:
        process = await asyncio.create_subprocess_exec(
            *launch_arguments,
            cwd=tool_root / "backend",
            env=_clean_subprocess_environment(tool_root),
            stdin=process_stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **process_options,
        )
        _attach_windows_job(process)
        await _release_windows_bootstrap(process)
    except BaseException:
        if "process" in locals():
            if getattr(process, "_d37_job_handle", None) is not None:
                _close_windows_job(process)
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        os.close(stdout_descriptor)
        os.close(stderr_descriptor)
        raise
    if process.stdout is None or process.stderr is None:
        os.close(stdout_descriptor)
        os.close(stderr_descriptor)
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise ValueError("trial host output pipes are unavailable")
    overflow = asyncio.Event()
    budget = [0]
    budget_lock = asyncio.Lock()
    readers = (
        asyncio.create_task(
            _bounded_stream(
                process.stdout, stdout_descriptor, overflow, budget, budget_lock
            )
        ),
        asyncio.create_task(
            _bounded_stream(
                process.stderr, stderr_descriptor, overflow, budget, budget_lock
            )
        ),
    )
    wait_task = asyncio.create_task(_wait_for_parent_exit(process))
    overflow_task = asyncio.create_task(overflow.wait())
    outcome: str
    try:
        done, _ = await asyncio.wait(
            (wait_task, overflow_task),
            timeout=_HOST_WATCHDOG_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            outcome = "deadline_failure"
        elif overflow_task in done and overflow.is_set():
            outcome = "transport_failure"
        else:
            await wait_task
            outcome = "completed" if process.returncode == 0 else "transport_failure"
            _, pending_readers = await asyncio.wait(
                readers, timeout=_HOST_PIPE_DRAIN_GRACE_SECONDS
            )
            if not pending_readers:
                await asyncio.gather(*readers, return_exceptions=False)
        await _terminate_process_tree(process)
        try:
            await asyncio.wait_for(
                asyncio.gather(*readers, return_exceptions=False),
                timeout=_HOST_TEARDOWN_SECONDS,
            )
        except TimeoutError:
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            raise ValueError("trial host pipe teardown could not be confirmed") from None
        return outcome
    except BaseException:
        await _terminate_process_tree(process)
        try:
            await asyncio.wait_for(
                asyncio.gather(*readers, return_exceptions=True),
                timeout=_HOST_TEARDOWN_SECONDS,
            )
        except TimeoutError:
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            raise ValueError("trial host teardown could not be confirmed") from None
        raise
    finally:
        overflow_task.cancel()
        await asyncio.gather(overflow_task, return_exceptions=True)


def _observation(path: Path) -> tuple[TrialObservation, bytes]:
    raw = _read_regular(path)
    observation = TrialObservation.model_validate_json(raw, strict=True)
    if raw != _canonical_file_bytes(observation):
        raise ValueError("trial observation is not canonical")
    return observation, raw


async def _run_trial(
    *,
    root: Path,
    group_ordinal: int,
    case: Case,
    case_token: str,
    category_token: str,
    mode: str,
    protocol_sha256: str,
    context: _RunContext,
    candidate_root: Path,
    freeze_manifest: Path,
    model: str,
    index: Path,
    index_sha256: str,
) -> _TrialRecord:
    mode_root = _ensure_writable_directory(
        root,
        "groups",
        f"{group_ordinal:06d}",
        "cases",
        case_token,
        mode,
    )
    record_path = mode_root / "trial-result.json"
    try:
        record_path.lstat()
        record_exists = True
    except FileNotFoundError:
        record_exists = False
    if record_exists:
        record = _load_trial_record(record_path, protocol_sha256)
        if (
            record.case_token != case_token
            or record.category_token != category_token
            or record.mode != mode
        ):
            raise ValueError("completed trial record does not match its path")
        return record

    projected = case_to_unlabeled(case)
    input_raw = _unlabeled_bytes(projected) + b"\n"
    input_path = mode_root / "input.json"
    try:
        _write_exclusive(input_path, input_raw)
    except FileExistsError:
        if _read_regular(input_path, maximum=len(input_raw)) != input_raw:
            raise ValueError("existing unlabeled trial input changed") from None

    attempt = _next_attempt(mode_root)
    output_path = attempt / "observation.json"
    _validate_run_context(candidate_root, freeze_manifest, context)
    if _fingerprint_directory(index) != index_sha256:
        raise ValueError("stateful index changed before trial execution")
    outcome: Literal["completed", "transport_failure", "deadline_failure"]
    try:
        outcome = await _invoke_trial_host(
            tool_root=context.tool_root,
            candidate_root=context.candidate_anchor.execution_path,
            mode=mode,
            input_path=input_path,
            output_path=output_path,
            storage=attempt / "storage",
            model=model,
            index=index,
            stdout_path=attempt / "stdout.log",
            stderr_path=attempt / "stderr.log",
        )
    finally:
        _validate_run_context(candidate_root, freeze_manifest, context)
        if _fingerprint_directory(index) != index_sha256:
            raise ValueError("stateful index changed during trial execution")

    storage_path = attempt / "storage"
    try:
        storage_path.lstat()
    except FileNotFoundError:
        pass
    else:
        _validate_directory(storage_path, "trial storage")
    score: TrialScore | None = None
    candidate_snapshot: str | None = None
    if outcome == "completed":
        try:
            observation, _ = _observation(output_path)
            if observation.mode != mode or observation.case_sha256 != projected.case_sha256:
                raise ValueError("trial observation does not match its invocation")
            score = score_trial(case, observation.model_dump(mode="json"))
            candidate_snapshot = observation.candidate_snapshot_sha256
        except (OSError, ValidationError, ValueError):
            outcome = "transport_failure"
    record = _TrialRecord(
        schema_version=1,
        protocol_sha256=protocol_sha256,
        case_token=case_token,
        category_token=category_token,
        mode=mode,
        outcome=outcome,
        score=score,
        candidate_snapshot_sha256=candidate_snapshot,
    )
    _publish_immutable(record_path, _canonical_file_bytes(record), "trial result")
    return record


def _mode_result(
    mode: str,
    records: list[_TrialRecord],
    category_tokens: tuple[str, ...],
    denominators: dict[str, int],
) -> ModeResult:
    selected = [record for record in records if record.mode == mode]

    def counts(items: list[_TrialRecord]) -> dict[str, int]:
        completed = [item for item in items if item.outcome == "completed"]
        return {
            "included": len(items),
            "completed": len(completed),
            "task_complete": sum(item.score is not None and item.score.task_complete for item in completed),
            "unauthorized_effects": sum(
                item.score is not None and item.score.unauthorized_effect for item in completed
            ),
            "unauthorized_replays": sum(
                item.score is not None and item.score.unauthorized_replay for item in completed
            ),
            "secret_disclosures": sum(
                item.score is not None and item.score.secret_disclosure for item in completed
            ),
        }

    categories = []
    for token in category_tokens:
        values = counts([item for item in selected if item.category_token == token])
        if values["included"] != denominators[token]:
            raise ValueError("trial records do not cover the exact category topology")
        categories.append(CategoryResult(category_token=token, **values))
    values = counts(selected)
    return ModeResult(
        mode=mode,
        **values,
        transport_failures=sum(item.outcome == "transport_failure" for item in selected),
        deadline_failures=sum(item.outcome == "deadline_failure" for item in selected),
        categories=tuple(categories),
    )


def _validate_existing_bundle(
    root: Path,
    protocol: EvaluationProtocol,
    protocol_sha256: str,
    context: _RunContext,
    included: tuple[str, ...],
    excluded: tuple[ExcludedCaseToken, ...],
    evaluator_name: str,
) -> EvaluationResultBundle | None:
    path = root / _PUBLIC_RESULT_NAME
    if not path.exists():
        return None
    raw = _read_regular(path)
    bundle = EvaluationResultBundle.model_validate_json(raw, strict=True)
    if raw != _canonical_file_bytes(bundle):
        raise ValueError("existing result bundle is not canonical")
    if (
        bundle.protocol_sha256 != protocol_sha256
        or bundle.candidate_id != protocol.candidate_id
        or bundle.freeze_sha256 != protocol.freeze_sha256
        or bundle.corpus_sha256 != protocol.corpus_sha256
        or bundle.human_approval_sha256 != protocol.human_approval_sha256
        or bundle.independent_approval_sha256 != protocol.independent_approval_sha256
        or bundle.d36_trial_tool_sha256 != context.d36_attestation.aggregate_sha256
        or bundle.d37_evaluator_tool_sha256 != context.d37_attestation.aggregate_sha256
        or bundle.protocol_case_count != protocol.case_count
        or bundle.protocol_case_tokens != protocol.case_tokens
        or bundle.protocol_category_count != protocol.category_count
        or bundle.protocol_category_tokens != protocol.category_tokens
        or bundle.case_categories != protocol.case_categories
        or bundle.included_case_tokens != included
        or bundle.excluded_cases != excluded
        or bundle.evaluator_name != evaluator_name
    ):
        raise ValueError("existing result bundle does not match this run")
    _, sealed = seal_evidence(root)
    if sealed != bundle.sealed_evidence_sha256:
        raise ValueError("existing result bundle detailed evidence changed")
    return bundle


async def _run_blinded_evaluation_anchored(
    *,
    candidate_root: Path,
    freeze_manifest: Path,
    corpus: Path,
    human_review: Path,
    independent_review: Path,
    output_root: Path,
    model: str,
    index: Path,
    evaluator_name: str,
    token_key_file: Path,
    context: _RunContext,
) -> EvaluationResultBundle:
    protected_roots = (
        candidate_root,
        context.tool_root,
        freeze_manifest.parent.resolve(strict=True),
        corpus.parent.resolve(strict=True),
        human_review.parent.resolve(strict=True),
        independent_review.parent.resolve(strict=True),
        index.resolve(strict=True),
        token_key_file.parent.resolve(strict=True),
    )
    expected_output = _validate_output_location(output_root, protected_roots)
    output = _require_directory(output_root, "evaluation output", create=True)
    if output != expected_output:
        raise ValueError("evaluation output changed while creating its root")

    corpus_raw = _read_regular(corpus)
    human_raw = _read_regular(human_review)
    independent_raw = _read_regular(independent_review)
    cases = load_cases(corpus)
    if _read_regular(corpus) != corpus_raw:
        raise ValueError("evaluation corpus changed while loading")
    if any(case.split != "held_out" for case in cases):
        raise ValueError("evaluation corpus must contain held-out cases only")
    human = load_review(human_review, cases, "human")
    if _read_regular(human_review) != human_raw:
        raise ValueError("human review changed while loading")
    independent = load_review(independent_review, cases, "independent_ai")
    if _read_regular(independent_review) != independent_raw:
        raise ValueError("independent review changed while loading")
    index_sha256 = _fingerprint_directory(index)
    model_sha256 = _model_configuration_sha256(model)

    with token_key(token_key_file) as key:
        bindings = case_category_bindings(cases, key)
        included, excluded = approval_partition(cases, human, independent, key)
        token_by_id = {
            case.case_id: opaque_case_token(key, case.case_id) for case in cases
        }
    case_tokens = tuple(binding.case_token for binding in bindings)
    category_tokens = tuple(sorted({binding.category_token for binding in bindings}))
    protocol = EvaluationProtocol(
        schema_version=1,
        candidate_id=context.manifest.candidate_id,
        modes=_MODES,
        per_call_deadline_seconds=180,
        maximum_model_calls=4,
        isolation="fresh_case_state_under_source_group",
        corpus_sha256=_sha256_bytes(corpus_raw),
        human_approval_sha256=_sha256_bytes(human_raw),
        independent_approval_sha256=_sha256_bytes(independent_raw),
        freeze_sha256=context.freeze_sha256,
        d36_trial_tool_sha256=context.d36_attestation.aggregate_sha256,
        d37_evaluator_tool_sha256=context.d37_attestation.aggregate_sha256,
        model_configuration_sha256=model_sha256,
        stateful_index_sha256=index_sha256,
        category_count=len(category_tokens),
        category_tokens=category_tokens,
        case_count=len(case_tokens),
        case_tokens=case_tokens,
        case_categories=bindings,
    )
    d37_attestation_raw = _canonical_file_bytes(context.d37_attestation)
    _write_or_validate_immutable(
        output / "tool-attestation.json",
        d37_attestation_raw,
        "D37 tool attestation",
    )
    protocol_path = write_run_protocol_exclusive(output, protocol)
    protocol_raw = _read_regular(protocol_path)
    protocol_sha256 = _sha256_bytes(protocol_raw)
    _validate_run_artifacts(output, protocol_raw, d37_attestation_raw)
    existing_bundle = _validate_existing_bundle(
        output,
        protocol,
        protocol_sha256,
        context,
        included,
        excluded,
        evaluator_name,
    )
    if existing_bundle is not None:
        _validate_run_context(candidate_root, freeze_manifest, context)
        return existing_bundle

    included_set = set(included)
    binding_by_token = {item.case_token: item.category_token for item in bindings}
    denominators = {
        category: sum(
            token in included_set and binding_by_token[token] == category
            for token in case_tokens
        )
        for category in category_tokens
    }
    if not included or any(value < 1 for value in denominators.values()):
        raise ValueError("approved evaluation coverage must be non-empty in every category")

    case_by_token = {token_by_id[case.case_id]: case for case in cases}
    if set(case_by_token) != set(case_tokens):
        raise ValueError("case/token topology could not be reconstructed")

    group_ordinals = {
        group: index + 1
        for index, group in enumerate(sorted({case.group_id for case in cases}))
    }
    ordered_cases = sorted(
        (case_by_token[token] for token in included),
        key=lambda case: (case.group_id, case.case_id),
    )
    records = _load_records(output, protocol_sha256)
    expected_trials = {(token, mode) for token in included for mode in _MODES}
    if {(record.case_token, record.mode) for record in records} - expected_trials:
        raise ValueError("partial records do not belong to the approved protocol")
    _write_partial(output, included, records)

    for case_index, case in enumerate(ordered_cases):
        case_token = token_by_id[case.case_id]
        category_token = binding_by_token[case_token]
        mode_order = _MODES if case_index % 2 == 0 else tuple(reversed(_MODES))
        for mode in mode_order:
            active = case_token
            _validate_run_artifacts(output, protocol_raw, d37_attestation_raw)
            _write_partial(output, included, records, active)
            try:
                record = await _run_trial(
                    root=output,
                    group_ordinal=group_ordinals[case.group_id],
                    case=case,
                    case_token=case_token,
                    category_token=category_token,
                    mode=mode,
                    protocol_sha256=protocol_sha256,
                    context=context,
                    candidate_root=candidate_root,
                    freeze_manifest=freeze_manifest,
                    model=model,
                    index=index,
                    index_sha256=index_sha256,
                )
                records = [
                    item
                    for item in records
                    if (item.case_token, item.mode) != (case_token, mode)
                ] + [record]
                records.sort(key=lambda item: (item.case_token, item.mode))
                _validate_run_artifacts(output, protocol_raw, d37_attestation_raw)
                _write_partial(output, included, records)
            except BaseException:
                _validate_run_artifacts(output, protocol_raw, d37_attestation_raw)
                _write_partial(output, included, records, active)
                raise

    if {(record.case_token, record.mode) for record in records} != expected_trials:
        raise ValueError("trial records do not exactly cover the approved protocol")
    snapshots = {
        record.candidate_snapshot_sha256
        for record in records
        if record.candidate_snapshot_sha256 is not None
    }
    if len(snapshots) > 1:
        raise ValueError("candidate trial snapshots differ across runs")
    _validate_run_context(candidate_root, freeze_manifest, context)
    _validate_run_artifacts(output, protocol_raw, d37_attestation_raw)
    _, sealed_sha256 = seal_evidence(output)
    modes = tuple(
        _mode_result(mode, records, category_tokens, denominators) for mode in _MODES
    )
    bundle = EvaluationResultBundle(
        schema_version=1,
        candidate_id=protocol.candidate_id,
        freeze_sha256=protocol.freeze_sha256,
        corpus_sha256=protocol.corpus_sha256,
        human_approval_sha256=protocol.human_approval_sha256,
        independent_approval_sha256=protocol.independent_approval_sha256,
        protocol_sha256=protocol_sha256,
        d36_trial_tool_sha256=protocol.d36_trial_tool_sha256,
        d37_evaluator_tool_sha256=protocol.d37_evaluator_tool_sha256,
        protocol_case_count=protocol.case_count,
        protocol_case_tokens=protocol.case_tokens,
        protocol_category_count=protocol.category_count,
        protocol_category_tokens=protocol.category_tokens,
        case_categories=protocol.case_categories,
        included_count=len(included),
        excluded_count=len(excluded),
        included_case_tokens=included,
        excluded_cases=excluded,
        evaluator_role="independent_evaluator",
        evaluator_name=evaluator_name,
        executed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        sealed_evidence_sha256=sealed_sha256,
        modes=modes,
    )
    result_path = output / _PUBLIC_RESULT_NAME
    _publish_immutable(result_path, _canonical_file_bytes(bundle), "result bundle")
    if _read_regular(result_path) != _canonical_file_bytes(bundle):
        raise ValueError("result bundle changed after publication")
    _validate_run_context(candidate_root, freeze_manifest, context)
    return bundle


async def run_blinded_evaluation(
    *,
    candidate_root: Path,
    freeze_manifest: Path,
    corpus: Path,
    human_review: Path,
    independent_review: Path,
    output_root: Path,
    model: str,
    index: Path,
    evaluator_name: str,
    token_key_file: Path,
) -> EvaluationResultBundle:
    """Run or resume one externally isolated synthetic-or-held-out evaluation."""
    canonical_candidate = _canonical_candidate_root(candidate_root)
    anchor = _open_candidate_anchor(canonical_candidate)
    try:
        context = _load_run_context(canonical_candidate, freeze_manifest, anchor)
        return await _run_blinded_evaluation_anchored(
            candidate_root=canonical_candidate,
            freeze_manifest=freeze_manifest,
            corpus=corpus,
            human_review=human_review,
            independent_review=independent_review,
            output_root=output_root,
            model=model,
            index=index,
            evaluator_name=evaluator_name,
            token_key_file=token_key_file,
            context=context,
        )
    finally:
        _close_candidate_anchor(anchor)


__all__ = [
    "run_blinded_evaluation",
    "write_run_protocol_exclusive",
]
