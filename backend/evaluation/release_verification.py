"""External exact-candidate verification; no application or private evaluator imports."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from evaluation import blinded_io, blinded_runtime, evidence_json, runtime_materialization as materialization
from evaluation.evidence_json import parse_canonical_model
from evaluation.release_candidate import freeze
from evaluation.release_candidate.contracts import FreezeManifest
from evaluation.smoke_contracts import (
    D39_COMMAND_DEADLINES,
    D39_REQUIRED_COMMANDS,
    CommandEvidence,
    RuntimeMaterialization,
    SmokeManifest,
    ToolExecutionBinding,
    VerificationManifest,
)
from evaluation.tool_attestation import (
    FileFingerprint,
    ToolAttestation,
    aggregate_fingerprints,
    attest_tool,
    canonical_json_bytes,
    validate_git_repository,
)

VERIFIER_SOURCE_PATHS: tuple[str, ...] = (
    "backend/evaluation/__init__.py",
    "backend/evaluation/blinded_io.py",
    "backend/evaluation/blinded_runtime.py",
    "backend/evaluation/browser_smoke.py",
    "backend/evaluation/evidence_json.py",
    "backend/evaluation/release_candidate/__init__.py",
    "backend/evaluation/release_candidate/contracts.py",
    "backend/evaluation/release_candidate/fingerprints.py",
    "backend/evaluation/release_candidate/freeze.py",
    "backend/evaluation/release_verification.py",
    "backend/evaluation/runtime_materialization.py",
    "backend/evaluation/scripts/d39_candidate_smoke.py",
    "backend/evaluation/scripts/d39_smoke.py",
    "backend/evaluation/scripts/materialize_candidate_runtime.py",
    "backend/evaluation/scripts/verify_release_candidate.py",
    "backend/evaluation/smoke_contracts.py",
    "backend/evaluation/tool_attestation.py",
    "backend/pyproject.toml",
    "backend/uv.lock",
)
SCAN_RULE_IDS: tuple[str, ...] = ("tracked_private_state", "tracked_generated_state", "credential_token", "private_key_block")
PRIVATE_COMPONENTS: frozenset[str] = frozenset({"private", "corpus", "keys", "secrets", "reviews", "evidence", "storage"})
PRIVATE_FILENAMES: frozenset[str] = frozenset({"held-out.jsonl", "human-review.json", "independent-review.json"})
PUBLIC_SYNTHETIC_PATHS: tuple[str, ...] = (
    "backend/tests/fixtures/blinded/synthetic-held-out.jsonl",
    "backend/tests/fixtures/blinded/synthetic-human-review.json",
    "backend/tests/fixtures/blinded/synthetic-independent-review.json",
    "backend/tests/fixtures/blinded/synthetic-result-bundle.json",
)
GENERATED_COMPONENTS: frozenset[str] = frozenset({".venv", "venv", "node_modules", "dist", "__pycache__", ".cache", ".pytest_cache", ".ruff_cache", "media", "generated"})
GENERATED_SUFFIXES: frozenset[str] = frozenset({".pyc", ".pyo", ".mp4", ".webm", ".wav"})
CREDENTIAL_PATTERN: bytes = rb"(?<![A-Za-z0-9_-])(?:sk-[A-Za-z0-9_-]{20,200}|gh[pousr]_[A-Za-z0-9_]{20,200}|github_pat_[A-Za-z0-9_]{20,200}|(?:AKIA|ASIA)[A-Z0-9]{16})(?![A-Za-z0-9_-])"
PRIVATE_KEY_PATTERN: bytes = rb"-----BEGIN (?:PRIVATE|RSA PRIVATE|EC PRIVATE|OPENSSH PRIVATE) KEY-----"
_EXAMPLE_PATTERN = re.compile(rb"(?:sk-|gh[pousr]_|github_pat_)[xX]{20,200}\Z")
_SCAN_PATTERNS = (("credential_token", re.compile(CREDENTIAL_PATTERN)), ("private_key_block", re.compile(PRIVATE_KEY_PATTERN)))
_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_METADATA_BYTES = 16 * 1024 * 1024
_MAX_TOOL_BYTES = 256 * 1024 * 1024
_MAX_SCAN_COUNT = 8192


def _trusted_tool_root() -> Path:
    return Path(__file__).resolve(strict=True).parents[2]


def _attest_verifier(root: Path) -> ToolAttestation:
    commit = validate_git_repository(root)
    return attest_tool(repo_root=root, tool_name="d39_release_verifier", git_commit=commit, source_paths=VERIFIER_SOURCE_PATHS)


def _scan_stream(stream: BinaryIO, counts: dict[str, int], maximum: int) -> int:
    size = 0
    overlap = b""
    counted_before = 0
    while chunk := stream.read(65536):
        size += len(chunk)
        if size > maximum:
            raise ValueError("public scan byte limit exceeded")
        window = overlap + chunk
        offset = size - len(window)
        final = stream.peek(1) == b"" if hasattr(stream, "peek") else size == maximum
        stable = size if final else max(0, size - 4096)
        for rule, pattern in _SCAN_PATTERNS:
            for match in pattern.finditer(window):
                start = offset + match.start()
                if start < counted_before or start >= stable:
                    continue
                token = match.group()
                if rule == "credential_token" and (token == b"AKIAIOSFODNN7EXAMPLE" or _EXAMPLE_PATTERN.fullmatch(token)):
                    continue
                counts[rule] = min(_MAX_SCAN_COUNT, counts[rule] + 1)
        counted_before = stable
        overlap = window[-4096:]
    if counted_before < size:
        offset = size - len(overlap)
        for rule, pattern in _SCAN_PATTERNS:
            for match in pattern.finditer(overlap):
                if offset + match.start() < counted_before:
                    continue
                token = match.group()
                if rule == "credential_token" and (token == b"AKIAIOSFODNN7EXAMPLE" or _EXAMPLE_PATTERN.fullmatch(token)):
                    continue
                counts[rule] = min(_MAX_SCAN_COUNT, counts[rule] + 1)
    return size


def scan_public_files(root: Path, paths: tuple[str, ...], metadata: tuple[bytes, ...]) -> dict[str, int]:
    """Count four bounded rules in explicit tracked files and bounded public metadata."""
    if len(paths) > 8192 or len(set(paths)) != len(paths) or len(metadata) > 16:
        raise ValueError("public scan inventory limit exceeded")
    counts = dict.fromkeys(SCAN_RULE_IDS, 0)
    total = 0
    for relative in paths:
        FileFingerprint(path=relative, size=0, sha256="0" * 64)
        parsed = PurePosixPath(relative.lower())
        name = parsed.name
        public_example = PurePosixPath(relative).name == ".env.example"
        private = bool(PRIVATE_COMPONENTS.intersection(parsed.parts) or name in PRIVATE_FILENAMES or (not public_example and (name == ".env" or name.startswith(".env."))))
        if private and relative not in PUBLIC_SYNTHETIC_PATHS:
            counts["tracked_private_state"] = min(_MAX_SCAN_COUNT, counts["tracked_private_state"] + 1)
        if GENERATED_COMPONENTS.intersection(parsed.parts) or parsed.suffix in GENERATED_SUFFIXES:
            counts["tracked_generated_state"] = min(_MAX_SCAN_COUNT, counts["tracked_generated_state"] + 1)
        path = root / relative
        materialization._directory(path.parent)
        descriptor = materialization._file_descriptor(path)
        try:
            before = materialization._descriptor_stat(descriptor)
            identity = materialization._identity(before)
            materialization._assert_file(path, descriptor, identity)
            if before.st_size > _MAX_SOURCE_BYTES:
                raise ValueError("public scan file limit exceeded")
            with os.fdopen(os.dup(descriptor), "rb") as stream:
                size = _scan_stream(stream, counts, _MAX_SOURCE_BYTES)
            after = materialization._assert_file(path, descriptor, identity)
            if size != before.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("public scan source changed")
            total += size
        finally:
            os.close(descriptor)
        if total > _MAX_TOTAL_BYTES:
            raise ValueError("public scan total limit exceeded")
    for blob in metadata:
        if type(blob) is not bytes or len(blob) > _MAX_METADATA_BYTES:
            raise ValueError("public scan metadata limit exceeded")
        total += _scan_stream(io.BufferedReader(io.BytesIO(blob)), counts, _MAX_METADATA_BYTES)
        if total > _MAX_TOTAL_BYTES:
            raise ValueError("public scan total limit exceeded")
    return counts


def build_group_environment(root: Path, *, python_executable: Path, node_executable: Path | None) -> dict[str, str]:
    """Construct a clean, group-contained low-concurrency environment from scratch."""
    root = materialization._directory(root)
    env: dict[str, str] = {}
    system_paths: list[str] = []
    if os.name == "nt":
        system = materialization._directory(Path(os.environ.get("SystemRoot", "C:/Windows")))
        env.update(SystemRoot=str(system), WINDIR=str(system), COMSPEC=str(system / "System32" / "cmd.exe"))
        system_paths = [str(system / "System32"), str(system)]
    else:
        system_paths = ["/usr/bin", "/bin"]
    writable = {
        "HOME": "home", "USERPROFILE": "home", "APPDATA": "home/appdata", "LOCALAPPDATA": "home/local",
        "XDG_CONFIG_HOME": "home/config", "XDG_CACHE_HOME": "home/cache", "XDG_DATA_HOME": "home/data", "XDG_STATE_HOME": "home/state",
        "TEMP": "temp", "TMP": "temp", "TMPDIR": "temp", "UV_PROJECT_ENVIRONMENT": "env", "UV_CACHE_DIR": "uv-cache",
        "NPM_CONFIG_CACHE": "npm-cache", "RUFF_CACHE_DIR": "ruff-cache", "PNPM_HOME": "pnpm-home",
        "BLOCKVIDEO_STORAGE_DIR": "storage",
    }
    for key, suffix in writable.items():
        directory = blinded_io.create_directory_tree(root / suffix, "group state")
        env[key] = str(directory)
    env.update({
        "NPM_CONFIG_USERCONFIG": str(root / "npm-user.conf"), "NPM_CONFIG_GLOBALCONFIG": str(root / "npm-global.conf"),
        "UV_PYTHON": str(python_executable.absolute()), "UV_CONCURRENT_DOWNLOADS": "2", "UV_CONCURRENT_BUILDS": "1", "UV_CONCURRENT_INSTALLS": "1",
        "UV_PYTHON_DOWNLOADS": "never", "UV_NO_CONFIG": "1", "UV_NO_PROGRESS": "1",
        "NODE_OPTIONS": "--max-old-space-size=512", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "PYTEST_ADDOPTS": "-o cache_dir=" + json.dumps((root / "pytest-cache").as_posix()),
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1", "RAYON_NUM_THREADS": "1",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false", "NPM_CONFIG_AUDIT": "false", "NPM_CONFIG_FUND": "false",
        "NPM_CONFIG_PRODUCTION": "false", "NPM_CONFIG_IGNORE_SCRIPTS": "true", "NPM_CONFIG_ENGINE_STRICT": "true",
        "CI": "true", "NO_COLOR": "1", "LANG": "C", "LC_ALL": "C",
    })
    native_paths = [str(python_executable.absolute().parent)]
    if node_executable is not None:
        native_paths.insert(0, str(node_executable.absolute().parent))
    git = shutil.which("git")
    if git is not None:
        native_paths.append(str(_native_path(Path(git)).parent))
    env["PATH"] = os.pathsep.join([str(root / "env" / ("Scripts" if os.name == "nt" else "bin")), *native_paths, *system_paths])
    for name in ("npm-user.conf", "npm-global.conf"):
        blinded_io.write_exclusive(root / name, b"")
    return env


class _ExecutionGroup:
    def __init__(self, work: Path, runtime: Path, record: RuntimeMaterialization) -> None:
        self.work = materialization._directory(work)
        self.work_anchor = materialization._open_anchor(self.work)
        self.root = self.work / ("group-" + secrets.token_hex(32))
        self.anchor: freeze._DirectoryAnchor | None = None
        self.source = self.root / "source"
        self.record = record
        try:
            materialization._assert_directory(self.work, self.work_anchor)
            self.root.mkdir(mode=0o700)
            self.anchor = materialization._open_anchor(self.root)
            self.source.mkdir(mode=0o700)
            tree = materialization._OwnedTree(self.source)
            try:
                tree.guard = self.assert_owned
                for item in record.files:
                    tree.copy(runtime, item)
                self.assert_source()
            finally:
                tree.close()
        except BaseException:
            try:
                if self.anchor is not None:
                    self.cleanup()
            finally:
                freeze._close_directory_anchor(self.work_anchor)
            raise

    def assert_owned(self) -> None:
        materialization._assert_directory(self.work, self.work_anchor)
        if self.anchor is None:
            raise ValueError("group ownership unavailable")
        materialization._assert_directory(self.root, self.anchor)

    def source_sha256(self) -> str:
        self.assert_owned()
        files: list[FileFingerprint] = []
        for expected in self.record.files:
            path = self.source / expected.path
            materialization._directory(path.parent)
            size, digest = blinded_io.fingerprint_regular(path, maximum=_MAX_SOURCE_BYTES)
            files.append(FileFingerprint(path=expected.path, size=size, sha256=digest))
        return aggregate_fingerprints(files)

    def assert_source(self) -> None:
        if self.source_sha256() != self.record.runtime_source_sha256:
            raise ValueError("group tracked source drift")

    def cleanup(self) -> None:
        self.assert_owned()
        assert self.anchor is not None
        _remove_group_directory(self.root, self.anchor)
        freeze._close_directory_anchor(self.work_anchor)


def _remove_group_directory(path: Path, anchor: freeze._DirectoryAnchor) -> None:
    materialization._assert_directory(path, anchor)
    with os.scandir(path) as entries:
        names = [entry.name for entry in entries]
    if len(names) > 262144:
        raise ValueError("group cleanup inventory exceeded")
    for name in names:
        materialization._assert_directory(path, anchor)
        child = path / name
        before = child.lstat()
        if stat.S_ISDIR(before.st_mode) and not blinded_io.is_reparse(before):
            nested = materialization._open_anchor(child)
            try:
                if nested.identity != materialization._directory_identity(child):
                    raise ValueError("group child identity lost")
                _remove_group_directory(child, nested)
            finally:
                freeze._close_directory_anchor(nested)
        else:
            descriptor = -1
            if stat.S_ISREG(before.st_mode) and not blinded_io.is_reparse(before):
                descriptor = materialization._file_descriptor(child)
                opened = materialization._descriptor_stat(descriptor)
                if materialization._identity(opened) != materialization._identity(before):
                    os.close(descriptor)
                    raise ValueError("group leaf changed before open")
                before = opened
            try:
                if materialization._identity(child.lstat()) != materialization._identity(before):
                    raise ValueError("group leaf identity lost")
                if os.name == "nt" and stat.S_ISREG(before.st_mode) and not blinded_io.is_reparse(before):
                    os.chmod(child, stat.S_IREAD | stat.S_IWRITE)
                materialization._assert_directory(path, anchor)
                if descriptor >= 0:
                    os.close(descriptor)
                    descriptor = -1
                if materialization._identity(child.lstat()) != materialization._identity(before):
                    raise ValueError("group leaf identity lost")
                if anchor.descriptor is not None:
                    os.unlink(name, dir_fd=anchor.descriptor)
                elif stat.S_ISDIR(before.st_mode):
                    child.rmdir()
                else:
                    child.unlink()
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
    materialization._assert_directory(path, anchor)
    if os.listdir(path):
        raise ValueError("group cleanup has unexpected entries")
    freeze._close_directory_anchor(anchor)
    if materialization._directory_identity(path) != anchor.identity:
        raise ValueError("group directory identity lost")
    path.rmdir()


def _read_smoke(path: Path, record: RuntimeMaterialization, digest: str) -> tuple[SmokeManifest, str]:
    raw = blinded_io.read_regular(path, maximum=1024 * 1024)
    result = parse_canonical_model(raw, SmokeManifest, maximum=1024 * 1024)
    for name in ("candidate_id", "git_commit", "freeze_sha256", "runtime_instance_id", "runtime_source_sha256"):
        if getattr(result, name) != getattr(record, name):
            raise ValueError("smoke runtime binding mismatch")
    if result.materialization_sha256 != digest:
        raise ValueError("smoke detached binding mismatch")
    _validate_smoke_tools(result)
    return result, hashlib.sha256(raw).hexdigest()


def _validate_smoke_tools(smoke: SmokeManifest) -> None:
    specifications = {
        "python_bootstrap": ("3.12.12", "tools/python_bootstrap", None),
        "python": ("3.12.12", "tools/python_sandbox", None),
        "uv": ("0.12.15", "tools/python_bootstrap", "tools/uv_module"),
        "node": ("24.11.1", "tools/node", None), "npx": (None, "tools/node", "tools/npx_cli"),
        "pnpm": ("10.18.3", "tools/node", "tools/pnpm_cjs"),
        "chrome": (None, "tools/chrome", None), "ffmpeg": (None, "tools/ffmpeg", None), "ffprobe": (None, "tools/ffprobe", None),
        "websockets": ("16.1.1", "tools/python_sandbox", "tools/websockets_module"),
    }
    seen: dict[str, FileFingerprint] = {}
    for receipt in smoke.stage_receipts:
        required = {"node", "npx", "pnpm", "python", "python_bootstrap", "uv"}
        required.update({"chrome", "websockets"} if receipt.stage == "browser" else {"ffmpeg", "ffprobe"} if receipt.stage == "ffmpeg" else set())
        if {item.role for item in receipt.tools} != required:
            raise ValueError("smoke native role inventory mismatch")
        for item in receipt.tools:
            version, executable, launcher = specifications[item.role]
            if item.executable.path != executable or (version is not None and item.version != version) or (launcher is None) != (item.launcher is None) or (item.launcher is not None and item.launcher.path != launcher):
                raise ValueError("smoke native binding mismatch")
            if item.role == "npx" and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", item.version) is None:
                raise ValueError("smoke npm version must be observed")
            for blob in (item.executable, item.launcher):
                if blob is None:
                    continue
                if blob.size > _MAX_TOOL_BYTES or (blob.path in seen and seen[blob.path] != blob):
                    raise ValueError("smoke tool size or fingerprint mismatch")
                seen[blob.path] = blob
    if sum(item.size for item in seen.values()) > 1024 * 1024 * 1024:
        raise ValueError("smoke tool aggregate limit exceeded")


def _publish_verification(output: Path, manifest_bytes: bytes, attestation_bytes: bytes) -> None:
    if os.name != "nt" and not sys.platform.startswith("linux"):
        raise ValueError("native verification publication unavailable")
    values = {"verification-manifest.json": manifest_bytes, "d39-verifier-attestation.json": attestation_bytes}
    if any(type(raw) is not bytes or not raw or len(raw) > _MAX_METADATA_BYTES for raw in values.values()):
        raise ValueError("verification publication size invalid")
    final = output.absolute()
    parent = materialization._directory(final.parent)
    if final.exists() or final.is_symlink() or final.name in {"", ".", ".."}:
        raise ValueError("verification destination already exists or is invalid")
    parent_anchor = materialization._open_anchor(parent)
    stage = parent / (".d39-stage-" + secrets.token_hex(32))
    stage_anchor = None
    retained: dict[str, tuple[int, tuple[int, int]]] = {}
    closed = False
    published = False

    def check(directory: Path) -> None:
        materialization._assert_directory(parent, parent_anchor)
        assert stage_anchor is not None
        if materialization._directory_identity(directory) != stage_anchor.identity:
            raise ValueError("verification stage identity lost")
        if set(os.listdir(directory)) != set(values):
            raise ValueError("verification stage inventory invalid")
        for name, (descriptor, identity) in retained.items():
            path = directory / name
            if not closed:
                materialization._assert_file(path, descriptor, identity)
                raw = materialization._read_descriptor(descriptor, maximum=_MAX_METADATA_BYTES)
            else:
                if materialization._identity(path.lstat()) != identity:
                    raise ValueError("verification file identity lost")
                raw = blinded_io.read_regular(path, maximum=_MAX_METADATA_BYTES)
            if raw != values[name]:
                raise ValueError("verification readback mismatch")

    try:
        materialization._assert_directory(parent, parent_anchor)
        stage.mkdir(mode=0o700)
        stage_anchor = materialization._open_anchor(stage)
        for name, raw in values.items():
            materialization._assert_directory(parent, parent_anchor)
            materialization._assert_directory(stage, stage_anchor)
            descriptor = materialization._file_descriptor(stage / name, create=True, writable=True)
            retained[name] = descriptor, materialization._identity(materialization._descriptor_stat(descriptor))
            materialization._write_descriptor(descriptor, raw)
        check(stage)
        if stage_anchor.descriptor is not None:
            assert parent_anchor.descriptor is not None
            os.fsync(stage_anchor.descriptor)
            alias = Path(f"/proc/self/fd/{parent_anchor.descriptor}")
            freeze._linux_rename_directory_no_replace(alias / stage.name, alias / final.name)
            published = True
            check(final)
            os.fsync(parent_anchor.descriptor)
        else:
            for descriptor, _ in retained.values():
                os.close(descriptor)
            closed = True
            check(stage)
            freeze._close_directory_anchor(stage_anchor)
            materialization._assert_directory(parent, parent_anchor)
            freeze._windows_move_directory_no_replace(stage, final)
            published = True
            check(final)
    finally:
        if not closed:
            for descriptor, _ in retained.values():
                os.close(descriptor)
        try:
            if stage_anchor is not None:
                freeze._close_directory_anchor(stage_anchor)
                if not published and stage.exists() and materialization._directory_identity(stage) == stage_anchor.identity:
                    _discard_publication_stage(stage, parent, parent_anchor, stage_anchor.identity, retained, values)
        finally:
            freeze._close_directory_anchor(parent_anchor)


def _discard_publication_stage(stage: Path, parent: Path, parent_anchor: freeze._DirectoryAnchor, stage_identity: tuple[int, int], retained: dict[str, tuple[int, tuple[int, int]]], values: dict[str, bytes]) -> None:
    materialization._assert_directory(parent, parent_anchor)
    anchor = materialization._open_anchor(stage)
    try:
        if anchor.identity != stage_identity or set(os.listdir(stage)) != set(retained):
            raise ValueError("verification stage cleanup ownership lost")
        for name, (_, identity) in retained.items():
            path = stage / name
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or blinded_io.is_reparse(metadata) or metadata.st_nlink != 1 or materialization._identity(metadata) != identity:
                raise ValueError("verification stage cleanup file replaced")
            raw = blinded_io.read_regular(path, maximum=len(values[name]))
            if not values[name].startswith(raw):
                raise ValueError("verification stage cleanup content changed")
        for name, (_, identity) in retained.items():
            materialization._assert_directory(parent, parent_anchor)
            materialization._assert_directory(stage, anchor)
            path = stage / name
            descriptor = materialization._file_descriptor(path)
            try:
                materialization._assert_file(path, descriptor, identity)
            finally:
                os.close(descriptor)
            if materialization._identity(path.lstat()) != identity:
                raise ValueError("verification stage file lost before unlink")
            if anchor.descriptor is not None:
                os.unlink(name, dir_fd=anchor.descriptor)
            else:
                path.unlink()
        materialization._assert_directory(stage, anchor)
        if os.listdir(stage):
            raise ValueError("verification stage has unexpected cleanup entries")
        freeze._close_directory_anchor(anchor)
        if materialization._directory_identity(stage) != stage_identity:
            raise ValueError("verification stage lost before removal")
        stage.rmdir()
    finally:
        freeze._close_directory_anchor(anchor)


def _validate_output(output: Path, tool_root: Path, candidate: Path, runtime: Path, work: Path, materialization_path: Path, smoke_path: Path, freeze_path: Path) -> None:
    parent = materialization._directory(output.absolute().parent)
    final = parent / output.name
    if not final.is_relative_to(tool_root) or final == tool_root or final.exists() or final.is_symlink():
        raise ValueError("verification output must be new tooling evidence")
    for path in (candidate, runtime, work, materialization_path.parent, smoke_path.parent, freeze_path.parent):
        if final == path or final in path.parents or path in final.parents:
            raise ValueError("verification output aliases overlap")
    if freeze._git(tool_root, "check-ignore", "--no-index", "--", str(final), check=False).returncode != 0:
        raise ValueError("verification output must be Git ignored")
    if freeze._git(tool_root, "ls-files", "--", str(final)).stdout:
        raise ValueError("verification output must be untracked")


def verify_release_candidate(*, candidate_root: Path, freeze_manifest_path: Path, runtime_root: Path, materialization_path: Path, expected_materialization_sha256: str, work_root: Path, output_dir: Path, smoke_manifest_path: Path) -> VerificationManifest:
    """Verify fixed inventories, preserve actual failed observations, always clean bound runtime."""
    record = materialization._bound_materialization(materialization_path.absolute(), expected_materialization_sha256)
    commands: list[CommandEvidence] = []
    attestation: ToolAttestation | None = None
    before: str | None = None
    after: str | None = None
    runtime_after: str | None = None
    clean_before = clean_after = scan_passed = False
    smoke: SmokeManifest | None = None
    smoke_digest: str | None = None
    failed = True
    cleanup = "completed"
    root = _trusted_tool_root()
    candidate = candidate_root.absolute()
    runtime = runtime_root.absolute()
    work = work_root.absolute()
    try:
        attestation = _attest_verifier(root)
        _validate_output(output_dir, root, candidate, runtime, work, materialization_path.absolute(), smoke_manifest_path.absolute(), freeze_manifest_path.absolute())
        before = freeze._snapshot_tree(candidate)
        frozen, digest, snapshot = materialization._freeze_inputs(candidate, freeze_manifest_path.absolute())
        _candidate_binding(frozen, digest, snapshot, record)
        clean_before = True
        materialization.read_materialized_runtime(runtime_root=runtime, work_root=work, materialization_path=materialization_path, expected_materialization_sha256=expected_materialization_sha256)
        smoke, smoke_digest = _read_smoke(smoke_manifest_path, record, expected_materialization_sha256)
        counts = scan_public_files(candidate, tuple(item.path for item in record.files), (canonical_json_bytes(record) + b"\n", canonical_json_bytes(smoke) + b"\n", canonical_json_bytes(attestation) + b"\n"))
        for rule in SCAN_RULE_IDS:
            print(rule + "=" + str(counts[rule]))
        scan_passed = not any(counts.values())
        if not scan_passed:
            raise ValueError("public scan failed")
        asyncio.run(_run_inventory(candidate=candidate, runtime=runtime, work=work, path=materialization_path, digest=expected_materialization_sha256, record=record, tool_root=root, attestation=attestation, commands=commands, frozen_path=freeze_manifest_path.absolute()))
        failed = False
    except _GroupCleanupFailed:
        cleanup = "failed"
        failed = True
    except (OSError, ValueError, subprocess.SubprocessError):
        failed = True
    finally:
        try:
            after = freeze._snapshot_tree(candidate)
            frozen, freeze_digest, snapshot = materialization._freeze_inputs(candidate, freeze_manifest_path.absolute())
            clean_after = True
            _candidate_binding(frozen, freeze_digest, snapshot, record)
        except (OSError, ValueError, subprocess.SubprocessError):
            failed = True
        try:
            materialization.read_materialized_runtime(runtime_root=runtime, work_root=work, materialization_path=materialization_path, expected_materialization_sha256=expected_materialization_sha256)
            runtime_after = record.runtime_source_sha256
        except (OSError, ValueError):
            failed = True
        try:
            materialization.cleanup_candidate_runtime(runtime_root=runtime, work_root=work, materialization_path=materialization_path, expected_materialization_sha256=expected_materialization_sha256)
        except (OSError, ValueError):
            cleanup = "failed"
            failed = True
    if attestation is None or before is None:
        raise ValueError("verification preflight rejected; runtime cleanup attempted")
    if after != before or before != record.candidate_snapshot_sha256:
        failed = True
    payload = dict(schema_version=1, candidate_id=record.candidate_id, git_commit=record.git_commit, freeze_sha256=record.freeze_sha256, verifier_tool_sha256=attestation.aggregate_sha256, status="failed" if failed else "passed", commands=tuple(commands), smoke_manifest_sha256=smoke_digest, smoke_manifest=smoke, secret_scan_passed=scan_passed, candidate_clean_before=clean_before, candidate_clean_after=clean_after, candidate_snapshot_before_sha256=before, candidate_snapshot_after_sha256=after, materialization_sha256=expected_materialization_sha256, runtime_instance_id=record.runtime_instance_id, runtime_source_sha256=record.runtime_source_sha256, runtime_snapshot_after_sha256=runtime_after, cleanup_status=cleanup)
    result = VerificationManifest.model_validate(payload, strict=True)
    if _attest_verifier(root) != attestation:
        raise ValueError("verifier source changed during execution")
    _validate_output(output_dir, root, candidate, runtime, work, materialization_path.absolute(), smoke_manifest_path.absolute(), freeze_manifest_path.absolute())
    _publish_verification(output_dir, canonical_json_bytes(result) + b"\n", canonical_json_bytes(attestation) + b"\n")
    return result


_BACKEND_IMPORTS: tuple[str, ...] = (
    "fastapi", "uvicorn", "pydantic", "pydantic_settings", "sqlalchemy", "aiosqlite",
    "httpx", "python_multipart", "anyio", "PIL", "cairosvg", "jinja2", "yaml", "loguru",
    "pytest", "pytest_asyncio", "mypy", "ruff", "numpy", "onnxruntime", "tokenizers",
)
_PYTHON_PROBE = (
    "import importlib,importlib.metadata,json,sys; "
    "names=json.loads(sys.argv[1]); modules={n:importlib.import_module(n) for n in names}; "
    "data={'version':'.'.join(map(str,sys.version_info[:3])),'executable':sys.executable,"
    "'prefix':sys.prefix,'base_prefix':sys.base_prefix,'base_executable':sys._base_executable,"
    "'origins':{n:m.__file__ for n,m in modules.items()}}; "
    "data.update({'uv_version':importlib.metadata.version('uv'),'uv_main':importlib.util.find_spec('uv.__main__').origin,"
    "'uv_binary':modules['uv'].find_uv_bin()}) if 'uv' in modules else None; print(json.dumps(data))"
)


class _GroupCleanupFailed(ValueError):
    pass


@dataclass(frozen=True)
class _ToolSet:
    executable: Path
    launcher: Path | None
    bindings: tuple[ToolExecutionBinding, ...]
    files: tuple[tuple[Path, FileFingerprint], ...]
    base_prefix: Path | None = None

    def verify(self) -> None:
        if not self.files or not self.bindings or self.executable.suffix.lower() in {".cmd", ".bat", ".py", ".ps1", ".sh"}:
            raise ValueError("native tool binding unavailable")
        native = self.executable.resolve(strict=True)
        if native != self.files[0][0].absolute() or any(item.executable != self.files[0][1] for item in self.bindings):
            raise ValueError("command native path differs from bound executable")
        if self.launcher is not None and not any(path.absolute() == self.launcher.absolute() and expected.path == "tools/npx_cli" for path, expected in self.files):
            raise ValueError("command launcher differs from bound npx")
        total = 0
        for path, expected in self.files:
            actual = _tool_file(path, expected.path)
            if actual != expected:
                raise ValueError("native tool binding drift")
            total += actual.size
        if total > 1024 * 1024 * 1024:
            raise ValueError("native tool aggregate byte limit exceeded")


def _native_path(path: Path) -> Path:
    if path.suffix.lower() in {".cmd", ".bat", ".py", ".ps1", ".sh"}:
        raise ValueError("native executable required")
    resolved = path.absolute().resolve(strict=True)
    _native_file(resolved, "tools/probe")
    return resolved


def _tool_file(path: Path, alias: str) -> FileFingerprint:
    materialization._directory(path.absolute().parent)
    size, digest = blinded_io.fingerprint_regular(path.absolute(), maximum=_MAX_TOOL_BYTES)
    return FileFingerprint(path=alias, size=size, sha256=digest)


def _native_file(path: Path, alias: str) -> FileFingerprint:
    if path.suffix.lower() in {".cmd", ".bat", ".py", ".ps1", ".sh"}:
        raise ValueError("native executable required")
    result = _tool_file(path, alias)
    descriptor = materialization._file_descriptor(path)
    try:
        header = os.read(descriptor, 4)
    finally:
        os.close(descriptor)
    if (os.name == "nt" and not header.startswith(b"MZ")) or (os.name != "nt" and header not in (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")):
        raise ValueError("native executable format required")
    return result


async def _probe(scope: blinded_runtime.OwnedProcessScope, group: _ExecutionGroup, argv: tuple[str, ...], env: dict[str, str]) -> bytes:
    group.assert_owned()
    token = secrets.token_hex(32)
    stdout = group.root / ("probe-" + token + ".out")
    stderr = group.root / ("probe-" + token + ".err")
    outcome = await blinded_runtime.run_owned_command(scope=scope, argv=argv, cwd=group.root, env=env, stdout_path=stdout, stderr_path=stderr, deadline_seconds=30)
    if outcome.outcome != "completed" or outcome.exit_code != 0:
        raise ValueError("native tool probe failed")
    raw = blinded_io.read_regular(stdout, maximum=65536)
    if (len(raw), hashlib.sha256(raw).hexdigest()) != (outcome.stdout_size, outcome.stdout_sha256):
        raise ValueError("native tool probe output changed")
    return raw


def _probe_json(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or len(raw) > 65536:
        raise ValueError("native probe byte limit exceeded")
    evidence_json._check_lexical_limits(raw)
    try:
        result = json.loads(raw, object_pairs_hook=evidence_json._unique_object, parse_constant=evidence_json._reject_constant)
        evidence_json._check_values(result)
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("native probe malformed output") from None
    if type(result) is not dict:
        raise ValueError("native probe object required")
    return result


def _validate_python_probe(data: dict[str, object], *, executable: Path, base_executable: Path, environment: Path | None, required: tuple[str, ...]) -> None:
    if data.get("version") != "3.12.12":
        raise ValueError("Python version mismatch")
    for key, expected in (("executable", executable), ("base_executable", base_executable)):
        value = data.get(key)
        if type(value) is not str or Path(value).absolute() != expected.absolute():
            raise ValueError("Python native origin mismatch")
    prefix = data.get("prefix")
    base = data.get("base_prefix")
    if type(prefix) is not str or type(base) is not str:
        raise ValueError("Python prefix observation missing")
    if not base_executable.absolute().is_relative_to(Path(base).absolute()):
        raise ValueError("Python base origin mismatch")
    if environment is None:
        if Path(prefix).absolute() != Path(base).absolute():
            raise ValueError("bootstrap Python must be native base")
    elif Path(prefix).absolute() != environment.absolute() or Path(base).absolute() == environment.absolute():
        raise ValueError("sandbox interpreter prefix mismatch")
    origins = data.get("origins")
    if type(origins) is not dict or set(origins) != set(required):
        raise ValueError("Python import inventory missing")
    allowed = Path(prefix).absolute()
    if environment is not None:
        allowed = environment.absolute() / ("Lib/site-packages" if os.name == "nt" else "lib/python3.12/site-packages")
    for name in required:
        origin = origins[name]
        if type(origin) is not str or not Path(origin).absolute().is_relative_to(allowed):
            raise ValueError("Python package outside verified environment")


async def _bootstrap_python(scope: blinded_runtime.OwnedProcessScope, group: _ExecutionGroup, env: dict[str, str]) -> _ToolSet:
    executable = await asyncio.to_thread(_native_path, Path(getattr(sys, "_base_executable", sys.executable)))
    fingerprint = await asyncio.to_thread(_native_file, executable, "tools/python_bootstrap")
    data = _probe_json(await _probe(scope, group, (str(executable), "-I", "-B", "-c", _PYTHON_PROBE, '["uv"]'), env))
    _validate_python_probe(data, executable=executable, base_executable=executable, environment=None, required=("uv",))
    if data.get("uv_version") != "0.12.15":
        raise ValueError("uv version mismatch")
    files: list[tuple[Path, FileFingerprint]] = [(executable, fingerprint)]
    origins = data["origins"]
    assert isinstance(origins, dict)
    for value in (origins["uv"], data.get("uv_main"), data.get("uv_binary")):
        if type(value) is not str or not Path(value).absolute().is_relative_to(Path(str(data["prefix"])).absolute()):
            raise ValueError("uv origin outside native bootstrap")
    main = Path(str(data["uv_main"]))
    if main != Path(str(origins["uv"])).parent / "__main__.py":
        raise ValueError("uv module origin mismatch")
    module = await asyncio.to_thread(_tool_file, main, "tools/uv_module")
    binary = await asyncio.to_thread(_native_path, Path(str(data["uv_binary"])))
    init = Path(str(origins["uv"]))
    files.extend(((main, module), (init, await asyncio.to_thread(_tool_file, init, "tools/uv_init")), (binary, await asyncio.to_thread(_native_file, binary, "tools/uv_binary"))))
    version = await _probe(scope, group, (str(binary), "--version"), env)
    if re.fullmatch(rb"uv 0\.12\.15(?: \([A-Za-z0-9 .-]{1,128}\))?", version.strip()) is None:
        raise ValueError("uv native version mismatch")
    bindings = (
        ToolExecutionBinding(role="python_bootstrap", version="3.12.12", executable=fingerprint, launcher=None),
        ToolExecutionBinding(role="uv", version="0.12.15", executable=fingerprint, launcher=module),
    )
    result = _ToolSet(executable, None, bindings, tuple(files), Path(str(data["base_prefix"])))
    await asyncio.to_thread(result.verify)
    return result


async def _sandbox_python(scope: blinded_runtime.OwnedProcessScope, group: _ExecutionGroup, env: dict[str, str], bootstrap: _ToolSet) -> _ToolSet:
    environment = group.root / "env"
    config = blinded_io.read_regular(environment / "pyvenv.cfg", maximum=4096)
    if re.search(rb"(?m)^include-system-site-packages\s*=\s*false\s*$", config) is None:
        raise ValueError("sandbox Python must exclude global site packages")
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if os.name != "nt":
        target = executable.resolve(strict=True)
        if target != bootstrap.executable:
            raise ValueError("sandbox interpreter native target mismatch")
        fingerprint = await asyncio.to_thread(_native_file, target, "tools/python_sandbox")
    else:
        fingerprint = await asyncio.to_thread(_native_file, executable, "tools/python_sandbox")
    data = _probe_json(await _probe(scope, group, (str(executable), "-I", "-B", "-c", _PYTHON_PROBE, json.dumps(_BACKEND_IMPORTS)), env))
    _validate_python_probe(data, executable=executable, base_executable=bootstrap.executable, environment=environment, required=_BACKEND_IMPORTS)
    if bootstrap.base_prefix is None or Path(str(data["base_prefix"])) != bootstrap.base_prefix:
        raise ValueError("sandbox base prefix differs from verified bootstrap")
    origins = data["origins"]
    assert isinstance(origins, dict)
    for origin in origins.values():
        materialization._directory(Path(str(origin)).parent)
        await asyncio.to_thread(blinded_io.fingerprint_regular, Path(str(origin)), maximum=_MAX_TOOL_BYTES)
    native_target = executable.resolve(strict=True) if os.name != "nt" else executable
    result = _ToolSet(executable, None, (ToolExecutionBinding(role="python", version="3.12.12", executable=fingerprint, launcher=None),), ((native_target, fingerprint),))
    await asyncio.to_thread(result.verify)
    await asyncio.to_thread(bootstrap.verify)
    return result


def _installed_node() -> Path:
    value = shutil.which("node.exe" if os.name == "nt" else "node")
    if value is None:
        raise ValueError("installed native Node unavailable")
    return _native_path(Path(value))


def _pnpm_package(group: _ExecutionGroup) -> tuple[Path, Path]:
    root = group.root / "npm-cache" / "_npx"
    materialization._directory(root)
    selected: list[tuple[Path, Path]] = []
    with os.scandir(root) as entries:
        for index, entry in enumerate(entries):
            if index >= 64:
                raise ValueError("npm cache inventory exceeded")
            directory = Path(entry.path)
            materialization._directory(directory)
            package = directory / "node_modules" / "pnpm" / "package.json"
            if not package.exists():
                continue
            materialization._directory(package.parent)
            data = _probe_json(blinded_io.read_regular(package, maximum=65536))
            if data.get("name") == "pnpm" and data.get("version") == "10.18.3":
                selected.append((package, package.parent / "bin" / "pnpm.cjs"))
    if len(selected) != 1:
        raise ValueError("pinned pnpm launcher origin ambiguous or absent")
    return selected[0]


async def _frontend_tools(scope: blinded_runtime.OwnedProcessScope, group: _ExecutionGroup, env: dict[str, str], executable: Path) -> _ToolSet:
    node = await asyncio.to_thread(_native_file, executable, "tools/node")
    npm_root = executable.parent / "node_modules" / "npm" if os.name == "nt" else executable.parent.parent / "lib" / "node_modules" / "npm"
    npx = npm_root / "bin" / "npx-cli.js"
    package = npm_root / "package.json"
    npm = _probe_json(blinded_io.read_regular(package, maximum=65536))
    if npm.get("name") != "npm" or type(npm.get("version")) is not str or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(npm["version"])) is None:
        raise ValueError("installed npm metadata invalid")
    launcher = await asyncio.to_thread(_tool_file, npx, "tools/npx_cli")
    initial = ((executable, node), (npx, launcher), (package, await asyncio.to_thread(_tool_file, package, "tools/npm_package")))
    data = _probe_json(await _probe(scope, group, (str(executable), "-e", "console.log(JSON.stringify({version:process.versions.node,executable:process.execPath}))"), env))
    if data.get("version") != "24.11.1" or type(data.get("executable")) is not str or Path(str(data["executable"])) != executable:
        raise ValueError("Node native origin or version mismatch")
    if (await _probe(scope, group, (str(executable), str(npx), "--version"), env)).strip().decode("ascii") != npm["version"]:
        raise ValueError("npx version mismatch")
    npmrc = (
        "store-dir=" + (group.root / "pnpm-store").as_posix() + "\n"
        "cache-dir=" + (group.root / "pnpm-cache").as_posix() + "\n"
        "state-dir=" + (group.root / "pnpm-state").as_posix() + "\n"
        "child-concurrency=1\nnetwork-concurrency=2\nengine-strict=true\nignore-scripts=true\n"
    ).encode("utf-8")
    blinded_io.write_exclusive(group.source / "frontend" / ".npmrc", npmrc)
    if (await _probe(scope, group, (str(executable), str(npx), "-y", "pnpm@10.18.3", "--version"), env)).strip() != b"10.18.3":
        raise ValueError("pinned pnpm bootstrap version mismatch")
    pnpm_package, pnpm = await asyncio.to_thread(_pnpm_package, group)
    pnpm_launcher = await asyncio.to_thread(_tool_file, pnpm, "tools/pnpm_cjs")
    if (await _probe(scope, group, (str(executable), str(pnpm), "--version"), env)).strip() != b"10.18.3":
        raise ValueError("pinned pnpm native launcher failed")
    result = _ToolSet(executable, npx, (
        ToolExecutionBinding(role="node", version="24.11.1", executable=node, launcher=None),
        ToolExecutionBinding(role="npx", version=str(npm["version"]), executable=node, launcher=launcher),
        ToolExecutionBinding(role="pnpm", version="10.18.3", executable=node, launcher=pnpm_launcher),
    ), (*initial, (pnpm, pnpm_launcher), (pnpm_package, await asyncio.to_thread(_tool_file, pnpm_package, "tools/pnpm_package"))))
    await asyncio.to_thread(result.verify)
    return result


async def _esbuild_preflight(scope: blinded_runtime.OwnedProcessScope, group: _ExecutionGroup, tools: _ToolSet, env: dict[str, str]) -> None:
    lock = blinded_io.read_regular(group.source / "frontend" / "pnpm-lock.yaml", maximum=_MAX_SOURCE_BYTES)
    versions = set(re.findall(rb"(?m)^  esbuild@([0-9]+\.[0-9]+\.[0-9]+):", lock))
    if len(versions) != 1:
        raise ValueError("locked esbuild version ambiguous or absent")
    script = "const p=require('node:path');const e=require(p.join(process.argv[1],'node_modules/esbuild'));const r=e.transformSync('const d39 = 1;', {loader:'js'});if(!r.code.includes('d39'))process.exit(2);console.log(e.version)"
    raw = await _probe(scope, group, (str(tools.executable), "-e", script, str(group.source / "frontend")), env)
    if raw.strip() != next(iter(versions)):
        raise ValueError("native esbuild does not match frozen lock")


def _command_target(index: int, tools: _ToolSet) -> tuple[tuple[str, ...], tuple[str, ...]]:
    logical = D39_REQUIRED_COMMANDS[index][1]
    if index < 5:
        alias = "tools/python_bootstrap" if index == 0 else "tools/python_sandbox"
        return (str(tools.executable), *logical[1:]), (alias, *logical[1:])
    if tools.launcher is None:
        raise ValueError("native npx launcher unavailable")
    return (str(tools.executable), str(tools.launcher), *logical[1:]), ("tools/node", "tools/npx_cli", *logical[1:])


async def _execute_command(*, index: int, group: _ExecutionGroup, scope: blinded_runtime.OwnedProcessScope, tools: _ToolSet, env: dict[str, str], commands: list[CommandEvidence]) -> CommandEvidence:
    await asyncio.to_thread(group.assert_source)
    await asyncio.to_thread(tools.verify)
    argv, aliases = _command_target(index, tools)
    name, canonical = D39_REQUIRED_COMMANDS[index]
    cwd = "backend" if index < 5 else "frontend"
    expected = ("python_bootstrap", "uv") if index == 0 else ("python",) if index < 5 else ("node", "npx", "pnpm")
    if tuple(item.role for item in tools.bindings) != expected:
        raise ValueError("command native binding inventory incomplete")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    CommandEvidence(name=name, argv=canonical, resolved_argv=aliases, tool_bindings=tools.bindings, cwd=cwd, deadline_seconds=D39_COMMAND_DEADLINES[index], outcome="launch_failed", exit_code=None, started_at=timestamp, finished_at=timestamp, stdout_size=0, stderr_size=0, stdout_sha256=hashlib.sha256(b"").hexdigest(), stderr_sha256=hashlib.sha256(b"").hexdigest())
    environment = {**env, "PYTHONSAFEPATH": "1"} if index == 0 else env
    observed = await blinded_runtime.run_owned_command(scope=scope, argv=argv, cwd=group.source / cwd, env=environment, stdout_path=group.root / (name + ".out"), stderr_path=group.root / (name + ".err"), deadline_seconds=D39_COMMAND_DEADLINES[index])
    result = CommandEvidence(name=name, argv=canonical, resolved_argv=aliases, tool_bindings=tools.bindings, cwd=cwd, deadline_seconds=D39_COMMAND_DEADLINES[index], **observed.__dict__)
    commands.append(result)
    await asyncio.to_thread(group.assert_source)
    await asyncio.to_thread(tools.verify)
    return result


def _candidate_binding(frozen: FreezeManifest, digest: str, snapshot: str, record: RuntimeMaterialization) -> None:
    if (frozen.candidate_id, frozen.git_commit, digest, snapshot, tuple(frozen.files)) != (record.candidate_id, record.git_commit, record.freeze_sha256, record.candidate_snapshot_sha256, record.files):
        raise ValueError("candidate materialization binding mismatch")


def _inventory_boundary(candidate: Path, runtime: Path, work: Path, path: Path, digest: str, record: RuntimeMaterialization, tool_root: Path, attestation: ToolAttestation, frozen_path: Path) -> None:
    actual = materialization.read_materialized_runtime(runtime_root=runtime, work_root=work, materialization_path=path, expected_materialization_sha256=digest)
    if actual != record:
        raise ValueError("runtime group boundary drift")
    frozen, freeze_digest, snapshot = materialization._freeze_inputs(candidate, frozen_path)
    _candidate_binding(frozen, freeze_digest, snapshot, record)
    if _attest_verifier(tool_root) != attestation:
        raise ValueError("verifier source boundary drift")


async def _run_inventory(*, candidate: Path, runtime: Path, work: Path, path: Path, digest: str, record: RuntimeMaterialization, tool_root: Path, attestation: ToolAttestation, commands: list[CommandEvidence], frozen_path: Path) -> None:
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1, thread_name_prefix="d39-check"))
    async def boundary() -> None:
        await asyncio.to_thread(_inventory_boundary, candidate, runtime, work, path, digest, record, tool_root, attestation, frozen_path)
    for indices in (range(0, 5), range(5, 9)):
        await boundary()
        group = await asyncio.to_thread(_ExecutionGroup, work, runtime, record)
        scope = blinded_runtime.OwnedProcessScope()
        entered = False
        try:
            python = await asyncio.to_thread(_native_path, Path(getattr(sys, "_base_executable", sys.executable)))
            node = await asyncio.to_thread(_installed_node) if indices.start == 5 else None
            env = await asyncio.to_thread(build_group_environment, group.root, python_executable=python, node_executable=node)
            await scope.__aenter__()
            entered = True
            if indices.start == 0:
                tools = await _bootstrap_python(scope, group, env)
            else:
                assert node is not None
                tools = await _frontend_tools(scope, group, env, node)
            for index in indices:
                await boundary()
                result = await _execute_command(index=index, group=group, scope=scope, tools=tools, env=env, commands=commands)
                await boundary()
                if result.outcome != "completed" or result.exit_code != 0:
                    raise ValueError("verification command failed")
                if index == 0:
                    tools = await _sandbox_python(scope, group, env, tools)
                elif index == 5:
                    if (group.source / "frontend" / "node_modules" / ".bin" / ("pnpm.cmd" if os.name == "nt" else "pnpm")).exists():
                        raise ValueError("local pnpm could shadow pinned launcher")
                    await _esbuild_preflight(scope, group, tools, env)
            await asyncio.to_thread(group.assert_source)
        finally:
            try:
                if entered:
                    await asyncio.shield(scope.close())
                await asyncio.to_thread(group.cleanup)
            except (OSError, ValueError):
                raise _GroupCleanupFailed("owned group cleanup failed") from None
            finally:
                if group.anchor is not None:
                    freeze._close_directory_anchor(group.anchor)
                freeze._close_directory_anchor(group.work_anchor)
        await boundary()


__all__ = ["D39_COMMAND_DEADLINES", "D39_REQUIRED_COMMANDS", "CommandEvidence", "SmokeManifest", "ToolExecutionBinding", "VerificationManifest", "VERIFIER_SOURCE_PATHS", "verify_release_candidate"]
