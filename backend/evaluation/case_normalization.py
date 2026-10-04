"""Read a D24 case into the one canonical state shared by D37 projection and scoring.

The D24 format leaves setting snapshots, prior-turn identity and event detail names
loosely specified. The development seed is the reference reading; this module
applies it once so the trial input and the expected state cannot diverge.
"""
from __future__ import annotations

from typing import Any

from app.schemas import ProjectCreate
from evaluation.contracts import Case

SETTING_FIELDS: tuple[str, ...] = (
    "subtitle_font_size",
    "voicevox_speed_scale",
    "voicevox_pitch_scale",
    "voicevox_speaker_id",
    "pronunciation_overrides",
    "narration_pacing_mode",
    "narration_sentence_pause_seconds",
)
SETTING_DEFAULTS: dict[str, Any] = {
    name: ProjectCreate.model_fields[name].get_default(call_default_factory=True)
    for name in SETTING_FIELDS
}

# Author spellings of event details, mapped to the D37 wire names.
_DETAIL_ALIASES: dict[str, dict[str, str]] = {
    "revision_race": {
        "competing_revision": "external_revision",
        "competing_settings": "external_settings",
    },
    "switch_target": {"switched_project_id": "selected_project_id_after"},
}


def complete_settings(
    value: dict[str, Any], base: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Complete a partial snapshot from its owner (or product defaults), wire fields only."""
    merged = {**SETTING_DEFAULTS, **(base or {}), **value}
    return {name: merged[name] for name in SETTING_FIELDS}


def _event_details(case: Case) -> dict[str, Any]:
    details = dict(case.event.details)
    for alias, name in _DETAIL_ALIASES.get(case.event.kind, {}).items():
        if name not in details and alias in details:
            details[name] = details[alias]
    if case.event.kind == "switch_target":
        details.setdefault("action", "read_original_request")
    if case.event.kind == "same_id_different_body" and "replacement_text" not in details:
        changed = details.get("changed_request")
        if isinstance(changed, str):
            details["replacement_text"] = changed
        elif isinstance(changed, dict) and "text" in changed:
            details["replacement_text"] = changed["text"]
            if "target_project_id" in changed:
                details["replacement_target_project_id"] = changed["target_project_id"]
    return details


def _prior_turn(case: Case, value: dict[str, Any], explicit_successors: bool) -> dict[str, Any]:
    turn = dict(value)
    if "project_id" not in turn and type(turn.get("target_project_id")) is int:
        turn["project_id"] = turn["target_project_id"]
    turn.setdefault("project_id", case.initial.project_id)
    result_revision = turn.get("result_revision")
    if type(turn.get("base_revision")) is not int:
        if type(result_revision) is int and result_revision > 1 and turn.get("settings_saved") is True:
            turn["base_revision"] = result_revision - 1
        elif type(result_revision) is int:
            turn["base_revision"] = result_revision
        else:
            turn["base_revision"] = case.initial.revision
    turn.setdefault("settings_saved", False)
    # The case's own request continues the last turn; the host links it itself.
    if explicit_successors and turn.get("successor_request_id") == case.request.request_id:
        turn["successor_request_id"] = None
    return turn


def normalize_case(case: Case) -> Case:
    """Return the canonical reading of one D24 case; labels are never changed."""
    initial = case.initial
    settings = complete_settings(initial.settings)
    owners: dict[int, dict[str, Any]] = {initial.project_id: settings}
    for job in initial.jobs:
        owners.setdefault(job["project_id"], complete_settings(job.get("input_settings", {})))
    jobs = [
        {"kind": "full", **job,
         "input_settings": complete_settings(job.get("input_settings", {}), owners[job["project_id"]])}
        for job in initial.jobs
    ]
    history = [
        {**item, "settings": complete_settings(item["settings"], settings)}
        for item in initial.history
    ]
    explicit = any("successor_request_id" in turn for turn in initial.prior_turns)
    prior_turns = [_prior_turn(case, turn, explicit) for turn in initial.prior_turns]
    return case.model_copy(update={
        "initial": initial.model_copy(update={
            "settings": settings, "jobs": jobs, "history": history, "prior_turns": prior_turns,
        }),
        "event": case.event.model_copy(update={"details": _event_details(case)}),
    })
