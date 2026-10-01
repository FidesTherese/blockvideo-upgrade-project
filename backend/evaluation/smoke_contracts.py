"""Pure, immutable D39 evidence contracts shared with offline D40 consumers."""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import PurePosixPath
from types import UnionType
from typing import Annotated, Literal, Self, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from evaluation.tool_attestation import FileFingerprint, aggregate_fingerprints, canonical_json_bytes

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Commit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
CandidateId = Annotated[str, Field(pattern=r"^[0-9a-f]{16}-[0-9a-f]{12}$")]
Count = Annotated[int, Field(ge=0)]
Inode = Annotated[int, Field(gt=0)]
Calls = Annotated[int, Field(ge=0, le=4)]
Version = Literal[0, 1]
Outcome = Literal["completed", "launch_failed", "timeout", "output_limit", "memory_limit", "teardown_failed"]
Stage = Literal["legacy_migration", "restore", "all_tools_startup", "stateful_startup", "browser", "ffmpeg"]
SMOKE_STAGES: tuple[str, ...] = get_args(Stage)
D39_REQUIRED_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("backend_uv_sync", ("python", "-m", "uv", "sync", "--locked", "--extra", "dev", "--extra", "retrieval", "--no-python-downloads", "--no-config")),
    ("backend_import", ("python", "-B", "-c", "import app.main")),
    ("backend_pytest", ("python", "-B", "-m", "pytest")),
    ("backend_ruff", ("python", "-B", "-m", "ruff", "check", ".")),
    ("backend_d31_d35", ("python", "-B", "-m", "pytest", "tests/test_d31_adversarial_safety.py", "tests/test_d32_concurrency_matrix.py", "tests/test_d33_recovery_matrix.py", "tests/test_d34_migrations.py", "tests/test_d35_startup_recovery_api.py", "-q")),
    ("frontend_pnpm_install", ("npx", "-y", "pnpm@10.18.3", "install", "--frozen-lockfile", "--prod=false", "--ignore-scripts")),
    ("frontend_test", ("npx", "-y", "pnpm@10.18.3", "test", "--maxWorkers=1", "--minWorkers=1", "--no-file-parallelism")),
    ("frontend_build", ("npx", "-y", "pnpm@10.18.3", "build")),
    ("frontend_lint", ("npx", "-y", "pnpm@10.18.3", "lint")),
)
D39_COMMAND_DEADLINES: tuple[int, ...] = (600, 30, 1800, 120, 600, 600, 600, 300, 180)


def _raw_bounds(value: object) -> None:
    if isinstance(value, BaseModel):
        _raw_bounds(value.model_dump(mode="python"))
    elif type(value) is str:
        if not value or len(value.encode("utf-8")) > 512 or "\0" in value:
            raise ValueError("invalid bounded evidence string")
    elif isinstance(value, (list, tuple)):
        if len(value) > 8192:
            raise ValueError("evidence collection limit exceeded")
        for item in value:
            _raw_bounds(item)
    elif type(value) is dict:
        for name, item in value.items():
            if name == "path" and type(item) is str:
                if ":" in item or any(ord(char) < 32 for char in item):
                    raise ValueError("evidence path must be a safe lexical alias")
                FileFingerprint(path=item, size=0, sha256="0" * 64)
            _raw_bounds(item)


def _raw_primitive(value: object, annotation: object) -> None:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        if not any(type(value) is type(choice) and value == choice for choice in args):
            raise ValueError("invalid raw evidence literal")
    elif annotation in (int, bool, str):
        if type(value) is not annotation:
            raise ValueError("invalid raw evidence primitive")
    elif origin is UnionType and value is not None:
        primitive = tuple(item for item in args if item in (int, bool, str))
        if primitive and type(value) not in primitive:
            raise ValueError("invalid raw evidence primitive")


class StrictEvidenceModel(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def validate_raw(cls, value: object, info: ValidationInfo) -> object:
        if type(value) is dict:
            converted = dict(value)
            for name, item in value.items():
                field = cls.model_fields.get(name)
                if field is not None:
                    _raw_primitive(item, field.annotation)
                    _raw_bounds(item)
                    if info.mode == "json" and get_origin(field.annotation) is tuple and type(item) is list:
                        converted[name] = tuple(item)
            return converted
        return value


class OwnedPathIdentity(StrictEvidenceModel):
    path: str
    kind: Literal["file", "directory"]
    device: Count
    inode: Inode

    @field_validator("path")
    @classmethod
    def lexical_path(cls, value: str) -> str:
        _raw_bounds({"path": value})
        return value


class RuntimeMaterialization(StrictEvidenceModel):
    schema_version: Literal[1]
    candidate_id: CandidateId
    git_commit: Commit
    freeze_sha256: Sha256
    candidate_snapshot_sha256: Sha256
    runtime_instance_id: Sha256
    files: Annotated[tuple[FileFingerprint, ...], Field(min_length=1, max_length=8192)]
    owned_paths: Annotated[tuple[OwnedPathIdentity, ...], Field(min_length=1, max_length=8192)]
    runtime_source_sha256: Sha256
    runtime_device: Count
    runtime_inode: Inode
    marker_device: Count
    marker_inode: Inode
    root_aliases: tuple[Literal["candidate"], Literal["runtime"], Literal["work"]]
    status: Literal["materialized"]

    @model_validator(mode="after")
    def inventory(self) -> Self:
        paths = tuple(item.path for item in self.files)
        owned = tuple(item.path for item in self.owned_paths)
        parents = {parent.as_posix() for path in paths for parent in PurePosixPath(path).parents if parent.as_posix() != "."}
        if paths != tuple(sorted(set(paths))) or owned != tuple(sorted(set(owned))):
            raise ValueError("runtime inventory must be unique and sorted")
        expected = {path: "file" for path in paths} | {path: "directory" for path in parents}
        if len(expected) != len(paths) + len(parents) or {item.path: item.kind for item in self.owned_paths} != expected:
            raise ValueError("runtime owned inventory must match files and required parents")
        if self.runtime_source_sha256 != aggregate_fingerprints(self.files):
            raise ValueError("runtime source aggregate mismatch")
        return self


class RuntimeOwnership(StrictEvidenceModel):
    schema_version: Literal[1]
    runtime_instance_id: Sha256
    runtime_device: Count
    runtime_inode: Inode
    marker_device: Count
    marker_inode: Inode
    work_root_alias: Literal["work"]
    runtime_root_alias: Literal["runtime"]
    materialization_sha256: Sha256 | None
    state: Literal["building", "active", "cleaning", "cleaned"]

    @model_validator(mode="after")
    def binding(self) -> Self:
        if self.state != "building" and self.materialization_sha256 is None:
            raise ValueError("published ownership requires a materialization binding")
        return self


class RuntimeCleanupReceipt(StrictEvidenceModel):
    schema_version: Literal[1]
    runtime_instance_id: Sha256
    materialization_sha256: Sha256 | None
    status: Literal["completed", "failed"]


class ToolExecutionBinding(StrictEvidenceModel):
    role: str
    version: str
    executable: FileFingerprint
    launcher: FileFingerprint | None


class MigrationSummary(StrictEvidenceModel):
    stage: Literal["legacy_migration"]
    from_version: Version
    to_version: Version
    integrity_ok: bool
    foreign_keys_enabled: bool
    rows_preserved: bool
    identities_preserved: bool
    backup_size: Annotated[int, Field(ge=0, le=32 * 1024 * 1024)]
    backup_sha256: Sha256 | None


class RestoreSummary(StrictEvidenceModel):
    stage: Literal["restore"]
    restored_version: Version
    integrity_ok: bool
    foreign_keys_enabled: bool
    rows_equal: bool
    identities_equal: bool
    lease_exclusion_passed: bool


class AllToolsStartupSummary(StrictEvidenceModel):
    stage: Literal["all_tools_startup"]
    mode: Literal["all_tools"]
    startup_ready: bool
    health_ok: bool
    request_completed: bool
    model_calls: Calls
    index_sha256: Sha256 | None


class StatefulStartupSummary(StrictEvidenceModel):
    stage: Literal["stateful_startup"]
    mode: Literal["stateful"]
    startup_ready: bool
    health_ok: bool
    request_completed: bool
    model_calls: Calls
    index_sha256: Sha256 | None
    profile_sha256: Sha256 | None
    embedding_calls: Calls
    retrieval_verified: bool


class BrowserSummary(StrictEvidenceModel):
    stage: Literal["browser"]
    narrow_width: Literal[390]
    wide_width: Literal[1440]
    waiting_ok: bool
    safe_retry_ok: bool
    unknown_remote_blocked: bool
    migration_failed_ok: bool
    keyboard_ok: bool
    duplicate_post_count: Calls
    horizontal_overflow: bool
    playback_ok: bool
    documentation_checks: dict[str, bool]

    @field_validator("documentation_checks", mode="before")
    @classmethod
    def documentation(cls, value: object) -> object:
        required = {"setup_paths", "locked_versions", "mode_commands", "recovery_codes", "migration_restore", "limitation_boundary"}
        if type(value) is not dict or set(value) != required or any(type(item) is not bool for item in value.values()):
            raise ValueError("documentation requires six exact raw checks")
        return value


class FFmpegSummary(StrictEvidenceModel):
    stage: Literal["ffmpeg"]
    providers_fake: bool
    ffmpeg_exit_code: int | None
    ffprobe_exit_code: int | None
    video_present: bool
    subtitle_present: bool
    publication_bound: bool
    duration_ms: Annotated[int, Field(ge=0, le=60000)]


Summary = Annotated[MigrationSummary | RestoreSummary | AllToolsStartupSummary | StatefulStartupSummary | BrowserSummary | FFmpegSummary, Field(discriminator="stage")]


def _sorted_unique(values: tuple[str, ...]) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError("evidence inventory must be unique and sorted")


class SmokeStageReceipt(StrictEvidenceModel):
    schema_version: Literal[1]
    stage: Stage
    candidate_id: CandidateId
    git_commit: Commit
    freeze_sha256: Sha256
    materialization_sha256: Sha256
    runtime_instance_id: Sha256
    runtime_source_sha256: Sha256
    outcome: Literal["passed", "failed"]
    tools: Annotated[tuple[ToolExecutionBinding, ...], Field(max_length=16)]
    artifacts: Annotated[tuple[FileFingerprint, ...], Field(min_length=1, max_length=64)]
    summary: Summary

    @model_validator(mode="after")
    def observations(self) -> Self:
        _sorted_unique(tuple(item.role for item in self.tools))
        _sorted_unique(tuple(item.path for item in self.artifacts))
        if self.stage != self.summary.stage:
            raise ValueError("smoke summary stage mismatch")
        if self.outcome == "passed":
            values = self.summary.model_dump()
            for name, value in values.items():
                if type(value) is bool and value is not (name != "horizontal_overflow"):
                    raise ValueError("passed smoke requires all observations")
            if not self.tools:
                raise ValueError("passed smoke requires bound tools")
            summary = self.summary
            if isinstance(summary, MigrationSummary) and (summary.from_version != 0 or summary.to_version != 1 or not summary.backup_size or summary.backup_sha256 is None):
                raise ValueError("passed migration requires a verified backup")
            if isinstance(summary, RestoreSummary) and summary.restored_version != 1:
                raise ValueError("passed restore requires schema one")
            if isinstance(summary, AllToolsStartupSummary) and (summary.index_sha256 is not None or summary.model_calls < 1):
                raise ValueError("all-tools startup observation mismatch")
            if isinstance(summary, StatefulStartupSummary) and (summary.index_sha256 is None or summary.profile_sha256 is None or summary.embedding_calls < 1 or summary.model_calls < 1):
                raise ValueError("passed stateful startup requires verified retrieval")
            if isinstance(summary, BrowserSummary) and (summary.duplicate_post_count != 1 or not all(summary.documentation_checks.values())):
                raise ValueError("passed browser requires one POST and all documentation checks")
            if isinstance(summary, FFmpegSummary) and (summary.ffmpeg_exit_code != 0 or summary.ffprobe_exit_code != 0 or summary.duration_ms < 1):
                raise ValueError("passed FFmpeg requires zero exits and duration")
        if len(canonical_json_bytes(self)) + 1 > 65536:
            raise ValueError("smoke receipt size limit exceeded")
        return self


class SmokeManifest(StrictEvidenceModel):
    schema_version: Literal[1]
    candidate_id: CandidateId
    git_commit: Commit
    freeze_sha256: Sha256
    materialization_sha256: Sha256
    runtime_instance_id: Sha256
    runtime_source_sha256: Sha256
    legacy_migration_sha256: Sha256
    restore_sha256: Sha256
    all_tools_startup_sha256: Sha256
    stateful_startup_sha256: Sha256
    browser_sha256: Sha256
    ffmpeg_sha256: Sha256
    stage_receipts: Annotated[tuple[SmokeStageReceipt, ...], Field(min_length=6, max_length=6)]

    @model_validator(mode="after")
    def complete_smoke(self) -> Self:
        if tuple(item.stage for item in self.stage_receipts) != SMOKE_STAGES:
            raise ValueError("smoke stages must be complete and ordered")
        for item in self.stage_receipts:
            for name in ("candidate_id", "git_commit", "freeze_sha256", "materialization_sha256", "runtime_instance_id", "runtime_source_sha256"):
                if getattr(item, name) != getattr(self, name):
                    raise ValueError("smoke stage binding mismatch")
            digest = hashlib.sha256(canonical_json_bytes(item) + b"\n").hexdigest()
            if item.outcome != "passed" or getattr(self, item.stage + "_sha256") != digest:
                raise ValueError("smoke stage failed or digest mismatch")
        return self


class CommandEvidence(StrictEvidenceModel):
    name: str
    argv: Annotated[tuple[str, ...], Field(min_length=1, max_length=64)]
    resolved_argv: Annotated[tuple[str, ...], Field(max_length=64)]
    tool_bindings: Annotated[tuple[ToolExecutionBinding, ...], Field(max_length=16)]
    cwd: Literal["backend", "frontend"]
    deadline_seconds: Annotated[int, Field(gt=0)]
    outcome: Outcome
    exit_code: int | None
    started_at: str
    finished_at: str
    stdout_size: Count
    stderr_size: Count
    stdout_sha256: Sha256
    stderr_sha256: Sha256

    @field_validator("started_at", "finished_at")
    @classmethod
    def utc_seconds(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            raise ValueError("timestamp must be exact UTC seconds") from None
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError("timestamp must be exact UTC seconds")
        return value

    @model_validator(mode="after")
    def command(self) -> Self:
        try:
            index = tuple(item[0] for item in D39_REQUIRED_COMMANDS).index(self.name)
        except ValueError:
            raise ValueError("unknown verification command") from None
        if self.argv != D39_REQUIRED_COMMANDS[index][1] or self.deadline_seconds != D39_COMMAND_DEADLINES[index] or self.cwd != ("backend" if index < 5 else "frontend"):
            raise ValueError("command inventory mismatch")
        _sorted_unique(tuple(item.role for item in self.tool_bindings))
        if self.stdout_size + self.stderr_size > 2 * 1024 * 1024 or self.finished_at < self.started_at:
            raise ValueError("command output or timestamp bounds violated")
        if self.outcome == "completed" and self.exit_code is None:
            raise ValueError("completed command requires an exit code")
        roles = tuple(item.role for item in self.tool_bindings)
        expected_roles = ("python_bootstrap", "uv") if index == 0 else ("python",) if index < 5 else ("node", "npx", "pnpm")
        if any(role not in expected_roles for role in roles):
            raise ValueError("command contains an unexpected native tool role")
        if self.outcome == "completed" and roles != expected_roles:
            raise ValueError("completed command requires exact native tool roles")
        executable_alias = "tools/python_bootstrap" if index == 0 else "tools/python_sandbox" if index < 5 else "tools/node"
        expected_argv = (executable_alias, *self.argv[1:]) if index < 5 else (executable_alias, "tools/npx_cli", *self.argv[1:])
        if self.resolved_argv:
            if self.resolved_argv != expected_argv:
                raise ValueError("resolved command argv must match native aliases")
        elif self.outcome != "launch_failed":
            raise ValueError("launched command requires resolved native argv")
        if len({(item.executable.path, item.executable.size, item.executable.sha256) for item in self.tool_bindings}) > 1:
            raise ValueError("shared native executable bindings disagree")
        versions = {"python_bootstrap": "3.12.12", "uv": "0.12.15", "python": "3.12.12", "node": "24.11.1", "pnpm": "10.18.3"}
        launchers = {"uv": "tools/uv_module", "npx": "tools/npx_cli", "pnpm": "tools/pnpm_cjs"}
        total = 0
        for binding in self.tool_bindings:
            if binding.executable.path != executable_alias or (binding.role in versions and binding.version != versions[binding.role]):
                raise ValueError("native tool alias or version mismatch")
            launcher_alias = launchers.get(binding.role)
            if (binding.launcher is None) != (launcher_alias is None) or (binding.launcher is not None and binding.launcher.path != launcher_alias):
                raise ValueError("native tool launcher mismatch")
            for blob in (binding.executable, binding.launcher):
                if blob is not None:
                    if blob.size > 256 * 1024 * 1024:
                        raise ValueError("native tool blob size limit exceeded")
                    total += blob.size
        if total > 1024 * 1024 * 1024:
            raise ValueError("native tool total size limit exceeded")
        return self


class VerificationManifest(StrictEvidenceModel):
    schema_version: Literal[1]
    candidate_id: CandidateId
    git_commit: Commit
    freeze_sha256: Sha256
    verifier_tool_sha256: Sha256
    status: Literal["passed", "failed"]
    commands: Annotated[tuple[CommandEvidence, ...], Field(max_length=9)]
    smoke_manifest_sha256: Sha256 | None
    smoke_manifest: SmokeManifest | None
    secret_scan_passed: bool
    candidate_clean_before: bool
    candidate_clean_after: bool
    candidate_snapshot_before_sha256: Sha256
    candidate_snapshot_after_sha256: Sha256 | None
    materialization_sha256: Sha256
    runtime_instance_id: Sha256
    runtime_source_sha256: Sha256
    runtime_snapshot_after_sha256: Sha256 | None
    cleanup_status: Literal["completed", "failed"]

    @model_validator(mode="after")
    def verification(self) -> Self:
        if tuple((item.name, item.argv) for item in self.commands) != D39_REQUIRED_COMMANDS[:len(self.commands)]:
            raise ValueError("commands must be an attempted ordered prefix")
        if any(item.outcome != "completed" or item.exit_code != 0 for item in self.commands[:-1]):
            raise ValueError("command prefix continued after failure")
        if (self.smoke_manifest is None) != (self.smoke_manifest_sha256 is None):
            raise ValueError("smoke digest and observation must coexist")
        if self.smoke_manifest is not None:
            smoke = self.smoke_manifest
            if hashlib.sha256(canonical_json_bytes(smoke) + b"\n").hexdigest() != self.smoke_manifest_sha256:
                raise ValueError("smoke manifest digest mismatch")
            for name in ("candidate_id", "git_commit", "freeze_sha256", "materialization_sha256", "runtime_instance_id", "runtime_source_sha256"):
                if getattr(smoke, name) != getattr(self, name):
                    raise ValueError("verification smoke binding mismatch")
        if self.status == "passed" and (len(self.commands) != 9 or any(item.outcome != "completed" or item.exit_code != 0 for item in self.commands) or self.smoke_manifest is None or not self.secret_scan_passed or not self.candidate_clean_before or not self.candidate_clean_after or self.candidate_snapshot_before_sha256 != self.candidate_snapshot_after_sha256 or self.runtime_snapshot_after_sha256 != self.runtime_source_sha256 or self.cleanup_status != "completed"):
            raise ValueError("passed verification requires complete actual observations")
        return self
