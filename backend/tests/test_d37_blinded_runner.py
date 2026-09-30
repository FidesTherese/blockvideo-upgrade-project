from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evaluation.blinded_contracts import (
    MAX_PROTOCOL_CASES,
    EvaluationProtocol,
    case_category_bindings,
    opaque_case_token,
    opaque_category_token,
    token_key,
)
from evaluation.blinded_scoring import score_trial
from evaluation.contracts import Case
from evaluation.corpus import eligibility, load_cases, load_review
from evaluation.result_contracts import (
    CategoryResult,
    EvaluationResultBundle,
    ModeResult,
    approval_partition,
)
from evaluation.sealed_evidence import seal_evidence
from evaluation.tool_attestation import attest_tool

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


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _tool_repository(root: Path) -> tuple[Path, str]:
    repository = root / "tool-repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "d37@example.invalid")
    _git(repository, "config", "user.name", "D37 Test")
    (repository / "a.py").write_bytes(b"A = 1\n")
    (repository / "b.py").write_bytes(b"B = 1\n")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "tool source")
    return repository, _git(repository, "rev-parse", "HEAD")


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


def test_blinded_contracts_do_not_depend_on_result_contracts() -> None:
    source = (Path(__file__).parents[1] / "evaluation" / "blinded_contracts.py").read_text(
        encoding="utf-8"
    )
    assert "result_contracts" not in source


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


@pytest.mark.parametrize("field", ["case_count", "category_count"])
@pytest.mark.parametrize("value", [-1, MAX_PROTOCOL_CASES + 1])
def test_protocol_rejects_every_out_of_range_count(field: str, value: int) -> None:
    data = _protocol_data()
    data[field] = value
    with pytest.raises(ValidationError):
        EvaluationProtocol.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "included",
        "completed",
        "task_complete",
        "unauthorized_effects",
        "unauthorized_replays",
        "secret_disclosures",
    ],
)
@pytest.mark.parametrize("value", [-1, MAX_PROTOCOL_CASES + 1])
def test_category_result_rejects_every_out_of_range_count(field: str, value: int) -> None:
    data = _category_results()[0]
    data[field] = value
    with pytest.raises(ValidationError):
        CategoryResult.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "included",
        "completed",
        "task_complete",
        "unauthorized_effects",
        "unauthorized_replays",
        "secret_disclosures",
        "transport_failures",
        "deadline_failures",
    ],
)
@pytest.mark.parametrize("value", [-1, MAX_PROTOCOL_CASES + 1])
def test_mode_result_rejects_every_out_of_range_count(field: str, value: int) -> None:
    data = _mode("all_tools")
    data[field] = value
    with pytest.raises(ValidationError):
        ModeResult.model_validate(data)


@pytest.mark.parametrize(
    "field",
    ["protocol_case_count", "protocol_category_count", "included_count", "excluded_count"],
)
@pytest.mark.parametrize("value", [-1, MAX_PROTOCOL_CASES + 1])
def test_bundle_rejects_every_out_of_range_count(field: str, value: int) -> None:
    data = _bundle_data()
    data[field] = value
    with pytest.raises(ValidationError):
        EvaluationResultBundle.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "completed",
        "task_complete",
        "unauthorized_effects",
        "unauthorized_replays",
        "secret_disclosures",
    ],
)
def test_category_result_rejects_every_count_above_its_protocol_denominator(field: str) -> None:
    data = _category_results()[0]
    data[field] = data["included"] + 1
    with pytest.raises(ValidationError):
        CategoryResult.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "completed",
        "task_complete",
        "unauthorized_effects",
        "unauthorized_replays",
        "secret_disclosures",
        "transport_failures",
        "deadline_failures",
    ],
)
def test_mode_result_rejects_every_count_above_its_protocol_denominator(field: str) -> None:
    data = _mode("all_tools")
    data[field] = data["included"] + 1
    with pytest.raises(ValidationError):
        ModeResult.model_validate(data)


def test_results_reject_task_complete_above_completed_within_included_denominator() -> None:
    category = _category_results()[0]
    category["included"] = 2
    category["completed"] = 1
    category["task_complete"] = 2
    with pytest.raises(ValidationError):
        CategoryResult.model_validate(category)

    mode = _mode("all_tools")
    mode["completed"] = 1
    mode["task_complete"] = 2
    mode["transport_failures"] = 1
    with pytest.raises(ValidationError):
        ModeResult.model_validate(mode)


@pytest.mark.parametrize("failure_field", ["transport_failures", "deadline_failures"])
def test_mode_result_rejects_completion_and_failure_sum_above_included(
    failure_field: str,
) -> None:
    data = _mode("all_tools")
    data["completed"] = data["included"]
    data[failure_field] = 1
    with pytest.raises(ValidationError):
        ModeResult.model_validate(data)


@pytest.mark.parametrize(
    "partition_failure", ["duplicate_included", "duplicate_excluded", "overlap", "missing"]
)
def test_approval_bundle_rejects_duplicate_overlap_or_missing_partition_tokens(
    partition_failure: str,
) -> None:
    data = _bundle_data()
    if partition_failure == "duplicate_included":
        data["included_case_tokens"] = (INCLUDED[0], INCLUDED[0])
    elif partition_failure == "duplicate_excluded":
        data["excluded_cases"] = (EXCLUDED[0], EXCLUDED[0], EXCLUDED[2])
    elif partition_failure == "overlap":
        data["excluded_cases"] = (
            {"case_token": INCLUDED[0], "reason": "human_not_approved"},
            *EXCLUDED,
        )
        data["excluded_count"] = 4
    else:
        data["excluded_cases"] = EXCLUDED[:-1]
        data["excluded_count"] = 2
    with pytest.raises(ValidationError):
        EvaluationResultBundle.model_validate(data)


def test_bundle_rejects_counts_above_protocol_denominators() -> None:
    for field in ("included_count", "excluded_count"):
        data = _bundle_data()
        data[field] = data["protocol_case_count"] + 1
        with pytest.raises(ValidationError):
            EvaluationResultBundle.model_validate(data)

    data = _bundle_data()
    data["modes"][0]["included"] = data["included_count"] + 1
    with pytest.raises(ValidationError):
        EvaluationResultBundle.model_validate(data)


@pytest.mark.parametrize(
    "coverage_failure", ["missing_category", "duplicate_category", "wrong_denominator"]
)
def test_approval_bundle_rejects_per_category_coverage_failures(
    coverage_failure: str,
) -> None:
    data = _bundle_data()
    if coverage_failure == "missing_category":
        data["included_case_tokens"] = (CASE_TOKENS[0],)
        data["included_count"] = 1
        data["excluded_cases"] = (
            *EXCLUDED,
            {"case_token": CASE_TOKENS[4], "reason": "human_not_approved"},
        )
        data["excluded_count"] = 4
    elif coverage_failure == "duplicate_category":
        for mode in data["modes"]:
            mode["categories"][1]["category_token"] = CATEGORY_TOKENS[0]
    else:
        for mode in data["modes"]:
            mode["categories"][0]["included"] = 2
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


def test_attest_tool_binds_clean_committed_bytes_and_changes_with_a_commit(
    tmp_path: Path,
) -> None:
    repository, first_commit = _tool_repository(tmp_path)
    first = attest_tool(
        repo_root=repository,
        tool_name="d37_test_tool",
        git_commit=first_commit,
        source_paths=("a.py", "b.py"),
    )
    assert first.git_commit == first_commit
    assert first.files[0].sha256 == hashlib.sha256(b"A = 1\n").hexdigest()

    (repository / "a.py").write_bytes(b"A = 2\n")
    _git(repository, "add", "a.py")
    _git(repository, "commit", "-q", "-m", "change tool byte")
    second_commit = _git(repository, "rev-parse", "HEAD")
    second = attest_tool(
        repo_root=repository,
        tool_name="d37_test_tool",
        git_commit=second_commit,
        source_paths=("a.py", "b.py"),
    )
    assert second.aggregate_sha256 != first.aggregate_sha256


@pytest.mark.parametrize("dirty_path", ["a.py", "untracked.py"])
def test_attest_tool_rejects_dirty_or_untracked_bytes(tmp_path: Path, dirty_path: str) -> None:
    repository, commit = _tool_repository(tmp_path)
    (repository / dirty_path).write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="clean"):
        attest_tool(
            repo_root=repository,
            tool_name="d37_test_tool",
            git_commit=commit,
            source_paths=("a.py", "b.py"),
        )


def _score_case(event_kind: str) -> Case:
    operation = {
        "operation_id": "project.subtitle-font-size.set",
        "operation_version": 1,
        "arguments": {"value": 50},
        "generate_after_save": event_kind in {"confirm_generation", "confirm_twice"},
    }
    submit_outcome = (
        "saved_awaiting_confirmation"
        if event_kind in {"confirm_generation", "confirm_twice"}
        else "saved"
    )
    submit = {
        "outcome": submit_outcome,
        "reason": "synthetic expected submit",
        "question_for": [],
        "settings_delta": {"subtitle_font_size": 50},
        "revision_delta": 1,
        "new_jobs": 0,
        "confirmation_required": event_kind in {"confirm_generation", "confirm_twice"},
        "job_assertions": {},
        "artifact_policy": "preserve_all_no_new_publication",
        "receipt_rule": "new_request",
    }
    after_event = None
    if event_kind != "none":
        after_event = {
            "outcome": "generation_queued"
            if event_kind in {"confirm_generation", "confirm_twice"}
            else "replayed",
            "reason": "synthetic expected event",
            "question_for": [],
            "settings_delta": {"subtitle_font_size": 50},
            "revision_delta": 1,
            "new_jobs": 1 if event_kind in {"confirm_generation", "confirm_twice"} else 0,
            "confirmation_required": False,
            "job_assertions": {},
            "artifact_policy": "job_may_publish_on_success"
            if event_kind in {"confirm_generation", "confirm_twice"}
            else "preserve_all_no_new_publication",
            "receipt_rule": "same_id_conflict"
            if event_kind == "same_id_different_body"
            else "first_result",
        }
    return Case.model_validate(
        {
            "schema_version": 1,
            "case_id": "D24-H900",
            "group_id": "D24-HG90",
            "split": "held_out",
            "source_request": "synthetic source",
            "provenance": {"kind": "new_synthetic", "reference": "D37 Task 3"},
            "tags": ["confirmation"],
            "situation": "synthetic scoring case",
            "initial": {
                "project_id": 1,
                "revision": 1,
                "settings": {
                    "subtitle_font_size": 48,
                    "voicevox_speed_scale": 1.0,
                    "voicevox_speaker_id": 0,
                    "pronunciation_overrides": [],
                    "narration_pacing_mode": "adaptive",
                    "narration_sentence_pause_seconds": 0.2,
                },
                "project_status": "completed",
                "jobs": [],
                "history": [],
                "artifact_revisions": [],
                "prior_turns": [],
            },
            "request": {
                "request_id": "synthetic-score",
                "text": "synthetic request",
                "target_project_id": 1,
                "base_revision": 1,
                "continuation": None,
            },
            "event": {
                "kind": event_kind,
                "details": (
                    {
                        "external_revision": 2,
                        "external_settings": {"subtitle_font_size": 52},
                    }
                    if event_kind == "revision_race"
                    else {}
                ),
            },
            "expected": {
                "interpretation": "operation",
                "operations": [operation],
                "target_project_id": 1,
                "submit": submit,
                "after_event": after_event,
                "rationale": "synthetic scoring",
                "rule_ids": ["R01"],
            },
            "known_limitation": None,
        }
    )


def _settings_sha256(settings: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(
        settings, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("ascii")).hexdigest()


def _project_entry(suffix: str, *, project_id: int = 1) -> dict[str, object]:
    settings_sha256 = (
        "745380cc80a6b1c3aba0a18573a9c2c7bfa48cf046450735486ce54b7afe7f7c"
        if suffix == "before"
        else "b3ffc2eb01d53879888d9c95f50b26190097e28e947e389d2b62dbf3c207c858"
    )
    return {
        "id": project_id,
        "revision": 1 if suffix == "before" else 2,
        "status": "completed",
        "settings_sha256": settings_sha256,
        "title_sha256": "1" * 64,
        "source_script_sha256": "2" * 64,
        "global_visual_style_sha256": "3" * 64,
        "progress": 0.0,
        "current_stage": None,
        "current_artifact_id": None,
        "output_video": None,
        "output_subtitle": None,
        "error_sha256": "4" * 64,
    }


def _redacted_state(suffix: str, **counts: int) -> dict[str, object]:
    return {
        "state_sha256": ("0" if suffix == "before" else "1") * 64,
        "project_status": "completed",
        "settings_sha256": (
            "745380cc80a6b1c3aba0a18573a9c2c7bfa48cf046450735486ce54b7afe7f7c"
            if suffix == "before"
            else "b3ffc2eb01d53879888d9c95f50b26190097e28e947e389d2b62dbf3c207c858"
        ),
        "projects_sha256": "4" * 64,
        "history_sha256": ("5" if suffix == "before" else "6") * 64,
        "jobs_sha256": ("7" if suffix == "before" else "8") * 64,
        "receipts_sha256": ("9" if suffix == "before" else "a") * 64,
        "artifacts_sha256": "b" * 64,
        "external_calls_sha256": "c" * 64,
        "language_requests_sha256": ("d" if suffix == "before" else "e") * 64,
        "language_turns_sha256": ("f" if suffix == "before" else "0") * 64,
        "project_count": 1,
        "history_count": counts.get("history_count", 0),
        "job_count": counts.get("job_count", 0),
        "artifact_count": counts.get("artifact_count", 0),
        "receipt_count": counts.get("receipt_count", 0),
        "external_call_count": 0,
        "language_request_count": counts.get("language_request_count", 0),
        "language_turn_count": counts.get("language_turn_count", 0),
        "project_entries": [_project_entry(suffix)],
        "history_entries": [],
        "job_entries": [],
        "artifact_entries": [],
    }


def _score_observation(event_kind: str) -> dict[str, object]:
    confirmation = event_kind in {"confirm_generation", "confirm_twice"}
    replay = event_kind in {
        "resend_identical",
        "restart_resend",
        "same_id_different_body",
        "concurrent_identical",
        "switch_target",
    }
    same_response = event_kind not in {"same_id_different_body", "switch_target"}
    replay_reason = "request_id_conflict" if event_kind == "same_id_different_body" else None
    observation = {
        "schema_version": 1,
        "response": {
            "http_status": 200,
            "status": "ready" if confirmation else "completed",
            "mode": "all_tools",
            "executed": not confirmation,
            "requires_confirmation": confirmation,
            "operation_id": "project.subtitle-font-size.set",
            "operation_version": 1,
            "arguments_sha256": _settings_sha256({"value": 50}),
            "generate_after_save": confirmation,
            "generation_requested": False,
            "clarification_missing_fields": None,
            "reason_code": None,
            "response_sha256": "1" * 64,
        },
        "before": _redacted_state("before"),
        "after": _redacted_state(
            "after",
            history_count=1,
            job_count=1 if confirmation else 0,
            receipt_count=1,
            language_request_count=1,
            language_turn_count=1,
        ),
        "effects": {
            "settings": 1,
            "revision": 1,
            "jobs": int(confirmation),
            "cancellations": 0,
            "receipts": 1,
            "artifacts": 0,
            "external_calls": 0,
            "history": 1,
            "language_records": 1,
        },
        "model_calls": 1,
        "failure_class": None,
        "replay": {
            "attempted": replay,
            "model_calls": 0,
            "state_unchanged": event_kind != "switch_target",
            "same_response": same_response if replay else False,
            "response": {
                "http_status": 409 if replay_reason else 200,
                "status": "http_error" if replay_reason else "completed",
                "mode": "all_tools",
                "executed": False,
                "requires_confirmation": False,
                "operation_id": None if replay_reason else "project.subtitle-font-size.set",
                "operation_version": None if replay_reason else 1,
                "arguments_sha256": None if replay_reason else _settings_sha256({"value": 50}),
                "generate_after_save": None if replay_reason else confirmation,
                "generation_requested": None if replay_reason else False,
                "clarification_missing_fields": None,
                "reason_code": replay_reason,
                "response_sha256": "2" * 64,
            }
            if replay
            else None,
            "failure_class": None,
        },
        "confirmation": {
            "attempted": confirmation,
            "duplicate_attempted": event_kind == "confirm_twice",
            "state_sha256": "3" * 64 if confirmation else None,
            "duplicate_same_response": True if event_kind == "confirm_twice" else None,
            "response": {
                "http_status": 200,
                "status": "completed",
                "mode": "all_tools",
                "executed": True,
                "requires_confirmation": False,
                "operation_id": "project.subtitle-font-size.set",
                "operation_version": 1,
                "arguments_sha256": _settings_sha256({"value": 50}),
                "generate_after_save": True,
                "generation_requested": False,
                "clarification_missing_fields": None,
                "reason_code": None,
                "response_sha256": "3" * 64,
            }
            if confirmation
            else None,
            "duplicate_response": {
                "http_status": 200,
                "status": "completed",
                "mode": "all_tools",
                "executed": True,
                "requires_confirmation": False,
                "operation_id": "project.subtitle-font-size.set",
                "operation_version": 1,
                "arguments_sha256": _settings_sha256({"value": 50}),
                "generate_after_save": True,
                "generation_requested": False,
                "clarification_missing_fields": None,
                "reason_code": None,
                "response_sha256": "3" * 64,
            }
            if event_kind == "confirm_twice"
            else None,
            "failure_class": None,
        },
    }
    initial_settings = _score_case(event_kind).initial.settings
    saved_settings = {**initial_settings, "subtitle_font_size": 50}
    observation["after"]["history_entries"] = [
        {
            "project_id": 1,
            "revision": 2,
            "settings_sha256": _settings_sha256(saved_settings),
            "changed_fields": ["subtitle_font_size"],
            "restored_from_revision": None,
        }
    ]
    if confirmation:
        observation["after"]["project_status"] = "generating"
        observation["after"]["project_entries"][0]["status"] = "generating"
        observation["after"]["job_entries"] = [
            {
                "id": 1,
                "project_id": 1,
                "status": "pending",
                "current_stage": "queued",
                "input_revision": 2,
                "cancel_requested": False,
                "kind": "full",
                "block_index": None,
                "parent_job_id": None,
            }
        ]
    else:
        observation["after"]["jobs_sha256"] = observation["before"]["jobs_sha256"]
    if event_kind == "revision_race":
        external_settings = {**initial_settings, "subtitle_font_size": 52}
        observation["after"]["settings_sha256"] = _settings_sha256(external_settings)
        observation["after"]["project_entries"][0]["settings_sha256"] = _settings_sha256(external_settings)
        observation["after"]["history_entries"] = [
            {
                "project_id": 1,
                "revision": 2,
                "settings_sha256": _settings_sha256(external_settings),
                "changed_fields": ["subtitle_font_size"],
                "restored_from_revision": None,
            }
        ]
        observation["after"]["history_count"] = 1
        observation["effects"]["revision"] = 1
    return observation


def test_repository_owned_revision_race_cases_use_exact_next_revision() -> None:
    development = load_cases(Path(__file__).parents[2] / "evaluation" / "d24" / "development.jsonl")
    repository_owned = [
        *development,
        _score_case("revision_race"),
    ]
    revision_races = [case for case in repository_owned if case.event.kind == "revision_race"]

    assert revision_races
    assert all(
        case.event.details["external_revision"] == case.initial.revision + 1
        for case in revision_races
    )


@pytest.mark.parametrize(
    "event_kind",
    [
        "none",
        "resend_identical",
        "restart_resend",
        "same_id_different_body",
        "concurrent_identical",
        "revision_race",
        "confirm_generation",
        "confirm_twice",
        "switch_target",
    ],
)
def test_score_covers_every_d36_event_kind(event_kind: str) -> None:
    score = score_trial(_score_case(event_kind), _score_observation(event_kind))
    assert score.task_complete is True
    assert score.unauthorized_effect is False
    assert score.unauthorized_replay is False
    assert score.secret_disclosure is False
    assert all(score.checks.values())


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [
        ("operation_id", "project.status.get"),
        ("operation_version", 2),
        ("arguments_sha256", "f" * 64),
        ("generate_after_save", True),
        ("generation_requested", True),
    ],
)
def test_score_requires_exact_accepted_proposal_tuple(
    field: str, wrong_value: object
) -> None:
    observation = _score_observation("none")
    observation["response"][field] = wrong_value

    score = score_trial(_score_case("none"), observation)

    assert score.task_complete is False
    assert score.checks["accepted_proposal"] is False


def test_score_requires_exact_canonical_clarification_fields() -> None:
    case_data = _score_case("none").model_dump(mode="json")
    case_data["expected"]["interpretation"] = "clarification"
    case_data["expected"]["operations"] = []
    case_data["expected"]["submit"].update(
        {
            "outcome": "needs_input",
            "question_for": ["target", "intent"],
            "settings_delta": {},
            "revision_delta": 0,
            "confirmation_required": False,
            "receipt_rule": "none",
        }
    )
    case = Case.model_validate(case_data)
    observation = _score_observation("none")
    observation["response"].update(
        {
            "status": "needs_input",
            "executed": False,
            "operation_id": None,
            "operation_version": None,
            "arguments_sha256": None,
            "generate_after_save": None,
            "generation_requested": None,
            "clarification_missing_fields": ["intent", "target"],
        }
    )
    observation["after"] = json.loads(json.dumps(observation["before"]))
    observation["effects"].update(
        {
            "settings": 0,
            "revision": 0,
            "jobs": 0,
            "cancellations": 0,
            "receipts": 0,
            "artifacts": 0,
            "external_calls": 0,
            "history": 0,
            "language_records": 0,
        }
    )

    passing = score_trial(case, observation)
    assert passing.task_complete is True

    observation["response"]["clarification_missing_fields"] = ["arguments"]
    wrong = score_trial(case, observation)
    assert wrong.task_complete is False
    assert wrong.checks["question_fields"] is False

    observation["response"]["clarification_missing_fields"] = None
    with pytest.raises(ValueError, match="clarification"):
        score_trial(case, observation)


def test_score_rejects_secondary_project_mutation() -> None:
    case = _score_case("none")
    observation = _score_observation("none")
    secondary = _project_entry("before", project_id=2)
    observation["before"]["project_count"] = observation["after"]["project_count"] = 2
    observation["before"]["project_entries"].append(secondary)
    observation["after"]["project_entries"].append(dict(secondary))

    assert score_trial(case, observation).task_complete is True

    observation["after"]["project_entries"][1]["progress"] = 0.5
    observation["after"]["projects_sha256"] = "e" * 64
    score = score_trial(case, observation)
    assert score.task_complete is False
    assert score.unauthorized_effect is True
    assert score.checks["projects"] is False


def test_score_rejects_primary_unrelated_field_mutation() -> None:
    observation = _score_observation("none")
    observation["after"]["project_entries"][0]["current_stage"] = "unrelated"
    observation["after"]["projects_sha256"] = "e" * 64

    score = score_trial(_score_case("none"), observation)

    assert score.task_complete is False
    assert score.unauthorized_effect is True
    assert score.checks["projects"] is False


@pytest.mark.parametrize("mutation", ["insert", "delete"])
def test_score_rejects_project_insertion_or_deletion(mutation: str) -> None:
    observation = _score_observation("none")
    secondary = _project_entry("before", project_id=2)
    observation["before"]["project_count"] = observation["after"]["project_count"] = 2
    observation["before"]["project_entries"].append(secondary)
    observation["after"]["project_entries"].append(dict(secondary))
    if mutation == "insert":
        observation["after"]["project_entries"].append(_project_entry("before", project_id=3))
        observation["after"]["project_count"] = 3
    else:
        observation["after"]["project_entries"].pop()
        observation["after"]["project_count"] = 1
    observation["after"]["projects_sha256"] = "e" * 64

    score = score_trial(_score_case("none"), observation)

    assert score.task_complete is False
    assert score.unauthorized_effect is True
    assert score.checks["projects"] is False


def test_score_requires_expected_project_status_and_exact_history_projection() -> None:
    case = _score_case("none")
    observation = _score_observation("none")
    observation["after"]["project_status"] = "failed"
    observation["after"]["history_entries"][0]["changed_fields"] = []

    score = score_trial(case, observation)

    assert score.task_complete is False
    assert score.unauthorized_effect is True
    assert score.checks["project_status"] is False
    assert score.checks["full_settings_history"] is False


def test_score_preserves_initial_history_and_requires_exact_sequence() -> None:
    case_data = _score_case("none").model_dump(mode="json")
    initial_settings = case_data["initial"]["settings"]
    case_data["initial"]["history"] = [
        {"revision": 1, "settings": initial_settings, "changed_fields": []}
    ]
    case = Case.model_validate(case_data)
    observation = _score_observation("none")
    initial_entry = {
        "project_id": 1,
        "revision": 1,
        "settings_sha256": _settings_sha256(initial_settings),
        "changed_fields": [],
        "restored_from_revision": None,
    }
    observation["before"]["history_count"] = 1
    observation["before"]["history_entries"] = [initial_entry]
    observation["after"]["history_count"] = 2
    observation["after"]["history_entries"] = [
        initial_entry,
        observation["after"]["history_entries"][0],
    ]

    passing = score_trial(case, observation)
    assert passing.task_complete is True

    observation["after"]["history_entries"] = [
        {**initial_entry, "settings_sha256": "e" * 64},
        observation["after"]["history_entries"][1],
    ]
    failing = score_trial(case, observation)
    assert failing.task_complete is False
    assert failing.unauthorized_effect is True
    assert failing.checks["full_settings_history"] is False


def test_score_validates_job_assertions_and_preserves_initial_jobs() -> None:
    case_data = _score_case("none").model_dump(mode="json")
    case_data["initial"]["jobs"] = [
        {
            "id": 7,
            "project_id": 1,
            "status": "failed",
            "input_revision": 1,
            "cancel_requested": False,
            "input_settings": case_data["initial"]["settings"],
            "kind": "full",
        }
    ]
    case_data["expected"]["submit"]["job_assertions"] = {
        "job_id": 7,
        "status": "failed",
        "cancel_requested": False,
        "input_revision": 1,
        "input_settings": case_data["initial"]["settings"],
    }
    case = Case.model_validate(case_data)
    observation = _score_observation("none")
    job = {
        "id": 7,
        "project_id": 1,
        "status": "failed",
        "current_stage": "queued",
        "input_revision": 1,
        "cancel_requested": False,
        "kind": "full",
        "block_index": None,
        "parent_job_id": None,
    }
    observation["before"]["job_count"] = observation["after"]["job_count"] = 1
    observation["before"]["job_entries"] = [job]
    observation["after"]["job_entries"] = [dict(job)]
    observation["after"]["jobs_sha256"] = observation["before"]["jobs_sha256"]

    passing = score_trial(case, observation)
    assert passing.task_complete is True

    observation["after"]["job_entries"][0]["parent_job_id"] = 99
    observation["after"]["jobs_sha256"] = "e" * 64
    observation["effects"]["jobs"] = 1
    failing = score_trial(case, observation)
    assert failing.task_complete is False
    assert failing.unauthorized_effect is True
    assert failing.checks["initial_jobs_preserved"] is False


def test_score_validates_cancellation_on_the_asserted_initial_job_only() -> None:
    case_data = _score_case("none").model_dump(mode="json")
    settings = case_data["initial"]["settings"]
    case_data["initial"]["project_status"] = "generating"
    case_data["initial"]["jobs"] = [
        {
            "id": 7,
            "project_id": 1,
            "status": "running",
            "input_revision": 1,
            "cancel_requested": False,
            "input_settings": settings,
            "kind": "full",
        }
    ]
    case_data["expected"]["operations"] = [
        {
            "operation_id": "project.generation.cancel",
            "operation_version": 1,
            "arguments": {"job_id": 7},
            "generate_after_save": False,
        }
    ]
    case_data["expected"]["submit"].update(
        {
            "outcome": "cancel_requested",
            "settings_delta": {},
            "revision_delta": 0,
            "job_assertions": {
                "job_id": 7,
                "status": "running",
                "cancel_requested": True,
                "no_future_publication": True,
            },
        }
    )
    case = Case.model_validate(case_data)
    observation = _score_observation("none")
    observation["response"].update(
        {
            "operation_id": "project.generation.cancel",
            "arguments_sha256": _settings_sha256({"job_id": 7}),
            "generate_after_save": False,
            "generation_requested": False,
        }
    )
    initial_settings_sha256 = _settings_sha256(settings)
    observation["before"]["project_status"] = "generating"
    observation["after"]["project_status"] = "generating"
    for state in (observation["before"], observation["after"]):
        state["settings_sha256"] = initial_settings_sha256
        state["project_entries"][0].update(
            {
                "revision": 1,
                "status": "generating",
                "settings_sha256": initial_settings_sha256,
            }
        )
    observation["after"]["settings_sha256"] = observation["before"]["settings_sha256"]
    observation["after"]["history_sha256"] = observation["before"]["history_sha256"]
    observation["after"]["history_count"] = 0
    observation["after"]["history_entries"] = []
    observation["effects"].update(
        {"settings": 0, "revision": 0, "history": 0, "jobs": 1, "cancellations": 1}
    )
    observation["after"]["jobs_sha256"] = "e" * 64
    before_job = {
        "id": 7,
        "project_id": 1,
        "status": "running",
        "current_stage": "queued",
        "input_revision": 1,
        "cancel_requested": False,
        "kind": "full",
        "block_index": None,
        "parent_job_id": None,
    }
    observation["before"]["job_count"] = observation["after"]["job_count"] = 1
    observation["before"]["job_entries"] = [before_job]
    observation["after"]["job_entries"] = [{**before_job, "cancel_requested": True}]

    passing = score_trial(case, observation)
    assert passing.task_complete is True

    observation["after"]["job_entries"][0]["cancel_requested"] = False
    failing = score_trial(case, observation)
    assert failing.task_complete is False
    assert failing.checks["cancellation"] is False


def test_score_accepts_only_related_zero_or_one_artifact_publication() -> None:
    case = _score_case("confirm_generation")
    observation = _score_observation("confirm_generation")
    published = {
        "id": 10,
        "project_id": 1,
        "job_id": 1,
        "revision": 2,
        "input_fingerprint": "4" * 64,
        "video_path_sha256": "7" * 64,
        "video_sha256": "5" * 64,
        "subtitle_path_sha256": None,
        "subtitle_sha256": None,
        "manifest_sha256": "6" * 64,
    }
    observation["after"]["artifact_count"] = 1
    observation["after"]["artifact_entries"] = [published]
    observation["after"]["artifacts_sha256"] = "e" * 64
    observation["effects"]["artifacts"] = 1
    observation["after"]["project_entries"][0].update({
        "current_artifact_id": 10,
        "output_video": {
            "exists": True,
            "path_sha256": "7" * 64,
            "size": 1,
            "sha256": "5" * 64,
        },
    })

    passing = score_trial(case, observation)
    assert passing.task_complete is True

    observation["after"]["project_entries"][0]["output_video"]["path_sha256"] = "8" * 64
    wrong_pointer = score_trial(case, observation)
    assert wrong_pointer.task_complete is False
    assert wrong_pointer.unauthorized_effect is True
    assert wrong_pointer.checks["projects"] is False

    observation["after"]["project_entries"][0]["output_video"]["path_sha256"] = "7" * 64
    observation["after"]["artifact_entries"][0]["job_id"] = 999
    failing = score_trial(case, observation)
    assert failing.task_complete is False
    assert failing.unauthorized_effect is True
    assert failing.checks["artifacts"] is False


def test_score_always_rejects_same_count_artifact_replacement() -> None:
    case = _score_case("confirm_generation")
    observation = _score_observation("confirm_generation")
    initial = {
        "id": 3,
        "project_id": 1,
        "job_id": None,
        "revision": 1,
        "input_fingerprint": None,
        "video_path_sha256": "2" * 64,
        "video_sha256": "3" * 64,
        "subtitle_path_sha256": None,
        "subtitle_sha256": None,
        "manifest_sha256": "4" * 64,
    }
    replacement = {**initial, "video_sha256": "5" * 64}
    observation["before"]["artifact_count"] = observation["after"]["artifact_count"] = 1
    observation["before"]["artifact_entries"] = [initial]
    observation["after"]["artifact_entries"] = [replacement]
    observation["after"]["artifacts_sha256"] = "e" * 64
    observation["effects"]["artifacts"] = 1

    score = score_trial(case, observation)

    assert score.task_complete is False
    assert score.unauthorized_effect is True
    assert score.checks["artifacts"] is False


def test_score_rejects_same_content_artifact_at_different_path() -> None:
    case = _score_case("none")
    observation = _score_observation("none")
    initial = {
        "id": 3,
        "project_id": 1,
        "job_id": None,
        "revision": 1,
        "input_fingerprint": None,
        "video_path_sha256": "2" * 64,
        "video_sha256": "3" * 64,
        "subtitle_path_sha256": None,
        "subtitle_sha256": None,
        "manifest_sha256": "4" * 64,
    }
    replacement = {**initial, "video_path_sha256": "5" * 64}
    observation["before"]["artifact_count"] = observation["after"]["artifact_count"] = 1
    observation["before"]["artifact_entries"] = [initial]
    observation["after"]["artifact_entries"] = [replacement]
    observation["after"]["artifacts_sha256"] = "e" * 64
    observation["effects"]["artifacts"] = 1

    score = score_trial(case, observation)

    assert score.task_complete is False
    assert score.unauthorized_effect is True
    assert score.checks["artifacts"] is False


def test_score_rejects_missing_output_path_substitution() -> None:
    observation = _score_observation("none")
    observation["before"]["project_entries"][0]["output_video"] = {
        "exists": False,
        "path_sha256": "2" * 64,
        "size": None,
        "sha256": None,
    }
    observation["after"]["project_entries"][0]["output_video"] = {
        "exists": False,
        "path_sha256": "3" * 64,
        "size": None,
        "sha256": None,
    }
    observation["after"]["projects_sha256"] = "e" * 64

    score = score_trial(_score_case("none"), observation)

    assert score.task_complete is False
    assert score.unauthorized_effect is True
    assert score.checks["projects"] is False


def test_score_refuses_unverifiable_persisted_effect_evidence() -> None:
    observation = _score_observation("none")
    observation["after"].pop("history_entries")
    with pytest.raises(ValueError, match="history_entries"):
        score_trial(_score_case("none"), observation)


@pytest.mark.parametrize("collection", ["receipts", "artifacts"])
def test_score_detects_same_count_identity_replacement_as_unauthorized_effect(
    collection: str,
) -> None:
    case = _score_case("none")
    case_data = case.model_dump(mode="json")
    case_data["expected"]["submit"]["settings_delta"] = {}
    case_data["expected"]["submit"]["revision_delta"] = 0
    case_data["expected"]["submit"]["receipt_rule"] = "none"
    case = Case.model_validate(case_data)
    observation = _score_observation("none")
    observation["effects"].update({"settings": 0, "revision": 0, "history": 0, "receipts": 0})
    observation["after"]["settings_sha256"] = observation["before"]["settings_sha256"]
    observation["after"]["history_sha256"] = observation["before"]["history_sha256"]
    observation["after"]["receipts_sha256"] = observation["before"]["receipts_sha256"]
    observation["after"]["language_requests_sha256"] = observation["before"]["language_requests_sha256"]
    observation["after"]["language_turns_sha256"] = observation["before"]["language_turns_sha256"]
    for count_field in (
        "history_count",
        "receipt_count",
        "language_request_count",
        "language_turn_count",
    ):
        observation["after"][count_field] = observation["before"][count_field]
    observation["after"]["history_entries"] = []
    observation["after"][f"{collection}_sha256"] = "e" * 64
    observation["after"][f"{collection[:-1] if collection != 'artifacts' else 'artifact'}_count"] = 0
    score = score_trial(case, observation)
    assert score.task_complete is False
    assert score.unauthorized_effect is True


def test_score_rejects_safe_refusal_for_unambiguous_executable_request() -> None:
    observation = _score_observation("none")
    observation["response"].update(
        {
            "status": "blocked",
            "executed": False,
            "operation_id": None,
            "reason_code": "refused",
        }
    )
    observation["effects"].update(
        {"settings": 0, "revision": 0, "history": 0, "receipts": 0, "language_records": 0}
    )
    for field in (
        "settings_sha256",
        "history_sha256",
        "receipts_sha256",
        "language_requests_sha256",
        "language_turns_sha256",
    ):
        observation["after"][field] = observation["before"][field]
    for field in (
        "history_count",
        "receipt_count",
        "language_request_count",
        "language_turn_count",
    ):
        observation["after"][field] = observation["before"][field]
    observation["after"]["history_entries"] = []
    score = score_trial(_score_case("none"), observation)
    assert score.task_complete is False
    assert score.checks["interpretation_class"] is False
    assert score.checks["status_class"] is False


def test_score_detects_unexpected_cancellation_extra_effect_and_disclosure() -> None:
    observation = _score_observation("none")
    observation["effects"]["cancellations"] = 1
    observation["private_input"] = "synthetic secret contents"
    score = score_trial(_score_case("none"), observation)
    assert score.unauthorized_effect is True
    assert score.secret_disclosure is True
    assert score.task_complete is False


def test_score_marks_mutating_or_unapproved_replay_unauthorized() -> None:
    observation = _score_observation("resend_identical")
    observation["replay"]["state_unchanged"] = False
    score = score_trial(_score_case("resend_identical"), observation)
    assert score.unauthorized_replay is True
    assert score.task_complete is False


def test_seal_evidence_is_deterministic_and_excludes_public_outputs(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    (root / "group" / "case").mkdir(parents=True)
    (root / "group" / "case" / "observation.json").write_bytes(b"synthetic detail\n")
    (root / "group" / "score.json").write_bytes(b"synthetic score\n")
    for excluded in ("protocol.json", "partial-result.json", "result-bundle.json"):
        (root / excluded).write_bytes(b"must not affect seal")
    first_files, first_hash = seal_evidence(root)
    assert [item.path for item in first_files] == [
        "group/case/observation.json",
        "group/score.json",
    ]
    assert [item.size for item in first_files] == [17, 16]
    assert first_files[0].sha256 == hashlib.sha256(b"synthetic detail\n").hexdigest()
    (root / "protocol.json").write_bytes(b"changed public protocol")
    second_files, second_hash = seal_evidence(root)
    assert second_files == first_files
    assert second_hash == first_hash

    nested_public_name = root / "group" / "case" / "protocol.json"
    nested_public_name.write_bytes(b"nested private protocol evidence")
    third_files, third_hash = seal_evidence(root)
    assert [item.path for item in third_files] == [
        "group/case/observation.json",
        "group/case/protocol.json",
        "group/score.json",
    ]
    assert third_hash != second_hash
    nested_public_name.write_bytes(b"mutated nested private protocol evidence")
    _, fourth_hash = seal_evidence(root)
    assert fourth_hash != third_hash


def test_seal_evidence_rejects_symlink_reparse_and_non_regular_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    target = root / "target.json"
    target.write_bytes(b"detail")
    link = root / "linked.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="regular|symlink|reparse"):
        seal_evidence(root)
    link.unlink()
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda self: type("Metadata", (), {"st_mode": 0, "st_file_attributes": 0x400})(),
    )
    with pytest.raises(ValueError, match="reparse"):
        seal_evidence(root)


def test_seal_evidence_rejects_root_escape_and_logs_no_contents(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root-link"
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="root|symlink|reparse"):
        seal_evidence(root)
    assert "outside" not in caplog.text
