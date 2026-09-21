# D12–D15 implementation contract

Status: implemented and verified through D15. See `work-report-12-15.md` for evidence.
Baseline: D11 local changes from `codex/plan-c-d11`; continued on `codex/plan-c-d12-d15`.

## Confirmed product choices (2026-09-19)

- Settings remain locked for queued/running jobs. Successful final videos are all
  retained as history, including separate successful runs at the same revision.
- The user may choose any recorded historical settings revision to restore.
  Restoration checks the current base revision and saves a NEW revision. It does
  not roll back source text/block edits, delete videos, cancel or start jobs.
- Cancellation is cooperative at safe boundaries. A persisted cancellation that
  wins the publication transaction prevents output publication; settings remain saved.
- The UI's retry action creates a NEW job using CURRENT settings and inputs, with
  a link to the source failed/cancelled job. Its wording must explain this. A
  transport resend reuses its original request ID/body and cannot create another job.
- An uncertain billed external call is not blindly repeated, including after restart.
  Current provider adapters have no remote result-query endpoint. Such results
  remain unknown and block automatic/retry resubmission pending genuine resolution.
- Verification uses synthetic data, fake providers and mocked HTTP with no paid calls.

## Architecture and contracts

Retain SQLite, current packages, explicit registered operations and D11 receipt
lookup before current-state checks. Additive migration only; no live user database
migration during development. Models/services never import operation/API modules.

`GenerationJob` gains kind/block target, immutable initial input snapshot/revision/
fingerprint, stage plan, retry parent and recovery message. Add `unknown` status.
`GenerationArtifact` retains immutable final outputs and material manifests.
`SettingsRevision` stores non-secret configuration snapshots.
`ExternalCall` records actual outbound attempts and cached successful responses.
`Project.current_artifact_id` points only to validated current output.

D12: declare existing settings-to-stage dependencies and union affected stages into
one ordered plan. Reuse completed stages only when their inputs/files are valid.
Existing edited blocks must not be overwritten by unconditional splitting.
Subtitle-only changes require render; readings/speaker/speed require audio+render;
subtitle visibility requires image+render; slide-count affects image/audio/render.
Generation remains explicit, and a fresh request at unchanged settings still gets a job.

D13: capture inputs at enqueue, validate frozen expectations and actual media files,
write final candidates into immutable per-job history, then check cancellation,
revision and input identity under the writer lock before current publication.
Preserve valid old outputs as history without promoting them to current. Import
pre-upgrade output conservatively as unknown-revision history before replacement.
Show current/stale/missing output, settings saved/unreflected, active job, old output.

D14: commit external attempt intent before network calls; never hold the writer
lock during network/media work. Reuse durable successful responses. A remote call
interrupted in flight or with ambiguous response becomes unknown, not retryable
failure. VOICEVOX/local deterministic processing has a separate safe replay policy.
Recovery resumes safe persisted work when its inputs still match, and visibly marks
unknown or unrecoverable work. No fabricated provider lookup by repeating POST.

D15 operations (all mutations require request ID and current base revision):

- `project.settings.update`: flat validated project-setting changes, optionally generation_requested.
- `project.generation.start`: one explicit generation job; `{}` means full. Optional
  `kind` is `full`, `rerender`, `block_visual` or `block_audio`; block kinds require
  `block_index` (the display index, not the database block ID).
- `project.generation.cancel`: `{job_id}`; request durable cancellation, no settings mutation.
- `project.generation.retry`: `{job_id}`; new job from current inputs, lineage retained.
- `project.settings.restore`: `{revision}`; restore recorded configuration as a new change.

Legacy setting endpoints share configuration history and invalidation. Legacy
generation endpoints create the same snapshot/plan jobs and use the durable dispatcher.
`GET /api/projects/{id}/history` returns revision/output state, all artifact summaries,
settings versions and recent job summaries. History artifact download routes check
project ownership, storage containment and stored file integrity.

## Verification requirements

Planner stage call counts/dependency union; edited block preservation; repeated
generation and current-settings retry; old result arrival; missing/corrupt/swapped
media; publication/cancel races; historical videos surviving failures; migration;
process-death recovery and unknown no-resend; arbitrary historical restore with
stale revision rejection and receipt replay; UI current/old/unknown states and action
identity; full existing backend/frontend suites and fake-provider MP4 smoke.

G2 technical acceptance is recorded from executed evidence in the work report.
The original schedule's human sign-off checkboxes are not changed by automation.

## Storage and upgrade

New tables are `settings_revisions`, `generation_artifacts`, `external_calls`, and
`project_identities`. Project ID reservations survive deletion, preventing URL,
receipt and directory identity reuse while old directory cleanup is still running.
Explicit project deletion removes its settings/video history and media. Operation
receipts, external-call records and ID reservations remain as durable audit records.
Job allocation also reserves IDs referenced by receipts, external calls and artifacts.

The initial job snapshot stays immutable. Generated style/block plans can be recorded
in a separate checkpoint, but project/runtime/effective provider identity cannot be
silently adopted from a later configuration. Losing process-local BYOK overrides
fails validation instead of switching to a different default endpoint or model.

Before upgrading a real installation, stop its single backend process and back up
the database (including WAL/SHM when present), complete storage tree and configuration.
`init_db()` adds columns/tables without dropping existing data and is repeatable.
Pre-upgrade jobs without verifiable snapshots are failed on restart, never silently
replayed. A prior completed video is imported as unknown-revision history before its
first managed replacement. Historical settings predating recording cannot be reconstructed.

Rollback means restoring the matching code and complete pre-upgrade DB/storage backup
while stopped. An old binary against the upgraded live DB cannot maintain revision,
receipt or history contracts. Preserve wanted post-backup videos before restoring.
Development verification only migrated temporary synthetic databases.

## External calls and restart state transitions

| Persisted state at restart | Result | Subsequent action |
|---|---|---|
| Pending job with a snapshot | Claim once | Run the saved intent against verified inputs |
| Running, intact matching inputs and no uncertain remote call | Pending | Resume required stages; reuse cached successful responses |
| Running with remote in-flight/unknown call | Unknown | Show unresolved state; prohibit generation/retry |
| Running, cancellation persisted and no uncertain remote call | Cancelled | No downstream execution/publication |
| Running with changed/missing/corrupt input or provider identity | Failed | Explicit new job with current settings |
| Completed artifact and job | Completed | Keep history/current pointer; no replay |

OpenAI-compatible text/image POSTs and non-loopback VOICEVOX POSTs are treated as
potential remote effects. Timeout, transport interruption, HTTP 408 and HTTP 5xx
become unknown. Known responses are durably cached before processing; same-job calls
reuse them. A 4xx rejection is recorded; supported parameter-compatibility fallbacks
can submit a changed request after a known rejection. Loopback VOICEVOX is local
deterministic work and can safely retry after interruption. No adapter currently
provides remote result reconciliation; repeating POST is never treated as a query.

The UI keeps an uncertain operation's complete request in sessionStorage and offers
same-ID resend. It clears only the matching completed intent. A deliberate new
action gets a new UUID; retry creates a new job using the current snapshot, preserving
`parent_job_id`. Legacy generation endpoints share planning/worker safeguards but
do not themselves accept a durable request identity; use the operation API for replay.

## Operational limits

- One backend server per database; SQLite request serialization is not multi-server
  media-worker leadership. Existing process-local BYOK secrets remain ephemeral.
- Successful final MP4/ASS files are all retained; mutable intermediate images/audio
  are not a full asset version archive. Disk usage grows without automatic pruning.
- Video-history reads verify hashes. Very large histories may need pagination and
  an integrity cache later. Idle browser history polling is disabled.
- Browser sessionStorage protects transport resends in that tab session, not every
  browser/device after a user intentionally clears browser storage.
- The settings editor reloads server values when another client advances the revision;
  an unsaved local draft is not retained across that refresh.
- Quicker project creation derives its title locally; external paid work starts only
  after durable job creation. D16+ natural-language/model UI is outside this delivery.
