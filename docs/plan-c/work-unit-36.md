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
- Claim the final candidate directory with exclusive `mkdir`; immediately record its
  non-reparse/non-symlink `lstat` device/inode identity and strict resolved parent, then
  exclusively open and retain descriptors for `.d36-publication-state`,
  `freeze-manifest.json`, and `d36-tool-attestation.json`. Store all three descriptor
  identities in the claim and write/fsync a random 32-byte token through the state
  descriptor. Before and after every artifact write/readback and completion-state
  write/readback, require the same directory, fixed-file paths, descriptors, parent,
  and expected state bytes. Every write, truncate, seek, fsync, and pre-completion
  readback MUST use only those retained descriptors; never reopen a claimed fixed file,
  hard-link it, or perform a path-based file write. After validating both artifacts,
  write and read back canonical `CompletionMarker` bytes last through the retained
  state descriptor. Close each descriptor exactly once in `finally`. On failure or
  ownership loss, touch no publication path; leave the incomplete original wherever
  moved and leave any replacement empty. On success, close descriptors, fsync the
  directory only if its identity is still owned, then validate through the independent
  reader. No staging publication helper or staging name remains. Readers MUST require
  exactly the canonical
  artifact pair plus `.d36-publication-state`, and MUST accept that state only when its
  bytes are the exact canonical completion record with the artifact sizes and SHA-256
  values. Require exact canonical artifact bytes, fsyncs, a recomputed tool-attestation
  aggregate, an exact recomputed manifest file aggregate, and the candidate ID derived
  from that aggregate prefix plus commit prefix.

## Non-goals

No tag, publication, deployment, or final readiness claim.

## Acceptance

The same checkout and inputs reproduce byte-identical canonical manifest bytes,
including deterministic `created_at`. Any relevant byte change is detected. The
manifest fingerprints reconstruct from the declared commit. A concurrent pre-existing
or post-claim replacement final directory is never replaced or removed. Race tests at
write, readback, and cleanup boundaries preserve a replacement sentinel at the exact
final path, preserve an empty replacement, and return the bounded ownership-lost error.
An ordinary failed claim remains incomplete and non-evidentiary, and a retry fails
closed until operator cleanup. Deterministic races at the former check/unlink boundaries
leave replacement exact paths untouched. A successful reader rejects a missing,
altered, replaced, non-regular, or token-valued state file and every extra entry. A
successful final directory contains exactly two evidence files and one state file, with
no random token remaining in the state bytes. The frozen candidate can be reconstructed
using documented commands.

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
