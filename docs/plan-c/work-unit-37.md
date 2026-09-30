# D37 — Blinded evaluation runner

## Goal

Run approved held-out evaluation without exposing its content to the implementation
process or allowing mode-specific test conditions.

## Scope

- Accept a separately mounted corpus and approval ledger at execution time.
- Validate corpus, approval, protocol, and D36 freeze fingerprints before running.
- Isolate database and media state per source-request group.
- Execute frozen All Tools and stateful-retrieval modes with identical limits.
- Score persisted receipts/effects and expected state, not model prose. Require the
  exact accepted proposal tuple or exact clarification missing-field set. Require exact
  project-count/identity preservation, byte-equal non-primary project projections,
  only expected primary revision/settings/status changes, and only policy-permitted
  artifact/output pointer changes. Project output and artifact video/subtitle identities
  include the hash of the canonical stored relative path string, including when a
  referenced file is missing; raw and resolved paths are never emitted. Also require
  exact project-status, history-row,
  settings-hash/revision/changed-field, job-assertion,
  initial-job, cancellation, and artifact-subset evidence from D36. Missing projections
  are unverifiable and fail closed. Under the publication policy, artifact delta +0
  permits no current/output pointer change. Delta +1 requires exactly one artifact
  bound to the sole added or explicitly expected job and to the primary expected
  project/revision; its video and subtitle must exist with size/content hashes, and
  the primary current/output pointers must exactly match its full path/size/content
  identities. Orphans, stale pointers, wrong-job artifacts, same-content
  different-path replacement, missing files, and every same-count replacement are
  unauthorized.
- Derive domain-separated evaluator-keyed HMAC-SHA-256 case/category tokens. Publish
  only a non-empty complete sorted opaque token set/count and non-empty opaque category
  bindings in the canonical protocol; never publish raw case IDs, text, category names,
  or labels.
- Require a non-empty included token set and at least one included token in every
  declared category in each mode; zero overall/category inclusion fails D37.
- Save sealed detailed evidence and a non-sensitive aggregate containing exact sorted
  included tokens and exact sorted excluded tokens with one deterministic reason per
  exclusion: `both_not_approved` when both approvals are absent, otherwise the sole
  missing approval's reason.
  without logging request text or labels. Exclude designated public outputs from the
  detailed-evidence seal only at the run root; nested files with the same basename are
  sealed private evidence.
- Test runner behavior only with repository-owned synthetic fixtures.

## Non-goals

The implementation agent does not inspect held-out cases, labels, rendered review
HTML, or detailed evaluator evidence. D37 does not report final quality itself.

## Acceptance

Synthetic tests prove isolation, opaque-token privacy, exact included/excluded union
accounting, deterministic exclusion precedence, non-empty overall/per-category
coverage, crash-safe no-replace interruption and resume for trial/bundle publication,
mode symmetry, scoring correctness, exact proposal/clarification matching, complete
runtime-source attestation mutation detection, bidirectional protected-root/output rejection (including workspace-parent output),
full-run retained candidate identity, anchored-inode execution across checkout
replacement and swap/restore attempts, non-link writable directory enforcement,
bounded output, early-parent inherited-pipe descendant termination, cancellation with
bounded confirmed teardown, and token-key zeroization after final-`fstat` and close
faults as well as normal exit. They also prove rejection of secondary-project mutation,
primary unrelated-field mutation, project insertion/deletion, unapproved, selectively
filtered, duplicate, zero-coverage, or mismatched input. Every repository-owned
synthetic/development revision race uses `initial + 1`; a nonconforming mounted
held-out case fails host validation before candidate execution rather than changing
race semantics.
