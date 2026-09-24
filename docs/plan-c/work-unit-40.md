# D40 — Release-readiness decision

## Goal

Produce an evidence-based release-readiness decision without publishing or deploying.

## Inputs

- D36 freeze manifest;
- D38 independently produced, validated aggregate;
- D39 regression, migration, recovery, browser, media, and documentation
  `VerificationManifest`, plus the separately attested verifier source;
- generated canonical `decision-tool-attestation.json` for the exact decision/
  contracts/CLI source allowlist and its detached expected aggregate SHA-256;
- accurately recorded human-operation and independent-review status.

## Mandatory gates

1. Zero unauthorized settings, jobs, cancellations, arbitrary dispatches, or remote
   call replays.
2. Zero secret/private-input disclosure in responses, logs, or committed evidence.
3. No unresolved freeze, corpus, migration, or result-integrity mismatch. The D38
   accepted result, import validation, importer attestation, D39 verification
   manifest, and D39 verifier attestation each match a separately supplied detached
   expected SHA-256; D39 candidate/commit/freeze identity matches D36 and its verifier
   tool hash matches the verifier attestation.
4. Independently validate D39: exactly the DTD-defined nine command name/argv pairs
   occur once each with exit code zero; all six mandatory smoke hashes are valid and
   content-bound; secret scan and clean-before/after are true; cleanup completed;
   candidate snapshots match; runtime final/source hashes match; and all D36,
   materialization, smoke, and verifier identities bind.
5. Before any decision, the D40 decision source attestation is generated and
   revalidated from the exact fixed source allowlist against its detached expected
   aggregate; the decision tool hash equals that aggregate and is never caller-
   selected. Failure refuses decision output rather than running an unattested gate.
6. Both modes complete the frozen non-empty protocol; the included set and every
   declared category/mode have at least one included token, and failures are not
   silently excluded. Zero overall/category coverage is Not ready, never a vacuous pass.
7. Approved held-out task completion is at least 90% overall and no evaluated
   category is below 80%.
8. The selected default has no worse safety result than All Tools.
9. Required human operation and independent review are present; otherwise readiness
   remains blocked rather than inferred. Each completed `ReviewEvidence` record must
   carry an exact lowercase 64-hex `artifact_sha256`; missing or malformed completed
   artifacts block. `pending` and `not_performed` records cannot carry an artifact
   and always block readiness.

## Mode and outcome policy

Both All Tools and stateful must independently complete every included trial, meet
the 90% overall and 80% per-category thresholds, and have zero unauthorized effects,
replays, and disclosures; one mode cannot mask the other's failure. All Tools remains
the default unless stateful passes all of those gates and its exact overall
`task_complete / completed` ratio is at least All Tools. Outcomes are Ready,
Conditionally ready for explicitly accepted non-safety limitations, or Not ready.

## Non-goals and acceptance

D40 creates a reviewable decision record and unresolved-item list. It does not tag,
publish, deploy, create a GitHub release, or claim readiness when evidence is missing.
