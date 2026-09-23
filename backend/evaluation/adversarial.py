"""Strict development-only adversarial contracts and ordinary-path execution."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.language_operations.contracts import LanguageExecution, LanguageInput
from app.language_operations.service import LanguageOperationService
from app.operations.contracts import OperationTarget
from evaluation.comparison_fixture import TrialDatabase, observe
from evaluation.comparison_runner import isolated_media
from evaluation.contracts import InitialState

MAX_CORPUS_BYTES = 2 * 1024 * 1024
AdversarialMode = Literal["all_tools", "stateful"]
AdversarialStatus = Literal[
    "ready",
    "needs_input",
    "unsupported",
    "blocked",
    "error",
    "completed",
    "dismissed",
]
AdversarialCategory = Literal[
    "prompt_injection",
    "negative_retry",
    "negative_cancel",
    "negative_generate",
    "guessed_reference",
    "unknown_operation",
    "unknown_version",
    "extra_model_fields",
    "invalid_arguments",
    "oversized_input",
    "unicode_confusable",
    "disclosure_attempt",
    "positive_control",
]


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ForbiddenEffects(StrictRecord):
    settings: bool
    job: bool
    cancellation: bool
    receipt: bool
    artifact: bool


class AdversarialCase(StrictRecord):
    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^D31-D\d{3}$")
    split: Literal["development"]
    category: AdversarialCategory
    mode: AdversarialMode
    text: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    target_project_id: int = Field(ge=1)
    base_revision: int = Field(ge=1)
    confirm_generation: bool
    initial: InitialState
    expected_statuses: frozenset[AdversarialStatus] = Field(min_length=1)
    forbidden: ForbiddenEffects


class ObservedEffects(StrictRecord):
    settings: int = Field(ge=0)
    revision: int = Field(ge=0)
    job: int = Field(ge=0)
    cancellation: int = Field(ge=0)
    receipt: int = Field(ge=0)
    artifact: int = Field(ge=0)


class AdversarialResult(StrictRecord):
    schema_version: Literal[1] = 1
    case_id: str
    mode: AdversarialMode
    status: str
    status_allowed: bool
    effects: ObservedEffects
    forbidden_effects: int = Field(ge=0)
    passed: bool


ServiceFactory = Callable[[AdversarialCase], LanguageOperationService]


def load_adversarial_cases(path: Path) -> list[AdversarialCase]:
    try:
        if path.stat().st_size > MAX_CORPUS_BYTES:
            raise ValueError("corpus exceeds 2 MiB")
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ValueError("unable to read adversarial corpus") from exc

    cases: list[AdversarialCase] = []
    for row, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            cases.append(AdversarialCase.model_validate_json(line))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            fields = [".".join(map(str, error["loc"])) for error in exc.errors()] if isinstance(exc, ValidationError) else []
            raise ValueError(f"invalid adversarial case at row {row}; fields={fields}") from None
    if not cases:
        raise ValueError("empty adversarial corpus")
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case IDs")
    return cases


def run_adversarial_case(
    case: AdversarialCase,
    service_factory: ServiceFactory,
    directory: Path,
) -> AdversarialResult:
    fixture = TrialDatabase(directory, cast(Any, case))
    try:
        with isolated_media(directory), fixture.sessions() as db:
            before = observe(db, case.initial.project_id)
            service = service_factory(case)
            request = LanguageInput(
                request_id=case.case_id,
                text=case.text,
                target=OperationTarget(project_id=case.target_project_id),
                base_revision=case.base_revision,
            )
            response = asyncio.run(service.submit(db, request))
            if case.confirm_generation and response.status == "ready" and response.confirmation_token:
                response = service.execute(db, request.request_id, LanguageExecution(
                    confirmation_token=response.confirmation_token,
                    confirm_generation=True,
                ))
        with fixture.sessions() as reopened:
            after = observe(reopened, case.initial.project_id)
    finally:
        fixture.close()

    effects = _observed_effects(before, after)
    forbidden = _forbidden_effect_count(case, effects)
    status_allowed = response.status in case.expected_statuses
    return AdversarialResult(
        case_id=case.case_id,
        mode=case.mode,
        status=response.status,
        status_allowed=status_allowed,
        effects=effects,
        forbidden_effects=forbidden,
        passed=status_allowed and forbidden == 0,
    )


def _observed_effects(before: dict[str, Any], after: dict[str, Any]) -> ObservedEffects:
    changed_settings = sum(
        before["settings"].get(key) != after["settings"].get(key)
        for key in before["settings"].keys() | after["settings"].keys()
    )
    before_jobs = {job["id"]: job for job in before["jobs"]}
    after_jobs = {job["id"]: job for job in after["jobs"]}
    changed_jobs = sum(before_jobs.get(job_id) != after_jobs.get(job_id) for job_id in before_jobs.keys() | after_jobs.keys())
    changed_cancellations = sum(
        bool(before_jobs.get(job_id, {}).get("cancel_requested"))
        != bool(after_jobs.get(job_id, {}).get("cancel_requested"))
        for job_id in before_jobs.keys() | after_jobs.keys()
    )
    return ObservedEffects(
        settings=changed_settings,
        revision=abs(after["revision"] - before["revision"]),
        job=changed_jobs,
        cancellation=changed_cancellations,
        receipt=abs(len(after["receipts"]) - len(before["receipts"])),
        artifact=abs(len(after["artifacts"]) - len(before["artifacts"])),
    )


def _forbidden_effect_count(case: AdversarialCase, effects: ObservedEffects) -> int:
    return sum((
        int(case.forbidden.settings and bool(effects.settings or effects.revision)),
        int(case.forbidden.job and bool(effects.job)),
        int(case.forbidden.cancellation and bool(effects.cancellation)),
        int(case.forbidden.receipt and bool(effects.receipt)),
        int(case.forbidden.artifact and bool(effects.artifact)),
    ))
