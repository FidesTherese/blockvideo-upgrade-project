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
- Never create or open a child at the final candidate path. Create a cryptographically
  random hidden staging directory directly under the validated output root and acquire
  its platform directory anchor immediately. POSIX MUST retain an
  `O_DIRECTORY|O_NOFOLLOW` descriptor, derive identity with `fstat`, and create every
  fixed child with `dir_fd`. Windows MUST retain a `CreateFileW` directory handle with
  backup semantics and read/write sharing but no delete sharing, derive identity with
  `GetFileInformationByHandle`, and hold it until immediately before publication.
  Build and validate the complete staging directory through retained file descriptors;
  write/read back canonical `CompletionMarker` bytes last. Atomically publish the whole
  directory with Linux `renameat2(RENAME_NOREPLACE)` or Windows `MoveFileExW` without a
  replace flag. A concurrent final creator wins untouched. Perform no final-path writes
  or publisher readbacks; invoke the independent reader only after successful rename.
  On failure or identity loss, never recursively delete or move an unowned path; random
  staging may remain and MUST be rejected as evidence. This protects cooperative
  processes and post-anchor path replacement. Malicious same-user mutation in the
  unavoidable `mkdir` to anchor gap is outside the trust boundary because that
  principal can also tamper process memory/handles; do not claim atomic Win32 mkdir+open.
  Readers MUST require exactly the canonical
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
manifest fingerprints reconstruct from the declared commit. Construction occurs only
inside an anchored random hidden staging directory. A concurrent final creator wins
untouched under true no-replace publication, while the unpublished staging directory
remains non-evidentiary. Windows tests cover mocked API flags and native no-delete
handle behavior; POSIX tests cover anchored `dir_fd` behavior and Linux no-replace where
available. Failures perform no recursive or identity-blind cleanup. A successful reader rejects a missing,
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
