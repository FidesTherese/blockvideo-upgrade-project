"""Strict label-free wire contracts for one external D36 candidate trial."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_IDENTIFIER = 128
MAX_REVISION = 10**12
MAX_DATABASE_ID = 2**63 - 1


class StrictUnlabeledRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class UnlabeledPronunciation(StrictUnlabeledRecord):
    surface: str = Field(min_length=1, max_length=80)
    reading: str = Field(min_length=1, max_length=160, pattern=r"^[ァ-ヴー]+$")
    accent: int | None = Field(default=None, ge=0, le=1000)


class UnlabeledSettings(StrictUnlabeledRecord):
    subtitle_font_size: int = Field(ge=16, le=120)
    voicevox_speed_scale: float = Field(ge=0.5, le=2.0)
    voicevox_speaker_id: int = Field(ge=0, le=100000)
    pronunciation_overrides: tuple[UnlabeledPronunciation, ...] = Field(max_length=100, strict=False)
    narration_pacing_mode: Literal["adaptive", "fixed"]
    narration_sentence_pause_seconds: float = Field(ge=0, le=5)


class UnlabeledSettingsPatch(StrictUnlabeledRecord):
    subtitle_font_size: int | None = Field(default=None, ge=16, le=120)
    voicevox_speed_scale: float | None = Field(default=None, ge=0.5, le=2.0)
    voicevox_speaker_id: int | None = Field(default=None, ge=0, le=100000)
    pronunciation_overrides: tuple[UnlabeledPronunciation, ...] | None = Field(default=None, max_length=100, strict=False)
    narration_pacing_mode: Literal["adaptive", "fixed"] | None = None
    narration_sentence_pause_seconds: float | None = Field(default=None, ge=0, le=5)

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("settings patch must contain a consumed field")
        return self


class UnlabeledProject(StrictUnlabeledRecord):
    project_id: int = Field(ge=1, le=MAX_DATABASE_ID)
    revision: int = Field(ge=1, le=MAX_REVISION)
    settings: UnlabeledSettings
    project_status: Literal[
        "pending", "splitting", "planning", "generating", "rendering",
        "completed", "failed", "cancelled",
    ]


class UnlabeledInitialJob(StrictUnlabeledRecord):
    id: int = Field(ge=1, le=MAX_DATABASE_ID)
    project_id: int = Field(ge=1, le=MAX_DATABASE_ID)
    status: Literal["pending", "running", "completed", "failed", "cancelled", "unknown"]
    input_revision: int = Field(ge=1, le=MAX_REVISION)
    cancel_requested: bool
    input_settings: UnlabeledSettings
    kind: Literal["full", "rerender"]
    block_index: int | None = Field(default=None, ge=0, le=100000)
    parent_job_id: int | None = Field(default=None, ge=1, le=MAX_DATABASE_ID)


class UnlabeledInitialHistory(StrictUnlabeledRecord):
    project_id: int | None = Field(default=None, ge=1, le=MAX_DATABASE_ID)
    revision: int = Field(ge=1, le=MAX_REVISION)
    settings: UnlabeledSettings
    changed_fields: tuple[Literal[
        "subtitle_font_size", "voicevox_speed_scale", "voicevox_speaker_id",
        "pronunciation_overrides", "narration_pacing_mode",
        "narration_sentence_pause_seconds",
    ], ...] = Field(default=(), max_length=6, strict=False)
    restored_from_revision: int | None = Field(default=None, ge=1, le=MAX_REVISION)


class UnlabeledInitialArtifact(StrictUnlabeledRecord):
    id: int = Field(ge=1, le=MAX_DATABASE_ID)
    project_id: int = Field(ge=1, le=MAX_DATABASE_ID)
    job_id: int | None = Field(default=None, ge=1, le=MAX_DATABASE_ID)
    revision: int | None = Field(default=None, ge=1, le=MAX_REVISION)
    file_content_hex: str = Field(default="78", max_length=8192, pattern=r"^(?:[0-9a-f]{2})*$")
    file_size: int = Field(default=1, ge=0, le=4096)
    file_sha256: str = Field(default=hashlib.sha256(b"x").hexdigest(), pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def content_identity_matches(self) -> Self:
        content = bytes.fromhex(self.file_content_hex)
        if len(content) != self.file_size or hashlib.sha256(content).hexdigest() != self.file_sha256:
            raise ValueError("artifact content identity mismatch")
        return self


class UnlabeledInitialReceipt(StrictUnlabeledRecord):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    operation_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9.-]*$")
    operation_version: int = Field(ge=1, le=100)
    project_id: int = Field(ge=1, le=MAX_DATABASE_ID)
    base_revision: int = Field(ge=1, le=MAX_REVISION)
    result_revision: int = Field(ge=1, le=MAX_REVISION)
    generation_requested: bool
    job_id: int | None = Field(default=None, ge=1, le=MAX_DATABASE_ID)
    canonical_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class UnlabeledInitialExternalCall(StrictUnlabeledRecord):
    id: int = Field(ge=1, le=MAX_DATABASE_ID)
    job_id: int = Field(ge=1, le=MAX_DATABASE_ID)
    fingerprint: str = Field(min_length=1, max_length=64)
    provider: Literal["synthetic"] = "synthetic"
    endpoint: Literal["https://synthetic.invalid/d36"] = "https://synthetic.invalid/d36"
    remote_side_effect: bool
    status: Literal["in_flight", "succeeded", "failed", "unknown"]
    attempts: int = Field(default=1, ge=1, le=100)
    response_status: int | None = Field(default=None, ge=100, le=599)
    response_body_hex: str | None = Field(default=None, max_length=8192, pattern=r"^(?:[0-9a-f]{2})*$")
    response_body_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    response_content_type: Literal["application/json"] | None = None
    provider_response_id: str | None = Field(default=None, min_length=1, max_length=128)
    error_code: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")

    @model_validator(mode="after")
    def response_identity_matches(self) -> Self:
        if (self.response_body_hex is None) != (self.response_body_sha256 is None):
            raise ValueError("external response body and hash must be supplied together")
        if self.response_body_hex is not None:
            content = bytes.fromhex(self.response_body_hex)
            if hashlib.sha256(content).hexdigest() != self.response_body_sha256:
                raise ValueError("external response identity mismatch")
        return self


class UnlabeledOperationArguments(StrictUnlabeledRecord):
    settings: UnlabeledSettingsPatch | None = None
    value: int | None = Field(default=None, ge=16, le=120)
    delta: int | None = Field(default=None, ge=-104, le=104)
    subtitle_font_size: int | None = Field(default=None, ge=16, le=120)
    subtitle_font_size_delta: int | None = Field(default=None, ge=-104, le=104)
    voicevox_speed_scale: float | None = Field(default=None, ge=0.5, le=2.0)
    voicevox_speaker_id: int | None = Field(default=None, ge=0, le=100000)
    pronunciation_overrides: tuple[UnlabeledPronunciation, ...] | None = Field(default=None, max_length=100, strict=False)
    narration_pacing_mode: Literal["adaptive", "fixed"] | None = None
    narration_sentence_pause_seconds: float | None = Field(default=None, ge=0, le=5)
    revision: int | None = Field(default=None, ge=1, le=MAX_REVISION)
    job_id: int | None = Field(default=None, ge=1, le=MAX_DATABASE_ID)
    block_index: int | None = Field(default=None, ge=0, le=100000)
    kind: Literal["full", "rerender"] | None = None


class UnlabeledOperationProposal(StrictUnlabeledRecord):
    kind: Literal["operation"]
    operation_id: Literal[
        "project.subtitle-font-size.set", "project.subtitle-font-size.adjust",
        "project.settings.update", "project.status.get", "project.generation.start",
        "project.generation.cancel", "project.generation.retry", "project.settings.restore",
    ]
    operation_version: int = Field(ge=1, le=2)
    arguments: UnlabeledOperationArguments
    generate_after_save: bool

    @model_validator(mode="after")
    def arguments_match_operation(self) -> Self:
        supplied = set(self.arguments.model_dump(exclude_none=True))
        allowed = {
            "project.subtitle-font-size.set": {"value"},
            "project.subtitle-font-size.adjust": {"delta"},
            "project.settings.update": ({
                "subtitle_font_size", "voicevox_speed_scale", "voicevox_speaker_id",
                "pronunciation_overrides", "narration_pacing_mode", "narration_sentence_pause_seconds",
            } if self.operation_version == 1 else {"settings", "subtitle_font_size_delta"}),
            "project.status.get": set(),
            "project.generation.start": {"kind", "block_index"},
            "project.generation.cancel": {"job_id"},
            "project.generation.retry": {"job_id"},
            "project.settings.restore": {"revision"},
        }[self.operation_id]
        if supplied - allowed:
            raise ValueError("proposal arguments do not belong to operation")
        return self


class UnlabeledClarificationProposal(StrictUnlabeledRecord):
    kind: Literal["clarification"]
    question: str = Field(min_length=1, max_length=240)
    missing_fields: tuple[Literal["target", "arguments", "revision", "job_id"], ...] = Field(max_length=16, strict=False)


UnlabeledPriorProposal = Annotated[
    UnlabeledOperationProposal | UnlabeledClarificationProposal,
    Field(discriminator="kind"),
]


class UnlabeledInitialPriorTurn(StrictUnlabeledRecord):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    project_id: int = Field(ge=1, le=MAX_DATABASE_ID)
    base_revision: int = Field(ge=1, le=MAX_REVISION)
    status: Literal["ready", "needs_input", "unsupported", "blocked", "error", "completed", "dismissed"]
    question: str | None = Field(default=None, min_length=1, max_length=240)
    result_revision: int | None = Field(default=None, ge=1, le=MAX_REVISION)
    settings_saved: bool
    proposal: UnlabeledPriorProposal | None = None
    text: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    relation: Literal["answer", "correction", "dismiss"] | None = None


class UnlabeledInitialState(StrictUnlabeledRecord):
    project_id: int = Field(ge=1, le=MAX_DATABASE_ID)
    revision: int = Field(ge=1, le=MAX_REVISION)
    settings: UnlabeledSettings
    project_status: Literal[
        "pending", "splitting", "planning", "generating", "rendering",
        "completed", "failed", "cancelled",
    ]
    additional_projects: tuple[UnlabeledProject, ...] = Field(default=(), max_length=16, strict=False)
    jobs: tuple[UnlabeledInitialJob, ...] = Field(max_length=32, strict=False)
    history: tuple[UnlabeledInitialHistory, ...] = Field(max_length=32, strict=False)
    artifact_revisions: tuple[int, ...] = Field(default=(), max_length=32, strict=False)
    artifacts: tuple[UnlabeledInitialArtifact, ...] = Field(default=(), max_length=32, strict=False)
    receipts: tuple[UnlabeledInitialReceipt, ...] = Field(default=(), max_length=32, strict=False)
    external_calls: tuple[UnlabeledInitialExternalCall, ...] = Field(default=(), max_length=32, strict=False)
    prior_turns: tuple[UnlabeledInitialPriorTurn, ...] = Field(max_length=8, strict=False)

    @model_validator(mode="after")
    def unique_owned_records(self) -> Self:
        project_ids = [self.project_id, *(item.project_id for item in self.additional_projects)]
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("project IDs must be unique")
        allowed = set(project_ids)
        if any(item.project_id not in allowed for item in self.jobs):
            raise ValueError("job references unknown project")
        if any(item.project_id not in allowed for item in self.artifacts):
            raise ValueError("artifact references unknown project")
        collections = (
            ("job", [item.id for item in self.jobs]),
            ("artifact", [item.id for item in self.artifacts]),
            ("receipt", [item.request_id for item in self.receipts]),
            ("external call", [item.id for item in self.external_calls]),
            ("prior turn", [item.request_id for item in self.prior_turns]),
            ("history", [(item.project_id or self.project_id, item.revision) for item in self.history]),
        )
        for name, identities in collections:
            if len(identities) != len(set(identities)):
                raise ValueError(f"{name} identities must be unique")
        jobs = {item.id: item for item in self.jobs}
        if any(item.job_id not in jobs for item in self.external_calls):
            raise ValueError("external call references unknown job")
        if any(item.job_id is not None and item.job_id not in jobs for item in self.artifacts):
            raise ValueError("artifact references unknown job")
        for item in self.jobs:
            owner_revision = self.revision if item.project_id == self.project_id else next(
                project.revision for project in self.additional_projects if project.project_id == item.project_id
            )
            if item.status in {"pending", "running"} and item.input_revision != owner_revision:
                raise ValueError("active job input revision must equal owner revision")
        return self


class UnlabeledContinuation(StrictUnlabeledRecord):
    parent_request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    relation: Literal["answer", "correction", "dismiss"]


class UnlabeledRequest(StrictUnlabeledRecord):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    text: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    target_project_id: int | None = Field(default=None, ge=1, le=MAX_DATABASE_ID)
    base_revision: int | None = Field(default=None, ge=1, le=MAX_REVISION)
    continuation: UnlabeledContinuation | None = None


class _RequestEvent(StrictUnlabeledRecord):
    request: UnlabeledRequest


class UnlabeledNormalEvent(_RequestEvent):
    kind: Literal["none", "resend_identical", "restart_resend", "concurrent_identical", "confirm_generation", "confirm_twice"]


class UnlabeledDifferentBodyEvent(_RequestEvent):
    kind: Literal["same_id_different_body"]
    replacement_text: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    replacement_target_project_id: int | None = Field(default=None, ge=1, le=MAX_DATABASE_ID)


class UnlabeledRevisionRaceEvent(_RequestEvent):
    kind: Literal["revision_race"]
    external_revision: int = Field(ge=1, le=MAX_REVISION)
    external_settings: UnlabeledSettingsPatch


class UnlabeledSwitchTargetEvent(_RequestEvent):
    kind: Literal["switch_target"]
    selected_project_id_after: int = Field(ge=1, le=MAX_DATABASE_ID)
    replacement_text: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    replacement_target_project_id: int = Field(ge=1, le=MAX_DATABASE_ID)


UnlabeledEvent = Annotated[
    UnlabeledNormalEvent | UnlabeledDifferentBodyEvent | UnlabeledRevisionRaceEvent | UnlabeledSwitchTargetEvent,
    Field(discriminator="kind"),
]


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def canonical_case_sha256(value: object) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json", exclude={"case_sha256"}, exclude_unset=True)
    elif isinstance(value, dict):
        payload = {key: item for key, item in value.items() if key != "case_sha256"}
    else:
        raise TypeError("case must be a model or mapping")
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


class UnlabeledTrialCase(StrictUnlabeledRecord):
    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^D24-H\d{3}$")
    group_id: str = Field(pattern=r"^D24-HG\d{2}$")
    category: Literal[
        "paraphrase", "negation", "omission", "correction", "compound", "blocked",
        "unsupported", "resend", "race", "boundary", "target", "confirmation",
        "history", "failure", "status",
    ]
    split: Literal["held_out"]
    event: UnlabeledEvent
    initial: UnlabeledInitialState
    case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_content_hash(self) -> Self:
        if self.case_sha256 != canonical_case_sha256(self):
            raise ValueError("case_sha256 does not match canonical case content")
        return self
