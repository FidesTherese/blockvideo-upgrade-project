from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evaluation.blinded_contracts import (
    EvaluationProtocol,
    approval_partition,
    case_category_bindings,
    opaque_case_token,
    opaque_category_token,
    token_key,
)
from evaluation.contracts import Case
from evaluation.corpus import eligibility, load_cases, load_review
from evaluation.result_contracts import EvaluationResultBundle
from evaluation.tool_attestation import aggregate_fingerprints, fingerprint_file

FIXTURES = Path(__file__).parent / "fixtures" / "blinded"
SYNTHETIC_KEY = bytes(range(32))
CASE_TOKENS = (
    "3803e6c2ed9d44b3b8b7e2cdec697221bcc4accf0530d3c90627b672249638c0",
    "a68dbb976cdcc2e99970a3d622629f0a03b1437df63e9678887433d0ef36bcfd",
    "b41f76271d1f585b9eb4bc8ae64164e053e0f4d9f3c4b05bf54ff6fcc58867a1",
    "b4ea897a8b2a0e81ef6f65e81c91bc791f220be1f33789408e4a2215975dbbef",
    "e3b8c902c18aa3bede1a4c6edaaae7bf97fbd30eff96c42d102a9cffdfe5c849",
)
CATEGORY_TOKENS = (
    "457a76aeb467da2b9216e9a4c8ace6c6ac433279beadedce04cbdfef3b68ab8c",
    "f2c22f7b5fc64960d2e64e1f86851619c99122f4e36e74f7e325249b5f4520e1",
)
BINDINGS = (
    {"case_token": CASE_TOKENS[0], "category_token": CATEGORY_TOKENS[0]},
    {"case_token": CASE_TOKENS[1], "category_token": CATEGORY_TOKENS[0]},
    {"case_token": CASE_TOKENS[2], "category_token": CATEGORY_TOKENS[0]},
    {"case_token": CASE_TOKENS[3], "category_token": CATEGORY_TOKENS[1]},
    {"case_token": CASE_TOKENS[4], "category_token": CATEGORY_TOKENS[1]},
)
INCLUDED = (CASE_TOKENS[0], CASE_TOKENS[4])
EXCLUDED = (
    {"case_token": CASE_TOKENS[1], "reason": "independent_not_approved"},
    {"case_token": CASE_TOKENS[2], "reason": "human_not_approved"},
    {"case_token": CASE_TOKENS[3], "reason": "both_not_approved"},
)
HASHES = {
    "freeze_sha256": "1" * 64,
    "corpus_sha256": "2" * 64,
    "human_approval_sha256": "3" * 64,
    "independent_approval_sha256": "4" * 64,
    "protocol_sha256": "5" * 64,
    "d36_trial_tool_sha256": "6" * 64,
    "d37_evaluator_tool_sha256": "7" * 64,
}


def _cases() -> list[Case]:
    return load_cases(FIXTURES / "synthetic-held-out.jsonl")


def _protocol_data() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "candidate_id": "d35-synthetic-candidate",
        "modes": ("all_tools", "stateful"),
        "per_call_deadline_seconds": 180,
        "maximum_model_calls": 4,
        "isolation": "fresh_case_state_under_source_group",
        "corpus_sha256": HASHES["corpus_sha256"],
        "human_approval_sha256": HASHES["human_approval_sha256"],
        "independent_approval_sha256": HASHES["independent_approval_sha256"],
        "freeze_sha256": HASHES["freeze_sha256"],
        "d36_trial_tool_sha256": HASHES["d36_trial_tool_sha256"],
        "d37_evaluator_tool_sha256": HASHES["d37_evaluator_tool_sha256"],
        "model_configuration_sha256": "8" * 64,
        "stateful_index_sha256": "9" * 64,
        "category_count": 2,
        "category_tokens": CATEGORY_TOKENS,
        "case_count": 5,
        "case_tokens": CASE_TOKENS,
        "case_categories": BINDINGS,
    }


def _category_results() -> list[dict[str, Any]]:
    return [
        {
            "category_token": CATEGORY_TOKENS[0],
            "included": 1,
            "completed": 1,
            "task_complete": 1,
            "unauthorized_effects": 0,
            "unauthorized_replays": 0,
            "secret_disclosures": 0,
        },
        {
            "category_token": CATEGORY_TOKENS[1],
            "included": 1,
            "completed": 1,
            "task_complete": 1,
            "unauthorized_effects": 0,
            "unauthorized_replays": 0,
            "secret_disclosures": 0,
        },
    ]


def _mode(mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "included": 2,
        "completed": 2,
        "task_complete": 2,
        "unauthorized_effects": 0,
        "unauthorized_replays": 0,
        "secret_disclosures": 0,
        "transport_failures": 0,
        "deadline_failures": 0,
        "categories": tuple(_category_results()),
    }


def _bundle_data() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "candidate_id": "d35-synthetic-candidate",
        **HASHES,
        "protocol_case_count": 5,
        "protocol_case_tokens": CASE_TOKENS,
        "protocol_category_count": 2,
        "protocol_category_tokens": CATEGORY_TOKENS,
        "case_categories": BINDINGS,
        "included_count": 2,
        "excluded_count": 3,
        "included_case_tokens": INCLUDED,
        "excluded_cases": EXCLUDED,
        "evaluator_role": "independent_evaluator",
        "evaluator_name": "Synthetic independent evaluator",
        "executed_at": "2026-09-20T00:00:00Z",
        "sealed_evidence_sha256": "a" * 64,
        "modes": (_mode("all_tools"), _mode("stateful")),
    }


def test_protocol_tokens_are_domain_separated_lowercase_hmac_sha256() -> None:
    assert opaque_case_token(SYNTHETIC_KEY, "D24-H001") == CASE_TOKENS[4]
    assert opaque_category_token(SYNTHETIC_KEY, "paraphrase") == CATEGORY_TOKENS[1]
    assert opaque_category_token(SYNTHETIC_KEY, "D24-H001") != CASE_TOKENS[4]
    assert opaque_case_token(bytes(reversed(SYNTHETIC_KEY)), "D24-H001") != CASE_TOKENS[4]
    assert opaque_case_token(SYNTHETIC_KEY, "D24-H002") == CASE_TOKENS[0]


@pytest.mark.parametrize("size", [0, 31, 33, 64])
def test_protocol_token_key_requires_exactly_32_raw_bytes(tmp_path: Path, size: int) -> None:
    path = tmp_path / "token.key"
    path.write_bytes(b"x" * size)
    with pytest.raises(ValueError, match="exactly 32"):
        with token_key(path):
            pass


def test_protocol_token_key_buffer_is_zeroed_after_use(tmp_path: Path) -> None:
    path = tmp_path / "token.key"
    path.write_bytes(SYNTHETIC_KEY)
    with token_key(path) as key:
        retained = key
        assert bytes(key) == SYNTHETIC_KEY
    assert retained == bytearray(32)


def test_protocol_category_binding_uses_first_d24_tag() -> None:
    bindings = case_category_bindings(_cases(), SYNTHETIC_KEY)
    by_case = {item.case_token: item.category_token for item in bindings}
    assert by_case[CASE_TOKENS[4]] == CATEGORY_TOKENS[1]
    assert by_case[CASE_TOKENS[4]] != "76095133a1dfa74355592beebcf4a4f6942381834362260487bc7122e4e3af25"
    assert tuple(item.case_token for item in bindings) == CASE_TOKENS


def test_protocol_contract_is_strict_and_carries_complete_sorted_topology() -> None:
    protocol = EvaluationProtocol.model_validate(_protocol_data())
    assert protocol.modes == ("all_tools", "stateful")
    assert protocol.case_count == len(protocol.case_tokens) == 5
    assert protocol.category_count == len(protocol.category_tokens) == 2
    assert tuple(item.model_dump(mode="json") for item in protocol.case_categories) == BINDINGS
    with pytest.raises(ValidationError):
        EvaluationProtocol.model_validate({**_protocol_data(), "approval_sha256": "f" * 64})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("modes", ["stateful", "all_tools"]),
        ("case_tokens", list(reversed(CASE_TOKENS))),
        ("case_count", 4),
        ("category_tokens", [CATEGORY_TOKENS[0]]),
        ("case_categories", list(BINDINGS[:-1])),
    ],
)
def test_protocol_rejects_incomplete_or_noncanonical_topology(field: str, value: object) -> None:
    data = _protocol_data()
    data[field] = value
    with pytest.raises(ValidationError):
        EvaluationProtocol.model_validate(data)


def test_approval_gate_requires_both_bound_review_ledgers() -> None:
    cases = _cases()
    human = load_review(FIXTURES / "synthetic-human-review.json", cases, "human")
    independent = load_review(
        FIXTURES / "synthetic-independent-review.json", cases, "independent_ai"
    )
    gate = eligibility(cases, human, independent)
    included, excluded = approval_partition(cases, human, independent, SYNTHETIC_KEY)
    assert gate["eligible_case_ids"] == ["D24-H001", "D24-H002"]
    assert included == INCLUDED
    assert tuple(item.model_dump(mode="json") for item in excluded) == EXCLUDED


def test_approval_bundle_is_strict_redacted_and_binds_all_independent_hashes() -> None:
    bundle = EvaluationResultBundle.model_validate(_bundle_data())
    raw = bundle.model_dump_json().encode("utf-8")
    for forbidden in (
        b"D24-H",
        b"synthetic request",
        b"paraphrase",
        b"negation",
        b'"decision":"approved"',
        b"expected",
    ):
        assert forbidden not in raw
    assert bundle.human_approval_sha256 != bundle.independent_approval_sha256
    assert bundle.d36_trial_tool_sha256 != bundle.d37_evaluator_tool_sha256
    with pytest.raises(ValidationError):
        EvaluationResultBundle.model_validate({**_bundle_data(), "approval_sha256": "f" * 64})


def test_protocol_and_approval_contracts_have_the_exact_shared_field_inventory() -> None:
    assert tuple(EvaluationProtocol.model_fields) == (
        "schema_version",
        "candidate_id",
        "modes",
        "per_call_deadline_seconds",
        "maximum_model_calls",
        "isolation",
        "corpus_sha256",
        "human_approval_sha256",
        "independent_approval_sha256",
        "freeze_sha256",
        "d36_trial_tool_sha256",
        "d37_evaluator_tool_sha256",
        "model_configuration_sha256",
        "stateful_index_sha256",
        "category_count",
        "category_tokens",
        "case_count",
        "case_tokens",
        "case_categories",
    )
    assert tuple(EvaluationResultBundle.model_fields) == (
        "schema_version",
        "candidate_id",
        "freeze_sha256",
        "corpus_sha256",
        "human_approval_sha256",
        "independent_approval_sha256",
        "protocol_sha256",
        "d36_trial_tool_sha256",
        "d37_evaluator_tool_sha256",
        "protocol_case_count",
        "protocol_case_tokens",
        "protocol_category_count",
        "protocol_category_tokens",
        "case_categories",
        "included_count",
        "excluded_count",
        "included_case_tokens",
        "excluded_cases",
        "evaluator_role",
        "evaluator_name",
        "executed_at",
        "sealed_evidence_sha256",
        "modes",
    )
    encoded = json.dumps(_bundle_data(), separators=(",", ":"))
    parsed = EvaluationResultBundle.model_validate_json(encoded)
    assert parsed.protocol_case_tokens == CASE_TOKENS
    nested_extra = _bundle_data()
    nested_extra["modes"][0]["categories"][0]["raw_case_id"] = "D24-H001"
    with pytest.raises(ValidationError):
        EvaluationResultBundle.model_validate(nested_extra)


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("included_case_tokens", list(reversed(INCLUDED))),
        ("excluded_count", 2),
        ("protocol_case_count", 4),
        ("protocol_category_tokens", list(reversed(CATEGORY_TOKENS))),
        ("evaluator_name", ""),
        ("executed_at", "2026-09-20T00:00:00+00:00"),
    ],
)
def test_approval_bundle_rejects_broken_shared_invariants(mutation: str, value: object) -> None:
    data = _bundle_data()
    data[mutation] = value
    with pytest.raises(ValidationError):
        EvaluationResultBundle.model_validate(data)


def test_approval_bundle_rejects_vacuous_category_or_invalid_mode_equations() -> None:
    vacuous = _bundle_data()
    vacuous["included_case_tokens"] = [CASE_TOKENS[0]]
    vacuous["included_count"] = 1
    vacuous["excluded_count"] = 4
    vacuous["excluded_cases"] = [
        *EXCLUDED,
        {"case_token": CASE_TOKENS[4], "reason": "human_not_approved"},
    ]
    with pytest.raises(ValidationError):
        EvaluationResultBundle.model_validate(vacuous)

    invalid_equation = _bundle_data()
    invalid_equation["modes"][0]["transport_failures"] = 1
    with pytest.raises(ValidationError):
        EvaluationResultBundle.model_validate(invalid_equation)

    bool_count = _bundle_data()
    bool_count["modes"][0]["completed"] = True
    with pytest.raises(ValidationError):
        EvaluationResultBundle.model_validate(bool_count)


def test_attestation_hash_changes_when_a_tool_byte_changes(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "tool.py").write_bytes(b"VALUE = 1\n")
    (second / "tool.py").write_bytes(b"VALUE = 2\n")
    first_fingerprint = fingerprint_file(first, "tool.py")
    second_fingerprint = fingerprint_file(second, "tool.py")
    assert aggregate_fingerprints([first_fingerprint]) != aggregate_fingerprints(
        [second_fingerprint]
    )
