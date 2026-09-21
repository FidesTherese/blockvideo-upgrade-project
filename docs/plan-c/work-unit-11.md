# Work unit 11: durable requests and revisions

## Scope and decisions

Implement the user's D11 request on baseline `c6924d7`. Reuse SQLite, SQLAlchemy,
FastAPI and the existing single-server worker. No new dependency or external API
spend. D12 planning, D13 artifact revision binding and D14 running-job recovery
are not implemented here.

## Request contract

`OperationRequest` gains optional `request_id` (1–128 safe ASCII characters),
`base_revision` (strict positive integer), and `generation_requested` (strict bool,
default false). Existing absolute set/status v1 requests remain compatible.
An ID-bearing setting mutation requires a base revision. Relative adjustment and
explicit generation require both ID and base revision. The status operation cannot
request generation. Readiness checks do not reserve an ID or write a receipt.

`project.subtitle-font-size.adjust` version 1 accepts only `{"delta": integer}`
within -104..104. After replay lookup and revision validation, add delta to the
current subtitle size and validate the resulting `value` against the existing
set operation's 16..120 rule. No clipping or natural-language parsing occurs.

Normalize request identity using operation ID/version, resolved project ID,
original arguments, base revision, legacy observation token and generation intent.
JSON key order and explicit/default omitted fields do not distinguish requests;
resolved target aliases are equivalent. Different delta versus absolute requests
are distinct even if they would produce the same value. Preserve original input
identity separately from resolved absolute arguments. Unknown fields fail validation.

The primary key on `operation_requests.request_id` enforces uniqueness in SQLite.
Store the full normalized JSON (not only a hash), project ID, base/result revisions,
resolved arguments, generation flag, unique nullable job ID, result reference,
immutable result JSON and creation time. Historical receipts survive project
deletion; replay is an acknowledgement of prior work, not a new execution.

## Transaction and concurrency

Use a clean request/session boundary. `BEGIN IMMEDIATE` acquires the SQLite writer
lock before reading receipts or project state. Discard only a caller's clean
read transaction; reject pending new/dirty/deleted ORM objects. Callers must not
pass sessions that already flushed uncommitted writes. Expire cached ORM state
before reading. Keep all provider and media work outside this transaction.

1. Canonicalize the typed request and look up request ID.
2. Same identity: return stored result without readiness/revision checks or handler.
   Different identity: reject with `request_id_conflict` (409).
3. Validate operation, argument shape and required durable metadata.
4. Resolve current project, readiness and base revision. Reject stale revisions.
5. Resolve relative values; validate the final absolute value.
6. Recheck readiness and invoke the registered handler (no handler commit).
7. Save receipt and, only when explicitly requested, insert the pending full-pipeline
   job. Persist job/result references and the exact response in the same transaction.
8. Commit once. Exceptions before commit roll back all effects. Lost responses after
   commit are recovered by replay or receipt GET.

`Project.revision` starts at 1 and advances once per changed settings request or user
block PATCH. Progress updates, generation artifacts, reads and unchanged values do
not advance it. Existing PATCH writes use the same writer-lock boundary and shared
mutation service. Base revision is exposed in project and readiness responses.
SQLite lock contention returns a retryable failure, never an unguarded write.

## Durable generation handoff

The receipt and linked `GenerationJob` row form a transactional outbox: saving
settings cannot succeed without the generation intent and pending job also being
saved. The result contains a stable job ID, not a claim that media is complete.
A background dispatcher periodically scans pending receipt-linked jobs. Restarting
the single-server backend recovers jobs committed before in-memory submission.
Workers atomically transition pending -> running so duplicate dispatch cannot run
the same job twice. Cancellation before dispatch transitions the job to cancelled.
Receipt replay never creates another job or changes the stored response.

Legacy enqueue paths also recheck project-busy state under the writer lock.
All enqueue paths allocate job IDs above both live rows and historical receipt
references, so deleting a completed project cannot cause a receipt to point to a
different, later job. Active jobs block project deletion. Receipts are retained
indefinitely in this local MVP; retention/archival policy is future work.

A process lost after the running claim is ambiguous: startup marks its durable jobs
failed with an interruption message and does not automatically repeat provider work.
Do not run multiple application servers against this DB; the original single-server
runtime remains the supported topology. Multi-process request tests prove SQLite
receipt/settings serialization, not multi-server media execution support.
Pending recovery still uses the existing provider configuration. Process-local BYOK
secrets do not survive a restart; a recovered job can fail if its provider settings
are unavailable. No secret is copied into the receipt.

## API example: replay versus a new action

First GET `/api/projects/1` and read `revision`. Assuming size 48 and revision 1,
POST `/api/operations/execute`:

```json
{
  "request_id": "subtitle-change-001",
  "operation_id": "project.subtitle-font-size.adjust",
  "operation_version": 1,
  "target": {"project_id": 1},
  "base_revision": 1,
  "arguments": {"delta": 2},
  "generation_requested": false
}
```

The first result reports `resolved_arguments: {"value": 50}`, `revision: 2`,
and `result_ref: "/api/operations/requests/subtitle-change-001"`. Repeat the exact
request after a timeout/restart to get that exact stored result. Keep the original
base revision when resending; changing it with the same ID is a content conflict.

To intentionally increase the size again, read the latest revision and use a new
ID (`subtitle-change-002` with base revision 2 in this example). Size becomes 52
and revision 3. A fresh ID with an old base revision receives `stale_state` (409).
Use a new UUID or similarly unique ID per user intent in real clients.

`generation_requested: true` must be present on the original request if generation
is intended. The response acknowledges a queued job; inspect its live status via
`GET /api/projects/1/jobs` and match `job_id`. The receipt GET never replaces its
snapshot with later job status. Cancellation uses the existing project endpoint.

These guarantees are available through the structured operation API. The current
browser UI continues using its legacy endpoints and does not generate request IDs.
Natural-language parsing and UI integration remain later work.

## Migration and rollback

Stop the backend before upgrade. Back up the SQLite DB and its WAL/SHM sidecars (if
present), storage and local configuration using the existing operational procedure.
Do not log or commit these backups. `init_db()` adds `projects.revision INTEGER`
with server default 1 and creates `operation_requests` with its uniqueness
constraints. Existing project IDs, settings, jobs and files are preserved.
Migration is additive and repeatable; tests cover a database without the new column.

For rollback, stop the server and restore the pre-upgrade DB backup with the matching
code. This discards post-backup changes; preserve required artifacts separately.
Simply checking out old code leaves receipt history and pending D11 jobs unprocessed
and invalidates revision tracking, so do not downgrade a live database that way.

## Verification

Cover same-ID same/different content, target/default normalization, one-step relative
updates, fresh IDs, strict bounds, stale and missing revisions, durable status snapshots,
rollback on failure, primary-key uniqueness, threads and independent processes sharing
SQLite, replay in a fresh process, process death before/after commit, pending-job recovery,
duplicate dispatch, cancellation, interrupted running jobs, legacy PATCH revision
changes, and additive migration. Run existing backend/frontend regression suites.
