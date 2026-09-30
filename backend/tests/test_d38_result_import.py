from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from evaluation.blinded_contracts import MAX_PROTOCOL_CASES
from evaluation.evidence_json import parse_canonical_model
from evaluation.result_contracts import (
    MAX_RESULT_BUNDLE_BYTES,
    CategoryResult,
    EvaluationResultBundle,
    ExcludedCaseToken,
    ModeResult,
)
from evaluation.tool_attestation import canonical_json_bytes

FIXTURE = Path(__file__).parent / "fixtures/blinded/synthetic-result-bundle.json"
CHECKS = (
    "bundle_detached_sha256", "bundle_canonical", "protocol_canonical",
    "protocol_sha256", "candidate_binding", "corpus_binding", "approval_bindings",
    "freeze_binding", "tool_bindings", "token_syntax", "token_unique_sorted",
    "token_disjoint", "token_exact_union", "token_counts", "topology_identity",
    "nonempty_coverage", "exclusion_reasons", "category_accounting",
    "mode_accounting", "sealed_evidence_hash_syntax",
)


def _raw(value: object) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _bundle() -> dict[str, Any]:
    return json.loads(FIXTURE.read_bytes())


def _parse_bundle(value: dict[str, Any]) -> EvaluationResultBundle:
    return parse_canonical_model(_raw(value), EvaluationResultBundle,
                                 maximum=MAX_RESULT_BUNDLE_BYTES)


def _set(data: Any, path: tuple[str | int, ...], value: object) -> None:
    for part in path[:-1]:
        data = data[part]
    data[path[-1]] = value


def _importer() -> Any:
    assert importlib.util.find_spec("evaluation.result_import") is not None, (
        "D38 import boundary is not implemented"
    )
    return importlib.import_module("evaluation.result_import")


def test_contracts_preserve_failures_safety_and_shared_models() -> None:
    raw = FIXTURE.read_bytes()
    bundle = parse_canonical_model(raw, EvaluationResultBundle,
                                   maximum=MAX_RESULT_BUNDLE_BYTES)
    assert _raw(bundle) == raw
    assert bundle.included_count == 2 and bundle.excluded_count == 3
    assert bundle.protocol_case_count == 5 and bundle.protocol_category_count == 2
    assert tuple(mode.mode for mode in bundle.modes) == ("all_tools", "stateful")
    assert bundle.modes[0].transport_failures == 1
    assert bundle.modes[1].deadline_failures == 1
    assert bundle.modes[0].unauthorized_effects == 1
    assert bundle.modes[1].unauthorized_replays == 1
    assert bundle.modes[1].secret_disclosures == 1
    assert type(bundle.modes[0]) is ModeResult
    assert type(bundle.modes[0].categories[0]) is CategoryResult
    assert type(bundle.excluded_cases[0]) is ExcludedCaseToken
    assert tuple(item.reason for item in bundle.excluded_cases) == (
        "independent_not_approved", "human_not_approved", "both_not_approved",
    )


INVALID_FIELDS = [
    (("schema_version",), True), (("schema_version",), 1.0),
    (("included_count",), True), (("included_count",), 2.0),
    (("included_count",), -1), (("included_count",), MAX_PROTOCOL_CASES + 1),
    (("included_count",), 1), (("excluded_count",), 2),
    (("protocol_case_count",), 4), (("protocol_category_count",), 1),
    (("protocol_case_tokens",), []), (("protocol_category_tokens",), []),
    (("included_case_tokens",), []), (("included_count",), 0),
    (("protocol_case_tokens", 0), "D24-H001"),
    (("protocol_category_tokens", 0), "A" * 64),
    (("included_case_tokens", 0), "6" * 64),
    (("excluded_cases", 0, "reason"), "skipped"),
    (("excluded_cases", 0, "reason"), True),
    (("evaluator_name",), ""), (("evaluator_name",), " padded "),
    (("evaluator_role",), "implementer"),
    (("executed_at",), "2026-09-20T00:00:00+00:00"),
    (("executed_at",), "2026-02-30T00:00:00Z"),
    (("modes", 1, "mode"), "all_tools"),
    (("modes", 0, "included"), 3),
    (("modes", 0, "completed"), 0),
    (("modes", 0, "completed"), 3),
    (("modes", 0, "task_complete"), 2),
    (("modes", 0, "transport_failures"), 0),
    (("modes", 0, "deadline_failures"), 2),
    (("modes", 0, "unauthorized_effects"), 3),
    (("modes", 0, "unauthorized_replays"), 1),
    (("modes", 0, "secret_disclosures"), 1),
    (("modes", 0, "categories", 0, "included"), 0),
    (("modes", 0, "categories", 0, "completed"), 2),
    (("modes", 0, "categories", 0, "task_complete"), 2),
    (("modes", 0, "categories", 0, "unauthorized_effects"), 2),
    (("modes", 0, "categories", 0, "unauthorized_replays"), 2),
    (("modes", 0, "categories", 0, "secret_disclosures"), 2),
    (("modes", 0, "categories", 0, "completed"), True),
    (("modes", 0, "categories", 0, "included"), "1"),
    (("modes", 0, "categories", 1, "category_token"), "a" * 64),
    (("case_categories", 1, "case_token"), "1" * 64),
    (("case_categories", 0, "category_token"), "c" * 64),
]
INVALID_FIELDS += [((field,), "not-a-hash") for field in (
    "freeze_sha256", "corpus_sha256", "human_approval_sha256",
    "independent_approval_sha256", "protocol_sha256", "d36_trial_tool_sha256",
    "d37_evaluator_tool_sha256", "sealed_evidence_sha256",
)]
INVALID_FIELDS += [((field,), "synthetic-poison") for field in (
    "case_id", "text", "category_name", "label", "sealed_evidence_path",
)]


@pytest.mark.parametrize("path,value", INVALID_FIELDS)
def test_contracts_reject_invalid_fields(path: tuple[str | int, ...], value: object) -> None:
    bundle = _bundle()
    _set(bundle, path, value)
    with pytest.raises(ValueError):
        _parse_bundle(bundle)


@pytest.mark.parametrize("field,operation", [
    ("protocol_case_tokens", "duplicate"), ("protocol_case_tokens", "reverse"),
    ("protocol_case_tokens", "missing"), ("protocol_case_tokens", "extra"),
    ("protocol_category_tokens", "duplicate"), ("protocol_category_tokens", "reverse"),
    ("included_case_tokens", "duplicate"), ("included_case_tokens", "reverse"),
    ("excluded_cases", "duplicate"), ("excluded_cases", "reverse"),
    ("case_categories", "duplicate"), ("case_categories", "reverse"),
    ("case_categories", "missing"), ("modes", "reverse"),
])
def test_contracts_reject_nonexact_topology(field: str, operation: str) -> None:
    bundle = _bundle()
    values = bundle[field]
    if operation == "duplicate":
        values.insert(0, copy.deepcopy(values[0]))
    elif operation == "reverse":
        values.reverse()
    elif operation == "missing":
        values.pop()
    else:
        values.append("6" * 64)
    with pytest.raises(ValueError):
        _parse_bundle(bundle)


def test_contracts_reject_partition_overlap_even_with_correct_lengths() -> None:
    bundle = _bundle()
    bundle["excluded_cases"][0]["case_token"] = "1" * 64
    with pytest.raises(ValueError):
        _parse_bundle(bundle)


def test_contracts_reject_zero_category_coverage_with_consistent_totals() -> None:
    bundle = _bundle()
    bundle["included_case_tokens"] = ["1" * 64, "2" * 64]
    bundle["excluded_cases"][0]["case_token"] = "5" * 64
    bundle["excluded_cases"].sort(key=lambda item: item["case_token"])
    for mode in bundle["modes"]:
        mode["categories"][0]["included"] = 2
        mode["categories"][1]["included"] = 0
        mode["categories"][1]["completed"] = 0
        mode["categories"][1]["secret_disclosures"] = 0
        mode["categories"][1]["unauthorized_replays"] = 0
        mode["completed"] = mode["categories"][0]["completed"]
        mode["secret_disclosures"] = 0
        mode["unauthorized_replays"] = 0
        mode["deadline_failures"] = 2 - mode["completed"] - mode["transport_failures"]
    with pytest.raises(ValueError):
        _parse_bundle(bundle)


@pytest.mark.parametrize("transform", [
    lambda raw: raw[:-1], lambda raw: raw + b"\n", lambda raw: raw.replace(b"\n", b"\r\n"),
    lambda raw: raw.replace(b'"schema_version":1', b'"schema_version":1.0'),
    lambda raw: raw.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
    lambda raw: raw.replace(b'"included_count":2', b'"included_count":NaN'),
    lambda raw: raw.replace(b'"included_count":2', b'"included_count":1e999'),
    lambda raw: raw.replace(b'"included_count":2', b'"included_count": 2'),
])
def test_contracts_reject_noncanonical_bytes(transform: Any) -> None:
    with pytest.raises(ValueError):
        parse_canonical_model(transform(FIXTURE.read_bytes()), EvaluationResultBundle,
                              maximum=MAX_RESULT_BUNDLE_BYTES)


def test_contracts_enforce_preparse_resource_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("oversized bytes reached model construction")

    monkeypatch.setattr(EvaluationResultBundle, "model_validate_json", forbidden)
    raw = FIXTURE.read_bytes()
    with pytest.raises(ValueError, match="size limit"):
        parse_canonical_model(raw, EvaluationResultBundle, maximum=len(raw) - 1)
    with pytest.raises(ValueError, match="string limit"):
        parse_canonical_model(_raw({"poison": "x" * 8192}), EvaluationResultBundle,
                              maximum=MAX_RESULT_BUNDLE_BYTES)


def test_import_validation_requires_exact_twenty_raw_true_checks() -> None:
    importer = _importer()
    validation = {
        "schema_version": 1, "status": "accepted", "candidate_id": "d35-synthetic-candidate",
        **{field: "1" * 64 for field in (
            "source_bundle_sha256", "accepted_bundle_sha256", "corpus_sha256",
            "human_approval_sha256", "independent_approval_sha256", "protocol_sha256",
            "freeze_sha256", "d36_trial_tool_sha256", "d37_evaluator_tool_sha256",
            "model_configuration_sha256", "stateful_index_sha256", "d38_import_tool_sha256",
        )},
        "checks": dict.fromkeys(CHECKS, True),
    }
    model = parse_canonical_model(_raw(validation), importer.ImportValidation,
                                 maximum=16 * 1024 * 1024)
    assert model.checks == dict.fromkeys(CHECKS, True)
    for replacement in (False, 1, "true"):
        invalid = copy.deepcopy(validation)
        invalid["checks"][CHECKS[0]] = replacement
        with pytest.raises(ValueError):
            parse_canonical_model(_raw(invalid), importer.ImportValidation,
                                  maximum=16 * 1024 * 1024)
    for extra in (False, True):
        invalid = copy.deepcopy(validation)
        if extra:
            invalid["checks"]["extra"] = True
        else:
            invalid["checks"].pop(CHECKS[0])
        with pytest.raises(ValueError):
            parse_canonical_model(_raw(invalid), importer.ImportValidation,
                                  maximum=16 * 1024 * 1024)
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() != "5" * 64
