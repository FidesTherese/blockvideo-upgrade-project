# Plan C D32 Work Report — Concurrency and lifecycle invariants

## Result

D32 is complete at the automated verification gate. D33 has not started.

The race matrix uses independent SQLAlchemy sessions and spawned Python processes against isolated SQLite files. The authoritative boundaries remain SQLite `BEGIN IMMEDIATE`, immutable request receipts, project revisions, dialogue successor links, persisted job claims, cancellation/publication transactions, and the external-call journal. No dependency, distributed lock, queue service, public failpoint, request selector, environment selector, schema, provider, or media implementation was added.

D32 found and corrected three production contract gaps:

1. a durable dialogue successor now takes precedence over later project-revision resolution, so losing continuations return `dialogue_superseded`;
2. project deletion alone also blocks unknown jobs and unresolved remote calls, transactionally deletes resolved external-call rows, and drops process-local secrets only after the database commit;
3. startup dispatch accepts an internal injected `JobRegistry`, while each worker's database pending-to-running claim remains authoritative.

## Exact race matrix

| Scenario | Iterations / contenders | Permitted result | Reopened durable evidence |
|---|---:|---|---|
| Canonical snapshot | 1 project, two fresh reads | Equal JSON-safe snapshots | revision 2; settings history revisions 1 and 2; one receipt; one pending job; no call/artifact; bytes represented only by SHA-256 |
| Same ID, same body | 5 projects × 3 processes | Three byte-equivalent responses for one effect | one revision-2 settings row, one receipt, no job/call/artifact, saved value and receipt result agree |
| Same ID, changed body | 5 × 3 processes | One committed result, two `request_id_conflict` | exactly the winner's revision/history/receipt and no partial loser effect |
| Different IDs, same revision | 5 × 3 processes | One committed result, two `stale_state` | exactly one receipt and one revision advance |
| Answer/correction/dismiss | 5 projects × 3 sessions | Answer/correction: one `completed` plus two `dialogue_superseded`; dismiss: one `dismissed` plus two `dialogue_superseded` | one successor and immutable parent link; answer/correction has one revision and receipt; dismiss has neither; no job/call/artifact; winner and stored losers replay without model calls |
| Same successor ID, changed body | 5 projects × 2 sessions | One completed winner, one `request_id_conflict` | one successor, one receipt, winning saved value; winner replay and persistent loser conflict |
| Confirmation vs setting | 5 projects × 2 sessions | Generation wins and setting loses `project_busy`/`stale_state`, or setting wins and confirmation loses `stale_state`/`dialogue_stale` | one receipt/effect only; generation yields one pending job, setting yields one revision; no call/artifact; winner replay is exact |
| Cancellation vs publication | 2 deterministic schedules | Cancellation observed first: cancelled and no new artifact; publication commits first: completed and late cancel false | prior artifact remains valid; receipt/job/artifact references resolve; current pointer selects prior or newly committed artifact; repeat is idempotent/rejected |
| Non-recoverable retry vs recovery | 1 synchronized race | Retry loses `project_busy` with no child, or sees failed source and creates one pending child | source failed, at most one child/receipt, correct parent and snapshot, no call/artifact; second recovery is no-op |
| Remote in-flight retry vs recovery | 1 synchronized race | Retry loses `project_busy` or `external_outcome_unknown` | one unknown source job and one unknown call; no child/retry receipt/artifact; second recovery is no-op |
| Delete vs pending/running claim | 1 synchronized race | Delete returns 409 while work is active; succeeds after terminalization | target mutable rows/files removed after success; immutable receipt still replays exactly |
| Delete vs unknown job / unresolved remote call | 2 blocker variants | Delete returns 409 until explicit resolution, then one delete may win | target project/job/settings/artifact/call rows and files removed; concurrent new project survives; immutable receipt survives and replays |
| Delete commit failure | 1 injected session failure after flush | Fixed 500 and complete rollback | canonical DB snapshot, exact secret object, and file bytes survive; no filesystem removal; ordinary retry commits then drops secret/removes files |
| Competing startup scans | 5 pending jobs × 2 injected registries | Both scans may submit stale candidates; DB claim permits each callback once | five jobs each complete once, one receipt each, no call/artifact; later scans submit zero |
| API writer busy | 1 held writer plus one contender | HTTP 503, `Retry-After: 1`, fixed `database_busy`; same ID/body retry succeeds | busy attempt creates no receipt/effect; retry advances once to revision 2 with one receipt |

Every race assertion reopens the database. Canonical snapshots include project revision/settings/status/current-artifact pointer plus sorted settings history, jobs, receipts, language requests/turns, external calls, and artifacts. Artifact checks require no dangling row, broken job/project relationship, or invalid current pointer. D32 does not change the existing allowance for an unreferenced file after a failed publication commit.

## RED/GREEN iterations and production fixes

### Task 1 — process matrix

- Initial snapshot RED was the expected missing helper. The first matrix iterations then exposed test-helper scope/rendezvous and baseline-history expectation defects.
- GREEN passed with a parent-controlled spawned-process rendezvous and exact pre/post canonical assertions.
- Production changes: none; existing transaction, revision, and receipt boundaries passed.

### Task 2 — dialogue races

- A test expectation first incorrectly omitted the revision-1 baseline after a dismiss.
- Production RED: after correction, answer/correction losers returned `stale_state` because revision resolution occurred before checking the already committed parent successor.
- GREEN: `dialogue.require_not_superseded()` is called inside the existing claim writer transaction before `resolve_context()`; `attach()` reuses it. Losers now persist and replay `dialogue_superseded`.
- Follow-up added canonical language-request/turn evidence and durable loser replay checks; it found no additional production defect.

### Task 3 — confirmation and publication

- RED observations were test-contract defects: a detached expired ORM return from idempotent artifact publication and an incorrect expectation that a losing confirmation was a saved success.
- GREEN asserts durable snapshots and the actual `request_not_ready` repeat behavior.
- Production changes: none; both cancellation-first and publication-first schedules passed existing production boundaries.

### Task 4 — lifecycle and startup

- Initial RED had five failures: deletion allowed unknown/unresolved work; dispatcher lacked the planned injection seam; and two test harnesses had a reused barrier/event-loop blocking defect. Harness defects were corrected before production edits.
- GREEN added deletion-only `ensure_project_deletable()` and keyword-only registry injection. Existing API busy handling already met the contract.
- Review RED found resolved `ExternalCall` rows orphaned after deletion. GREEN deletes target-job call rows in the same writer transaction before project/job deletion.
- Review confirmed `registry or job_registry` was too broad for injected falsey registries; GREEN uses the explicit `registry is not None` selection.
- Final production RED flushed deletion changes and forced commit failure: the database rolled back but the secret had already been dropped. GREEN moves `secret_store.drop(project_id)` after successful commit and before best-effort filesystem cleanup.
- Final test-only coverage required empty target settings-history and artifact collections after successful deletion; no further production change was needed.

## Verification

All commands below ran sequentially. Backend and frontend checks were not overlapped.

### Focused Task 5 gate

```bash
cd backend
python -m uv run pytest tests/test_d32_concurrency_matrix.py tests/test_operation_processes.py tests/test_operation_dispatcher.py tests/test_operation_durability.py tests/test_operation_storage.py tests/test_language_dialogue.py tests/test_generation_controls.py tests/test_artifact_history.py -q
```

Result: **133 passed, 0 skipped, 0 failed, 1 warning in 49.16s**. The warning is the existing Starlette `TestClient`/`httpx` deprecation warning.

A preliminary attempt to wrap this command with `/usr/bin/time -p` exited 127 because that executable does not exist in the Windows shell environment; pytest did not start. The exact planned command above was then run successfully. This was a measurement-wrapper error, not a product failure.

### Three fresh complete D32 repetitions

The command `cd backend && python -m uv run pytest tests/test_d32_concurrency_matrix.py -q` ran three times on the final pre-documentation code:

1. **17 passed, 0 skipped, 0 failed, 1 warning in 19.99s**;
2. **17 passed, 0 skipped, 0 failed, 1 warning in 20.18s**;
3. **17 passed, 0 skipped, 0 failed, 1 warning in 20.25s**.

Each warning was the same existing Starlette/httpx deprecation. Durations are observations only and are not throughput or capacity evidence.

### Full repository gate

| Command | Result |
|---|---|
| `cd backend && python -m uv run pytest` | **1132 passed, 7 skipped, 0 failed, 1 warning in 136.87s (2:16)** |
| `cd backend && python -m uv run ruff check .` | exit 0, `All checks passed!`; Ruff printed no duration |
| `cd frontend && npx -y pnpm@10.18.3 test` | **16 files / 123 tests passed, 0 skipped, 0 failed in 9.99s**; no warnings |
| `cd frontend && npx -y pnpm@10.18.3 build` | exit 0; TypeScript and Vite transformed **188 modules**, Vite build **1.88s**; no warnings |
| `cd frontend && npx -y pnpm@10.18.3 lint` | exit 0; ESLint printed no errors, warnings, counts, or duration |

The seven backend skips are the existing ONNX embedding runtime/asset-dependent cases in `tests/test_onnx_embeddings.py`. The backend warning is the same existing Starlette/httpx deprecation. The initial D31-era concurrent verification failure that motivated sequential execution was a historical load-sensitive D22 deadline observation, not a D32 product failure; D32's gate was run sequentially as required.

## Acceptance and limitations

- Every covered scenario has at most one permitted durable effect.
- Winner replay, loser conflict/blocking, recovery no-op behavior, and post-race canonical state are deterministic across the required repetitions.
- No dangling database artifact, invalid current pointer, orphan resolved external-call row, or partial mutable deletion state remained in the tested paths. Immutable operation receipts intentionally survive deletion.
- Tests use isolated SQLite/media roots and fake or synthetic providers only. No real provider, paid API, real user data, or generated evidence is tracked.
- This is a **single-server SQLite correctness matrix**, not a multi-server, distributed-lock, load, throughput, latency, or capacity claim.
- Process-local credentials are cleaned only after committed deletion; filesystem cleanup remains best effort after commit. Failed cleanup may leave unreferenced files under the existing artifact/storage contract.
- D32 does not provide D33 process-kill/crash-boundary recovery coverage. **D33 has not started.**
- No release, tag, publication, deployment, or human/independent acceptance was performed.
