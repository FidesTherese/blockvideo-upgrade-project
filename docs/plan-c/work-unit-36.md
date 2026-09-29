# D36 — Frozen release candidate

## Goal

Create a content-addressed candidate whose behavior and evaluation inputs cannot
change unnoticed.

## Scope

- Record Git commit and dirty status; operation/search-scope, prompt, response
  schema, guard, model, embedding, index, database-schema, evaluation-protocol,
  runtime, and relevant non-secret configuration fingerprints. Hash committed
  `HEAD` blobs only after exact working-byte comparison; reject assume-unchanged,
  skip-worktree, sparse, and other special index entries. Include the explicit
  non-secret `backend/.env.example` before applying the broad `.env` exclusion.
- Refuse a freeze with uncommitted behavior changes, missing assets, unknown schema,
  or inconsistent manifests.
- Classify documentation-only amendments separately; any executable-input change
  creates a new candidate and invalidates affected results.
- Derive `created_at` only from the frozen candidate commit's integer committer
  timestamp normalized to `YYYY-MM-DDTHH:MM:SSZ`; wall-clock time is forbidden.
- Keep secrets, absolute private paths, corpus text, and model response bodies out
  of the public manifest.
- Detect current schema version from exactly one strict committed migration-source
  AST assignment and accept only version 1; missing, ambiguous, malformed, or newer
  versions fail closed.
- Bind tool attestation to a clean identified tooling repository and its declared
  `HEAD` blobs. Real output generation is valid only after the tooling commit.
- Permit in-repository output only below resolved `<tool-repo>/release-evidence/`;
  permit external roots without treating other ignored in-repository roots as evidence.
- Claim the final candidate directory with exclusive `mkdir`, publish each verified
  file with no-replace hard-link/copy semantics, fsync, and remove only the claimed
  partial directory on failure. Read back both bounded regular artifacts; require
  exact canonical bytes and a recomputed tool-attestation aggregate.

## Non-goals

No tag, publication, deployment, or final readiness claim.

## Acceptance

The same checkout and inputs reproduce byte-identical canonical manifest bytes,
including deterministic `created_at`. Any relevant byte change is detected. The
manifest fingerprints reconstruct from the declared commit. A concurrent pre-existing
final directory is never replaced or removed. The frozen candidate can be
reconstructed using documented commands.

For Task 1 trial evidence, equivalent fresh runs MUST produce identical logical-state
and response projections: timestamps, leases, runtime durations, and generated opaque
IDs cannot perturb hashes. Every primary, replay, confirmation, and duplicate event
MUST retain its actual strict HTTP/status/reason projection. The trusted host MUST give
each worker an explicit internal model-call budget from 0 through 4. The first process
receives 4; a `restart_resend` process receives 4 minus the validated first-process
count. The adapter MUST return fixed `budget_exhausted` before an over-budget model
invocation, and reported aggregate calls and actual adapter calls MUST never exceed 4.
The host MUST disable bytecode writes, prove a pre/post-equal candidate snapshot, and publish evidence with
an atomic no-replace hard link so a competing destination is never overwritten.
`RedactedState` count maxima MUST accept the strict seed maxima plus up to four
event/model effects: 17 projects, 36 history rows, 36 jobs, 68 artifacts, 36 receipts,
36 external calls, 12 language requests, and 12 language turns. The 68-artifact bound
MUST include both independently valid 32-item artifact inputs. Any relationship that would make worker seeding impossible MUST be rejected before
candidate invocation. This includes out-of-range or future artifact revisions, unknown
project/job/artifact/history/receipt/call/prior-turn/parent/successor references,
cross-project ownership, cyclic job or dialogue ancestry, non-reciprocal dialogue
links, duplicate database-unique identities, receipt identity mismatch, current-artifact
ownership mismatch, and derived artifact IDs above the database integer range. Artifact
presence MUST NOT infer a current artifact: null or omitted `current_artifact_id` remains
null, and current/output pointers are set only for an explicit validated same-project
artifact. A maximum-count graph-valid case MUST seed through the real worker.
