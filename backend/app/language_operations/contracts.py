"""Structured HTTP values for language requests, previews and execution results."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.interpretation.contracts import CandidateRef, ClarificationProposal, FailureView, InterpretationOutcome, StrictValue
from app.operations.contracts import OperationRequest, OperationResult, OperationTarget
from app.semantic_interpretation.contracts import SearchTrace


class Continuation(StrictValue):
    parent_request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    relation: Literal["answer", "correction", "dismiss"]


class LanguageInput(StrictValue):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    text: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    target: OperationTarget = Field(default_factory=OperationTarget)
    base_revision: int | None = Field(default=None, ge=1)
    review_all: bool = False
    continuation: Continuation | None = None


class LanguageExecution(StrictValue):
    """Acknowledge a stored proposal; no editable operation fields accepted."""

    confirmation_token: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]+$")
    confirm_generation: bool = False


class LanguageDiagnostics(StrictValue):
    retrieval: SearchTrace | None = None
    started_at: float | None = Field(default=None, ge=0)
    candidates: list[CandidateRef] = Field(default_factory=list, max_length=32)
    interpretation_ms: int | None = Field(default=None, ge=0)
    execution_ms: int | None = Field(default=None, ge=0)
    generation_execution_ms: int | None = Field(default=None, ge=0)
    guard_code: Literal["reference", "subtitle_value", "settings_value", "pending_settings", "reading", "empty_settings"] | None = None


class LanguageResponse(StrictValue):
    request_id: str
    core_request_id: str
    mode: Literal["all_tools", "semantic"] = "all_tools"
    status: Literal["interpreting", "ready", "needs_input", "unsupported", "blocked", "error", "completed", "dismissed"]
    project_id: int | None = None
    base_revision: int | None = None
    interpretation: InterpretationOutcome | None = None
    clarification: ClarificationProposal | None = None
    prepared_request: OperationRequest | None = None
    requires_confirmation: bool = False
    confirmation_token: str | None = None
    result: OperationResult | None = None
    failure: FailureView | None = None
    executed: bool = False
    generate_after_save: bool = False
    generation_request: OperationRequest | None = None
    generation_result: OperationResult | None = None
    parent_request_id: str | None = None
    relation: Literal["answer", "correction", "dismiss"] | None = None
    superseded_by: str | None = None
    dialogue_available: bool = False
    diagnostics: LanguageDiagnostics = Field(default_factory=LanguageDiagnostics)


class LanguageError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)
