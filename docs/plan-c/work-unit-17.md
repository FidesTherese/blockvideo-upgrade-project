# D17 — All Tools natural language to the operation core

## Boundary

The user requested D17 with discussion of product choices. D16 remains a read-only
interpreter. A separate `app.language_operations` orchestrator calls that interpreter
with every approved operation definition (no retrieval), then calls the existing
`OperationService` with an immutable, application-created structured request.
Models and shared services never import this orchestrator; interpretation never
imports execution/DB. The new API depends on orchestration, not the reverse.

Requests carry a client ID, text, explicit/selected project context, and optionally
the observed base revision. Project identity and the base revision come from the
application, never from model output. Missing/conflicting/nonexistent targets do
not execute. Explicit numeric project references in text must match the selected
target. Name-based project lookup and multi-turn target correction remain D19 work.

The orchestrator always sets `generation_requested: false` for settings operations.
Generation.start/retry proposals require a separate, explicit confirmation tied to
the stored proposal. One utterance cannot chain settings changes and generation.
No argument, operation ID, target, revision, or core request ID is accepted by the
confirmation endpoint; these are read from the durable record. The current core
revalidates arguments, readiness and revision under its existing writer lock.

## Durability and replay

Add an independent `language_requests` table. A unique client request ID binds to a
canonical input fingerprint, application-generated core request ID, target/revision,
strict interpretation outcome and frozen structured request. Do not store raw
utterance/provider text in logs or this ledger; retain a hash for input identity.
The operation receipt remains the authoritative execution result.

Claim interpretation in a short SQLite writer transaction. Do not hold it during
inference. Concurrent same-ID/same-content requests return the pending/stored state;
different content conflicts. A bounded interpretation lease makes interrupted work
visible without blindly rerunning inference. Expired/failed interpretation requires
a new ID. Late responses cannot overwrite an expired or already resolved claim.

Lookup existing language records before current state and before model access.
Core receipt lookup also precedes execution confirmation/current state on replay.
If a process dies after core commit but before the language response is saved,
recover from that receipt; never interpret or create a second job. Preserve both
request identifiers in the public structured record.

## Entry points and decisions

Provide a development API for prepare, submit, lookup, and confirm/execute.
Prepare never mutates project state. Submit can execute unambiguous settings/status
through the core; generation remains awaiting explicit confirmation. A review-all
mode is available for callers who want to inspect every proposal before execution.
The confirmation token binds the immutable operation body to its language request.
Product confirmation policy and unspecified subtitle increments are discussed with
the user before finalizing defaults. The user confirmed immediate settings saves,
separate generation confirmation, and asking about unspecified amounts (retaining
the existing explicitly defined "slightly" = 2 px rule). The user pointed out that
phrasing differs by person; representative synthetic variations are prepared by
the developer instead of requiring one fixed phrase from the user. The normal
input UI/result cards remain D18.

Local model configuration is separate from the video generation provider. No model
connection is enabled by default. Reuse D16's local HTTP adapter and tested thinking
setting, with synthetic data and zero external API cost for verification. No raw
script, media, titles, credentials, provider URLs or full history is sent. State is
the D16 allowlist plus no arbitrary expansion; explicit job/history IDs may be
supplied by the user's text, and the core validates ownership/existence.
Additionally, the application requires exactly one explicit matching job/history
reference in that text. A model-guessed ID or the current revision cannot stand in
for the user's chosen history entry. Missing/conflicting references return an
application clarification while retaining the original structured interpretation
for inspection. Supported reference forms include `ジョブ7`, `job_id: 7`,
`revision 2`, `リビジョン2`, and `第2版`; other forms may need clarification.

The four API routes are `POST /api/language/requests/prepare`,
`POST /api/language/requests`, `GET /api/language/requests/{request_id}`, and
`POST /api/language/requests/{request_id}/execute`. The last accepts only the stored
`confirmation_token` and optional `confirm_generation`. Structured `completed`
means the core operation finished; a generation start has queued a job, not finished
rendering a video. Job/artifact state remains authoritative for generation progress.
Malformed HTTP values return a fixed 422 error without echoing the user's input.

Language request IDs are terminal after an error, missing input or blocked state;
a corrected/new request needs a new ID. Same ID/body returns the stored outcome.
An abandoned interpretation becomes `interpretation_interrupted` after 210 seconds;
it is never automatically interpreted again. This lease exceeds the local adapter's
maximum 180-second deadline. Default local inference has no API key, remote access,
retries or provider fallback. SQLite initialization adds only a new table; existing
projects and settings do not need to be rewritten for this feature.

## Verification

Compare NL and typed requests for saved settings/revision, read-only status, jobs,
cancel/retry/restore, and artifacts where relevant. Exercise all eight definitions,
missing/invalid targets and args, extra fields/IDs, model failure, state changes
during inference and before confirmation, same-ID concurrency/restart/replay,
confirmation tampering, and generation hallucinated from a settings-only request.
Run actual local inference with all definitions and the user's representative
phrases, then use only an isolated synthetic project with fake video providers.
Inspect structured proposals, core results, persisted state and generated video;
do not use model prose as evidence of execution.
