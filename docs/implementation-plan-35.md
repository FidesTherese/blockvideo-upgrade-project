# D35 Recovery-Oriented Operational UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present backend-authoritative recovery and startup states with accurate, accessible user actions and no browser-side retry authority.

**Architecture:** Backend job summaries derive exact recovery/action enums from persisted jobs and unresolved calls. Small `RecoveryStatus` and `StartupStatus` components render those contracts; existing operation hooks remain the only action path and durable receipts remain authoritative.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, React 18, TypeScript 5.6, TanStack Query, Vitest, Testing Library.

## Global Constraints

- Follow `docs/plan-c/work-unit-35.md` and the D35 section/roadmap in `docs/DTD.md`.
- The browser never decides retryability, migration safety, remote outcome, or receipt state.
- `JobSummary.recovery_code` and `recommended_action` are required exact enums, not prose inference.
- Unknown external outcomes never expose retry controls.
- Native buttons, DOM-order focus, `role="status"`/`role="alert"`, keyboard operation, and 390 px layout are mandatory.
- Duplicate action clicks remain safe through existing request IDs/locks.
- The original D35 delivery commit is `561677c` (`[DONE] Mission 35 Add recovery-oriented operational UI`).
- Final-review corrections remain D35 candidate behavior; D36 is not started.

---

### Task 1: Backend recovery and startup contracts

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/services/job_views.py`
- Modify: `backend/tests/test_d35_startup_recovery_api.py`
- Modify: existing job-view tests discovered by `rg "job_summary|retryable" backend/tests`

**Interfaces:**

```python
RecoveryCode = Literal[
    "wait", "safe_retry", "external_outcome_unknown", "refresh_required",
    "cancelled", "completed", "failed",
]
RecommendedAction = Literal[
    "wait", "retry_current", "check_provider", "refresh", "none",
]
```

`JobSummary` adds required `recovery_code: RecoveryCode` and `recommended_action: RecommendedAction`. `job_summary(job: GenerationJob) -> JobSummary` derives them from persisted status, cancellation, object-session availability, and unresolved calls.

- [ ] **Step 1: Write RED table-driven job mapping tests**

Cover pending/running, cancel requested, failed retryable, failed blocked by unknown call, unknown, cancelled, completed, and detached-session failed jobs. Assert exact `(recovery_code, recommended_action, retryable)` tuples and fixed non-sensitive messages.

- [ ] **Step 2: Run backend RED tests**

```bash
cd backend
python -m uv run pytest tests/test_d35_startup_recovery_api.py -k recovery_code -q
```

Expected: FAIL because required fields do not exist.

- [ ] **Step 3: Implement exact mappings**

Use these rules: active/cancel-requested -> `wait/wait`; failed with safe retry -> `safe_retry/retry_current`; failed with unresolved remote work or unknown -> `external_outcome_unknown/check_provider`; detached state requiring a fresh read -> `refresh_required/refresh`; cancelled -> `cancelled/none` unless existing retry permission makes it `safe_retry/retry_current`; completed -> `completed/none`; terminal non-retryable local failure -> `failed/none`.

- [ ] **Step 4: Run backend API/regression tests**

```bash
cd backend
python -m uv run pytest tests/test_d35_startup_recovery_api.py tests/test_job_recovery.py tests/test_external_call_recovery.py tests/test_operation_api.py -q
python -m uv run ruff check app/schemas/__init__.py app/services/job_views.py tests/test_d35_startup_recovery_api.py
```

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/app/schemas/__init__.py backend/app/services/job_views.py backend/tests
git commit -m "feat: expose authoritative recovery actions"
```

### Task 2: Typed recovery and startup components

**Files:**
- Create: `frontend/src/components/RecoveryStatus.tsx`
- Create: `frontend/src/components/StartupStatus.tsx`
- Create: `frontend/src/test/recovery-status.test.tsx`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/GenerationHistory.tsx`

**Interfaces:**

```typescript
export type RecoveryCode = 'wait' | 'safe_retry' | 'external_outcome_unknown' |
  'refresh_required' | 'cancelled' | 'completed' | 'failed';
export type RecommendedAction = 'wait' | 'retry_current' | 'check_provider' | 'refresh' | 'none';
export interface StartupState {
  status: 'starting' | 'ready' | 'migration_failed';
  reason_code: string | null;
  message: string;
  schema_version: number | null;
  backup_available: boolean;
}
```

- `api.startup(signal?: AbortSignal): Promise<StartupState>` calls `GET /api/startup`.
- `RecoveryStatus({ job }: { job: JobSummary })` renders one status region and action guidance only.
- `StartupStatus()` polls only startup status every two seconds while `starting`, aborts and clears timers on cleanup, and stops on terminal/network outcomes. It renders restore guidance only when `backup_available` is true, otherwise stop/restart/support guidance, and provides a native status-refetch button after network failure. It executes no operation, migration, or restore.

- [ ] **Step 1: Write RED component tests**

For every recovery/action enum pair, assert exact Japanese label/guidance, one status region, and no retry button inside `RecoveryStatus`. Test both migration backup branches, fixed-interval starting-to-ready polling, terminal stop, network refetch, operation non-invocation, abort/timer cleanup, stale completion after unmount, and ensure no private path is rendered.

- [ ] **Step 2: Run frontend RED tests**

```bash
cd frontend
npx -y pnpm@10.18.3 test -- recovery-status.test.tsx
```

Expected: FAIL because components/types do not exist.

- [ ] **Step 3: Implement types, API, and components**

Make new `JobSummary` fields required. Replace status-specific prose in `GenerationHistory` with `RecoveryStatus`; show retry only when `recommended_action === 'retry_current' && retryable`, and keep unknown/check-provider states button-free.

- [ ] **Step 4: Run component tests, type build, and lint**

```bash
cd frontend
npx -y pnpm@10.18.3 test -- recovery-status.test.tsx project-history.test.tsx durable-operation.test.tsx
npx -y pnpm@10.18.3 build
npx -y pnpm@10.18.3 lint
```

- [ ] **Step 5: Commit Task 2**

```bash
git add frontend/src/components/RecoveryStatus.tsx frontend/src/components/StartupStatus.tsx frontend/src/test/recovery-status.test.tsx frontend/src/lib/types.ts frontend/src/api/client.ts frontend/src/components/GenerationHistory.tsx
git commit -m "feat: render typed recovery and startup status"
```

### Task 3: Page integration, stale transitions, and accessibility

**Files:**
- Modify: `frontend/src/pages/ProjectDetailPage.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/test/recovery-status.test.tsx`
- Modify: `frontend/src/test/project-history.test.tsx`
- Modify: `frontend/src/test/durable-operation.test.tsx`

**Interfaces:**
- `StartupStatus` is mounted once in `Layout` above routed content.
- Project controls disable during project/history fetches and refetches. Retry/cancel callbacks refetch both resources immediately before execution and require the same current job's typed action/status/retryability plus coherent revisions.
- `GenerationHistory` invokes existing `onRetry(job.id)` and `onCancel(job.id)` callbacks only from enabled native buttons.

- [ ] **Step 1: Add RED interaction tests**

Test stale history -> refresh -> safe retry, same-revision transition rejection, query/refetch and revalidation locks, unknown external outcome with no retry, cancellation wait, completed state, duplicate retry activation, `userEvent.tab()` DOM order plus `userEvent.keyboard('{Enter}')` activation, one live status announcement, and structural narrow-layout containment. jsdom does not prove overflow; Task 4 must provide real-browser 390 px evidence.

- [ ] **Step 2: Implement page integration**

Mount `StartupStatus`, preserve current polling/refetch behavior, disable controls during project/history fetches or revision mismatch, and key action visibility only from typed fields. Immediately refetch and revalidate the same job before retry/cancel without weakening the duplicate lock. Do not add automatic resend/retry intervals.

- [ ] **Step 3: Run focused frontend and backend contract tests**

```bash
cd frontend
npx -y pnpm@10.18.3 test -- recovery-status.test.tsx project-history.test.tsx durable-operation.test.tsx history-polling.test.tsx
npx -y pnpm@10.18.3 build
npx -y pnpm@10.18.3 lint
cd backend
python -m uv run pytest tests/test_d35_startup_recovery_api.py tests/test_operation_api.py -q
```

- [ ] **Step 4: Commit Task 3**

```bash
git add frontend/src/pages/ProjectDetailPage.tsx frontend/src/components/Layout.tsx frontend/src/test/recovery-status.test.tsx frontend/src/test/project-history.test.tsx frontend/src/test/durable-operation.test.tsx
git commit -m "test: verify D35 recovery interactions"
```

### Task 4: Browser evidence, documentation, and D35 gate

**Files:**
- Create: `docs/plan-c/work-report-35.md`
- Modify: `docs/plan-c/handoff.md`
- Modify: `docs/modules/operation-core.md`
- Modify: `specification.md` and `docs/DTD.md` if implementation evidence differs

**Interfaces:**
- Browser evidence uses synthetic states/API responses and records viewport, keyboard path, actions available, and observed backend reason codes; it is not human acceptance.

- [ ] **Step 1: Run full verification sequentially**

```bash
cd backend && python -m uv run pytest
cd backend && python -m uv run ruff check .
cd frontend && npx -y pnpm@10.18.3 test
cd frontend && npx -y pnpm@10.18.3 build
cd frontend && npx -y pnpm@10.18.3 lint
```

- [ ] **Step 2: Run bounded browser checks**

Start the synthetic local app, exercise wait/safe-retry/unknown/migration-failed/stale-refresh states, keyboard navigation, duplicate click locking, and 390 px layout. Store screenshots/logs only under ignored `release-evidence/d35-browser/`; record hashes/counts in the report and do not claim hands-on user acceptance.

- [ ] **Step 3: Inspect and write evidence**

```bash
git status --short
git diff --check
git ls-files .env storage release-evidence
```

State D36 has not started and list any skipped browser/environment check exactly.

- [ ] **Step 4: Commit and push the implementation task**

```bash
git add backend frontend docs/plan-c/work-report-35.md docs/plan-c/handoff.md docs/modules/operation-core.md specification.md docs/DTD.md
git commit -m "[DONE] Mission 35 Add recovery-oriented operational UI"
git push
```

Do not freeze, tag, publish, or deploy in D35.

### Task 5: Final-review project recovery and backup guidance correction

**Files:**
- Modify: `backend/app/schemas/__init__.py`
- Modify: `backend/app/services/job_views.py`
- Modify: `backend/app/services/job_records.py`
- Modify: `backend/app/api/routes_projects.py`
- Modify: `backend/app/migrations/contracts.py`
- Modify: `backend/app/migrations/runner.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_d35_startup_recovery_api.py`
- Modify: `backend/tests/test_d34_migrations.py`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/pages/ProjectDetailPage.tsx`
- Modify: `frontend/src/test/project-fixtures.ts`
- Modify: `frontend/src/test/project-history.test.tsx`
- Modify: D35 specification, DTD, module note, report, and handoff

**Interfaces:**
- `ProjectDetail.generation_recovery` is a required bounded object containing
  `code: "busy" | "external_outcome_unknown" | "ready"` and
  `recommended_action: "wait" | "check_provider" | "generate"`.
- `build_recovery_contexts()` performs one aggregate query over all project jobs and
  joined external calls, independent of list/history limits.
- `MigrationError(reason_code, *, backup_available=False)` exposes only a boolean
  backup signal in addition to its bounded reason code.

- [ ] **Step 1: Write and run RED backend tests**

Add API coverage where the blocking job or unresolved remote-side-effect call falls
outside the newest 100 history rows. Assert project detail still returns the exact
project recovery contract and generation execution rejects. Add migration tests for
failure after verified backup publication (`backup_available is True`) and failure
before publication (`False`), plus lifespan propagation. Run:

```bash
cd backend
python -m uv run pytest tests/test_d35_startup_recovery_api.py tests/test_d34_migrations.py -q
```

Expected: failures for the missing project contract and missing exception boolean.

- [ ] **Step 2: Implement minimal backend contracts and rerun focused tests**

Keep the recovery aggregate independent of returned history rows. Require the same
active/unknown/unresolved facts before pending-job creation. Set the migration error
boolean only after the verified backup publisher returns successfully, and copy it to
startup status without exposing a path.

- [ ] **Step 3: Write and run RED frontend tests**

Assert an old busy blocker and an old unresolved remote call disable project, rerender,
and block controls and show the matching fixed guidance despite no blocking job in the
history payload. Assert retry/cancel revalidation refuses when the refreshed project
contract disagrees with the job-level contract.

```bash
cd frontend
npx -y pnpm@10.18.3 test -- project-history.test.tsx recovery-status.test.tsx
```

- [ ] **Step 4: Implement frontend project-contract gating and rerun focused tests**

Use `ProjectDetail.generation_recovery` together with job rows for initial controls and
immediate revalidation. Do not infer recovery from project prose or private details.

- [ ] **Step 5: Reconcile D35 records and run the full gate**

Record the original completed delivery commit `561677c`, the final correction commit
subject, and that D36 is not started. Run backend pytest/Ruff and frontend test/build/
lint, inspect diff/privacy, commit exactly
`fix: align D35 project recovery and backup guidance`, and push `main`.
