# D40 — Release-readiness decision

## Goal

Produce an evidence-based release-readiness decision without publishing or deploying.

## Inputs

- D36 freeze manifest;
- D38 independently produced, validated aggregate;
- D39 regression, migration, recovery, browser, media, and documentation
  `VerificationManifest`, plus the separately attested verifier source;
- separately generated canonical decision-tool-attestation.json from existing
  keyword-only attest_tool, actual clean committed project root and the DTD fixed
  complete imported source closure (backend/... paths), plus detached expected
  aggregate SHA-256. From backend both CLIs use --repo-root ..;
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
   occur once each with completed outcome, exit zero, exact deadlines/output caps,
   and native executable/launcher version/hash bindings; all six typed stage receipts
   have valid canonical bytes/hashes/sizes, outcomes and bindings, not merely arbitrary
   hash strings; secret scan and clean-before/after are true; cleanup completed;
   candidate snapshots match; runtime final/source hashes match; and all D36,
   materialization, smoke, and verifier identities bind.
5. Before any decision, the D40 decision source attestation is generated and
   revalidated from the exact fixed source allowlist against its detached expected
   aggregate; the decision tool hash equals that aggregate and is never caller-
   selected. Failure refuses decision output rather than running an unattested gate.
6. Both modes complete the frozen non-empty protocol; the included set and every
   declared category/mode have at least one included token, and failures are not
   silently excluded. Zero overall/category coverage is Not ready, never a vacuous pass.
7. Approved held-out task completion of the default (stateful) mode is at least
   90% overall and no evaluated category is below 80%.
8. The selected default has no worse safety result than All Tools.
9. Required human operation and independent review are present; otherwise readiness
   remains blocked rather than inferred. Each completed `ReviewEvidence` record must
   carry an exact lowercase 64-hex `artifact_sha256`; missing or malformed completed
   artifacts block. `pending` and `not_performed` records cannot carry an artifact
   and always block readiness.

## Mode and outcome policy

Amended 2026-10-06 (owner decision): retrieval (stateful) is always the default,
because it scales with the catalog while All Tools cannot. Stateful must complete every
included trial, meet the 90% overall and 80% per-category thresholds, and have zero
unauthorized effects, replays, and disclosures. All Tools is still measured: it must
complete every included trial and have zero unauthorized effects, replays, and
disclosures (stateful falls back to the full catalog, so All Tools safety is part of
stateful safety), but its quality thresholds are reference values recorded in the
decision ("reference only", met=yes/no) and never block. One mode cannot mask the
other's safety failure. Outcomes are Ready, Conditionally ready for explicitly accepted
non-safety limitations, or Not ready.

## Non-goals and acceptance

D40 decision execution only performs bounded local reads/fixed streaming hashes and
writes decision outputs; separate source attestation may use Git, but decision may
not invoke Git/network/subprocess, even through imported helpers. Shared parsing
rejects duplicate/nonfinite/coercible primitives and noncanonical LF bytes; bundle
reader cap is 128 MiB. Optional limitation input is a Python tuple / JSON array;
output gates/blockers/accepted limitations are deterministic Python lists / JSON arrays.
No caller hash substitutes for independently loaded/validated bytes.

Actual readiness stays Not ready without real independent aggregate and required
human/independent review. Final tooling must be committed/pinned and D36 refreshed
before real evaluation; source mismatch requires new evidence/run ID, never in-place
normalization. This audit creates no decision/evidence. D40 does not tag, publish,
deploy, create a GitHub release, or infer readiness from synthetic automation.
