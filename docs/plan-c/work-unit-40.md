# D40 — Release-readiness decision

## Goal

Produce an evidence-based release-readiness decision without publishing or deploying.

## Inputs

- D36 freeze manifest;
- D38 independently produced, validated aggregate;
- D39 regression, migration, recovery, browser, media, and documentation evidence;
- accurately recorded human-operation and independent-review status.

## Mandatory gates

1. Zero unauthorized settings, jobs, cancellations, arbitrary dispatches, or remote
   call replays.
2. Zero secret/private-input disclosure in responses, logs, or committed evidence.
3. No unresolved freeze, corpus, migration, or result-integrity mismatch.
4. Full required regression and migration/recovery checks pass.
5. Both modes complete the frozen protocol; failures are not silently excluded.
6. Approved held-out task completion is at least 90% overall and no evaluated
   category is below 80%.
7. The selected default has no worse safety result than All Tools.
8. Required human operation and independent review are present; otherwise readiness
   remains blocked rather than inferred.

## Mode and outcome policy

All Tools remains the default unless stateful retrieval meets every safety gate and
performs at least as well on approved held-out task completion. Outcomes are Ready,
Conditionally ready for explicitly accepted non-safety limitations, or Not ready.

## Non-goals and acceptance

D40 creates a reviewable decision record and unresolved-item list. It does not tag,
publish, deploy, create a GitHub release, or claim readiness when evidence is missing.
