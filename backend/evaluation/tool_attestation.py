"""Strict canonical source attestations for external evaluation tools."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_REPARSE_POINT = 0x400


class FileFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: str
    sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]
    size: Annotated[int, Field(ge=0)]

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        parsed = PurePosixPath(value)
        if not value or "\\" in value or parsed.is_absolute() or ".." in parsed.parts:
            raise ValueError("fingerprint path must be a lexical relative POSIX path")
        if parsed.as_posix() != value or any(part in ("", ".") for part in parsed.parts):
            raise ValueError("fingerprint path must be normalized")
        return value


class ToolAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    tool_name: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z0-9_]+$")]
    git_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    files: list[FileFingerprint]
    aggregate_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]

    @field_validator("files")
    @classmethod
    def validate_files(cls, value: list[FileFingerprint]) -> list[FileFingerprint]:
        paths = [item.path for item in value]
        if not paths or paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("attestation files must be non-empty, unique, and sorted")
        return value


def canonical_json_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _REPARSE_POINT)


def fingerprint_file(repo_root: Path, relative_path: str) -> FileFingerprint:
    FileFingerprint(path=relative_path, sha256="0" * 64, size=0)
    path = repo_root / Path(*PurePosixPath(relative_path).parts)
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"tool source is not a regular file: {relative_path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _is_reparse(opened):
            raise ValueError(f"tool source is not a regular file: {relative_path}")
        digest = hashlib.sha256()
        size = 0
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = (metadata.st_dev, metadata.st_ino, metadata.st_size)
    opened_identity = (opened.st_dev, opened.st_ino, opened.st_size)
    final_identity = (final.st_dev, final.st_ino, final.st_size)
    if identity != opened_identity or opened_identity != final_identity or size != opened.st_size:
        raise ValueError(f"tool source changed while hashing: {relative_path}")
    return FileFingerprint(path=relative_path, sha256=digest.hexdigest(), size=size)


def aggregate_fingerprints(files: tuple[FileFingerprint, ...] | list[FileFingerprint]) -> str:
    payload = [item.model_dump(mode="json") for item in files]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def attest_tool(
    *, repo_root: Path, tool_name: str, git_commit: str, source_paths: tuple[str, ...]
) -> ToolAttestation:
    if tuple(sorted(source_paths)) != source_paths or len(source_paths) != len(set(source_paths)):
        raise ValueError("tool source allowlist must be unique and sorted")
    files = [fingerprint_file(repo_root, path) for path in source_paths]
    if [fingerprint_file(repo_root, path) for path in source_paths] != files:
        raise ValueError("tool source changed while attesting")
    return ToolAttestation(
        schema_version=1,
        tool_name=tool_name,
        git_commit=git_commit,
        files=files,
        aggregate_sha256=aggregate_fingerprints(files),
    )
