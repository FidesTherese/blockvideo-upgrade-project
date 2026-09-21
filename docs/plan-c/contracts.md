# Operation Core Contracts

- Request: operation ID/version, one project target, strict arguments, optional observed
  state token, request ID, base revision, and explicit generation flag (default false).
- ID-bearing mutations require the base revision. Relative adjustment and generation
  require both ID and revision. Legacy absolute requests without either remain supported.
- Readiness: `ready`, `needs_input`, `blocked`, or `unsupported`, with reason code,
  missing fields, resolved project, string state token and integer revision.
- Result: operation/project IDs, changed flag, state token/revision, non-secret data,
  request/base revision, resolved arguments, generation flag, job ID and result reference.
- Candidate/retrieval output is not an executable request type.
- D28 candidate state carries exact operation ID/version, candidate_preview phase,
  arguments_checked=false, reason/missing fields, target/revision and snapshot time.
  Known busy/target restrictions precede unchecked arguments. needs_input with
  arguments_unchecked does not mean the user's text necessarily lacks values.
  It means arguments and referenced job/history records have not yet been validated.
  Even a candidate labelled ready is provisional; final readiness remains below.
- Per-stage candidate observations are immutable diagnostics. The read-only
  language candidate-readiness endpoint returns a fresh observation separately,
  without rewriting a receipt or executing/retrying its operation.
- Execution first checks the durable receipt under the SQLite writer lock. Same ID/content
  returns the original result; different content returns 409. Fresh requests repeat catalog,
  target, current job/readiness and revision checks before resolving relative values.
- The service owns one transaction in a clean caller-provided session. Handlers never
  commit. Settings, revision, receipt and optional pending generation job are atomic.
- Status reads with an ID persist a snapshot receipt without mutating the project.
- `GET /api/operations/requests/{request_id}` returns the original response, even after
  later edits or project deletion. It is not a live generation-progress endpoint.
- The handler registry is the only dispatch mechanism. Catalog text is not imported or evaluated.

D12–D15 extends these contracts with snapshot/plan jobs, immutable successful video
history, external-call journals and separate control handlers. All five new mutation
operations require both ID and current base revision. Restore creates a new revision;
cancel does not restore settings; retry creates a new job from current settings.

See `docs/DTD.md` and `docs/plan-c/work-unit-12-15.md` for current signatures,
examples, restart state transitions, migration and limits.
