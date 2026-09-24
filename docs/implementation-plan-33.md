# D33 Crash and Recovery Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove stable restart behavior at every durable request, provider, checkpoint, cancellation, and publication boundary without duplicate remote attempts or loss of prior successful artifacts.

**Architecture:** Extend the existing D14 recovery seams with deterministic monkeypatch failures and subprocess termination after durable markers. Reopen the database after each failure, run `mark_interrupted_operation_jobs()` twice, and compare canonical project/job/receipt/call/checkpoint/artifact state; production changes are permitted only for a demonstrated failing invariant.

**Tech Stack:** Python 3.12, pytest/pytest-asyncio, SQLAlchemy 2, SQLite, `subprocess`, existing fake providers, and existing recovery/journal/artifact services.

## Global Constraints

- Follow `docs/plan-c/work-unit-33.md` and the D33 section/roadmap in `docs/DTD.md`.
- Start only after D32's report/review gate and pull the current branch before implementation.
- Public HTTP input and environment variables cannot select failpoints; use monkeypatches or a subprocess test program only.
- Never automatically retry `ExternalCall.remote_side_effect=True` after an in-flight or unknown outcome.
- Resume local work only when `input_snapshot`, `input_fingerprint`, revision, and checkpoint fingerprint agree.
- Use synthetic projects and fake providers; never fault-inject into user storage.
- Every scenario must reopen SQLite, restart twice, and inspect full durable state.
- Final delivery commit is `[DONE] Mission 33 Verify crash and recovery boundaries`.

---

### Task 1: Canonical restart snapshot and request/core crash boundaries

**Files:**
- Create: `backend/tests/test_d33_recovery_matrix.py`
- Modify only after a RED invariant: `backend/app/operations/receipts.py`, `backend/app/operations/service.py`, `backend/app/language_operations/repository.py`

**Interfaces:**
- Test helper `recovery_snapshot(project_id: int) -> dict[str, object]` opens a fresh session and returns canonical project revision/status/current artifact plus sorted settings revisions, jobs, receipts, external calls, and artifacts; response bytes are represented only by SHA-256.
- Test helper `restart_twice() -> tuple[int, int]` invokes `mark_interrupted_operation_jobs()` twice and returns both transition counts.
- Existing callable seams are `repository.claim`, `receipts.save_receipt`, and operation transaction commit; no runtime failpoint registry is added.

- [x] **Step 1: Write RED tests for deterministic snapshots**

Seed a synthetic project with one prior successful artifact, one language request, and one operation receipt. Assert two independently reopened `recovery_snapshot()` values are equal, contain no ORM objects/raw response bytes, and retain the prior artifact identity.

- [x] **Step 2: Run the snapshot test**

```bash
cd backend
python -m uv run pytest tests/test_d33_recovery_matrix.py -k canonical_snapshot -q
```

Expected: FAIL until the D33 test helper and assertions exist, then PASS without a production change.

- [x] **Step 3: Add request-claim and core-commit failure tests**

Monkeypatch `repository.claim` and `receipts.save_receipt` separately to raise `OSError("synthetic D33 boundary")` immediately before and after their durable writes. Cover a settings save and a generation confirmation. For each boundary assert either no committed effect or one complete effect with its immutable receipt; reject a revision without history/receipt, a receipt without its declared effect, and a job without its receipt. Replay the same request ID/body and assert exact saved replay or one clean first execution.

- [x] **Step 4: Run request/core recovery tests and regressions**

```bash
cd backend
python -m uv run pytest tests/test_d33_recovery_matrix.py -k "claim or receipt or core_commit" tests/test_operation_durability.py tests/test_language_operations.py -q
python -m uv run ruff check tests/test_d33_recovery_matrix.py app/operations/receipts.py app/operations/service.py app/language_operations/repository.py
```

- [x] **Step 5: Commit Task 1**

```bash
git add backend/tests/test_d33_recovery_matrix.py backend/app/operations/receipts.py backend/app/operations/service.py backend/app/language_operations/repository.py
git commit -m "test: add D33 durable request recovery matrix"
```

Only add production files that changed to satisfy a RED invariant.

### Task 2: Provider, checkpoint, cancellation, and publication process death

**Files:**
- Modify: `backend/tests/test_d33_recovery_matrix.py`
- Modify only after RED: `backend/app/services/external_calls.py`, `backend/app/services/generation_snapshots.py`, `backend/app/services/artifact_store.py`, `backend/app/workers/operation_dispatcher.py`, `backend/app/workers/job_runner.py`

**Interfaces:**
- Use existing seams `external_calls._finish`, `generation_snapshots.capture_inputs`, `artifact_store.publish_artifact`, `JobRegistry.request_cancel(job_id: int) -> bool`, and `mark_interrupted_operation_jobs() -> int`.
- Subprocess scenarios write only fixed markers `claimed`, `sent`, `response_saved`, `checkpoint_saved`, and `artifact_renamed`, then call `os._exit()` with fixed non-zero codes.
- Remote POST count is an append-only synthetic marker count and must remain at most one after recovery/replay.

- [ ] **Step 1: Add provider transmission/response crash tests**

Run isolated subprocesses that terminate (a) after journal claim before send, (b) after one synthetic remote send before `_finish`, and (c) after `_finish` persisted success. After startup reconciliation, assert (a) and (b) are `unknown` and cannot send again, while (c) reuses the cached response. The remote marker count remains zero for (a) and one for (b)/(c), including after a second restart.

- [ ] **Step 2: Add checkpoint and cancellation crash tests**

Terminate after initial snapshot persistence, after `resume_inputs`/`resume_fingerprint` persistence, and after durable `cancel_requested=True`. Valid frozen checkpoints become pending once; missing, altered, or changed-revision checkpoints become failed; persisted cancellation becomes cancelled without provider construction. A second restart performs zero transitions in every case.

- [ ] **Step 3: Add artifact publication crash tests**

Terminate before candidate rename, after rename before DB publication, and after DB publication. Assert no incomplete artifact row is served, an unreferenced renamed file never replaces the current artifact, an already committed artifact remains current/history, and rerunning `publish_artifact()` for the same completed job returns the same artifact without another row. Preserve the seeded prior successful artifact in all failure cases.

- [ ] **Step 4: Run the complete crash matrix three times**

```bash
cd backend
python -m uv run pytest tests/test_d33_recovery_matrix.py -q
python -m uv run pytest tests/test_d33_recovery_matrix.py -q
python -m uv run pytest tests/test_d33_recovery_matrix.py -q
python -m uv run pytest tests/test_external_call_recovery.py tests/test_job_recovery.py tests/test_artifact_history.py tests/test_generation_controls.py -q
python -m uv run ruff check .
```

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/tests/test_d33_recovery_matrix.py backend/app/services/external_calls.py backend/app/services/generation_snapshots.py backend/app/services/artifact_store.py backend/app/workers/operation_dispatcher.py backend/app/workers/job_runner.py
git commit -m "test: complete D33 process death recovery matrix"
```

Only add changed production files.

### Task 3: D33 evidence and gate

**Files:**
- Create: `docs/plan-c/work-report-33.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `docs/modules/operation-core.md` only if a production recovery contract changed
- Modify: `specification.md` and `docs/DTD.md` only if verified behavior differs from their current contract

**Interfaces:**
- Report each durable marker, pre/post-restart state, second-restart transition count, remote attempt count, and retained artifact identity.

- [ ] **Step 1: Run focused and full verification sequentially**

```bash
cd backend && python -m uv run pytest tests/test_d33_recovery_matrix.py tests/test_external_call_recovery.py tests/test_job_recovery.py tests/test_artifact_history.py tests/test_operation_durability.py tests/test_generation_controls.py -q
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

- [ ] **Step 2: Inspect outputs and write the report**

```bash
git status --short
git diff --check
git ls-files .env storage release-evidence
```

Record exact pass/skip/failure counts and state that D34 has not started. Mark D33 incomplete if any scenario duplicates a remote send, changes frozen input, publishes an incomplete artifact, loses prior history, or changes state on the second restart.

- [ ] **Step 3: Commit and push the implementation task**

```bash
git add backend docs/plan-c/work-report-33.md docs/plan-c/handoff.md docs/modules/operation-core.md specification.md docs/DTD.md
git commit -m "[DONE] Mission 33 Verify crash and recovery boundaries"
git push
```

Do not tag, publish, deploy, or start D34 before the D33 gate is reviewed.
