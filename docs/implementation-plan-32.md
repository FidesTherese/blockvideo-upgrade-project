# D32 Concurrency and Race Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that concurrent requests, confirmations, lifecycle controls, and startup dispatch produce at most one permitted durable effect and leave no orphan receipt, job, external call, or artifact.

**Architecture:** Exercise independent SQLAlchemy sessions and spawned Python processes against one temporary SQLite file. Use existing `BEGIN IMMEDIATE`, immutable receipts, revisions, dialogue currency, persisted job claims, and artifact transactions as the correctness boundaries; add production code only when a failing race test demonstrates a violated invariant.

**Tech Stack:** Python 3.12, SQLAlchemy 2, SQLite, FastAPI TestClient, pytest/pytest-asyncio, `ThreadPoolExecutor`, `threading.Barrier`, and spawned Python subprocesses.

## Global Constraints

- Follow `docs/plan-c/work-unit-32.md` and the D32 section of `docs/DTD.md`.
- Work on `main` as explicitly requested; pull before the unit and preserve unrelated changes.
- No new dependency, distributed lock, queue service, multi-server claim, or capacity claim.
- `BEGIN IMMEDIATE`, durable receipts/revisions, and persisted job state remain authoritative; process-local locks may optimize only.
- Network/provider/media work must never run inside a database writer transaction.
- Public request data and environment variables must not select race barriers or failpoints.
- Tests use isolated SQLite/media roots and fake/synthetic providers only.
- Every race assertion must reopen the database and inspect projects, settings history, jobs, receipts, external calls, and artifact rows/current pointers.
- In D32, "no orphan artifact" means no dangling `GenerationArtifact` row, broken foreign key, or invalid current-artifact pointer. An unreferenced file left after a failed publication commit remains permitted by the existing artifact-store contract and must be reported; D32 does not redesign filesystem garbage collection.
- A passing pre-existing invariant requires no production change; a failure must remain RED until the minimal fix passes.
- Commit final delivery as `[DONE] Mission 32 Verify concurrent operation and lifecycle invariants` only after full verification.

---

### Task 1: Canonical concurrency snapshot and repeated process matrix

**Files:**
- Create: `backend/tests/test_d32_concurrency_matrix.py`
- Modify only if a RED invariant requires it: `backend/app/services/transactions.py`, `backend/app/operations/receipts.py`, or `backend/app/operations/service.py`

**Interfaces:**
- Test helper `snapshot(project_id: int) -> dict[str, object]` reopens a session and returns canonical project revision/settings/status/current artifact plus sorted full settings-history, job, receipt, external-call, and artifact records. Binary response fields are represented by SHA-256, not raw bytes.
- Reuse `tests.test_operation_processes.run_process`, `adjustment`, and `make_project`.

- [ ] **Step 1: Write canonical snapshot tests**

Seed a project, one durable setting request with a generation job, and reopen the DB. Assert the snapshot contains project revision 2, exactly two settings-history rows (the revision-1 baseline and revision-2 result), one receipt, one pending job, zero external calls, and zero artifacts. Assert two fresh snapshots are equal and contain no ORM objects or response bytes.

- [ ] **Step 2: Run the snapshot tests**

```bash
cd backend
python -m uv run pytest tests/test_d32_concurrency_matrix.py -k snapshot -q
```

Expected: the test fails during collection until the helper/test file exists; after the helper is written, it passes without production changes.

- [ ] **Step 3: Add a repeated three-process request matrix**

For five iterations each, synchronize three processes for:

```python
("same-id-same-body", "same-id-different-body", "different-id-same-revision")
```

Expected durable outcomes: the same-ID/same-body case creates one effect and returns three byte-equivalent serialized results; the changed-body case returns one committed result plus two `request_id_conflict` failures; the different-ID case returns one committed result plus two `stale_state` failures. For every iteration, the reopened snapshot must have revision 2, one settings-history row for revision 2, one receipt, no orphan job unless the request explicitly asked for one, no calls/artifacts, and a subtitle value equal to the winning receipt.

- [ ] **Step 4: Run the process matrix**

```bash
cd backend
python -m uv run pytest tests/test_d32_concurrency_matrix.py -k process_matrix -q
```

If it passes, record that existing durable boundaries satisfy this matrix. If it fails, preserve the failure output and implement the smallest transaction/receipt fix before rerunning.

- [ ] **Step 5: Run related regressions and Ruff**

```bash
cd backend
python -m uv run pytest tests/test_operation_processes.py tests/test_operation_durability.py tests/test_d32_concurrency_matrix.py -q
python -m uv run ruff check tests/test_d32_concurrency_matrix.py app/services/transactions.py app/operations/receipts.py app/operations/service.py
```

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/tests/test_d32_concurrency_matrix.py backend/app/services/transactions.py backend/app/operations/receipts.py backend/app/operations/service.py
git commit -m "test: add D32 process and receipt race matrix"
```

Only add production paths that actually changed.

### Task 2: Dialogue successor races

**Files:**
- Modify: `backend/tests/test_d32_concurrency_matrix.py`
- Modify only after a RED failure: `backend/app/language_operations/dialogue.py`, `backend/app/language_operations/repository.py`, or `backend/app/language_operations/service.py`

**Interfaces:**
- Reuse the existing language harness and `LanguageOperationService` with independent sessions.
- Parent dialogue may have at most one durable successor across answer, correction, and dismiss requests.

- [ ] **Step 1: Add a synchronized answer/correction/dismiss race**

Create one pending subtitle-size question. Use three independent sessions and a barrier to submit:

```python
("answer", "56px"), ("correction", "58px"), ("dismiss", "取り下げる")
```

Use distinct request IDs. Accept only these terminal shapes:

- answer or correction wins: one `completed`, two `blocked` with `dialogue_superseded`, one settings revision and one operation receipt;
- dismiss wins: one `dismissed`, two `blocked`, no settings revision and no operation receipt.

Always assert one `LanguageTurn` successor, one immutable parent `superseded_by`, no job/call/artifact, and replay of each winner returns the identical saved result without a model call.

- [ ] **Step 2: Run the three-way race repeatedly**

```bash
cd backend
python -m uv run pytest tests/test_d32_concurrency_matrix.py -k dialogue_three_way -q
```

Do not add a repeat plugin. Implement repetition inside the test with five fresh projects. If the pre-existing implementation passes, make no production change.

- [ ] **Step 3: Add same-successor-ID changed-body race**

Submit the same continuation request ID concurrently with `56px` and `58px`. Assert one committed result, one `request_id_conflict`, one successor turn, one receipt, and the saved project value equals the committed result. Replaying the winning body returns the exact original; replaying the losing body remains conflict.

- [ ] **Step 4: Run dialogue-focused regression**

```bash
cd backend
python -m uv run pytest tests/test_d32_concurrency_matrix.py -k dialogue tests/test_language_dialogue.py tests/test_language_operations.py -q
```

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/tests/test_d32_concurrency_matrix.py backend/app/language_operations/dialogue.py backend/app/language_operations/repository.py backend/app/language_operations/service.py
git commit -m "test: cover D32 dialogue successor races"
```

Only add changed production files.

### Task 3: Confirmation, revision, cancellation, and publication races

**Files:**
- Modify: `backend/tests/test_d32_concurrency_matrix.py`
- Modify only after RED: `backend/app/operations/service.py`, `backend/app/services/job_control.py`, `backend/app/services/artifact_store.py`, `backend/app/workers/job_runner.py`

**Interfaces:**
- A generation confirmation remains bound to its saved project revision.
- A terminal committed publication wins over a late cancellation; cancellation before publication prevents a new current artifact.

- [ ] **Step 1: Add confirmation-versus-setting race**

Prepare a revision-bound language generation confirmation. Synchronize two independent sessions: one executes the confirmation token; the other performs a durable settings update from the same base revision. Accept exactly one winner:

- generation wins: one pending job/receipt and the setting loses with `project_busy` or `stale_state`;
- setting wins: revision advances once and confirmation loses with `stale_state`/`dialogue_stale`.

Assert no partial second receipt, no external call/artifact, and exact replay of the winning request.

- [ ] **Step 2: Run the confirmation race five times**

```bash
cd backend
python -m uv run pytest tests/test_d32_concurrency_matrix.py -k confirmation_vs_setting -q
```

- [ ] **Step 3: Add cancellation-versus-terminal-publication race**

Seed a running synthetic job and a verified temporary MP4/subtitle artifact using existing artifact-store test helpers. Place a barrier immediately before the publication transaction and race `JobRegistry.request_cancel(job_id)` against publication. Assert only two valid outcomes:

- publication commits first: job/project completed, cancel returns false, one current artifact;
- cancellation is observed first at the worker's publication safe boundary: `request_cancel()` sets `cancel_requested` while the job remains running, the worker raises `GenerationCancelled` before publication, and `JobRegistry` finalization moves the job/project to cancelled without creating or selecting a new artifact.

Run publication as the work callback of `JobRegistry.submit()` so the established worker finalizer—not the test—performs terminal cancellation. In both outcomes after the task settles, the prior successful artifact remains available, artifact/receipt foreign keys resolve, and a second cancel/publication attempt is idempotent or rejected without new rows.

- [ ] **Step 4: Run lifecycle regressions**

```bash
cd backend
python -m uv run pytest tests/test_d32_concurrency_matrix.py -k "confirmation_vs_setting or cancel_vs_publication" tests/test_operation_dispatcher.py tests/test_artifact_history.py tests/test_generation_controls.py -q
```

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/tests/test_d32_concurrency_matrix.py backend/app/operations/service.py backend/app/services/job_control.py backend/app/services/artifact_store.py backend/app/workers/job_runner.py
git commit -m "test: verify D32 confirmation and publication races"
```

Only add changed production files.

### Task 4: Retry/recovery, deletion, startup dispatch, and busy guidance

**Files:**
- Modify: `backend/tests/test_d32_concurrency_matrix.py`
- Modify only after RED: `backend/app/workers/operation_dispatcher.py`, `backend/app/workers/job_runner.py`, `backend/app/services/job_records.py`, `backend/app/api/routes_operations.py`, `backend/app/api/routes_projects.py`, `backend/app/api/utils.py`, `backend/app/main.py`

**Interfaces:**
- Persisted job claim determines retry/recovery winner.
- Active or unresolved external work blocks deletion.
- Multiple pending jobs are claimed once each across competing registries/startup scans.
- SQLite writer contention maps to fixed HTTP 503 with `Retry-After: 1`; retry uses the same request ID.

- [ ] **Step 1: Add retry-versus-recovery race**

Create a non-recoverable interrupted running job whose required frozen input snapshot is missing, so startup reconciliation must terminalize it as failed. Synchronize reconciliation with a retry request using independent sessions. Assert one new/effective execution intent at most: retry may lose before terminalization with `project_busy`, leaving the source failed and no child, or it may observe the committed failed source and create exactly one retry child; recovery must never requeue the source. Reopen and assert parent linkage, statuses, receipts, snapshots, and zero external calls/artifact rows.

- [ ] **Step 2: Add deletion races for active and unknown work**

Race project deletion against (a) a pending/running job claim and (b) an `unknown` job or unresolved remote external-call state. Deletion must return conflict while either durable blocker exists. If the existing deletion helper misses unknown/unresolved work, add a narrow `ensure_project_deletable(project_id, db)` in `app/api/utils.py` and use it only from `delete_project`; do not broaden `has_active_project_job()` or the normal settings-edit contract. After an explicit successful resolution path, deletion may win once and must remove that project's mutable rows/files without affecting a concurrently created project. Immutable operation receipts intentionally survive target deletion and must keep exact replay working.

- [ ] **Step 3: Add competing startup scans with multiple pending jobs**

Seed five projects with one pending durable job each. First add the narrow internal injection seam `dispatch_pending_operation_jobs(*, registry: JobRegistry | None = None) -> int`, resolving `None` to the existing module-global registry; no HTTP/environment selector is added. Invoke two dispatcher scans using separate injected `JobRegistry` instances and a barrier; each job's worker stub increments a thread-safe per-job counter. Assert every job runs exactly once, all five reach one terminal state, and repeated scans submit zero additional work.

- [ ] **Step 4: Add API writer-busy guidance test**

Hold `BEGIN IMMEDIATE` in one independent connection, submit a durable operation through TestClient in another thread, and assert HTTP 503, `Retry-After: 1`, fixed non-sensitive detail, no receipt/effect, and success when the exact same request ID/body is retried after releasing the lock.

- [ ] **Step 5: Run the focused D32 matrix repeatedly**

```bash
cd backend
python -m uv run pytest tests/test_d32_concurrency_matrix.py -q
python -m uv run pytest tests/test_d32_concurrency_matrix.py -q
python -m uv run pytest tests/test_d32_concurrency_matrix.py -q
```

All three complete runs must pass. Record duration as observation only, not a capacity claim.

- [ ] **Step 6: Run related regressions and Ruff**

```bash
cd backend
python -m uv run pytest tests/test_operation_processes.py tests/test_operation_dispatcher.py tests/test_operation_storage.py tests/test_job_recovery.py tests/test_generation_controls.py tests/test_project_delete.py tests/test_d32_concurrency_matrix.py -q
python -m uv run ruff check .
```

If `tests/test_project_delete.py` does not exist in the backend, use the existing backend deletion tests discovered by `rg "delete.*project|project.*delete" tests` and record the exact files selected.

- [ ] **Step 7: Commit Task 4**

```bash
git add backend/tests/test_d32_concurrency_matrix.py backend/app/workers/operation_dispatcher.py backend/app/workers/job_runner.py backend/app/services/job_records.py backend/app/api/routes_operations.py backend/app/api/routes_projects.py backend/app/api/utils.py backend/app/main.py
git commit -m "test: complete D32 lifecycle race matrix"
```

Only add changed production files.

### Task 5: D32 verification and documentation gate

**Files:**
- Create: `docs/plan-c/work-report-32.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `docs/modules/operation-core.md` only if a production contract changed.
- Modify: `specification.md` and `docs/DTD.md` only when verified implementation differs from the approved contract.

**Interfaces:**
- Report each race's permitted winner/loser outcomes and persisted invariant evidence; do not claim load, multi-server, real-provider, or D33 crash recovery coverage.

- [ ] **Step 1: Run D32 focused and related checks sequentially**

```bash
cd backend
python -m uv run pytest tests/test_d32_concurrency_matrix.py tests/test_operation_processes.py tests/test_operation_dispatcher.py tests/test_operation_durability.py tests/test_operation_storage.py tests/test_language_dialogue.py tests/test_generation_controls.py tests/test_artifact_history.py -q
```

Record exact passes, skips, failures, warnings, and the three repeated D32-matrix runs.

- [ ] **Step 2: Run full repository verification sequentially**

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

Do not run backend and frontend suites concurrently because the existing D22 deadline test is load-sensitive. Record the initial concurrent D31 verification failure only as historical D31 evidence, not a D32 product failure.

- [ ] **Step 3: Inspect changes and tracked outputs**

```bash
git status --short
git diff --check
git ls-files .superpowers release-evidence storage
```

No SDD scratch report, DB, media, `.env`, model asset, or generated evidence may be tracked.

- [ ] **Step 4: Write the D32 report and handoff**

Document the exact matrix, iteration count, original failures and production fixes, post-race canonical snapshots, verification commands/counts, and limitations. State explicitly that D33 has not started.

- [ ] **Step 5: Review against D32 acceptance**

Every scenario must show at most one effect, consistent reopened state, no orphan receipt/artifact/external call, deterministic replay/recovery, and bounded busy guidance. If any required scenario is untested or flaky across the three focused repetitions, mark D32 incomplete.

- [ ] **Step 6: Commit and push**

```bash
git add backend docs/plan-c/work-report-32.md docs/plan-c/handoff.md docs/modules/operation-core.md specification.md docs/DTD.md
git commit -m "[DONE] Mission 32 Verify concurrent operation and lifecycle invariants"
git push
```

Do not tag, publish, deploy, or start D33 before D32's final review gate.
