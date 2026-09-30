"""Canonical D37-D40 blinded evaluation result contract."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from evaluation.blinded_contracts import (
    MAX_PROTOCOL_CASES,
    CaseCategoryBinding,
    OpaqueToken,
    ProtocolCount,
    ResultCount,
    Sha256,
)

_COUNT_FIELDS = (
    "included",
    "completed",
    "task_complete",
    "unauthorized_effects",
    "unauthorized_replays",
    "secret_disclosures",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CategoryResult(_StrictModel):
    category_token: OpaqueToken
    included: ResultCount
    completed: ResultCount
    task_complete: ResultCount
    unauthorized_effects: ResultCount
    unauthorized_replays: ResultCount
    secret_disclosures: ResultCount

    @model_validator(mode="after")
    def validate_denominator(self) -> Self:
        if self.task_complete > self.completed or self.completed > self.included:
            raise ValueError("category completion counts exceed their denominator")
        if any(getattr(self, name) > self.included for name in _COUNT_FIELDS[3:]):
            raise ValueError("category safety count exceeds its denominator")
        return self


class ModeResult(_StrictModel):
    mode: Literal["all_tools", "stateful"]
    included: ResultCount
    completed: ResultCount
    task_complete: ResultCount
    unauthorized_effects: ResultCount
    unauthorized_replays: ResultCount
    secret_disclosures: ResultCount
    transport_failures: ResultCount
    deadline_failures: ResultCount
    categories: Annotated[
        tuple[CategoryResult, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)
    ]

    @model_validator(mode="after")
    def validate_denominator(self) -> Self:
        if self.task_complete > self.completed or self.completed > self.included:
            raise ValueError("mode completion counts exceed their denominator")
        bounded = (
            self.unauthorized_effects,
            self.unauthorized_replays,
            self.secret_disclosures,
            self.transport_failures,
            self.deadline_failures,
        )
        if any(value > self.included for value in bounded):
            raise ValueError("mode count exceeds its denominator")
        completion_sum = self.completed + self.transport_failures + self.deadline_failures
        if completion_sum > MAX_PROTOCOL_CASES or completion_sum != self.included:
            raise ValueError("mode completion and failure counts must cover included cases")
        return self


class ExcludedCaseToken(_StrictModel):
    case_token: OpaqueToken
    reason: Literal[
        "both_not_approved",
        "human_not_approved",
        "independent_not_approved",
    ]


class EvaluationResultBundle(_StrictModel):
    schema_version: Literal[1]
    candidate_id: Annotated[str, Field(min_length=1, max_length=128)]
    freeze_sha256: Sha256
    corpus_sha256: Sha256
    human_approval_sha256: Sha256
    independent_approval_sha256: Sha256
    protocol_sha256: Sha256
    d36_trial_tool_sha256: Sha256
    d37_evaluator_tool_sha256: Sha256
    protocol_case_count: ProtocolCount
    protocol_case_tokens: Annotated[
        tuple[OpaqueToken, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)
    ]
    protocol_category_count: ProtocolCount
    protocol_category_tokens: Annotated[
        tuple[OpaqueToken, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)
    ]
    case_categories: Annotated[
        tuple[CaseCategoryBinding, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)
    ]
    included_count: ResultCount
    excluded_count: ResultCount
    included_case_tokens: Annotated[
        tuple[OpaqueToken, ...], Field(min_length=1, max_length=MAX_PROTOCOL_CASES)
    ]
    excluded_cases: Annotated[
        tuple[ExcludedCaseToken, ...], Field(max_length=MAX_PROTOCOL_CASES)
    ]
    evaluator_role: Literal["independent_evaluator"]
    evaluator_name: Annotated[str, Field(min_length=1, max_length=128)]
    executed_at: str
    sealed_evidence_sha256: Sha256
    modes: tuple[ModeResult, ModeResult]

    @field_validator("evaluator_name")
    @classmethod
    def validate_evaluator_name(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("evaluator name must not contain surrounding whitespace")
        return value

    @field_validator("executed_at")
    @classmethod
    def validate_executed_at(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            raise ValueError("execution time must be canonical UTC seconds") from None
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError("execution time must be canonical UTC seconds")
        return value

    @model_validator(mode="after")
    def validate_topology(self) -> Self:
        if self.protocol_case_tokens != tuple(sorted(set(self.protocol_case_tokens))):
            raise ValueError("protocol case tokens must be unique and sorted")
        if self.protocol_category_tokens != tuple(sorted(set(self.protocol_category_tokens))):
            raise ValueError("protocol category tokens must be unique and sorted")
        if self.protocol_case_count != len(self.protocol_case_tokens):
            raise ValueError("protocol case count does not match its tokens")
        if self.protocol_category_count != len(self.protocol_category_tokens):
            raise ValueError("protocol category count does not match its tokens")
        if self.protocol_category_count > self.protocol_case_count:
            raise ValueError("protocol category count cannot exceed case count")
        binding_pairs = tuple(
            (binding.case_token, binding.category_token) for binding in self.case_categories
        )
        if binding_pairs != tuple(sorted(set(binding_pairs))):
            raise ValueError("case/category bindings must be unique and sorted")
        bound_cases = tuple(binding.case_token for binding in self.case_categories)
        if len(bound_cases) != len(set(bound_cases)) or tuple(sorted(bound_cases)) != (
            self.protocol_case_tokens
        ):
            raise ValueError("every protocol case must have exactly one category binding")
        if tuple(sorted({binding.category_token for binding in self.case_categories})) != (
            self.protocol_category_tokens
        ):
            raise ValueError("binding categories must equal the protocol category set")
        return self

    @model_validator(mode="after")
    def validate_partition(self) -> Self:
        if self.included_case_tokens != tuple(sorted(set(self.included_case_tokens))):
            raise ValueError("included case tokens must be unique and sorted")
        excluded_tokens = tuple(item.case_token for item in self.excluded_cases)
        if excluded_tokens != tuple(sorted(set(excluded_tokens))):
            raise ValueError("excluded cases must be unique and sorted")
        if self.included_count != len(self.included_case_tokens) or self.included_count < 1:
            raise ValueError("included count must match a non-empty included set")
        if self.excluded_count != len(self.excluded_cases):
            raise ValueError("excluded count does not match excluded cases")
        included = set(self.included_case_tokens)
        excluded = set(excluded_tokens)
        if included & excluded or included | excluded != set(self.protocol_case_tokens):
            raise ValueError("included and excluded cases must exactly partition the protocol")
        if self.protocol_case_count != self.included_count + self.excluded_count:
            raise ValueError("partition counts must equal protocol case count")
        return self

    @model_validator(mode="after")
    def validate_mode_and_category_counts(self) -> Self:
        if tuple(mode.mode for mode in self.modes) != ("all_tools", "stateful"):
            raise ValueError("result modes must use the exact canonical order")
        included = set(self.included_case_tokens)
        category_by_case = {
            binding.case_token: binding.category_token for binding in self.case_categories
        }
        denominators = {
            category: sum(
                token in included and category_by_case[token] == category
                for token in self.protocol_case_tokens
            )
            for category in self.protocol_category_tokens
        }
        if any(value < 1 for value in denominators.values()):
            raise ValueError("every protocol category must include at least one case")
        for mode in self.modes:
            if mode.included != self.included_count:
                raise ValueError("mode included count must equal bundle included count")
            category_tokens = tuple(category.category_token for category in mode.categories)
            if category_tokens != self.protocol_category_tokens:
                raise ValueError("mode categories must equal the protocol category order")
            for category in mode.categories:
                if category.included != denominators[category.category_token]:
                    raise ValueError("category included count must equal its derived denominator")
            for field in _COUNT_FIELDS:
                total = sum(getattr(category, field) for category in mode.categories)
                if total > MAX_PROTOCOL_CASES or total != getattr(mode, field):
                    raise ValueError("category counts must sum exactly to the mode count")
        return self
