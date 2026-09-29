"""Strict label-free wire contracts for one external D36 candidate trial."""
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictUnlabeledRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class UnlabeledPronunciation(StrictUnlabeledRecord):
    surface: str = Field(min_length=1, max_length=100)
    reading: str = Field(min_length=1, max_length=200)
    accent: int | None = Field(default=None, ge=0)


class UnlabeledSettings(StrictUnlabeledRecord):
    subtitle_font_size: int = Field(ge=16, le=160)
    voicevox_speed_scale: float = Field(gt=0, le=4)
    voicevox_speaker_id: int = Field(ge=0)
    pronunciation_overrides: tuple[UnlabeledPronunciation, ...] = Field(max_length=100)
    narration_pacing_mode: Literal["adaptive", "fixed"]
    narration_sentence_pause_seconds: float = Field(ge=0, le=10)


class UnlabeledSettingsPatch(StrictUnlabeledRecord):
    subtitle_font_size: int | None = Field(default=None, ge=16, le=160)
    voicevox_speed_scale: float | None = Field(default=None, gt=0, le=4)
    voicevox_speaker_id: int | None = Field(default=None, ge=0)
    pronunciation_overrides: tuple[UnlabeledPronunciation, ...] | None = Field(default=None, max_length=100)
    narration_pacing_mode: Literal["adaptive", "fixed"] | None = None
    narration_sentence_pause_seconds: float | None = Field(default=None, ge=0, le=10)


class UnlabeledInitialJob(StrictUnlabeledRecord):
    id: int = Field(ge=1)
    project_id: int = Field(ge=1)
    status: Literal["pending", "running", "completed", "failed", "cancelled", "unknown"]
    input_revision: int = Field(ge=1)
    cancel_requested: bool
    input_settings: UnlabeledSettingsPatch
    kind: str = Field(min_length=1, max_length=32)


class UnlabeledInitialHistory(StrictUnlabeledRecord):
    revision: int = Field(ge=1)
    settings: UnlabeledSettings


class UnlabeledOperationArguments(StrictUnlabeledRecord):
    value: int | float | str | None = None
    subtitle_font_size: int | None = Field(default=None, ge=16, le=160)
    voicevox_speed_scale: float | None = Field(default=None, gt=0, le=4)
    voicevox_speaker_id: int | None = Field(default=None, ge=0)
    pronunciation_overrides: tuple[UnlabeledPronunciation, ...] | None = Field(default=None, max_length=100)
    revision: int | None = Field(default=None, ge=1)
    job_id: int | None = Field(default=None, ge=1)
    block_index: int | None = Field(default=None, ge=0)
    kind: Literal["full", "rerender"] | None = None


class UnlabeledPriorProposal(StrictUnlabeledRecord):
    kind: Literal["operation", "clarification"]
    operation_id: str | None = Field(default=None, min_length=1, max_length=128)
    operation_version: int | None = Field(default=None, ge=1)
    arguments: UnlabeledOperationArguments | None = None
    generate_after_save: bool | None = None
    question: str | None = Field(default=None, min_length=1, max_length=240)
    missing_fields: tuple[str, ...] | None = Field(default=None, max_length=16)

    @model_validator(mode="after")
    def consistent_kind(self) -> Self:
        operation_fields = (self.operation_id, self.operation_version, self.arguments, self.generate_after_save)
        if self.kind == "operation" and any(value is None for value in operation_fields):
            raise ValueError("operation prior proposal requires operation fields")
        if self.kind == "clarification" and (self.question is None or self.missing_fields is None):
            raise ValueError("clarification prior proposal requires question and missing_fields")
        return self


class UnlabeledInitialPriorTurn(StrictUnlabeledRecord):
    request_id: str = Field(min_length=1, max_length=128)
    project_id: int = Field(ge=1)
    base_revision: int = Field(ge=1)
    status: str = Field(min_length=1, max_length=32)
    question: str | None = Field(default=None, min_length=1, max_length=240)
    result_revision: int | None = Field(default=None, ge=1)
    settings_saved: bool
    proposal: UnlabeledPriorProposal | None = None
    text: str = Field(min_length=1, max_length=2000)


class UnlabeledInitialState(StrictUnlabeledRecord):
    project_id: int = Field(ge=1)
    revision: int = Field(ge=1)
    settings: UnlabeledSettings
    project_status: Literal[
        "pending", "splitting", "planning", "generating", "rendering",
        "completed", "failed", "cancelled",
    ]
    jobs: tuple[UnlabeledInitialJob, ...] = Field(max_length=32)
    history: tuple[UnlabeledInitialHistory, ...] = Field(max_length=32)
    artifact_revisions: tuple[int, ...] = Field(max_length=32)
    prior_turns: tuple[UnlabeledInitialPriorTurn, ...] = Field(max_length=8)


class UnlabeledContinuation(StrictUnlabeledRecord):
    parent_request_id: str = Field(min_length=1, max_length=128)
    relation: Literal["answer", "correction", "dismiss"]


class UnlabeledRequest(StrictUnlabeledRecord):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    text: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    target_project_id: int | None = Field(default=None, ge=1)
    base_revision: int | None = Field(default=None, ge=1)
    continuation: UnlabeledContinuation | None = None


class UnlabeledEvent(StrictUnlabeledRecord):
    kind: Literal[
        "none", "resend_identical", "restart_resend", "same_id_different_body",
        "concurrent_identical", "revision_race", "confirm_generation",
        "confirm_twice", "switch_target",
    ]
    request: UnlabeledRequest
    external_revision: int | None = Field(default=None, ge=1)
    external_settings: UnlabeledSettingsPatch | None = None
    replacement_text: str | None = Field(default=None, min_length=1, max_length=2000)
    selected_project_id_after: int | None = Field(default=None, ge=1)
    action: str | None = Field(default=None, min_length=1, max_length=64)
    when: str | None = Field(default=None, min_length=1, max_length=64)
    then: str | None = Field(default=None, min_length=1, max_length=64)


class UnlabeledTrialCase(StrictUnlabeledRecord):
    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^D24-H\d{3}$")
    group_id: str = Field(pattern=r"^D24-HG\d{2}$")
    category: str = Field(min_length=1, max_length=64)
    split: Literal["held_out"]
    event: UnlabeledEvent
    initial: UnlabeledInitialState
    case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
