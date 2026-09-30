"""Score D37 trials from D24 labels and redacted D36 observations only."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from evaluation.contracts import Case, Effects
from evaluation.scripts.evaluation_trial_host import RedactedState


class TrialScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_complete: bool
    unauthorized_effect: bool
    unauthorized_replay: bool
    secret_disclosure: bool
    checks: dict[str, bool]


_STATUS_BY_OUTCOME: dict[str, frozenset[str]] = {
    "saved": frozenset({"completed"}),
    "saved_awaiting_confirmation": frozenset({"ready"}),
    "awaiting_confirmation": frozenset({"ready"}),
    "queried": frozenset({"completed"}),
    "needs_input": frozenset({"needs_input"}),
    "unsupported": frozenset({"unsupported"}),
    "dismissed": frozenset({"dismissed"}),
    "blocked": frozenset({"blocked"}),
    "replayed": frozenset({"completed", "ready"}),
    "cancel_requested": frozenset({"completed"}),
    "cancelled": frozenset({"completed"}),
    "unchanged": frozenset({"completed"}),
    "generation_queued": frozenset({"completed"}),
}
_REPLAY_EVENTS = frozenset(
    {
        "resend_identical",
        "restart_resend",
        "same_id_different_body",
        "concurrent_identical",
        "switch_target",
    }
)
_IDEMPOTENT_REPLAY_EVENTS = frozenset(
    {"resend_identical", "restart_resend", "concurrent_identical"}
)
_CONFIRMATION_EVENTS = frozenset({"confirm_generation", "confirm_twice"})
_SAFE_TOP_LEVEL = frozenset(
    {
        "schema_version",
        "case_sha256",
        "candidate_snapshot_sha256",
        "input_sha256",
        "mode",
        "response",
        "before",
        "after",
        "effects",
        "model_calls",
        "failure_class",
        "replay",
        "confirmation",
    }
)
_DISCLOSURE_KEY_PARTS = ("secret", "private", "prompt", "source_request", "expected", "label", "text")


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"redacted observation {name} must be an object")
    return value


def _final_effects(case: Case) -> Effects:
    return case.expected.after_event or case.expected.submit


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _has_cancellation(effects: Effects) -> bool:
    return (
        effects.outcome in {"cancel_requested", "cancelled"}
        or effects.job_assertions.get("cancel_requested") is True
        or effects.job_assertions.get("status") == "cancelled"
    )


def _changed(
    before: dict[str, Any],
    after: dict[str, Any],
    effects: dict[str, Any],
    collection: str,
    effect_name: str,
) -> bool:
    return (
        before.get(f"{collection}_sha256") != after.get(f"{collection}_sha256")
        or effects.get(effect_name) != 0
    )


def _sequence(state: dict[str, Any], name: str, count_name: str) -> list[dict[str, Any]]:
    value = state.get(name)
    count = state.get(count_name)
    if not isinstance(value, list) or type(count) is not int or len(value) != count:
        raise ValueError(f"redacted observation {name} must match {count_name}")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"redacted observation {name} entries must be objects")
    return value


def _initial_history(case: Case) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    settings_by_revision: dict[int, dict[str, Any]] = {
        case.initial.revision: dict(case.initial.settings)
    }
    for item in case.initial.history:
        if not isinstance(item, dict) or type(item.get("revision")) is not int:
            raise ValueError("case initial history must contain revisions")
        settings = {**case.initial.settings, **_mapping(item.get("settings"), "initial history settings")}
        revision = item["revision"]
        settings_by_revision[revision] = settings
        entries.append(
            {
                "project_id": item.get("project_id", case.initial.project_id),
                "revision": revision,
                "settings_sha256": _canonical_hash(settings),
                "changed_fields": sorted(item.get("changed_fields", [])),
                "restored_from_revision": item.get("restored_from_revision"),
            }
        )
    settings_by_revision[case.initial.revision] = dict(case.initial.settings)
    return sorted(entries, key=lambda item: (item["project_id"], item["revision"])), settings_by_revision


def _restore_revision(case: Case) -> int | None:
    revisions = {
        operation.arguments.get("revision")
        for operation in case.expected.operations
        if operation.operation_id == "project.settings.restore"
    }
    revisions.discard(None)
    if len(revisions) > 1:
        raise ValueError("restore proposals must agree on revision")
    return next(iter(revisions), None)


def _expected_history(
    case: Case, final: Effects
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[int, dict[str, Any]], dict[str, Any], int]:
    before, settings_by_revision = _initial_history(case)
    after = list(before)
    initial_revision = case.initial.revision
    initial_settings = dict(case.initial.settings)
    submit = case.expected.submit
    race_revision = case.event.details.get("external_revision") if case.event.kind == "revision_race" else None
    candidate_persists = submit.revision_delta == 1 and (
        type(race_revision) is not int or race_revision > initial_revision + 1
    )
    current_settings = initial_settings
    if candidate_persists:
        current_settings = {**current_settings, **submit.settings_delta}
        revision = initial_revision + 1
        settings_by_revision[revision] = current_settings
        after.append(
            {
                "project_id": case.initial.project_id,
                "revision": revision,
                "settings_sha256": _canonical_hash(current_settings),
                "changed_fields": sorted(submit.settings_delta),
                "restored_from_revision": _restore_revision(case),
            }
        )
    elif case.event.kind != "revision_race" and final.revision_delta == 1:
        current_settings = {**current_settings, **final.settings_delta}
        revision = initial_revision + 1
        settings_by_revision[revision] = current_settings
        after.append(
            {
                "project_id": case.initial.project_id,
                "revision": revision,
                "settings_sha256": _canonical_hash(current_settings),
                "changed_fields": sorted(final.settings_delta),
                "restored_from_revision": _restore_revision(case),
            }
        )
    if case.event.kind == "revision_race":
        external_settings = _mapping(case.event.details.get("external_settings"), "external settings")
        if type(race_revision) is not int or race_revision <= initial_revision:
            raise ValueError("revision_race requires a newer external revision")
        current_settings = {**current_settings, **external_settings}
        settings_by_revision[race_revision] = current_settings
        after.append(
            {
                "project_id": case.initial.project_id,
                "revision": race_revision,
                "settings_sha256": _canonical_hash(current_settings),
                "changed_fields": sorted(external_settings),
                "restored_from_revision": None,
            }
        )
    after.sort(key=lambda item: (item["project_id"], item["revision"]))
    revision_delta = max(settings_by_revision) - initial_revision if case.event.kind == "revision_race" else final.revision_delta
    return before, after, settings_by_revision, current_settings, revision_delta


def _initial_jobs(case: Case) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "id": item["id"],
                "project_id": item["project_id"],
                "status": item["status"],
                "current_stage": item.get("current_stage", "queued"),
                "input_revision": item["input_revision"],
                "cancel_requested": item["cancel_requested"],
                "kind": item.get("kind", "full"),
                "block_index": item.get("block_index"),
                "parent_job_id": item.get("parent_job_id"),
            }
            for item in case.initial.jobs
        ],
        key=lambda item: item["id"],
    )


def _job_assertions_match(
    assertions: dict[str, Any], selected: dict[str, Any] | None,
    new_jobs: list[dict[str, Any]], settings_by_revision: dict[int, dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> bool:
    if not assertions:
        return True
    if selected is None:
        return False
    supported = {
        "job_id", "status", "cancel_requested", "input_revision", "input_settings",
        "count", "parent_job_id", "new_job_id_differs_from", "no_future_publication",
        "kind", "block_index",
    }
    if not set(assertions) <= supported:
        return False
    for key in ("job_id", "status", "cancel_requested", "input_revision", "parent_job_id", "kind", "block_index"):
        if key in assertions and selected.get("id" if key == "job_id" else key) != assertions[key]:
            return False
    if "count" in assertions and len(new_jobs) != assertions["count"]:
        return False
    if "new_job_id_differs_from" in assertions and selected["id"] == assertions["new_job_id_differs_from"]:
        return False
    if "input_settings" in assertions:
        expected_settings = settings_by_revision.get(selected["input_revision"])
        if expected_settings is None or assertions["input_settings"] != expected_settings:
            return False
    if assertions.get("no_future_publication") is True and any(
        item.get("job_id") == selected["id"] for item in artifacts
    ):
        return False
    return True


def _contains_disclosure(value: object, *, top_level: bool = False) -> bool:
    if isinstance(value, dict):
        if top_level and not set(value) <= _SAFE_TOP_LEVEL:
            return True
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _DISCLOSURE_KEY_PARTS):
                return True
            if _contains_disclosure(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_disclosure(item) for item in value)
    return False


def _event_check(case: Case, observation: dict[str, Any]) -> tuple[bool, bool]:
    kind = case.event.kind
    replay = _mapping(observation.get("replay"), "replay")
    confirmation = _mapping(observation.get("confirmation"), "confirmation")
    replay_attempted = replay.get("attempted") is True
    confirmation_attempted = confirmation.get("attempted") is True
    duplicate_attempted = confirmation.get("duplicate_attempted") is True

    if kind == "none":
        valid = not replay_attempted and not confirmation_attempted
    elif kind in _IDEMPOTENT_REPLAY_EVENTS:
        valid = (
            replay_attempted
            and replay.get("state_unchanged") is True
            and replay.get("same_response") is True
            and not confirmation_attempted
        )
    elif kind == "same_id_different_body":
        replay_response = _mapping(replay.get("response"), "replay response")
        valid = (
            replay_attempted
            and replay.get("state_unchanged") is True
            and replay.get("same_response") is False
            and replay_response.get("reason_code")
            in {"request_conflict", "request_id_conflict", "core_request_conflict"}
            and not confirmation_attempted
        )
    elif kind == "switch_target":
        valid = replay_attempted and not confirmation_attempted
    elif kind == "revision_race":
        valid = not replay_attempted and not confirmation_attempted
    elif kind in _CONFIRMATION_EVENTS:
        confirmation_response = _mapping(confirmation.get("response"), "confirmation response")
        valid = (
            not replay_attempted
            and confirmation_attempted
            and confirmation_response.get("status") == "completed"
            and confirmation_response.get("executed") is True
            and duplicate_attempted == (kind == "confirm_twice")
        )
        if kind == "confirm_twice":
            valid = valid and confirmation.get("duplicate_same_response") is True
    else:
        valid = False

    unauthorized_replay = replay_attempted and (
        kind not in _REPLAY_EVENTS
        or replay.get("state_unchanged") is not True
        and kind in _IDEMPOTENT_REPLAY_EVENTS | {"same_id_different_body"}
    )
    return valid, unauthorized_replay


def score_trial(case: Case, observation: dict[str, object]) -> TrialScore:
    """Compare one strict D24 expectation with one label-free D36 JSON observation."""
    if not isinstance(observation, dict):
        raise ValueError("redacted observation must be an object")
    response = _mapping(observation.get("response"), "response")
    before = RedactedState.model_validate(
        _mapping(observation.get("before"), "before")
    ).model_dump(mode="json")
    after = RedactedState.model_validate(
        _mapping(observation.get("after"), "after")
    ).model_dump(mode="json")
    effects = _mapping(observation.get("effects"), "effects")
    final = _final_effects(case)

    expected_history_before, expected_history_after, settings_by_revision, expected_final_settings, expected_revision = _expected_history(case, final)
    history_before = _sequence(before, "history_entries", "history_count")
    history_after = _sequence(after, "history_entries", "history_count")
    jobs_before = _sequence(before, "job_entries", "job_count")
    jobs_after = _sequence(after, "job_entries", "job_count")
    artifacts_before = _sequence(before, "artifact_entries", "artifact_count")
    artifacts_after = _sequence(after, "artifact_entries", "artifact_count")
    initial_jobs = _initial_jobs(case)
    if jobs_before != initial_jobs:
        initial_jobs_valid = False
    else:
        initial_jobs_valid = True

    before_by_id = {item.get("id"): item for item in jobs_before}
    after_by_id = {item.get("id"): item for item in jobs_after}
    if len(before_by_id) != len(jobs_before) or len(after_by_id) != len(jobs_after):
        raise ValueError("redacted observation job entries must have unique identities")
    new_jobs = [item for item in jobs_after if item.get("id") not in before_by_id]
    removed_job_ids = set(before_by_id) - set(after_by_id)
    asserted_job_id = final.job_assertions.get("job_id")
    selected_job = (
        after_by_id.get(asserted_job_id)
        if asserted_job_id is not None
        else new_jobs[0] if len(new_jobs) == 1 else None
    )
    mutable_job_id = asserted_job_id if _has_cancellation(final) else None
    preserved_jobs = all(
        job_id in after_by_id
        and (
            after_by_id[job_id] == item
            or job_id == mutable_job_id
            and all(
                after_by_id[job_id].get(key) == value
                for key, value in item.items()
                if key not in {"status", "cancel_requested"}
            )
        )
        for job_id, item in before_by_id.items()
    ) and not removed_job_ids
    artifact_before_keys = {_canonical_hash(item) for item in artifacts_before}
    artifact_after_keys = {_canonical_hash(item) for item in artifacts_after}
    artifacts_preserved = artifact_before_keys <= artifact_after_keys
    added_artifacts = [
        item for item in artifacts_after if _canonical_hash(item) not in artifact_before_keys
    ]
    artifact_policy_valid = False
    if final.artifact_policy == "preserve_all_no_new_publication":
        artifact_policy_valid = artifacts_preserved and not added_artifacts
    elif artifacts_preserved and len(added_artifacts) <= 1:
        artifact_policy_valid = not added_artifacts or (
            len(new_jobs) == 1
            and added_artifacts[0].get("project_id") == case.initial.project_id
            and added_artifacts[0].get("job_id") == new_jobs[0].get("id")
            and added_artifacts[0].get("revision") == new_jobs[0].get("input_revision")
            and isinstance(added_artifacts[0].get("input_fingerprint"), str)
            and len(added_artifacts[0]["input_fingerprint"]) == 64
            and all(character in "0123456789abcdef" for character in added_artifacts[0]["input_fingerprint"])
        )
    assertions_valid = _job_assertions_match(
        final.job_assertions, selected_job, new_jobs, settings_by_revision, artifacts_after
    )
    job_count_valid = len(new_jobs) == final.new_jobs
    jobs_changed = _changed(before, after, effects, "jobs", "jobs")
    expected_job_change = bool(final.new_jobs or _has_cancellation(final))
    jobs_valid = (
        initial_jobs_valid
        and preserved_jobs
        and job_count_valid
        and assertions_valid
        and jobs_changed is expected_job_change
    )
    cancellations_before = {
        item["id"]: item.get("cancel_requested") for item in jobs_before
    }
    cancellations_after = {
        item["id"]: item.get("cancel_requested") for item in jobs_after
    }
    changed_cancellations = {
        job_id for job_id in cancellations_before
        if cancellations_after.get(job_id) != cancellations_before[job_id]
    }
    expected_cancellation = _has_cancellation(final)
    cancellation_valid = (
        effects.get("cancellations") == int(expected_cancellation)
        and (
            changed_cancellations == {asserted_job_id}
            if expected_cancellation and asserted_job_id is not None
            else not changed_cancellations
        )
        and (not expected_cancellation or selected_job is not None)
    )
    expected_project_status = case.initial.project_status
    if final.new_jobs:
        expected_project_status = "generating"
    elif (
        expected_cancellation
        and selected_job is not None
        and selected_job.get("status") == "cancelled"
    ):
        expected_project_status = "cancelled"

    expected_settings = expected_final_settings != case.initial.settings
    expected_receipts = (
        case.expected.submit.receipt_rule in {"new_request", "first_result"}
        or final.receipt_rule in {"new_request", "first_result"}
    )
    initial_settings_identity = before.get("settings_sha256") == _canonical_hash(case.initial.settings)
    settings_identity = after.get("settings_sha256") == _canonical_hash(expected_final_settings)
    count_deltas = {
        name: after.get(f"{name}_count", 0) - before.get(f"{name}_count", 0)
        for name in ("history", "job", "receipt", "artifact")
        if type(after.get(f"{name}_count")) is int
        and type(before.get(f"{name}_count")) is int
    }
    history_valid = (
        history_before == expected_history_before
        and history_after == expected_history_after
        and count_deltas.get("history") == len(expected_history_after) - len(expected_history_before)
        and effects.get("history") == int(expected_history_after != expected_history_before)
    )
    artifacts_changed = _changed(before, after, effects, "artifacts", "artifacts")
    artifact_change_valid = artifacts_changed is bool(added_artifacts)
    actual = {
        "settings": before.get("settings_sha256") != after.get("settings_sha256")
        or effects.get("settings") != 0,
        "revision": effects.get("revision"),
        "receipts": _changed(before, after, effects, "receipts", "receipts"),
        "external_calls": _changed(before, after, effects, "external_calls", "external_calls"),
    }
    persisted_checks = {
        "project_status": after.get("project_status") == expected_project_status,
        "settings": initial_settings_identity and actual["settings"] is expected_settings and settings_identity,
        "revision": actual["revision"] == expected_revision,
        "full_settings_history": history_valid,
        "initial_jobs_preserved": initial_jobs_valid and preserved_jobs,
        "jobs": jobs_valid,
        "cancellation": cancellation_valid,
        "artifacts": artifact_policy_valid and artifact_change_valid,
    }
    unauthorized_effect = any(
        (
            not all(persisted_checks.values()),
            actual["receipts"] is not expected_receipts,
            count_deltas.get("receipt") != int(expected_receipts),
            actual["external_calls"],
        )
    )
    event_valid, unauthorized_replay = _event_check(case, observation)
    accepted_operations = {item.operation_id for item in case.expected.operations}
    expected_interpretation = case.expected.interpretation
    interpretation_valid = {
        "operation": response.get("operation_id") in accepted_operations,
        "clarification": response.get("status") == "needs_input"
        and response.get("operation_id") is None,
        "unsupported": response.get("status") == "unsupported"
        and response.get("operation_id") is None,
        "no_operation": response.get("status") == "dismissed"
        and response.get("operation_id") is None,
        "not_called": observation.get("model_calls") == 0,
    }[expected_interpretation]
    checks = {
        "observation_completed": observation.get("failure_class") is None,
        "interpretation_class": interpretation_valid,
        "accepted_operations": (
            response.get("operation_id") in accepted_operations
            if accepted_operations
            else response.get("operation_id") is None
        ),
        "question_fields": (
            response.get("status") == "needs_input"
            if case.expected.submit.question_for
            else response.get("status") != "needs_input"
        ),
        "status_class": response.get("status") in _STATUS_BY_OUTCOME[case.expected.submit.outcome],
        "confirmation_required": response.get("requires_confirmation")
        is case.expected.submit.confirmation_required,
        **persisted_checks,
        "receipts": actual["receipts"] is expected_receipts
        and count_deltas.get("receipt") == int(expected_receipts),
        "declared_event": event_valid,
    }
    secret_disclosure = _contains_disclosure(observation, top_level=True)
    task_complete = (
        all(checks.values())
        and not unauthorized_effect
        and not unauthorized_replay
        and not secret_disclosure
    )
    return TrialScore(
        task_complete=task_complete,
        unauthorized_effect=unauthorized_effect,
        unauthorized_replay=unauthorized_replay,
        secret_disclosure=secret_disclosure,
        checks=checks,
    )
